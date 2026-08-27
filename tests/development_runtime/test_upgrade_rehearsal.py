"""Upgrade rehearsal as a first-class release-helper step (T-CTW-040).

Proves the ported rehearsal gate end to end on disposable clusters: the verb is wired into the
release helper's own entrypoint, the read-only live guard refuses everything that is not a plain
SELECT, the refusal classification names preconditions exactly, the kernel bridge never leaks the
live DSN into argv, and the full clone → fixture history → pending-set apply → verdict path answers
on this repository's own HEAD. The mission-control tool stays until AC-2's real-freeze cutover.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import tools.development_runtime.rehearsal as rehearsal  # noqa: PLR0402
from tools.development_runtime import interface as runtime_interface
from tools.development_runtime.host_commands import docker_path

__all__: tuple[str, ...] = ()

_REPO_ROOT = Path(__file__).resolve().parents[2]


class _FakeCursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows


class _FakeConnection:
    """The only surface ``live_read`` is allowed to touch: execute → fetchall."""

    def __init__(self, rows: list[tuple[object, ...]] | None = None) -> None:
        self.executed: list[str] = []
        self._rows = rows or [("ignored",)]

    def execute(self, statement: str, parameters: tuple[object, ...] = ()) -> _FakeCursor:
        self.executed.append(statement)
        return _FakeCursor(self._rows)


class TestEntrypointWiring:
    def test_the_rehearsal_verb_is_dispatched_by_the_release_helper_parser(self) -> None:
        """Severing the registration in interface.py must turn this RED (L6-B2 lesson)."""

        dispatched = runtime_interface._parser().parse_args(
            ["upgrade-rehearsal", "--scenario", "as-of-attempt"]
        )
        assert dispatched.command == "upgrade-rehearsal"

    def test_module_entrypoint_answers_help_for_the_rehearsal_verb(self) -> None:
        """`python -m tools.development_runtime upgrade-rehearsal --help` is the operator door."""

        finished = subprocess.run(
            [sys.executable, "-m", "tools.development_runtime", "upgrade-rehearsal", "--help"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=_REPO_ROOT,
            check=False,
        )
        assert finished.returncode == 0, finished.stderr
        for expected in ("--target-ref", "--target-source", "--base-ref", "--scenario", "--offline-fixture"):
            assert expected in finished.stdout


class TestLiveReadOnlyGuard:
    def test_select_shaped_statements_reach_the_connection(self) -> None:
        connection = _FakeConnection()
        assert rehearsal.live_read(connection, "SELECT count(*) FROM events") == [("ignored",)]
        assert (
            rehearsal.live_read(connection, "  WITH total AS (SELECT 1) SELECT * FROM total")
            == [("ignored",)]
        )

    def test_non_select_heads_are_refused_by_name(self) -> None:
        connection = _FakeConnection()
        with pytest.raises(rehearsal.UpgradeRehearsalError, match="non-read"):
            rehearsal.live_read(connection, "INSERT INTO events VALUES (1)")
        with pytest.raises(rehearsal.UpgradeRehearsalError, match="non-read"):
            rehearsal.live_read(connection, "update events SET kind = 'x'")

    def test_write_verbs_hidden_after_a_select_are_refused(self) -> None:
        connection = _FakeConnection()
        for statement in (
            "SELECT * FROM events; DROP TABLE events",
            "WITH deleted AS (DELETE FROM events RETURNING 1) SELECT * FROM deleted",
            "SELECT 1 WHERE 1 = 1; TRUNCATE events",
        ):
            with pytest.raises(rehearsal.UpgradeRehearsalError, match="carrying"):
                rehearsal.live_read(connection, statement)

    def test_string_literals_cannot_smuggle_or_hide_write_verbs(self) -> None:
        connection = _FakeConnection()
        # A quoted literal containing a forbidden word must NOT trip the guard...
        assert rehearsal.live_read(connection, "SELECT 'insert into foo' AS note") == [("ignored",)]
        # ...but literals cannot hide a real trailing write.
        with pytest.raises(rehearsal.UpgradeRehearsalError, match="carrying"):
            rehearsal.live_read(connection, "SELECT 'x'; ALTER TABLE events ADD COLUMN s text")

    def test_session_state_functions_are_refused(self) -> None:
        """The mission-control guard missed this: `\\bSET\\b` cannot match `set_config`."""

        connection = _FakeConnection()
        with pytest.raises(rehearsal.UpgradeRehearsalError, match="carrying"):
            rehearsal.live_read(
                connection, "SELECT set_config('default_transaction_read_only', 'off', true)"
            )
        with pytest.raises(rehearsal.UpgradeRehearsalError, match="carrying"):
            rehearsal.live_read(connection, "SELECT pg_terminate_backend(1)")


class TestRefusalClassification:
    def test_semantic_refusal_names_the_first_precondition(self) -> None:
        result = rehearsal.RehearsalResult(name="as-of-attempt")
        rehearsal._record_outcome(
            result,
            {"ok": False, "code": "advance-precondition-mismatch",
             "detail": "record-position-history-unprovable, more detail"},
        )
        assert result.first_failing_precondition == "record-position-history-unprovable"
        assert not result.passed

    def test_typed_refusal_falls_back_to_its_code(self) -> None:
        result = rehearsal.RehearsalResult(name="as-of-attempt")
        rehearsal._record_outcome(
            result,
            {"ok": False, "code": "ledger-schema-mismatch",
             "detail": "attested=a live_canonical=b live_superseded_raw=c"},
        )
        assert result.first_failing_precondition == "ledger-schema-mismatch"

    def test_success_records_the_applied_seconds(self) -> None:
        result = rehearsal.RehearsalResult(name="as-of-attempt")
        rehearsal._record_outcome(result, {"ok": True, "seconds": 4.5})
        assert result.passed
        assert "4.5" in result.reason

    def test_drifted_refusal_requires_all_three_digest_names(self) -> None:
        shaped = rehearsal.RehearsalResult(name="drifted-history-refuses")
        rehearsal._record_drifted_refusal(
            shaped,
            {"ok": False, "code": "ledger-schema-mismatch",
             "detail": "attested=a live_canonical=b live_superseded_raw=c"},
        )
        assert shaped.passed

        missing_name = rehearsal.RehearsalResult(name="drifted-history-refuses")
        rehearsal._record_drifted_refusal(
            missing_name,
            {"ok": False, "code": "ledger-schema-mismatch", "detail": "attested=a live_canonical=b"},
        )
        assert not missing_name.passed
        assert "live_superseded_raw" in missing_name.reason

        upgraded = rehearsal.RehearsalResult(name="drifted-history-refuses")
        rehearsal._record_drifted_refusal(upgraded, {"ok": True, "seconds": 1.0})
        assert not upgraded.passed
        assert "UPGRADED" in upgraded.reason


class TestVerdict:
    def test_exit_codes_preserve_the_gate_contract(self) -> None:
        healthy_live = SimpleNamespace(blockers=())
        passed = [rehearsal.RehearsalResult(name="s", passed=True)]
        assert rehearsal._verdict(healthy_live, passed) == 0
        failed = [rehearsal.RehearsalResult(name="s", passed=False, blocked=False)]
        assert rehearsal._verdict(healthy_live, failed) == 2
        blocked_live = SimpleNamespace(blockers=(("ledger-schema-mismatch", "detail"),))
        assert rehearsal._verdict(blocked_live, passed) == 3
        blocked_scenario = [rehearsal.RehearsalResult(name="s", passed=False, blocked=True)]
        assert rehearsal._verdict(healthy_live, blocked_scenario) == 3


class TestKernelBridge:
    def test_the_live_dsn_travels_through_the_environment_only(self) -> None:
        captured: list[tuple[list[str], dict[str, str]]] = []

        def fake_run(arguments, *, timeout, capture_output, text, env, check, cwd):  # noqa: ANN001
            captured.append((list(arguments), dict(env)))
            return SimpleNamespace(returncode=0, stdout=json.dumps({"ok": True}) + "\n", stderr="")

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(rehearsal.subprocess, "run", fake_run)
        try:
            rehearsal.kernel_call(
                Path("/tmp/source"),
                "install",
                live_dsn="postgresql://secret-user:secret-password@127.0.0.1:55432/ctower",
                admin_dsn="postgresql://postgres@127.0.0.1:1/ctower",
                migrator_dsn="postgresql://ctower_migrator@127.0.0.1:1/ctower",
            )
        finally:
            monkeypatch.undo()

        argv, environment = captured[0]
        assert all("secret-password" not in part for part in argv)
        assert environment[rehearsal.LIVE_DSN_ENVIRON].startswith("postgresql://secret-user")


class TestRehearsalArguments:
    def test_offline_fixture_mode_requires_a_base_ref(self) -> None:
        with pytest.raises(rehearsal.UpgradeRehearsalError, match="base-ref"):
            rehearsal.parse_rehearsal_arguments(["--offline-fixture"])

    def test_offline_fixture_arguments_round_trip(self) -> None:
        arguments = rehearsal.parse_rehearsal_arguments(
            ["--offline-fixture", "--base-ref", "HEAD", "--target-ref", "HEAD"]
        )
        assert arguments.offline_fixture
        assert arguments.base_ref == "HEAD"


@pytest.mark.skipif(not Path(docker_path()).exists(), reason="docker is required")
class TestOfflineRehearsalEndToEnd:
    def test_head_to_head_rehearsal_passes_and_drift_refuses(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty pending set on this repository's HEAD must PASS; injected drift must REFUSE."""

        def explode() -> tuple[str, str]:
            raise AssertionError("offline fixture mode must never resolve the live DSN")

        monkeypatch.setattr(rehearsal, "resolve_live_dsn", explode)
        evidence = tmp_path / "rehearsal.json"

        code = rehearsal.run_upgrade_rehearsal(
            rehearsal.parse_rehearsal_arguments(
                [
                    "--offline-fixture",
                    "--target-source", str(_REPO_ROOT),
                    "--base-ref", "HEAD",
                    "--scenario", "as-of-attempt",
                    "--json", str(evidence),
                ]
            )
        )
        assert code == 0
        payload = json.loads(evidence.read_text(encoding="utf-8"))
        assert payload["schema"] == "ctower.upgrade-rehearsal/v1"
        assert payload["scenarios"][0]["passed"] is True

        drifted = rehearsal.run_upgrade_rehearsal(
            rehearsal.parse_rehearsal_arguments(
                [
                    "--offline-fixture",
                    "--target-source", str(_REPO_ROOT),
                    "--base-ref", "HEAD",
                    "--scenario", "drifted-history-refuses",
                ]
            )
        )
        assert drifted == 0, "the drifted negative scenario PASSES exactly when the refusal has teeth"
