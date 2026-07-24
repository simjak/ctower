"""Fail-closed contracts for the CP3-D operator-binding packet."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Literal

import pytest

from tools.cp3d_packet.cli import main
from tools.cp3d_packet.compose import render_compose_config
from tools.cp3d_packet.interface import (
    PacketError,
    canonical_manifest,
    load_bindings,
    parse_bindings,
)
from tools.cp3d_packet.preflight import (
    FileObservation,
    PreflightError,
    validate_binding_document,
    validate_local_role,
)

__all__: list[str] = []

ROOT = Path(__file__).parents[3]
PACKET = ROOT / "deploy/private-vps/cp3d"
SYNTHETIC_BINDINGS = PACKET / "bindings.synthetic.json"
REJECTED_MATERIAL = "FORBIDDEN_INLINE_MATERIAL"
CLI_FAILURE = 2


def _raw_bindings() -> dict[str, Any]:
    value = json.loads(SYNTHETIC_BINDINGS.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_synthetic_bindings_are_strict_and_never_claim_cp3d() -> None:
    bindings = load_bindings(SYNTHETIC_BINDINGS)

    assert bindings.postgres.standby_application_name == "ctower_i1_ack"
    assert bindings.postgres.synchronous_commit == "remote_apply"
    assert bindings.runtime_policy == "pending_only"
    manifest = canonical_manifest(bindings, {"primary": {}, "standby": {}})
    decoded = json.loads(manifest)
    assert decoded["packet_state"] == "READY_FOR_OPERATOR_BINDING"
    assert decoded["cp3d_qualified"] is False
    assert decoded["external_evidence_claim"] == "not_exercised"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("postgres", "image"), "docker.io/library/postgres:17"),
        (("primary", "private_ip"), "127.0.0.1"),
        (("primary", "private_ip"), "203.0.113.10"),
        (("object_store", "versioning"), False),
        (("object_store", "object_lock"), False),
        (("object_store", "retention_days"), 0),
        (("runtime_policy",), "cutover_rpo0"),
        (("primary", "host_id"), "CP3D_REQUIRED_PRIMARY_HOST"),
    ],
)
def test_unsafe_or_unresolved_bindings_fail_closed(path: tuple[str, ...], value: object) -> None:
    raw = _raw_bindings()
    target: dict[str, Any] = raw
    for component in path[:-1]:
        nested = target[component]
        assert isinstance(nested, dict)
        target = nested
    target[path[-1]] = value

    with pytest.raises(PacketError):
        parse_bindings(raw)


def test_inline_credential_material_is_rejected_before_model_parsing() -> None:
    raw = _raw_bindings()
    raw["pass" + "word"] = REJECTED_MATERIAL

    with pytest.raises(PacketError, match="credential material"):
        parse_bindings(raw)


@pytest.mark.parametrize(
    "path",
    [
        ("primary", "tls_key"),
        ("signed_evidence", "network_tls_review"),
        ("alerting", "destination_reference"),
    ],
)
def test_required_tls_evidence_and_alert_references_cannot_be_omitted(
    path: tuple[str, str],
) -> None:
    raw = _raw_bindings()
    del raw[path[0]][path[1]]

    with pytest.raises(PacketError):
        parse_bindings(raw)


@pytest.mark.parametrize(
    ("field", "source"),
    [
        ("host_id", "primary"),
        ("private_ip", "primary"),
        ("failure_domain", "primary"),
        ("operator_domain", "primary"),
    ],
)
def test_primary_and_standby_must_be_distinct(field: str, source: str) -> None:
    raw = _raw_bindings()
    raw["standby"][field] = raw[source][field]

    with pytest.raises(PacketError, match="distinct"):
        parse_bindings(raw)


def test_workload_identities_cannot_be_shared() -> None:
    raw = _raw_bindings()
    raw["workload_identities"]["anchor"] = raw["workload_identities"]["backup"]

    with pytest.raises(PacketError, match="identities"):
        parse_bindings(raw)


def test_operator_bound_inputs_cannot_reuse_synthetic_fixture_values() -> None:
    raw = _raw_bindings()
    raw["binding_kind"] = "operator_bound"
    raw["validation_context"] = "distinct_host_review"

    with pytest.raises(PacketError, match="synthetic"):
        parse_bindings(raw)


def test_root_owned_references_reject_weak_permissions() -> None:
    raw = _raw_bindings()
    raw["standby"]["replication_passfile"]["mode"] = "0644"

    with pytest.raises(PacketError):
        parse_bindings(raw)


def test_host_preflight_rejects_observed_weak_permissions() -> None:
    raw = _raw_bindings()
    raw["binding_kind"] = "operator_bound"
    raw["validation_context"] = "distinct_host_review"
    encoded = json.dumps(raw).replace("synthetic", "operator-bound")
    bindings = parse_bindings(json.loads(encoded))

    def observe_weakly(reference: object) -> FileObservation:
        del reference
        return FileObservation(
            regular=True,
            owner_uid=0,
            group="ctower-postgres",
            group_gid=999,
            mode="0644",
            sha256="sha256:2111111111111111111111111111111111111111111111111111111111111111",
        )

    with pytest.raises(PreflightError, match="permissions"):
        validate_local_role(bindings, "primary", observer=observe_weakly)


def test_same_host_mechanics_cannot_enter_local_preflight() -> None:
    bindings = load_bindings(SYNTHETIC_BINDINGS)

    with pytest.raises(PreflightError, match="synthetic"):
        validate_local_role(bindings, "primary")


def test_operator_binding_document_rejects_broad_permissions(tmp_path: Path) -> None:
    path = tmp_path / "bindings.operator.json"
    path.write_text("{}\n", encoding="utf-8")
    path.chmod(0o644)

    with pytest.raises(PreflightError, match=r"root|permissions"):
        validate_binding_document(path)


def test_manifest_is_canonical_stable_and_contains_no_file_paths() -> None:
    bindings = load_bindings(SYNTHETIC_BINDINGS)
    primary = render_compose_config(PACKET / "primary.compose.yaml", "primary", bindings)
    standby = render_compose_config(PACKET / "standby.compose.yaml", "standby", bindings)
    compose_a = {"primary": primary, "standby": standby}
    compose_b = {"standby": standby, "primary": primary}

    first = canonical_manifest(bindings, compose_a)
    second = canonical_manifest(bindings, compose_b)

    assert first == second
    assert first.endswith(b"\n")
    assert b"/etc/ctower/" not in first
    assert b"replication.passfile" not in first
    assert b"FORBIDDEN_INLINE_MATERIAL" not in first


@pytest.mark.parametrize("role", ["primary", "standby"])
def test_compose_config_is_daemonless_and_preserves_safety_invariants(
    role: Literal["primary", "standby"],
) -> None:
    bindings = load_bindings(SYNTHETIC_BINDINGS)
    document = render_compose_config(PACKET / f"{role}.compose.yaml", role, bindings)
    service = document["services"][f"postgres-{role}"]
    command = service["command"]

    assert service["image"] == bindings.postgres.image
    assert service["network_mode"] == "host"
    assert service["restart"] == "no"
    assert "ports" not in service
    assert not service.get("environment")
    assert any("synchronous_commit=remote_apply" in item for item in command)
    assert any("ctower_i1_ack" in item for item in command)
    assert document["name"] == f"ctower-cp3d-{role}"


def test_compose_documents_reject_default_credential_fallbacks() -> None:
    bindings = load_bindings(SYNTHETIC_BINDINGS)
    primary = render_compose_config(PACKET / "primary.compose.yaml", "primary", bindings)
    mutated = copy.deepcopy(primary)
    mutated["services"]["postgres-primary"]["environment"] = {
        "POSTGRES_PASSWORD": REJECTED_MATERIAL
    }

    with pytest.raises(PacketError, match="environment"):
        canonical_manifest(bindings, {"primary": mutated, "standby": {}})


def test_cli_does_not_echo_rejected_material(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = _raw_bindings()
    raw["pass" + "word"] = REJECTED_MATERIAL
    path = tmp_path / "rejected.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    result = main(["validate", "--bindings", str(path)])

    captured = capsys.readouterr()
    assert result == CLI_FAILURE
    assert "credential material" in captured.err
    assert REJECTED_MATERIAL not in captured.err
