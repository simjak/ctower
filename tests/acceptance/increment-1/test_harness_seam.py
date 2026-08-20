"""CT-I1-041 acceptance — the seam holds at every boundary it crosses.

The conformance suite proves that the bindings obey one contract. This file proves the
things a conformance run cannot see: that the seam's vocabulary does not collide with the
one SPEC already owns, that the worker plane and the control plane use the same words for
the same credential facts, that no kernel or product path can reach a harness-private
parser, that the runner holds no record-tier connection, and that a spec is genuinely parsed
as data rather than resolved as code.
"""

from __future__ import annotations

import ast
import json
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest
from ctower_contracts import CATALOG

from ctower_kernel.pools import reconcile, resolve_registration, selectable
from ctower_kernel.pools.topology import TOPOLOGY_REVISION, model_weights
from ctower_kernel.record.pool_events import (
    AUTH_STATES,
    QUOTA_STATES,
    REACH_STATES,
    REGISTRATION_STATES,
    PoolObservationEntryPayload,
)
from ctower_runner.hermes.spec import HERMES_KEY, digest_of, harness_spec_document
from ctower_runner_sdk.credentials import EntryState, project_entry
from ctower_runner_sdk.credits import ModelWeight, TokenUsage, WeightTable
from ctower_runner_sdk.refusals import SEAM_MINTED, SPEC_OWNED, Refusal
from ctower_runner_sdk.registry import HarnessRegistry
from ctower_runner_sdk.seam import SEAM_VERBS
from ctower_runner_sdk.spec import HarnessSpec, parse_harness_spec

__all__: tuple[str, ...] = ()

_ROOT = Path(__file__).resolve().parents[3]
_SDK = _ROOT / "packages/ctower-runner-sdk/src"
_RUNNER = _ROOT / "apps/ctower-runner/src"
_SPEC_MD = _ROOT / "docs/internal/SPEC.md"
_SUITES = _ROOT / "tools/checks/expected-suites.toml"
_MANIFEST = _ROOT / "tests/contracts/evidence/fixtures/i1-complete-manifest.json"

# Harness-private observation lives inside a binding and nowhere else.
_PRIVATE_MODULES = ("ctower_runner.hermes.liveness", "ctower_runner.hermes.corpus")
_CONTROL_PLANE = (
    _ROOT / "packages/ctower-kernel/src",
    _ROOT / "apps/ctower-api/src",
    _ROOT / "apps/ctowerctl/src",
)
_RECORD_TIER = ("psycopg", "ctower_kernel.record", "ctower_kernel.pools")
_CODE_RESOLUTION = ("importlib", "__import__", "eval", "exec", "pickle", "subprocess")
_AC_IDS = tuple(f"AC-HAD-{index:02d}" for index in range(1, 13))
_SEAM_SUITES = ("harness-adapter-conformance", "harness-seam-acceptance")


def _document() -> dict[str, object]:
    return harness_spec_document(
        artifact_digest=digest_of(b"acceptance-artifact"),
        config_digest=digest_of(b"acceptance-config"),
    )


def _spec() -> HarnessSpec:
    parsed = parse_harness_spec(_document())
    assert isinstance(parsed, HarnessSpec), parsed
    return parsed


def _registration_registry(_spec: HarnessSpec | None = None) -> HarnessRegistry:
    return HarnessRegistry()


def _python_files(root: Path) -> Iterator[Path]:
    yield from sorted(path for path in root.rglob("*.py") if path.is_file())


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_the_authored_runner_contracts_reach_the_generated_closed_world() -> None:
    for reference in ("ctower.harness-spec/v1", "ctower.credential-lease/v1"):
        assert CATALOG.schema_for(reference) is not None, reference


def test_the_seam_is_exactly_five_verbs_over_the_existing_supervisor_interface() -> None:
    assert SEAM_VERBS == ("spawn", "liveness", "collect", "writeback", "teardown")


def test_no_minted_refusal_name_collides_with_the_vocabulary_spec_already_owns() -> None:
    spec_text = _SPEC_MD.read_text(encoding="utf-8")

    assert not SEAM_MINTED & SPEC_OWNED
    for name in sorted(SEAM_MINTED):
        assert f"`{name}`" not in spec_text, name
    for name in sorted(SPEC_OWNED):
        assert f"`{name}`" in spec_text, name


def test_the_worker_plane_and_the_kernel_use_one_vocabulary_for_the_three_axes() -> None:
    entry = project_entry(
        {
            "provider_key": "openai-codex",
            "subscription_identity": "seat-one@example.test",
            "entry_label": "seat-one",
            "registration_state": "enrolled",
            "auth_state": "healthy",
            "quota_state": "available",
            "reach_state": "ok",
            "request_count": 3,
            "last_status_observed": "ok",
            "secret_fingerprint": "sha256:" + "a" * 64,
        }
    )

    assert entry.auth_state in AUTH_STATES
    assert entry.quota_state in QUOTA_STATES
    assert entry.reach_state in REACH_STATES
    assert entry.registration_state in REGISTRATION_STATES


def test_a_selectable_entry_reads_the_same_on_both_planes() -> None:
    payload = PoolObservationEntryPayload(
        entry_ordinal=0,
        provider_key="openai-codex",
        subscription_identity="simonas@jakit.lt",
        entry_label="seat-one",
        registration_state="enrolled",
        auth_state="healthy",
        quota_state="available",
        quota_reset_at=None,
        reach_state="ok",
        request_count=7,
        last_status_observed="ok",
        secret_fingerprint="sha256:" + "b" * 64,
    )
    runner_entry = project_entry(payload.to_mapping() | {"quota_reset_at": None})

    assert selectable(payload) is (not runner_entry.blocking_axes())
    assert isinstance(runner_entry, EntryState)


def test_the_runner_prices_against_the_registrys_own_published_weight_table() -> None:
    table = WeightTable.from_rows(
        TOPOLOGY_REVISION,
        (
            ModelWeight(
                subscription_key=weight.subscription_key,
                model_ref=weight.model_ref,
                input_millicredits_per_mtok=weight.input_millicredits_per_mtok,
                cached_input_millicredits_per_mtok=weight.cached_input_millicredits_per_mtok,
                output_millicredits_per_mtok=weight.output_millicredits_per_mtok,
            )
            for weight in model_weights()
        ),
    )

    row = table.price(
        model_ref="gpt-5.6-sol",
        subscription_identity="simonas@jakit.lt",
        task_class="main",
        tokens=TokenUsage(1_000_000, 0, 1_000_000),
        expected_revision=TOPOLOGY_REVISION,
    )

    assert not isinstance(row, Refusal), row
    assert row.millicredits == 125_000 + 750_000


def test_an_undesired_identity_is_a_drift_finding_and_never_selectable() -> None:
    observed = (
        PoolObservationEntryPayload(
            entry_ordinal=0,
            provider_key="openai-codex",
            subscription_identity="stranger@example.test",
            entry_label="seat-four",
            registration_state="enrolled",
            auth_state="healthy",
            quota_state="available",
            quota_reset_at=None,
            reach_state="ok",
            request_count=1,
            last_status_observed="ok",
            secret_fingerprint=None,
        ),
    )

    resolved = resolve_registration(HERMES_KEY, observed)
    findings = reconcile(HERMES_KEY, resolved)

    assert resolved[0].registration_state == "discovered"
    assert not selectable(resolved[0])
    assert project_entry(resolved[0].to_mapping()).blocking_axes() != ()
    assert {finding.finding for finding in findings} == {"missing", "unregistered"}
    assert {finding.enactment for finding in findings} <= {"operator-ceremony", "secret-reference"}


def test_the_runner_sdk_imports_no_kernel_no_api_and_no_cli() -> None:
    forbidden = ("ctower_kernel", "ctower_api", "ctowerctl")

    for path in _python_files(_SDK):
        modules = _imported_modules(path)
        offending = [module for module in modules if module.split(".")[0] in forbidden]
        assert not offending, f"{path}: {offending}"


def test_the_runner_holds_no_record_tier_connection() -> None:
    for path in (*_python_files(_SDK), *_python_files(_RUNNER)):
        modules = _imported_modules(path)
        offending = [
            module for module in modules if any(module.startswith(bad) for bad in _RECORD_TIER)
        ]
        assert not offending, f"{path}: {offending}"


def test_no_control_plane_path_imports_a_harness_private_parser() -> None:
    for root in _CONTROL_PLANE:
        for path in _python_files(root):
            modules = _imported_modules(path)
            offending = [module for module in modules if module in _PRIVATE_MODULES]
            assert not offending, f"{path}: {offending}"


def test_a_harness_spec_is_parsed_as_data_and_never_resolved_as_code() -> None:
    spec_module = _SDK / "ctower_runner_sdk/spec.py"

    modules = _imported_modules(spec_module)
    source = spec_module.read_text(encoding="utf-8")

    assert not [name for name in _CODE_RESOLUTION if name in modules]
    assert not [name for name in ("eval(", "exec(", "__import__(") if name in source]


@pytest.mark.parametrize("field", ("artifact_digest", "config_digest"))
def test_a_digest_mismatch_performs_zero_dispatch_and_refuses_by_name(field: str) -> None:
    document = _document()
    document[field] = "sha256:not-a-real-digest"

    refusal = _registration_registry().register(document, "real")

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-spec-digest-mismatch"


def test_a_revoked_spec_is_a_refusal_and_never_a_fallback_to_a_generic_process() -> None:
    document = _document()
    document["status"] = "revoked"

    refusal = _registration_registry().register(document, "real")

    assert isinstance(refusal, Refusal), refusal
    assert refusal.name == "harness-spec-revoked"
    assert "generic" not in refusal.action.lower() or "never" in refusal.meaning.lower()


def test_the_public_seam_does_not_publish_on_one_real_binding() -> None:
    registry = _registration_registry()
    registry.register(_document(), "real")

    refusal = registry.publication()

    assert isinstance(refusal, Refusal)
    assert refusal.name == "harness-seam-unpublished"


def test_the_hermes_binding_declares_a_serving_source_that_is_not_its_own_footer() -> None:
    source = _spec().serving_source()

    assert source is not None
    assert source.source == "gateway_log"
    assert not [
        item
        for item in _spec().liveness_sources
        if item.fact == "served_model" and item.source == "pane_footer" and item.proves == "serving"
    ]


def test_every_frozen_acceptance_row_has_an_evidence_manifest_disposition() -> None:
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    body = json.dumps(manifest)
    spec_text = _SPEC_MD.read_text(encoding="utf-8")

    for identifier in _AC_IDS:
        assert identifier in spec_text, identifier
        assert identifier in body, identifier


def test_both_seam_suites_are_registered_in_the_suite_manifest() -> None:
    manifest = tomllib.loads(_SUITES.read_text(encoding="utf-8"))
    suites = {suite["id"]: suite for suite in manifest["suite"]}

    for suite_id in _SEAM_SUITES:
        assert suite_id in suites, suite_id
        assert suites[suite_id]["owner"] == "CT-I1-041"
        assert suites[suite_id]["phase"] in manifest["phase_order"]
