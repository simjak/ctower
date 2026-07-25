"""Acceptance 1, 2, 4, 5, 6, and 7 checks for the source-only VPS packet."""

from __future__ import annotations

import copy
import hashlib
import ipaddress
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from ruamel.yaml import YAML

from tools.private_vps.cli import main
from tools.private_vps.manifest import PacketError, load_model
from tools.private_vps.models import DeploymentBindings, RootOwnedFile
from tools.private_vps.preflight import (
    FileObservation,
    validate_deployment,
    verify_configuration,
)

__all__: list[str] = []

ROOT = Path(__file__).parents[3]
PACKET = ROOT / "deploy/private-vps/development"
BINDINGS = PACKET / "bindings.example.json"
DEPLOYMENT_SCHEMA = ROOT / "contracts/operations/private-vps-deployment.schema.json"
EVIDENCE_SCHEMA = ROOT / "contracts/operations/private-vps-evidence.schema.json"
START_SHA = "bf2ffb851ab31c0fb1e32792ca1230e38b66ba1e"
START_TREE = "029ff306a7c5495223d6c3e5fff78a3977e778cc"
CLI_FAILURE = 2
DATABASE_CREDENTIAL_COUNT = 5
POSTGRES_MAJOR = 17
UNSPECIFIED_ADDRESS = str(ipaddress.IPv4Address(0))


def _raw() -> dict[str, Any]:
    value = json.loads(BINDINGS.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_packet(tmp_path: Path, raw: dict[str, Any] | None = None) -> Path:
    for name in ("compose.yaml", "Caddyfile", "otel-collector.yaml"):
        shutil.copyfile(PACKET / name, tmp_path / name)
    document = copy.deepcopy(raw or _raw())
    document["bootstrap"]["output"]["path"] = "/etc/ctower-bootstrap-output.json"
    path = tmp_path / "bindings.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _observed(reference: RootOwnedFile) -> FileObservation:
    return FileObservation(
        regular=True,
        owner_uid=0,
        mode=reference.mode,
        sha256=reference.sha256,
    )


def test_acceptance_1_authored_schemas_and_models_are_strict_reference_only() -> None:
    raw = _raw()
    for path in (DEPLOYMENT_SCHEMA, EVIDENCE_SCHEMA):
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["additionalProperties"] is False
    Draft202012Validator(json.loads(DEPLOYMENT_SCHEMA.read_text())).validate(raw)
    bindings = DeploymentBindings.model_validate(raw)

    image_names = ("control", "postgres", "edge", "collector")
    assert all("@sha256:" in getattr(bindings.images, name) for name in image_names)
    assert bindings.images.postgres_major == POSTGRES_MAJOR
    distinct = {item.reference for item in bindings.database.credentials()}
    assert len(distinct) == DATABASE_CREDENTIAL_COUNT
    assert bindings.bootstrap.output.reference.startswith("file-ref://")
    assert bindings.objects.root.reference.startswith("object-root-ref://")
    assert bindings.telemetry.alert_owner_ref.startswith("alert-owner-ref://")


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("images", "control"), "example.invalid/ctower/control:latest"),
        (("bind_address",), UNSPECIFIED_ADDRESS),
        (("bind_address",), "127.0.0.1"),
        (("bind_address",), "203.0.113.10"),
        (("assurance",), "cp3d"),
        (("durability_policy",), "cutover_rpo0"),
        (("failure_domain_count",), 2),
        (("cp3d_qualified",), True),
        (("accepted_write_rpo0_claim",), True),
    ],
)
def test_acceptance_2_unsafe_image_bind_and_one_host_claims_fail_closed(
    path: tuple[str, ...],
    value: object,
) -> None:
    raw = _raw()
    target = raw
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        DeploymentBindings.model_validate(raw)


def test_acceptance_2_inline_material_and_shared_credentials_fail_closed(
    tmp_path: Path,
) -> None:
    inline = _raw()
    inline["database"]["service_dsn"] = "postgresql://user:credential@db/ctower"
    path = _write_packet(tmp_path, inline)
    with pytest.raises(PacketError, match="inline_secret_material"):
        load_model(path, DeploymentBindings, field="bindings")

    shared = _raw()
    shared["database"]["service_dsn"] = shared["database"]["role_admin_dsn"]
    with pytest.raises(ValidationError, match="distinct"):
        DeploymentBindings.model_validate(shared)


def test_acceptance_2_preflight_binds_source_config_and_reference_permissions(
    tmp_path: Path,
) -> None:
    path = _write_packet(tmp_path)
    bindings = validate_deployment(path, START_SHA, START_TREE, observer=_observed)
    assert bindings.assurance == "development"

    with pytest.raises(PacketError, match="source_changed"):
        validate_deployment(path, "f" * 40, START_TREE, observer=_observed)

    def weak(reference: RootOwnedFile) -> FileObservation:
        observation = _observed(reference)
        return FileObservation(
            regular=observation.regular,
            owner_uid=observation.owner_uid,
            mode="0644",
            sha256=observation.sha256,
        )

    with pytest.raises(PacketError, match="unsafe_reference_permissions"):
        validate_deployment(path, START_SHA, START_TREE, observer=weak)


def test_acceptance_2_changed_config_and_host_exposed_postgres_are_rejected(
    tmp_path: Path,
) -> None:
    path = _write_packet(tmp_path)
    (tmp_path / "Caddyfile").write_text("changed\n", encoding="utf-8")
    with pytest.raises(PacketError, match="configuration_changed"):
        verify_configuration(load_model(path, DeploymentBindings, field="bindings"), tmp_path)

    raw = _raw()
    path = _write_packet(tmp_path, raw)
    compose_path = tmp_path / "compose.yaml"
    compose_path.write_text(
        compose_path.read_text(encoding="utf-8").replace(
            "    networks: [record]\n",
            '    ports: ["10.0.0.10:5432:5432"]\n    networks: [record]\n',
            1,
        ),
        encoding="utf-8",
    )
    raw["configuration"]["compose"]["sha256"] = _digest(compose_path)
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(PacketError, match="postgres_host_exposure"):
        verify_configuration(load_model(path, DeploymentBindings, field="bindings"), tmp_path)


def test_acceptance_4_compose_uses_one_control_digest_and_hardened_boundaries() -> None:
    document = YAML(typ="safe", pure=True).load(
        (PACKET / "compose.yaml").read_text(encoding="utf-8")
    )
    services = document["services"]
    control = services["api"]["image"]

    assert {services[name]["image"] for name in ("api", "worker", "migrator", "role-admin")} == {
        control
    }
    assert "ports" not in services["postgres"]
    assert document["networks"]["record"]["internal"] is True
    assert services["edge"]["ports"] == ["10.0.0.10:443:443"]
    assert {"postgres-data", "object-data"} <= set(document["volumes"])
    for name in ("api", "worker", "migrator", "role-admin", "collector"):
        assert services[name]["read_only"] is True
        assert services[name]["cap_drop"] == ["ALL"]


def test_acceptance_5_example_and_boundary_readme_preserve_development_claims() -> None:
    raw = _raw()
    boundary = (ROOT / "deploy/private-vps/README.md").read_text(encoding="utf-8")

    assert raw["assurance"] == "development"
    assert raw["durability_policy"] == "pending_only"
    assert raw["failure_domain_count"] == 1
    assert raw["cp3d_qualified"] is False
    assert raw["data_classification"] == "disposable_synthetic_non_sensitive"
    assert raw["authoritative_ctower_project_writer"] is False
    assert raw["accepted_write_rpo0_claim"] is False
    assert "pending_only" in boundary
    assert "production target" in boundary


def test_acceptance_6_cli_has_only_read_only_machine_result_operations(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = _raw()
    rejected_value = "FORBIDDEN_INLINE_MATERIAL"
    raw["token"] = rejected_value
    path = _write_packet(tmp_path, raw)

    result = main(
        [
            "validate",
            "--bindings",
            str(path),
            "--source-sha",
            START_SHA,
            "--source-tree",
            START_TREE,
        ]
    )
    output = capsys.readouterr().out
    decoded = json.loads(output)

    assert result == CLI_FAILURE
    assert decoded["operation"] == "validate"
    assert decoded["ok"] is False
    assert decoded["code"] == "inline_secret_material"
    assert rejected_value not in output


def test_acceptance_7_packet_does_not_add_runtime_or_generated_authority() -> None:
    prohibited = (
        ROOT / ".python-version",
        ROOT / "uv.lock",
        ROOT / "generated/private-vps",
        ROOT / "apps/ctower-api/src/ctower_api/_deployment_server.py",
    )
    assert not any(path.exists() for path in prohibited)


def _digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
