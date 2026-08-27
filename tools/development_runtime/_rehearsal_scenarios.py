"""The four rehearsal scenarios and their teeth."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools.development_runtime._rehearsal_cluster import (
    Clone,
    _live_ports,
    _prune_docker_networks,
    disposable_cluster,
)
from tools.development_runtime._rehearsal_fixture import (
    checkpoint_round_trip,
    clone_counts,
    clone_ledger,
    inject_genuine_schema_drift,
    seed_fixture_history,
)
from tools.development_runtime._rehearsal_live import LiveProperties
from tools.development_runtime._rehearsal_vocabulary import (
    COMPOSE_RELATIVE,
    OFFLINE_FIXTURE_ENDPOINT,
    REPARSED_CONSTRAINT,
    REPARSED_TABLE,
    REQUIRED_DRIFT_DIGEST_NAMES,
    UpgradeRehearsalError,
)
from tools.development_runtime._rehearsal_bridge import kernel_call
from tools.development_runtime._rehearsal_checkpoint import resolve_replay_checkpoint, restore_product_checkpoint

__all__ = ["RehearsalResult", "run_scenario"]

# ---------------------------------------------------------------------------
# scenarios
# ---------------------------------------------------------------------------


@dataclass
class RehearsalResult:
    name: str
    passed: bool = False
    # A scenario that refuses for a reason the LIVE probe already named is not a defect in the
    # target ref: it is the box's own state, and no ref can fix it. It still holds the gate red.
    blocked: bool = False
    code: str = ""
    reason: str = ""
    first_failing_precondition: str | None = None
    ledger_before: tuple[int, str | None] = (0, None)
    ledger_after: tuple[int, str | None] = (0, None)
    schema_digest_before: str = ""
    schema_digest_after: str = ""
    fixture_vector: tuple[str, ...] = ()
    counts_before: dict[str, int] = field(default_factory=dict)
    counts_after: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def run_scenario(
    name: str,
    *,
    base: Path,
    target: Path,
    live: LiveProperties,
    keep: bool,
    replay_checkpoint: str | None = None,
) -> RehearsalResult:
    """Build the clone, prove it is faithful, then apply the pending set exactly as ``database-up``."""

    result = RehearsalResult(name=name, passed=False)
    _prune_docker_networks()
    forbidden = _live_ports(live.endpoint == OFFLINE_FIXTURE_ENDPOINT)
    with disposable_cluster(base / COMPOSE_RELATIVE, forbidden, keep) as clone:
        installed = kernel_call(
            base, "install", admin_dsn=clone.admin_dsn, migrator_dsn=clone.migrator_dsn
        )
        if not installed["ok"]:
            raise UpgradeRehearsalError(
                f"base install failed: {installed['code']}: {installed['detail']}"
            )
        if name == "as-live-now":
            # Replay the REAL rollback target: the product's recorded checkpoint (explicit or the
            # latest), never a synthetic reconstruction of a state that no longer exists.
            replay = resolve_replay_checkpoint(replay_checkpoint)
            if replay is not None:
                restore_product_checkpoint(clone, replay)
                result.notes.append(replay.note)
                result.counts_before = clone_counts(clone)
            else:
                checkpoint_round_trip(clone)
                result.notes.append(
                    "no recorded product checkpoint to replay — fell back to the historical "
                    "dump/restore drift reconstruction (the gate is weaker than it should be)"
                )
                result.counts_before = seed_fixture_history(clone, live)
        elif name == "deparse-variance":
            checkpoint_round_trip(clone)
            result.notes.append(
                "reconstructed the deparse-variance fixture (clean install -> dump/restore round "
                "trip -> original/superseded-raw attestation)"
            )
            result.counts_before = seed_fixture_history(clone, live)
        elif name == "drifted-history-refuses":
            inject_genuine_schema_drift(clone)
            result.notes.append(
                f"injected genuine schema drift by dropping {REPARSED_TABLE}.{REPARSED_CONSTRAINT}"
            )
            result.counts_before = seed_fixture_history(clone, live)
        else:
            result.counts_before = seed_fixture_history(clone, live)
        result.ledger_before = clone_ledger(clone)
        _assert_shape(name, clone, live, target, result)
        vector = kernel_call(target, "semantics", dsn=clone.admin_dsn)["checks"]
        result.fixture_vector = tuple(name_ for name_, v in vector.items() if v == "reject")
        _assert_fixture_faithful(result, live)
        result.schema_digest_before = kernel_call(target, "fingerprint", dsn=clone.admin_dsn)[
            "fingerprint"
        ]
        applied = kernel_call(
            target, "install", admin_dsn=clone.admin_dsn, migrator_dsn=clone.migrator_dsn
        )
        result.ledger_after = clone_ledger(clone)
        result.counts_after = clone_counts(clone)
        result.schema_digest_after = kernel_call(target, "fingerprint", dsn=clone.admin_dsn)[
            "fingerprint"
        ]
        if name == "drifted-history-refuses":
            _record_drifted_refusal(result, applied)
        else:
            _record_outcome(result, applied)
        result.blocked = result.code in {code for code, _ in live.blockers}
        _note_split_brain(result)
    return result


def _note_split_brain(result: RehearsalResult) -> None:
    """Name the second gh#232 defect when the clone exhibits it: DDL committed, ledger refused."""

    if result.passed or result.schema_digest_after == result.schema_digest_before:
        return
    result.notes.append(
        "SPLIT-BRAIN REPRODUCED: the schema transaction committed "
        f"({result.schema_digest_before[:20]}… -> {result.schema_digest_after[:20]}…) while the "
        f"ledger still terminates at {result.ledger_after[1]} — recovery needs a restore, not a retry"
    )


def _assert_shape(
    name: str, clone: Clone, live: LiveProperties, target: Path, result: RehearsalResult
) -> None:
    """The clone must stand where live stands: same ledger position, and for as-live-now, same schema."""

    rows, terminal = result.ledger_before
    if (rows, terminal) != (live.ledger_rows, live.terminal_migration):
        raise UpgradeRehearsalError(
            f"clone ledger {rows}@{terminal} does not reproduce live {live.ledger_rows}@"
            f"{live.terminal_migration}; the base ref is wrong"
        )
    if name != "as-live-now":
        return
    probe = kernel_call(target, "fingerprint", dsn=clone.admin_dsn)
    if probe["fingerprint"] != live.schema_fingerprint:
        raise UpgradeRehearsalError(
            f"clone schema {probe['fingerprint'][:20]}… does not reproduce live "
            f"{live.schema_fingerprint[:20]}…; differing records: "
            f"{_differing_records(probe['records'], live.schema_records)}"
        )
    # The teeth: as-live-now must stand where live stands RIGHT NOW. This is the assertion that
    # caught the fixture-vs-live divergence on 2026-08-04.
    attestation = _clone_ledger_attestation(clone)
    if attestation != live.ledger_attestation:
        raise UpgradeRehearsalError(
            f"clone terminal attestation {attestation[:20]}… does not match live's current "
            f"{live.ledger_attestation[:20]}…; the replay target diverges from live "
            f"(fixture-vs-live divergence) — refusing to make a claim"
        )
    result.notes.append("clone schema digest and terminal attestation equal live's exactly")


def _differing_records(clone: dict[str, str], live: dict[str, str], limit: int = 6) -> str:
    """Name what actually differs — a shape check that cannot say what moved is not a check."""

    names = sorted(key for key in set(clone) | set(live) if clone.get(key) != live.get(key))
    shown = ", ".join(names[:limit])
    remainder = f" (+{len(names) - limit} more)" if len(names) > limit else ""
    return f"{len(names)}: {shown}{remainder}"


def _assert_fixture_faithful(result: RehearsalResult, live: LiveProperties) -> None:
    if live.endpoint == OFFLINE_FIXTURE_ENDPOINT:
        result.notes.append(
            "offline fixture mode: no live probe; fixture vector recorded, not live-matched"
        )
        return
    if set(result.fixture_vector) == set(live.rejected_checks):
        return
    missing = sorted(set(live.rejected_checks) - set(result.fixture_vector))
    extra = sorted(set(result.fixture_vector) - set(live.rejected_checks))
    raise UpgradeRehearsalError(
        "fixture-infidelity: the clone's precondition vector differs from live "
        f"(live-only: {missing or 'none'}; clone-only: {extra or 'none'}); refusing to make a claim"
    )


def _record_outcome(result: RehearsalResult, applied: dict[str, Any]) -> None:
    if applied["ok"]:
        result.passed = True
        result.reason = f"full pending set applied and recorded in {applied['seconds']}s"
        return
    result.passed = False
    result.code = applied["code"]
    result.reason = f"{applied['code']}: {applied['detail']}"
    # A semantic refusal lists check names; every other refusal is named by its own typed code.
    candidate = str(applied["detail"]).split(",")[0].strip()
    named = re.fullmatch(r"[a-z][a-z0-9-]*", candidate) is not None
    result.first_failing_precondition = candidate if named else applied["code"]


# The three-generation diagnostic a ledger-schema-mismatch refusal must carry so a human can see
# at a glance which digest the live box diverged on. The CSO pinned this on 2026-08-03.
def _record_drifted_refusal(result: RehearsalResult, applied: dict[str, Any]) -> None:
    """Score the permanent negative scenario: drifted history MUST refuse, carrying the three names.

    PASS means the upgrade REFUSED ledger-schema-mismatch and the refusal detail carried all three
    digest names, pinning the gh#245-class catch forever. FAIL means either it wrongly upgraded
    (the catch broke) or it refused with the wrong shape, so the negative scenario stopped doing
    its job.
    """

    if applied["ok"]:
        result.passed = False
        result.code = ""
        result.reason = (
            "the drifted history UPGRADED instead of refusing ledger-schema-mismatch — "
            "the gh#245-class catch is broken"
        )
        return
    code = applied["code"]
    detail = str(applied["detail"])
    missing = [token for token in REQUIRED_DRIFT_DIGEST_NAMES if token not in detail]
    if code == "ledger-schema-mismatch" and not missing:
        result.passed = True
        result.code = code
        result.notes.append(f"refusal detail carried verbatim: {detail}")
        result.first_failing_precondition = code
        result.reason = (
            "PASS: the drifted history REFUSED ledger-schema-mismatch carrying all three digest "
            "names (attested= · live_canonical= · live_superseded_raw=)"
        )
        return
    result.passed = False
    result.code = code
    result.reason = (
        f"refused with {code or 'an untyped error'}, expected ledger-schema-mismatch with "
        f"{', '.join(REQUIRED_DRIFT_DIGEST_NAMES)}; missing {', '.join(missing) or 'none'}"
    )


