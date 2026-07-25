"""Adversarial contract and preflight tests for the private-VPS packet."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError
from ruamel.yaml import YAML

from tools.private_vps.cli import main
from tools.private_vps.compose_policy import verify_compose
from tools.private_vps.manifest import (
    MAX_DOCUMENT_BYTES,
    ConfinedRoot,
    FileSnapshot,
    PacketError,
    load_model,
)
from tools.private_vps.models import DeploymentBindings, RootOwnedDirectory, RootOwnedFile
from tools.private_vps.preflight import (
    DirectoryObservation,
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
POSTGRES_MAJOR = 17
DATABASE_CREDENTIAL_COUNT = 6
CTOWER_GROUP_ID = 10001


def _raw() -> dict[str, Any]:
    value = json.loads(BINDINGS.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_packet(tmp_path: Path, raw: dict[str, Any] | None = None) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    for name in ("compose.yaml", "Caddyfile", "otel-collector.yaml"):
        shutil.copyfile(PACKET / name, tmp_path / name)
    path = tmp_path / "bindings.json"
    path.write_text(json.dumps(copy.deepcopy(raw or _raw())), encoding="utf-8")
    return path


def _observed(reference: RootOwnedFile) -> FileObservation:
    return FileObservation(
        regular=True,
        owner_uid=0,
        owner_gid=reference.group_id,
        mode=reference.mode,
        sha256=reference.sha256,
    )


def _directory(reference: RootOwnedDirectory) -> DirectoryObservation:
    return DirectoryObservation(
        owner_uid=0,
        owner_gid=reference.group_id,
        mode=reference.mode,
    )


def _digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _rewrite_compose(
    packet_path: Path,
    raw: dict[str, Any],
    mutate: Callable[[dict[str, Any]], None],
) -> Path:
    path = packet_path / "compose.yaml"
    yaml = YAML(typ="safe", pure=True)
    document = yaml.load(path.read_text(encoding="utf-8"))
    mutate(document)
    with path.open("w", encoding="utf-8") as stream:
        yaml.dump(document, stream)
    raw["configuration"]["compose"]["sha256"] = _digest(path)
    bindings_path = packet_path / "bindings.json"
    bindings_path.write_text(json.dumps(raw), encoding="utf-8")
    return bindings_path


def test_authored_schemas_and_runtime_models_accept_the_example() -> None:
    raw = _raw()
    for path in (DEPLOYMENT_SCHEMA, EVIDENCE_SCHEMA):
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["additionalProperties"] is False
    validator = Draft202012Validator(
        json.loads(DEPLOYMENT_SCHEMA.read_text()),
        format_checker=FormatChecker(),
    )
    validator.validate(raw)
    bindings = DeploymentBindings.model_validate(raw)

    assert bindings.images.postgres_major == POSTGRES_MAJOR
    assert len({item.path for item in bindings.database.credentials()}) == DATABASE_CREDENTIAL_COUNT
    assert bindings.database.api_dsn != bindings.database.worker_dsn
    assert bindings.objects.api_key != bindings.objects.worker_key
    assert bindings.bootstrap.parent.group_id == CTOWER_GROUP_ID


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("images", "control"), "example.invalid/ctower/control:latest"),
        (("bind_address",), "127.0.0.1"),
        (("bind_address",), "203.0.113.10"),
        (("assurance",), "cp3d"),
        (("durability_policy",), "cutover_rpo0"),
        (("failure_domain_count",), 2),
        (("cp3d_qualified",), True),
        (("accepted_write_rpo0_claim",), True),
        (("configuration", "compose", "path"), "../compose.yaml"),
        (("workload_identities", "api"), "identity-ref://private-vps/api"),
    ],
)
def test_schema_and_model_reject_the_same_structural_counterexamples(
    path: tuple[str, ...],
    value: object,
) -> None:
    raw = _raw()
    target = raw
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    validator = Draft202012Validator(
        json.loads(DEPLOYMENT_SCHEMA.read_text()),
        format_checker=FormatChecker(),
    )

    assert not validator.is_valid(raw)
    with pytest.raises(ValidationError):
        DeploymentBindings.model_validate(raw)


def test_actual_loader_uses_authored_schema_before_runtime_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_packet(tmp_path)
    monkeypatch.setattr(
        DeploymentBindings,
        "model_validate_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("model reached")),
    )
    raw = json.loads(path.read_text())
    raw["configuration"]["compose"]["path"] = "../compose.yaml"
    path.write_text(json.dumps(raw))

    with pytest.raises(PacketError, match="invalid_document"):
        load_model(path, DeploymentBindings, field="bindings")


def test_inline_secret_material_and_non_private_octets_fail_closed(
    tmp_path: Path,
) -> None:
    raw = _raw()
    raw["database"]["api_dsn"] = "postgresql://user:credential@db/ctower"
    path = _write_packet(tmp_path, raw)
    with pytest.raises(PacketError, match="inline_secret_material"):
        load_model(path, DeploymentBindings, field="bindings")

    raw = _raw()
    raw["bind_address"] = "10.999.1.2"
    path.write_text(json.dumps(raw))
    with pytest.raises(PacketError, match="invalid_document"):
        load_model(path, DeploymentBindings, field="bindings")


def test_preflight_binds_source_config_uid_gid_and_bootstrap_parent(
    tmp_path: Path,
) -> None:
    path = _write_packet(tmp_path)
    bindings = validate_deployment(
        path,
        START_SHA,
        START_TREE,
        observer=_observed,
        directory_observer=_directory,
    )
    assert bindings.assurance == "development"

    with pytest.raises(PacketError, match="source_changed"):
        validate_deployment(
            path,
            "f" * 40,
            START_TREE,
            observer=_observed,
            directory_observer=_directory,
        )

    def wrong_gid(reference: RootOwnedFile) -> FileObservation:
        observed = _observed(reference)
        return FileObservation(
            regular=True,
            owner_uid=0,
            owner_gid=10002,
            mode=observed.mode,
            sha256=observed.sha256,
        )

    with pytest.raises(PacketError, match="unsafe_reference_owner"):
        validate_deployment(
            path,
            START_SHA,
            START_TREE,
            observer=wrong_gid,
            directory_observer=_directory,
        )


def test_unapproved_absolute_reference_and_bootstrap_owner_fail_closed(
    tmp_path: Path,
) -> None:
    raw = _raw()
    raw["database"]["api_dsn"]["path"] = "/opt/ctower/unapproved-api-dsn"
    path = _write_packet(tmp_path, raw)
    with pytest.raises(PacketError, match="reference_path_changed"):
        validate_deployment(
            path,
            START_SHA,
            START_TREE,
            observer=_observed,
            directory_observer=_directory,
        )

    path = _write_packet(tmp_path, _raw())

    def wrong_directory(_: RootOwnedDirectory) -> DirectoryObservation:
        return DirectoryObservation(owner_uid=0, owner_gid=0, mode="0755")

    with pytest.raises(PacketError, match="unsafe_output_owner"):
        validate_deployment(
            path,
            START_SHA,
            START_TREE,
            observer=_observed,
            directory_observer=wrong_directory,
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda doc: doc["services"]["worker"].update({"user": "10001:10001"}),
        lambda doc: doc["services"]["api"].update({"command": ["sh"]}),
        lambda doc: doc["services"]["postgres"].update({"ports": ["10.0.0.10:5432:5432"]}),
        lambda doc: doc["services"]["edge"].update({"privileged": True}),
        lambda doc: doc["services"]["api"].update({"cap_drop": []}),
        lambda doc: doc["services"]["api"].update({"networks": ["control"]}),
        lambda doc: doc["services"]["worker"]["volumes"].pop(),
        lambda doc: doc["volumes"].pop("postgres-data"),
        lambda doc: doc["services"].update({"surprise": copy.deepcopy(doc["services"]["api"])}),
    ],
)
def test_exact_normalized_compose_authority_rejects_every_mutation(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    raw = _raw()
    path = _write_packet(tmp_path, raw)
    path = _rewrite_compose(tmp_path, raw, mutate)
    bindings = load_model(path, DeploymentBindings, field="bindings")

    with pytest.raises(PacketError, match="compose_authority_changed"):
        verify_configuration(bindings, tmp_path)


def test_compose_binds_separate_service_credentials_and_achievable_output() -> None:
    document = YAML(typ="safe", pure=True).load(
        (PACKET / "compose.yaml").read_text(encoding="utf-8")
    )
    services = document["services"]

    assert services["api"]["user"] == "10001:10001"
    assert services["worker"]["user"] == "10002:10001"
    assert services["role-admin"]["user"] == "0:10001"
    assert services["role-admin"]["privileged"] is False
    assert services["role-admin"]["cap_drop"] == ["ALL"]
    assert services["role-admin"]["environment"]["CTOWER_BOOTSTRAP_OUTPUT"].endswith(
        "/first-tenant.json"
    )
    assert (
        services["api"]["environment"]["CTOWER_API_DSN_FILE"]
        != services["worker"]["environment"]["CTOWER_WORKER_DSN_FILE"]
    )
    assert (
        services["api"]["environment"]["CTOWER_OBJECT_KEY_FILE"]
        != services["worker"]["environment"]["CTOWER_OBJECT_KEY_FILE"]
    )


def test_digest_and_compose_parse_use_one_retained_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bindings_path = _write_packet(tmp_path)
    bindings = load_model(bindings_path, DeploymentBindings, field="bindings")
    original = verify_compose

    def replace_after_read(
        snapshot: FileSnapshot,
        actual: DeploymentBindings,
    ) -> None:
        (tmp_path / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
        original(snapshot, actual)

    monkeypatch.setattr(
        "tools.private_vps.preflight.verify_compose",
        replace_after_read,
    )
    verify_configuration(bindings, tmp_path)


def test_symlinked_root_and_leaf_are_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    path = _write_packet(real)
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(PacketError, match="missing_or_unsafe_directory"):
        load_model(alias / path.name, DeploymentBindings, field="bindings")

    path.unlink()
    path.symlink_to(BINDINGS)
    with pytest.raises(PacketError, match="missing_or_unsafe_file"):
        load_model(path, DeploymentBindings, field="bindings")

    hard_path = _write_packet(tmp_path / "hard")
    hard_link = hard_path.with_name("bindings-hard-link.json")
    os.link(hard_path, hard_link)
    with pytest.raises(PacketError, match="missing_or_unsafe_file"):
        load_model(hard_link, DeploymentBindings, field="bindings")


def test_document_compose_size_and_document_count_are_bounded(tmp_path: Path) -> None:
    path = tmp_path / "oversized.json"
    path.write_bytes(b"{" + b" " * MAX_DOCUMENT_BYTES + b"}")
    with pytest.raises(PacketError, match="document_too_large"):
        load_model(path, DeploymentBindings, field="bindings")

    raw = _raw()
    bindings_path = _write_packet(tmp_path / "documents", raw)
    compose = bindings_path.parent / "compose.yaml"
    compose.write_text(compose.read_text() + "\n---\n{}\n", encoding="utf-8")
    raw["configuration"]["compose"]["sha256"] = _digest(compose)
    bindings_path.write_text(json.dumps(raw))
    bindings = load_model(bindings_path, DeploymentBindings, field="bindings")
    with pytest.raises(PacketError, match="compose_document_count"):
        verify_configuration(bindings, bindings_path.parent)


def test_cli_failure_is_typed_and_never_echoes_secret_input(
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
    assert decoded["ok"] is False
    assert decoded["code"] == "inline_secret_material"
    assert rejected_value not in output


def test_packet_does_not_add_runtime_or_competing_generated_authority() -> None:
    prohibited = (
        ROOT / ".python-version",
        ROOT / "uv.lock",
        ROOT / "generated/private-vps",
        ROOT / "apps/ctower-api/src/ctower_api/_deployment_server.py",
    )
    assert not any(path.exists() for path in prohibited)
    with ConfinedRoot(PACKET) as root:
        assert root.read("compose.yaml", field="compose", max_bytes=64 * 1024).size > 0
