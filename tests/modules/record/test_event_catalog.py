"""The authoritative event catalog is the only source of an event-kind set.

This repository's recurring defect is a second, hand-typed copy of a kind set that
silently drifts from the authored contract. The catalog in
``ctower_kernel.record.events`` is the one authority; ``_parity_errors`` is the single
chokepoint that decides whether an authored contract still agrees with it, and every
guard below judges the committed contracts through that chokepoint. Adding a kind to the
catalog without its authored branch — or authoring a branch with no catalog kind — is
refused by name rather than discovered at runtime.

The guard lives beside the catalog it judges rather than under ``tests/contracts``:
reading the one authority means importing ``kernel-record``, and only a kernel module
test owns that dependency. Deriving the catalog from the contracts instead would prove
the contracts agree with themselves.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from ctower_kernel.record.events import EventKind, event_catalog
from ctower_kernel.record.request_proposal_events import RequestProposalChangedPayload

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
ENVELOPE = ROOT / "contracts/domain/events/event-envelope.schema.json"
OPENAPI = ROOT / "contracts/http/openapi.yaml"
PHANTOM = "session.heartbeat"
MINIMUM_PARITY_GUARDS = 2


def _parity_errors(catalog: Iterable[str], contract: Iterable[str], label: str) -> list[str]:
    """CHOKEPOINT: every disagreement between the catalog and one authored contract."""

    declared, authored = set(catalog), set(contract)
    return [f"{label} omits catalog kind {kind}" for kind in sorted(declared - authored)] + [
        f"{label} declares unknown kind {kind}" for kind in sorted(authored - declared)
    ]


def _envelope() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(ENVELOPE.read_text(encoding="utf-8")))


def _openapi() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(OPENAPI.read_text(encoding="utf-8")))


def _catalog_kinds() -> frozenset[str]:
    return frozenset(entry.kind.value for entry in event_catalog())


def _catalog_session_kinds() -> frozenset[str]:
    """Derive the session kind set from the catalog's own membership column."""

    return frozenset(entry.kind.value for entry in event_catalog() if entry.session_fact)


def _catalog_project_feed_kinds() -> frozenset[str]:
    """Derive the project-feed kind set from the catalog's own membership column."""

    return frozenset(entry.kind.value for entry in event_catalog() if entry.project_feed)


def _envelope_kinds() -> frozenset[str]:
    return frozenset(_envelope()["properties"]["kind"]["enum"])


def _envelope_branch_kinds() -> frozenset[str]:
    branches = _envelope()["allOf"][0]["oneOf"]
    return frozenset(branch["properties"]["kind"]["const"] for branch in branches)


def _audit_branch_kinds() -> frozenset[str]:
    schemas = _openapi()["components"]["schemas"]
    names = [item["$ref"].rsplit("/", 1)[-1] for item in schemas["AuditEvent"]["oneOf"]]
    return frozenset(schemas[name]["properties"]["kind"]["const"] for name in names)


def _project_event_branch_kinds() -> frozenset[str]:
    schemas = _openapi()["components"]["schemas"]
    names = [item["$ref"].rsplit("/", 1)[-1] for item in schemas["ProjectEvent"]["oneOf"]]
    return frozenset(schemas[name]["properties"]["kind"]["const"] for name in names)


def test_the_catalog_covers_every_authored_kind_exactly_once() -> None:
    assert [entry.kind for entry in event_catalog()] == list(EventKind)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("operation", "merged", "operation"),
        ("proposal_kind", "merge", "kind"),
        ("proposal_state", "DONE", "state"),
        ("target_outcome", "guessed", "outcome"),
    ),
)
def test_request_proposal_event_refuses_every_closed_vocabulary_drift(
    field: str, value: str, message: str
) -> None:
    values: dict[str, object] = {
        "operation": "appended",
        "proposal_id": UUID("00000000-0000-7000-8000-000000000101"),
        "proposal_kind": "keep",
        "proposal_state": "OPEN",
        "target_request_id": UUID("00000000-0000-7000-8000-000000000102"),
        "target_command_id": None,
        "target_outcome": None,
        "target_problem_code": None,
    }
    values[field] = value

    with pytest.raises(ValueError, match=message):
        RequestProposalChangedPayload(
            operation=cast(str, values["operation"]),
            proposal_id=cast(UUID, values["proposal_id"]),
            proposal_kind=cast(str, values["proposal_kind"]),
            proposal_state=cast(str, values["proposal_state"]),
            target_request_id=cast(UUID, values["target_request_id"]),
            target_command_id=cast(UUID | None, values["target_command_id"]),
            target_outcome=cast(str | None, values["target_outcome"]),
            target_problem_code=cast(str | None, values["target_problem_code"]),
        )


def test_the_envelope_enum_matches_the_catalog() -> None:
    assert _parity_errors(_catalog_kinds(), _envelope_kinds(), "the event envelope enum") == []


def test_every_envelope_branch_matches_the_catalog() -> None:
    assert (
        _parity_errors(_catalog_kinds(), _envelope_branch_kinds(), "the event envelope union") == []
    )


def test_every_catalog_stream_prefix_is_authored_in_the_envelope_stream_pattern() -> None:
    pattern = _envelope()["properties"]["stream_id"]["pattern"]
    for entry in event_catalog():
        assert f"{entry.stream_prefix}:[0-9a-f-]{{36}}" in pattern, entry.kind.value


def test_every_catalog_origin_is_authored_in_its_envelope_branch() -> None:
    branches = {
        branch["properties"]["kind"]["const"]: branch["properties"]["origin"]["const"]
        for branch in _envelope()["allOf"][0]["oneOf"]
    }
    for entry in event_catalog():
        assert branches[entry.kind.value] in {origin.value for origin in entry.origins}


def test_the_session_kind_set_is_derived_rather_than_retyped() -> None:
    """The session kinds the HTTP audit union carries are exactly the catalog's."""

    derived = _catalog_session_kinds()
    authored = frozenset(kind for kind in _audit_branch_kinds() if kind.startswith("session."))

    assert derived == authored
    assert derived == {"session.started", "session.transitioned", "session.closed"}


def test_a_catalog_kind_with_no_authored_branch_fails_by_name() -> None:
    """Adding a kind to the catalog alone makes the parity guard RED, by name."""

    mutated = _catalog_kinds() | {PHANTOM}

    assert _parity_errors(mutated, _envelope_kinds(), "the event envelope enum") == [
        f"the event envelope enum omits catalog kind {PHANTOM}"
    ]
    assert _parity_errors(mutated, _envelope_branch_kinds(), "the event envelope union") == [
        f"the event envelope union omits catalog kind {PHANTOM}"
    ]


def test_a_session_kind_with_no_authored_http_branch_fails_by_name() -> None:
    """The HTTP surface is a derived subset, and it drifts by name too."""

    mutated = _catalog_session_kinds() | {PHANTOM}
    authored = {kind for kind in _audit_branch_kinds() if kind.startswith("session.")}

    assert _parity_errors(mutated, authored, "the session audit union") == [
        f"the session audit union omits catalog kind {PHANTOM}"
    ]


def test_the_project_feed_kind_set_is_derived_rather_than_retyped() -> None:
    """The project event feed's kind set is exactly the catalog's `project_feed` column."""

    derived = _catalog_project_feed_kinds()

    assert derived == _project_event_branch_kinds()
    assert derived == {
        "ticket.created",
        "ticket.custody_transferred",
        "ticket.comment_added",
        "work.changed",
        "workflow.changed",
        "proof.changed",
    }
    # Session/heartbeat kinds stay off the project feed pending #200 (SPEC INV-78).
    assert derived.isdisjoint(_catalog_session_kinds())


def test_a_project_feed_kind_with_no_authored_http_branch_fails_by_name() -> None:
    """A catalog `project_feed` addition with no `ProjectEvent` branch drifts by name."""

    mutated = _catalog_project_feed_kinds() | {PHANTOM}

    assert _parity_errors(mutated, _project_event_branch_kinds(), "the project event union") == [
        f"the project event union omits catalog kind {PHANTOM}"
    ]


def test_the_project_event_union_reuses_the_existing_audit_branches() -> None:
    """`ProjectEvent` must not declare six duplicate schemas beside `AuditEvent`'s."""

    schemas = _openapi()["components"]["schemas"]
    project_refs = {item["$ref"] for item in schemas["ProjectEvent"]["oneOf"]}
    audit_refs = {item["$ref"] for item in schemas["AuditEvent"]["oneOf"]}

    assert project_refs <= audit_refs
    assert project_refs == {ref for ref in audit_refs if "Session" not in ref}


def test_an_authored_branch_with_no_catalog_kind_fails_by_name() -> None:
    """Authoring a contract branch alone is refused with the same chokepoint."""

    assert _parity_errors(
        _catalog_kinds(), _envelope_kinds() | {PHANTOM}, "the event envelope enum"
    ) == [f"the event envelope enum declares unknown kind {PHANTOM}"]


def test_the_chokepoint_and_its_guards_both_survive() -> None:
    """Deleting the chokepoint makes this RED instead of silently dropping parity."""

    source = Path(__file__).read_text(encoding="utf-8")

    assert callable(_parity_errors)
    assert source.count("_parity_errors(_catalog_kinds()") >= MINIMUM_PARITY_GUARDS
