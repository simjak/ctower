"""RED-first authored boundary inventory for Console Phase 1."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from ruamel.yaml import YAML

ROOT = Path(__file__).parents[3]


def _openapi() -> dict[str, object]:
    return cast(
        dict[str, object],
        YAML(typ="safe").load((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8")),
    )


def test_authored_console_contracts_are_strict_and_cover_grant_allowlist_and_stream() -> None:
    contract_dir = ROOT / "contracts/domain/console"
    expected = {
        "console-session-allow.schema.json",
        "console-view-grant.schema.json",
        "console-stream-event.schema.json",
        "phase1-verification.json",
    }
    assert {path.name for path in contract_dir.glob("*.json")} == expected
    for name in expected - {"phase1-verification.json"}:
        schema = json.loads((contract_dir / name).read_text(encoding="utf-8"))
        if "oneOf" in schema:
            assert all(item["additionalProperties"] is False for item in schema["oneOf"])
        else:
            assert schema["additionalProperties"] is False


def test_browser_stream_url_contains_no_grant_capability_or_cursor_credential() -> None:
    paths = cast(dict[str, object], _openapi()["paths"])
    assert "/v1/console/sessions/{console_session_id}/grants" in paths
    assert "/v1/console/sessions/{console_session_id}/renewals" in paths
    stream_path = "/v1/console/sessions/{console_session_id}/events"
    assert stream_path in paths
    assert all(word not in stream_path for word in ("grant", "capability", "cursor", "token"))


def test_stream_contract_names_exact_sse_security_and_bounded_close_events() -> None:
    schema = json.loads(
        (ROOT / "contracts/domain/console/console-stream-event.schema.json").read_text(
            encoding="utf-8"
        )
    )
    variants = schema["oneOf"]
    event_types = {variant["properties"]["type"]["const"] for variant in variants}
    assert event_types == {"chunk", "gap", "closed"}
    closed = next(item for item in variants if item["properties"]["type"]["const"] == "closed")
    gap = next(item for item in variants if item["properties"]["type"]["const"] == "gap")
    assert gap["properties"]["next_cursor"]["minimum"] == 1
    assert "rate_limited" in gap["properties"]["reason"]["enum"]
    assert set(closed["properties"]["code"]["enum"]) >= {
        "expired",
        "revoked",
        "fenced",
        "rate_limited",
        "slow_consumer",
    }


def test_console_migration_names_append_only_facts_and_output_reader_role() -> None:
    migration = (ROOT / "packages/ctower-kernel/migrations/0065_console_view_grants.sql").read_text(
        encoding="utf-8"
    )
    for table in (
        "console_session_allows",
        "console_session_revocations",
        "console_view_grants",
        "console_view_grant_revocations",
        "console_stream_opens",
        "console_stream_closes",
        "console_output_objects",
        "console_output_access_facts",
        "console_output_recovery_facts",
        "console_global_kill_switch_facts",
        "console_view_suspensions",
    ):
        assert f"CREATE TABLE {table}" in migration
    assert "console_output_reader" in migration
    assert "refuse_immutable_control_fact_mutation" in migration


def test_output_reader_role_adoption_refuses_every_unsafe_preexisting_shape() -> None:
    migration = (
        ROOT / "packages/ctower-kernel/migrations/0064_console_output_reader_role.sql"
    ).read_text(encoding="utf-8")
    for catalog_fact in (
        "rolcanlogin",
        "rolsuper",
        "rolcreatedb",
        "rolcreaterole",
        "rolinherit",
        "rolreplication",
        "rolbypassrls",
        "rolconnlimit",
        "rolpassword",
        "rolvaliduntil",
        "pg_auth_members",
        "pg_db_role_setting",
        "pg_shdepend",
    ):
        assert catalog_fact in migration
    assert "dependency.deptype = 'o'" in migration
    assert "dependency.deptype = 'a'" in migration
    assert "has_schema_privilege(reader_role, 'public', 'CREATE')" in migration
    assert "GRANT USAGE, CREATE" not in migration
    assert "GRANT CREATE ON SCHEMA" not in migration
    assert "unsafe pre-existing console_output_reader role" in migration

    database_migration = (
        ROOT / "packages/ctower-kernel/migrations/0065_console_view_grants.sql"
    ).read_text(encoding="utf-8")
    assert "ALTER FUNCTION recover_console_output_object(uuid, timestamptz)" in database_migration
    assert "GRANT CREATE ON SCHEMA" not in database_migration
    setup = (ROOT / "packages/ctower-kernel/src/ctower_kernel/record/_setup_sql.py").read_text(
        encoding="utf-8"
    )
    assert "_console_reader_ownership_transfer_pending" in setup
    assert "_set_console_reader_schema_create(role_admin_dsn, enabled=True)" in setup
    assert "finally:" in setup
    assert "_set_console_reader_schema_create(role_admin_dsn, enabled=False)" in setup


def test_phase1_verification_manifest_names_every_required_element_and_gate() -> None:
    manifest = json.loads(
        (ROOT / "contracts/domain/console/phase1-verification.json").read_text(encoding="utf-8")
    )
    assert manifest["schema"] == "ctower.console-phase1-verification/v1"
    assert set(manifest["elements"]) == {
        "grant-five-minute-renewable",
        "authenticated-browser-session-csrf-origin",
        "non-commander-project-allowlist",
        "current-assignment-session-join",
        "exact-tmux-project-runtime-runner-epoch-incarnation",
        "one-sse-per-grant-and-actor-session",
        "sse-no-credential-url-and-security-headers",
        "chunk-16k-delivery-1m-replay-1m-pending-256k",
        "durable-cursor-gap-before-broadcast",
        "envelope-per-object-dedicated-reader-access-facts",
        "expiry-revocation-fence-close-five-seconds",
        "per-session-and-global-kill-switch",
        "denial-suspension",
        "restricted-standard-loop-only",
        "tailnet-loopback-bind-and-ss-sweep",
        "real-private-shadow-view-proof",
    }
    assert manifest["gates"] == [
        "console-phase1-contracts",
        "console-phase1-module",
        "console-phase1-acceptance",
        "just check",
        "just verify",
    ]
