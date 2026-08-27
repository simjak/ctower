"""Shared vocabulary for the upgrade rehearsal (T-CTW-040).

Ported from mission-control's ``tools/ctower-upgrade-rehearsal`` (the source of truth until
AC-2's real-freeze cutover deletes it). Every ref-specific kernel operation runs inside a
subprocess bound to that ref's own source tree, so the target ref's kernel judges the base
ref's world and a pending-set definition cannot validate itself.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = [
    "CHECKPOINT_ARTIFACT_NAME",
    "CHECKPOINT_RESTORE_TIMEOUT_SECONDS",
    "COMPOSE_PROJECT_PREFIX",
    "COMPOSE_RELATIVE",
    "DATABASE_NAME",
    "EXIT_LIVE_BLOCKED",
    "EXIT_NO_CLAIM",
    "EXIT_PASS",
    "EXIT_REHEARSAL_FAIL",
    "FIXTURE_PROJECTS",
    "FIXTURE_ROUTINE_EVENTS",
    "FIXTURE_TICKETS",
    "KERNEL_CALL_TIMEOUT_SECONDS",
    "KERNEL_SOURCE_RELATIVE",
    "LIVE_DSN_ENVIRON",
    "LIVE_DSN_SENTINEL",
    "LIVE_READ_PREFIXES",
    "LIVE_FORBIDDEN",
    "MANIFEST_RELATIVE",
    "OFFLINE_FIXTURE_ENDPOINT",
    "REPARSED_CONSTRAINT",
    "REPARSED_TABLE",
    "REQUIRED_DRIFT_DIGEST_NAMES",
    "REPO_ROOT",
    "SCENARIO_NAMES",
    "UpgradeRehearsalError",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
KERNEL_SOURCE_RELATIVE = Path("packages/ctower-kernel/src")
COMPOSE_RELATIVE = Path("deploy/development/compose.yaml")
MANIFEST_RELATIVE = Path("packages/ctower-kernel/migrations/manifest.json")
CHECKPOINT_ARTIFACT_NAME = "database.sql.gpg"
CHECKPOINT_RESTORE_TIMEOUT_SECONDS = 900.0
KERNEL_CALL_TIMEOUT_SECONDS = 900.0
COMPOSE_PROJECT_PREFIX = "ctower-rehearsal-"
DATABASE_NAME = "ctower"
LIVE_DSN_SENTINEL = "live"
LIVE_DSN_ENVIRON = "CTOWER_REHEARSAL_LIVE_DSN"
OFFLINE_FIXTURE_ENDPOINT = "offline-fixture"
FIXTURE_PROJECTS = ("ctower", "manibo", "bh-loop")
FIXTURE_TICKETS = 20
FIXTURE_ROUTINE_EVENTS = 128
REPARSED_TABLE = "project_delivery_checkpoint_definitions"
REPARSED_CONSTRAINT = "project_delivery_checkpoint_definitions_applicable_states_check"
BASE_REF_SEARCH_DEPTH = 40
EXIT_PASS, EXIT_REHEARSAL_FAIL, EXIT_LIVE_BLOCKED, EXIT_NO_CLAIM = 0, 2, 3, 4
SCENARIO_NAMES = (
    "as-of-attempt",
    "as-live-now",
    "deparse-variance",
    "drifted-history-refuses",
)
REQUIRED_DRIFT_DIGEST_NAMES = ("attested=", "live_canonical=", "live_superseded_raw=")

# A live statement may only read. Enforced in one place so the "never writes to live" claim is
# checkable by reading one function rather than auditing every call site.
LIVE_READ_PREFIXES = ("SELECT", "WITH")
LIVE_FORBIDDEN = re.compile(
    r"(?:\b|\w_)(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|ALTER|DROP|CREATE|GRANT|REVOKE|COPY"
    r"|SET|CALL|DO|pg_terminate_backend|pg_cancel_backend|set_config|pg_reload_conf"
    r"|pg_terminate|lo_import|lo_export|dblink|pg_read_file|pg_read_binary_file)\b",
    re.IGNORECASE,
)


class UpgradeRehearsalError(RuntimeError):
    """The harness cannot make a claim; every message names what it could not prove."""
