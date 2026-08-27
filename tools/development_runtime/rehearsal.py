"""Prove a schema upgrade on a disposable clone before a freeze (T-CTW-040).

Ported from mission-control's ``tools/ctower-upgrade-rehearsal`` — the first-class rehearsal
step of the release helper. The mission-control tool stays the source of truth until AC-2's
real-freeze cutover deletes it.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from tools.development_runtime._rehearsal_live import (
    LiveProperties,
    live_read,
    probe_live,
    resolve_live_dsn,
)
from tools.development_runtime._rehearsal_vocabulary import (
    COMPOSE_RELATIVE,
    LIVE_DSN_ENVIRON,
    EXIT_LIVE_BLOCKED,
    EXIT_NO_CLAIM,
    EXIT_PASS,
    EXIT_REHEARSAL_FAIL,
    FIXTURE_ROUTINE_EVENTS,
    FIXTURE_TICKETS,
    OFFLINE_FIXTURE_ENDPOINT,
    SCENARIO_NAMES,
    UpgradeRehearsalError,
)
from tools.development_runtime._rehearsal_bridge import kernel_call, kernel_worker, open_database
from tools.development_runtime._rehearsal_cluster import (
    Clone,
    describe_source,
    disposable_cluster,
    resolve_base_ref,
    source_tree,
)
from tools.development_runtime._rehearsal_fixture import (
    _clone_ledger_attestation,
    clone_counts,
    clone_ledger,
    seed_fixture_history,
)
from tools.development_runtime._rehearsal_scenarios import (
    RehearsalResult,
    _record_drifted_refusal,
    _record_outcome,
    run_scenario,
)
from tools.development_runtime._rehearsal_report import emit_json, render

__all__ = [
    "Clone",
    "LIVE_DSN_ENVIRON",
    "_record_drifted_refusal",
    "_record_outcome",
    "_verdict",
    "LiveProperties",
    "RehearsalResult",
    "UpgradeRehearsalError",
    "kernel_call",
    "live_read",
    "parse_rehearsal_arguments",
    "resolve_live_dsn",
    "run_upgrade_rehearsal",
]


def parse_rehearsal_arguments(argv: list[str]) -> argparse.Namespace:
    """Parse the verb's arguments, refusing offline mode without an explicit base ref."""

    arguments = _rehearsal_parser().parse_args(argv)
    if arguments.offline_fixture and not arguments.base_ref:
        raise UpgradeRehearsalError(
            "--offline-fixture requires --base-ref because live is not probed"
        )
    return arguments


def _rehearsal_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="upgrade-rehearsal",
        description="prove a schema upgrade on a disposable clone before a freeze",
    )
    parser.add_argument("--target-ref", default="origin/main")
    parser.add_argument(
        "--target-source",
        type=Path,
        default=None,
        help="use an existing checkout as it stands, uncommitted changes included",
    )
    parser.add_argument(
        "--base-ref",
        default=None,
        help="default: the newest commit whose manifest ends at the live terminal",
    )
    parser.add_argument("--scenario", choices=(*SCENARIO_NAMES, "all"), default="all")
    parser.add_argument(
        "--offline-fixture",
        action="store_true",
        help="do not probe live; derive clone properties from the supplied --base-ref",
    )
    parser.add_argument(
        "--replay-checkpoint",
        default=None,
        help="product checkpoint id (or a path to its database.sql.gpg artifact) to replay",
    )
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--keep", action="store_true", help="leave the disposable cluster running")
    parser.add_argument("--kernel-op", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--kernel-source", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--dsn", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--admin-dsn", dest="admin_dsn", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--migrator-dsn", dest="migrator_dsn", default=None, help=argparse.SUPPRESS)
    return parser


def run_upgrade_rehearsal(arguments: argparse.Namespace) -> int:
    """Drive one rehearsal and answer the gate's exit code."""

    if arguments.kernel_op:
        return kernel_worker(arguments)
    run_root = _state_root() / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root.mkdir(parents=True, exist_ok=True)
    try:
        return _drive(arguments, run_root)
    except UpgradeRehearsalError as error:
        print(f"\nNO CLAIM: {error}\n", file=sys.stderr)
        return EXIT_NO_CLAIM
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or b"").decode()[-500:] if isinstance(error.stderr, bytes) else ""
        print(
            f"\nNO CLAIM: {' '.join(map(str, error.cmd))[:120]} failed: {detail}\n",
            file=sys.stderr,
        )
        return EXIT_NO_CLAIM
    finally:
        _remove_if_empty(run_root)


def _state_root() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / (
        "ctower-upgrade-rehearsal"
    )


def _remove_if_empty(run_root: Path) -> None:
    if run_root.is_dir() and not any(run_root.iterdir()):
        run_root.rmdir()


def _drive(arguments: argparse.Namespace, run_root: Path) -> int:
    with source_tree(arguments.target_ref, arguments.target_source, run_root, "target") as target:
        if arguments.offline_fixture:
            base_ref = arguments.base_ref
        else:
            live = probe_live(target)
            base_ref = arguments.base_ref or resolve_base_ref(live.terminal_migration)
        with source_tree(base_ref, None, run_root, "base") as base:
            if arguments.offline_fixture:
                live = _offline_fixture_properties(base, target, arguments.keep)
            names = SCENARIO_NAMES if arguments.scenario == "all" else (arguments.scenario,)
            results = [
                run_scenario(
                    name,
                    base=base,
                    target=target,
                    live=live,
                    keep=arguments.keep,
                    replay_checkpoint=arguments.replay_checkpoint
                    if name == "as-live-now"
                    else None,
                )
                for name in names
            ]
            reference = None if arguments.target_source else arguments.target_ref
            target_label = describe_source(target, reference)
            base_label = describe_source(base, base_ref)
        render(live, results, target_label, base_label)
        if arguments.json:
            emit_json(arguments.json, live, results, {"target": target_label, "base": base_label})
    return _verdict(live, results)


def _offline_fixture_properties(base: Path, target: Path, keep: bool) -> LiveProperties:
    """Construct the clone-property contract without touching live."""

    from tools.development_runtime._rehearsal_cluster import _prune_docker_networks

    _prune_docker_networks()
    fixture_counts = {
        "tickets": FIXTURE_TICKETS,
        "events": FIXTURE_TICKETS + FIXTURE_ROUTINE_EVENTS + 1,
    }
    seed_contract = LiveProperties(
        endpoint=OFFLINE_FIXTURE_ENDPOINT,
        in_recovery=False,
        server_version="offline-fixture",
        ledger_rows=0,
        terminal_migration="",
        ledger_attestation="",
        schema_fingerprint="",
        schema_records={},
        table_counts=fixture_counts,
        rejected_checks=(),
        event_kinds={},
        link_subject_kinds={},
        blockers=(),
    )
    with disposable_cluster(base / COMPOSE_RELATIVE, set(), keep) as clone:
        installed = kernel_call(
            base, "install", admin_dsn=clone.admin_dsn, migrator_dsn=clone.migrator_dsn
        )
        if not installed["ok"]:
            raise UpgradeRehearsalError(
                f"base install failed: {installed['code']}: {installed['detail']}"
            )
        seed_fixture_history(clone, seed_contract)
        rows, terminal = clone_ledger(clone)
        fingerprint = kernel_call(target, "fingerprint", dsn=clone.admin_dsn)
        vector = kernel_call(target, "semantics", dsn=clone.admin_dsn)["checks"]
        return LiveProperties(
            endpoint=OFFLINE_FIXTURE_ENDPOINT,
            in_recovery=False,
            server_version="offline-fixture",
            ledger_rows=rows,
            terminal_migration=terminal or "",
            ledger_attestation=_clone_ledger_attestation(clone),
            schema_fingerprint=str(fingerprint["fingerprint"]),
            schema_records=dict(fingerprint["records"]),
            table_counts=clone_counts(clone),
            rejected_checks=tuple(name for name, verdict in vector.items() if verdict == "reject"),
            event_kinds={},
            link_subject_kinds={},
            blockers=(),
        )


def _verdict(live: LiveProperties, results: list[RehearsalResult]) -> int:
    failed = [r.name for r in results if not r.passed and not r.blocked]
    if failed:
        print(
            f"VERDICT: REHEARSAL FAILED ({', '.join(failed)}) — "
            "do NOT open a freeze or attempt live."
        )
        return EXIT_REHEARSAL_FAIL
    if live.blockers or any(r.blocked for r in results):
        codes = ", ".join(code for code, _ in live.blockers)
        print(
            "VERDICT: the target ref is PROVEN on a clone that carries history, but the LIVE box "
            f"is blocked by: {codes} — clear that before opening a freeze."
        )
        return EXIT_LIVE_BLOCKED
    print(
        "VERDICT: PASS — the pending set applies on a clone that carries history. "
        "Freeze is earned."
    )
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(run_upgrade_rehearsal(_rehearsal_parser().parse_args()))

from tools.development_runtime._rehearsal_bridge import kernel_worker as _kernel_worker  # noqa: E402
