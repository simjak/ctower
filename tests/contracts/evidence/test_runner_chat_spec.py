"""Current-head contract checks for the deferred runner and chat/steer specification rows."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).parents[3]
_SPEC = ROOT / "docs/internal/SPEC.md"
_MANIFEST = ROOT / "tests/contracts/evidence/fixtures/i1-complete-manifest.json"
_CURRENT_COMMAND = "uv run pytest tests/contracts/evidence/test_runner_chat_spec.py -q"
_EN_DASH = "\N{EN DASH}"

_CRITERIA: tuple[tuple[str, str], ...] = (
    ("AC-RUN-16", "ct-i2-013"),
    ("AC-RUN-17", "ct-i2-013"),
    ("AC-RUN-18", "ct-i2-013"),
    ("AC-RUN-19", "ct-i2-013"),
    ("AC-RUN-20", "ct-i2-013"),
    ("AC-RUN-21", "ct-i2-013"),
    ("AC-CHAT-01", "ct-i2-014"),
    ("AC-CHAT-02", "ct-i2-014"),
    ("AC-CHAT-03", "ct-i2-014"),
    ("AC-CHAT-04", "ct-i2-014"),
    ("AC-CHAT-05", "ct-i2-014"),
    ("AC-CHAT-06", "ct-i2-014"),
    ("AC-CHAT-07", "ct-i2-014"),
    ("AC-CHAT-08", "ct-i2-014"),
    ("AC-CHAT-09", "ct-i2-014"),
    ("AC-CHAT-10", "ct-i2-014"),
    ("AC-CHAT-11", "ct-i2-014"),
    ("AC-CHAT-12", "ct-i2-014"),
    ("AC-CHAT-13", "ct-i2-014"),
    ("AC-CHAT-14", "ct-i2-014"),
)

_READ_GAPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("AC-CHAT-08", ("HarnessSpec", "listHarnessSpecs", "getHarnessSpec", "/v1/harness")),
    ("AC-CHAT-09", ("TicketResource", "stage", "workflow_ref")),
    ("AC-CHAT-10", ("listTickets", "getBoard")),
    (
        "AC-CHAT-11",
        (
            "attention findings",
            "intake queue",
            "project_seats",
            "poisoned outbox messages",
        ),
    ),
)

_INVENTORY = (
    "authored OpenAPI",
    "generated Python/TypeScript clients",
    "contract operation counters",
    "reference documentation",
)

_WRITE_SURFACES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "AC-CHAT-12",
        (
            "registerHarness",
            "POST /v1/harness/registrations",
            "HarnessRegistry.register",
            "harness-survey-answers-incomplete",
            "harness-layer-roles-conflict",
            "harness-runtime-kind-invalid",
        ),
    ),
    (
        "AC-CHAT-13",
        (
            "submitHarnessSurvey",
            "POST /v1/harness/{harness_key}/survey",
            "SURVEY_QUESTIONS",
            "harness-survey-answers-incomplete",
            "derive_roles",
        ),
    ),
    (
        "AC-CHAT-14",
        (
            "bindHarnessCredentialReference",
            "POST /v1/harness/{harness_key}/credential-reference",
            "CredentialReference",
            "credential_ref",
            "project-scope-denied",
            "writeback-scope-denied",
        ),
    ),
)


def _spec() -> str:
    return _SPEC.read_text(encoding="utf-8")


def _spec_row(code: str) -> str:
    rows = [line for line in _spec().splitlines() if f"</a>{code} |" in line]
    assert len(rows) == 1, f"SPEC declares {code} {len(rows)} times"
    return rows[0]


def _manifest_row(code: str) -> dict[str, Any]:
    manifest = cast(dict[str, Any], json.loads(_MANIFEST.read_text(encoding="utf-8")))
    rows = [
        cast(dict[str, Any], row)
        for row in cast(list[object], manifest["criteria"])
        if cast(dict[str, Any], row)["criterion_key"] == code
    ]
    assert len(rows) == 1, f"manifest declares {code} {len(rows)} times"
    return rows[0]


@pytest.mark.parametrize(
    "code, owner", _CRITERIA, ids=lambda item: str(item).lower().replace("-", "_")
)
def test_new_rows_designate_the_collectable_current_deferred_check(code: str, owner: str) -> None:
    row = _spec_row(code)
    commands = [
        command
        for command in re.findall(r"`([^`]+)`", row)
        if command.startswith(("uv run pytest", "python -m", "systemd-analyze"))
    ]
    assert commands == [_CURRENT_COMMAND]
    assert "not-yet-required" in row

    manifest_row = _manifest_row(code)
    assert manifest_row["disposition"] == "deferred"
    assert manifest_row["owner"] == owner
    assert "deferred until owner ticket" in manifest_row["reason"]


def test_i2_rows_name_the_accepted_harness_adapter_phase_activation() -> None:
    for ticket in ("CT-I2-013", "CT-I2-014"):
        row = next(line for line in _spec().splitlines() if line.startswith(f"| {ticket} |"))
        assert "accepted harness-adapter phase activation" in row
        assert 'active_phase = "CT-I1-043"' in row


def test_collect_remains_artifact_only_and_transcript_transport_is_separate() -> None:
    spec = _spec()
    transcript_route = (
        "collects typed artifacts; transports transcript observations "
        "through a separate typed runner vocabulary"
    )
    assert transcript_route in spec

    ac_run_19 = _spec_row("AC-RUN-19")
    assert (
        "`collect` crosses the boundary only as strict, revision-pinned typed artifacts."
        in ac_run_19
    )
    old_collect_route = (
        "collect` crosses the boundary only as strict, revision-pinned typed artifacts "
        "and a typed transcript"
    )
    assert old_collect_route not in ac_run_19
    assert "separate strict typed transcript observation vocabulary" in ac_run_19

    ct_i2_013 = next(line for line in spec.splitlines() if line.startswith("| CT-I2-013 |"))
    assert "collect strict typed artifacts; transport typed transcript observations" in ct_i2_013
    assert "collect strict typed artifacts/transcript facts" not in ct_i2_013


@pytest.mark.parametrize(
    "code, markers", _READ_GAPS, ids=lambda item: str(item).lower().replace("-", "_")
)
def test_record_backed_read_gaps_are_explicitly_folded_into_chat_surface(
    code: str, markers: tuple[str, ...]
) -> None:
    row = _spec_row(code)
    assert "docs/internal/design/ctower-app.md" in row
    assert "read over facts the record already stores" in row
    assert "no new authority" in row
    assert "no new seam capability" in row
    assert all(marker in row for marker in markers)
    assert all(inventory in row for inventory in _INVENTORY)


@pytest.mark.parametrize(
    "code, markers", _WRITE_SURFACES, ids=lambda item: str(item).lower().replace("-", "_")
)
def test_harness_setup_writes_are_http_faces_over_kernel_ceremonies(
    code: str, markers: tuple[str, ...]
) -> None:
    row = _spec_row(code)
    assert "docs/internal/design/ctower-app.md" in row
    assert "HTTP" in row
    assert "write" in row
    assert "kernel" in row
    assert "no new authority" in row
    assert "no new seam capability" in row
    assert all(marker in row for marker in markers)
    assert all(inventory in row for inventory in _INVENTORY)


def test_i2_backlog_rows_remain_inside_the_markdown_table() -> None:
    lines = _spec().splitlines()
    table_start = next(
        index for index, line in enumerate(lines) if line.startswith("| CT-I2-012 |")
    )
    assert lines[table_start + 1].startswith("| CT-I2-013 |")
    assert lines[table_start + 2].startswith("| CT-I2-014 |")


def test_runner_box_has_a_closed_right_edge_and_bounded_gap_claim() -> None:
    lines = ROOT.joinpath("ARCHITECTURE.md").read_text(encoding="utf-8").splitlines()
    right_edge = len(lines[334 - 1]) - 1
    for line_number in (341, 342):
        line = lines[line_number - 1]
        assert line.endswith("|")
        assert len(line) == right_edge + 1

    atlas = re.sub(r"\s+", " ", "\n".join(lines[362 - 1 : 368 - 1]))
    assert (
        f"admitted G1{_EN_DASH}G4 operation families, including the HarnessSpec read,"
        f" joined by the record-backed G10, G11, and G12 reads"
    ) in atlas
    assert "only operation families named by the" not in atlas
    assert f"G5{_EN_DASH}G9 (including G8b) remain outside" in atlas
