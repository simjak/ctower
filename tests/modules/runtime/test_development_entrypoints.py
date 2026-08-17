"""Development-runtime configuration and same-artifact entrypoint boundaries."""

from __future__ import annotations

import hashlib
import importlib
import signal
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from typing import Self, cast
from uuid import uuid4

import pytest
import uvicorn
from ctower_contracts import CATALOG

from ctower_api import (
    development_config as config_module,
)
from ctower_api import (
    development_finalizer as finalizer_module,
)
from ctower_api import (
    development_runtime as runtime_module,
)
from ctower_api import (
    development_secrets as secrets_module,
)
from ctower_api.development_config import DevelopmentConfig, DevelopmentState
from ctower_kernel.proof import ProofPolicy
from ctower_kernel.record import DurabilityFinalizationBatch
from ctower_kernel.runtime import RoutineRevision
from ctower_kernel.workflow import WorkflowGraph

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
REFERENCE = "secret-service:ctower-development/runtime"
OWNER_MODE = 0o600
EXPECTED_ROLE_COUNT = 4
FINALIZER_ATTEMPTS = 2
SIGNAL_COUNT = 2
MAX_PUBLIC_EXPORTS = 15


class Keyring:
    """Allowlisted in-memory shape used only at the adapter selection seam."""

    priority = 5.0

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


Keyring.__module__ = "keyring.backends.SecretService"


class _RuntimeClient:
    def __init__(self, base_url: str, *, credential: str) -> None:
        self.base_url = base_url
        self.credential = credential
        self.entered = False

    def __enter__(self) -> Self:
        self.entered = True
        return self

    def __exit__(self, *_args: object) -> None:
        self.entered = False


class _RuntimeWorker:
    def __init__(self, observed: dict[str, object]) -> None:
        self.observed = observed

    def run(self, stop: object) -> None:
        self.observed["stop"] = stop


def _config_payload() -> dict[str, object]:
    return {
        "schema": "ctower.development-runtime/v1",
        "label": "SHADOW_ONLY_CP3_D_NOT_PROVEN",
        "api_host": "127.0.0.1",
        "api_port": 8091,
        "database_host": "127.0.0.1",
        "database_name": "ctower",
        "primary_port": 55432,
        "standby_port": 55433,
        "postgres_image": "postgres@sha256:" + "a" * 64,
        "postgres_admin_secret_ref": "secret-service:ctower-development/postgres-admin",
        "migrator_secret_ref": "secret-service:ctower-development/migrator",
        "runtime_secret_ref": REFERENCE,
        "projection_secret_ref": "secret-service:ctower-development/projection",
        "operator_secret_ref": "secret-service:ctower-development/operator",
        "commander_secret_ref": "secret-service:ctower-development/commander",
    }


def _config() -> DevelopmentConfig:
    return DevelopmentConfig.model_validate(_config_payload())


def test_development_runtime_concerns_have_small_non_passthrough_interfaces() -> None:
    moved_names = {
        "DevelopmentFinalizerProgress",
        "development_dsn",
        "load_secret",
        "observe_finalizer_health",
    }

    assert len(config_module.__all__) <= MAX_PUBLIC_EXPORTS
    assert len(finalizer_module.__all__) <= MAX_PUBLIC_EXPORTS
    assert len(secrets_module.__all__) <= MAX_PUBLIC_EXPORTS
    assert moved_names.isdisjoint(config_module.__all__)


def test_config_state_owner_only_round_trip_and_strict_validation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    development_config = _config()
    development_state = DevelopmentState.model_validate(
        {
            "schema": "ctower.development-state/v1",
            "tenant_id": uuid4(),
            "operator_id": uuid4(),
            "commander_id": uuid4(),
        }
    )

    config_module.write_config(development_config)
    config_module.write_state(development_state)

    assert config_module.load_config() == development_config
    assert config_module.load_state() == development_state
    assert config_module.config_path().stat().st_mode & 0o777 == OWNER_MODE
    assert config_module.state_path().stat().st_mode & 0o777 == OWNER_MODE
    invalid_reference = {**_config_payload(), "runtime_secret_ref": "literal-secret"}
    invalid_image = {**_config_payload(), "postgres_image": "postgres:17"}
    with pytest.raises(ValueError, match="Secret Service"):
        DevelopmentConfig.model_validate(invalid_reference)
    with pytest.raises(ValueError, match="immutable digest"):
        DevelopmentConfig.model_validate(invalid_image)


def test_dsn_resolves_only_supported_keyring_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    development_config = _config()
    observed: list[str] = []

    def load(reference: str) -> str:
        observed.append(reference)
        return "slash/value ?"

    monkeypatch.setattr(secrets_module, "load_secret", load)
    for role in (
        "postgres",
        "ctower_migrator",
        "ctower_runtime",
        "ctower_projection_runtime",
    ):
        dsn = secrets_module.development_dsn(
            development_config,
            role,
            standby=role == "postgres",
        )
        assert "slash%2Fvalue%20%3F" in dsn
    assert len(observed) == EXPECTED_ROLE_COUNT
    assert ":55433/" in secrets_module.development_dsn(
        development_config,
        "postgres",
        standby=True,
    )
    with pytest.raises(ValueError, match="unsupported"):
        secrets_module.development_dsn(development_config, "unknown")


def test_keyring_adapter_persists_exact_values_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = Keyring()
    monkeypatch.setattr(secrets_module, "_secure_backend", lambda: backend)

    secrets_module.put_secret(REFERENCE, "current-value")

    assert secrets_module.load_secret(REFERENCE) == "current-value"
    with pytest.raises(ValueError, match="invalid"):
        secrets_module.put_secret("bad-ref", "value")
    with pytest.raises(ValueError, match="invalid"):
        secrets_module.put_secret(REFERENCE, "")
    with pytest.raises(ValueError, match="invalid"):
        secrets_module.load_secret("bad-ref")
    with pytest.raises(RuntimeError, match="missing reference"):
        secrets_module.load_secret("secret-service:ctower-development/missing")

    monkeypatch.setattr(backend, "set_password", lambda *_args: None)
    with pytest.raises(RuntimeError, match="did not persist"):
        secrets_module.put_secret(REFERENCE, "different")
    monkeypatch.setattr(backend, "get_password", lambda *_args: (_ for _ in ()).throw(OSError()))
    with pytest.raises(RuntimeError, match="refused"):
        secrets_module.put_secret(REFERENCE, "different")
    with pytest.raises(RuntimeError, match="unavailable"):
        secrets_module.load_secret(REFERENCE)


def test_keyring_backend_identity_and_unlock_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = Keyring()
    keyring_module = SimpleNamespace(get_keyring=lambda: backend)
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: keyring_module if name == "keyring" else None,
    )
    assert secrets_module._secure_backend() is backend

    backend.priority = 0.0
    with pytest.raises(RuntimeError, match="not allowlisted"):
        secrets_module._secure_backend()
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda _name: (_ for _ in ()).throw(ImportError()),
    )
    with pytest.raises(RuntimeError, match="allowlisted"):
        secrets_module._secure_backend()

    calls: list[tuple[object, ...]] = []
    service = SimpleNamespace(call=lambda *args: calls.append(args))
    util = SimpleNamespace(
        open_session=lambda connection: ("session", connection),
        DBusAddressWrapper=lambda *_args: service,
        format_secret=lambda session, value, content_type: (session, value, content_type),
    )
    modules = {
        "secretstorage": SimpleNamespace(dbus_init=lambda: "connection"),
        "secretstorage.defines": SimpleNamespace(SS_PATH="/service"),
        "secretstorage.util": util,
    }
    monkeypatch.setattr(importlib, "import_module", lambda name: modules[name])
    monkeypatch.setattr(secrets_module, "load_secret", lambda reference: reference)

    secrets_module.unlock_development_keyring()

    assert calls[0][0] == "UnlockWithMasterPassword"
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda _name: (_ for _ in ()).throw(ImportError()),
    )
    with pytest.raises(RuntimeError, match="passwordless"):
        secrets_module.unlock_development_keyring()


def test_config_home_defaults_to_owner_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    assert config_module.config_path() == Path.home() / ".config/ctower/development-runtime.json"
    assert (
        config_module.state_path()
        == Path.home() / ".local/state/ctower/development-runtime-state.json"
    )


def test_stalled_finalizer_progress_is_observably_degraded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    observe_health = finalizer_module.observe_finalizer_health
    write_progress = finalizer_module.write_finalizer_progress
    progress_type = finalizer_module.DevelopmentFinalizerProgress
    assert observe_health is not None
    assert write_progress is not None
    assert progress_type is not None
    now = datetime(2026, 7, 28, 17, 40, tzinfo=UTC)
    write_progress(
        progress_type.model_validate(
            {
                "schema": "ctower.development-finalizer-progress/v1",
                "sequence": 7,
                "observed_at": now - timedelta(seconds=11),
                "scan_status": "completed",
                "attempted": 0,
                "accepted": 0,
                "pending": 0,
                "refused": 0,
                "detail_code": None,
            }
        )
    )

    health = observe_health("active", now=now)

    assert health.status == "DEGRADED"
    assert health.reason == "progress_stalled"


def test_refusing_finalizer_progress_is_observably_degraded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    observe_health = finalizer_module.observe_finalizer_health
    write_progress = finalizer_module.write_finalizer_progress
    progress_type = finalizer_module.DevelopmentFinalizerProgress
    assert observe_health is not None
    assert write_progress is not None
    assert progress_type is not None
    now = datetime(2026, 7, 28, 17, 40, tzinfo=UTC)
    write_progress(
        progress_type.model_validate(
            {
                "schema": "ctower.development-finalizer-progress/v1",
                "sequence": 8,
                "observed_at": now,
                "scan_status": "completed",
                "attempted": 1,
                "accepted": 0,
                "pending": 0,
                "refused": 1,
                "detail_code": None,
            }
        )
    )

    health = observe_health("active", now=now)

    assert health.status == "DEGRADED"
    assert health.reason == "finalizer_refused"


def test_finalizer_health_fails_closed_and_requires_current_completed_progress(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    now = datetime(2026, 7, 28, 17, 40, tzinfo=UTC)

    unknown = finalizer_module.observe_finalizer_health("active", now=now)
    assert (unknown.status, unknown.reason) == ("DEGRADED", "progress_unknown")
    progress = finalizer_module.DevelopmentFinalizerProgress(
        schema="ctower.development-finalizer-progress/v1",
        sequence=1,
        observed_at=now,
        scan_status="completed",
        attempted=0,
        accepted=0,
        pending=0,
        refused=0,
        detail_code=None,
    )
    finalizer_module.write_finalizer_progress(progress)
    healthy = finalizer_module.observe_finalizer_health("active", now=now)
    assert (healthy.status, healthy.reason, healthy.sequence) == (
        "HEALTHY",
        "progress_observed",
        1,
    )
    inactive = finalizer_module.observe_finalizer_health("activating", now=now)
    assert (inactive.status, inactive.reason) == ("DEGRADED", "worker_inactive")
    finalizer_module.write_finalizer_progress(
        progress.model_copy(
            update={"sequence": 2, "scan_status": "failed", "detail_code": "finalizer-exception"}
        )
    )
    failed = finalizer_module.observe_finalizer_health("active", now=now)
    assert (failed.status, failed.reason) == ("DEGRADED", "finalizer_failed")


def test_development_finalizer_progress_recorder_is_monotonic_and_typed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written: list[finalizer_module.DevelopmentFinalizerProgress] = []
    monkeypatch.setattr(
        runtime_module,
        "load_finalizer_progress",
        lambda: (_ for _ in ()).throw(FileNotFoundError()),
    )
    monkeypatch.setattr(runtime_module, "write_finalizer_progress", written.append)
    recorder = runtime_module._DevelopmentFinalizerProgressRecorder.from_persisted_state()

    recorder.completed(DurabilityFinalizationBatch(2, 1, 1, 0))
    recorder.failed()

    assert [(item.sequence, item.scan_status) for item in written] == [
        (1, "completed"),
        (2, "failed"),
    ]
    assert written[0].attempted == FINALIZER_ATTEMPTS
    assert written[1].detail_code == "finalizer-exception"


def _read_side_stub(runtime_dsn: str, projection_dsn: str) -> SimpleNamespace:
    """Stand in for the read-side composition the entry point delegates to."""

    return SimpleNamespace(
        projections=f"Projections:{runtime_dsn}:{projection_dsn}",
        attention="Attention",
        board_context="BoardContext",
        inbox="Inbox",
        knowledge="Knowledge",
        pools="Pools",
    )


def test_development_api_composes_only_typed_same_artifact_adapters(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    observed: dict[str, object] = {}
    development_config = _config()
    monkeypatch.setattr(runtime_module, "load_config", lambda: development_config)
    monkeypatch.setattr(
        runtime_module,
        "development_dsn",
        lambda _config, role, *, standby=False: f"{role}:{standby}",
    )
    monkeypatch.setattr(runtime_module, "_pack_root", lambda: tmp_path)
    monkeypatch.setattr(runtime_module, "_proof_policy", lambda _packs: "proof-policy")
    monkeypatch.setattr(runtime_module, "_workflow_graph", lambda _packs: "workflow-graph")
    monkeypatch.setattr(runtime_module, "_policy_digests", lambda _packs: {"policy": "digest"})
    monkeypatch.setattr(runtime_module, "_synthetic_revision", lambda _items: "revision")
    monkeypatch.setattr(runtime_module, "load_routine_revisions", lambda _packs: ("raw",))
    for name in (
        "PostgresRecord",
        "PostgresProof",
        "PostgresWorkflowPolicyPins",
        "PostgresWork",
        "PostgresWorkflow",
        "PostgresRuntime",
        "PostgresCatalog",
        "PostgresProjections",
        "Proof",
        "Workflow",
        "Work",
        "Projections",
        "FixedOperations",
    ):
        monkeypatch.setattr(
            runtime_module,
            name,
            lambda *args, _name=name, **kwargs: (_name, args, kwargs),
        )
    monkeypatch.setattr(
        runtime_module,
        "create_app",
        lambda *args, **kwargs: observed.update(app=(args, kwargs)) or "app",
    )
    monkeypatch.setattr(runtime_module, "development_catalog_store", lambda: "catalog-store")
    monkeypatch.setattr(runtime_module, "read_side_modules", _read_side_stub)
    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda app, **kwargs: observed.update(server=(app, kwargs)),
    )

    runtime_module.api_main()

    server = cast(tuple[object, dict[str, object]], observed["server"])
    assert server[0] == "app"
    assert server[1] == {
        "host": "127.0.0.1",
        "port": 8091,
        "log_level": "info",
        "access_log": False,
    }
    app = cast(tuple[object, dict[str, object]], observed["app"])
    assert app[1]["catalog"] == (
        "PostgresCatalog",
        ("ctower_runtime:False", CATALOG, "catalog-store"),
        {"key_reference": "vault:development-catalog-key"},
    )


def test_development_worker_composes_finalizer_and_stops_by_signal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    observed: dict[str, object] = {}
    development_config = _config()
    development_state = SimpleNamespace(commander_id=uuid4())
    monkeypatch.setattr(runtime_module, "load_config", lambda: development_config)
    monkeypatch.setattr(runtime_module, "load_state", lambda: development_state)
    monkeypatch.setattr(
        runtime_module,
        "development_dsn",
        lambda _config, role, *, standby=False: f"{role}:{standby}",
    )
    monkeypatch.setattr(runtime_module, "load_secret", lambda reference: f"value:{reference}")
    monkeypatch.setattr(runtime_module, "_pack_root", lambda: tmp_path)
    monkeypatch.setattr(
        runtime_module,
        "_workflow_graph",
        lambda _packs: SimpleNamespace(digest="sha256:" + "a" * 64),
    )
    monkeypatch.setattr(runtime_module, "_digest", lambda path: f"digest:{path.name}")
    monkeypatch.setattr(runtime_module, "CtowerClient", _RuntimeClient)
    for name in (
        "PostgresRuntime",
        "Routine",
        "PostgresProjections",
        "Projections",
        "FixedOperations",
        "SyntheticFourStageHandler",
        "PostgresDurabilityFinalizer",
    ):
        monkeypatch.setattr(
            runtime_module,
            name,
            lambda *args, _name=name, **kwargs: (_name, args, kwargs),
        )
    monkeypatch.setattr(
        runtime_module,
        "build_worker",
        lambda *args, **kwargs: observed.update(worker=(args, kwargs)) or _RuntimeWorker(observed),
    )
    handlers: list[object] = []
    monkeypatch.setattr(signal, "signal", lambda _kind, handler: handlers.append(handler))

    runtime_module.worker_main()

    stop = observed["stop"]
    assert isinstance(stop, Event)
    assert len(handlers) == SIGNAL_COUNT
    handlers[0](None, None)  # type: ignore[operator]
    assert stop.is_set()
    worker = cast(tuple[object, dict[str, object]], observed["worker"])
    assert "durability_finalizer" in worker[1]
    assert "durability_progress" in worker[1]


def test_pack_policy_digest_and_exact_revision_helpers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prefix = tmp_path / "venv"
    installed_packs = tmp_path / "packs"
    installed_packs.mkdir()
    monkeypatch.setattr(sys, "prefix", str(prefix))
    assert runtime_module._pack_root() == installed_packs
    installed_packs.rmdir()
    assert runtime_module._pack_root() == ROOT / "packs"

    gate = tmp_path / runtime_module._GATE
    evidence = tmp_path / runtime_module._EVIDENCE
    execution = tmp_path / runtime_module._EXECUTION
    workflow = tmp_path / runtime_module._WORKFLOW
    for path, content in (
        (gate, b"gate"),
        (evidence, b"evidence"),
        (execution, b"execution"),
        (workflow, b'{"schema":"test"}'),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    monkeypatch.setattr(
        ProofPolicy,
        "from_bytes",
        lambda gate_bytes, evidence_bytes: (gate_bytes, evidence_bytes),
    )
    monkeypatch.setattr(WorkflowGraph, "from_mapping", lambda payload: payload)

    assert cast(object, runtime_module._proof_policy(tmp_path)) == (b"gate", b"evidence")
    assert cast(object, runtime_module._workflow_graph(tmp_path)) == {"schema": "test"}
    assert runtime_module._digest(gate) == "sha256:" + hashlib.sha256(b"gate").hexdigest()
    assert set(runtime_module._policy_digests(tmp_path)) == {
        "ctower.trust-spine-four-stage.execution@1",
        "ctower.trust-spine-four-stage.gates@1",
        "ctower.trust-spine-four-stage.evidence@1",
    }
    workflow.write_text("[]", encoding="utf-8")
    with pytest.raises(TypeError, match="must be an object"):
        runtime_module._workflow_graph(tmp_path)

    matching = cast(
        RoutineRevision,
        SimpleNamespace(routine_ref="ctower.i1.synthetic-four-stage@1"),
    )
    other = cast(RoutineRevision, SimpleNamespace(routine_ref="other"))
    assert runtime_module._synthetic_revision((other, matching)) is matching
    with pytest.raises(ValueError, match="exact synthetic"):
        runtime_module._synthetic_revision((other,))
    with pytest.raises(ValueError, match="exact synthetic"):
        runtime_module._synthetic_revision((matching, matching))
