"""Generate the narrow Python client from the authored OpenAPI contract."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from tools.checks.generated import (
    GeneratedArtifact,
    GeneratedManifestError,
    atomic_write_generated_text,
    digest_bytes,
    digest_file,
    load_generated_manifest,
    render_generated_manifest,
)
from tools.codegen._client_codegen import render_client
from tools.codegen._model_codegen import render_init, render_models

__all__ = ["CodegenError", "check", "write"]

_MANIFEST = Path("generated/.generated-manifest.json")
_OPENAPI = Path("contracts/http/openapi.yaml")
_TELEMETRY = Path("contracts/observability/telemetry-context.schema.json")
_OUTPUTS = {
    "__init__.py": Path("generated/python/ctower_client/__init__.py"),
    "client.py": Path("generated/python/ctower_client/client.py"),
    "models.py": Path("generated/python/ctower_client/models.py"),
}
_INPUTS = (
    _OPENAPI,
    _TELEMETRY,
    Path("contracts/domain/events/event-envelope.schema.json"),
    Path("contracts/domain/tickets/ticket-event.schema.json"),
    Path("tools/codegen/__init__.py"),
    Path("tools/codegen/__main__.py"),
    Path("tools/codegen/_client_codegen.py"),
    Path("tools/codegen/_model_codegen.py"),
    Path("tools/codegen/generator.py"),
    Path("tools/checks/generated.py"),
)
_EXPECTED_OPERATIONS = {
    "bootstrapFirstTenant",
    "createTicket",
    "freezeProofCriteria",
    "getTicket",
    "getTicketTimeline",
    "recordProofEvidence",
    "recordProofVerdict",
    "resolveCloseWorkflow",
    "transferTicketCustody",
    "transitionWorkflow",
}
_EXPECTED_SCHEMAS = {
    "ActivityClass",
    "BootstrapReceipt",
    "BootstrapRequest",
    "CustodyTransferredPayload",
    "CustodyTransferRequest",
    "DurabilityState",
    "EvidenceRequest",
    "FreezeCriteriaRequest",
    "Priority",
    "Problem",
    "ProofCriterion",
    "ProofReceipt",
    "ResolveCloseRequest",
    "SourceReference",
    "TicketCommandResult",
    "TicketCreateRequest",
    "TicketCreatedPayload",
    "TicketResource",
    "TimelineEvent",
    "TimelineResponse",
    "VerdictDecision",
    "VerdictRequest",
    "WorkflowReceipt",
    "WorkflowTransitionRequest",
}


class CodegenError(ValueError):
    """The authored contract or generated client is malformed or stale."""


@dataclass(frozen=True, slots=True)
class _Rendered:
    outputs: tuple[tuple[Path, str], ...]
    manifest: str


def write(root: Path) -> None:
    """Write generated client bytes and their exact manifest entry."""

    resolved = root.resolve()
    rendered = _render(resolved)
    for path, content in rendered.outputs:
        atomic_write_generated_text(resolved, path, content)
    atomic_write_generated_text(resolved, _MANIFEST, rendered.manifest)


def check(root: Path) -> None:
    """Regenerate in memory and compare every committed byte."""

    resolved = root.resolve()
    rendered = _render(resolved)
    for path, expected in (*rendered.outputs, (_MANIFEST, rendered.manifest)):
        try:
            current = (resolved / path).read_text(encoding="utf-8")
        except OSError as error:
            raise CodegenError(f"cannot read generated output {path}: {error}") from error
        if current != expected:
            raise CodegenError(f"generated output is stale: {path}")


def _render(root: Path) -> _Rendered:
    contract = _load_openapi(root)
    generated_contract = _with_telemetry_schema(root, contract)
    contract_digest = hashlib.sha256(
        json.dumps(generated_contract, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    rendered = {
        "__init__.py": render_init(generated_contract, contract_digest),
        "client.py": render_client(generated_contract, contract_digest),
        "models.py": render_models(generated_contract, contract_digest),
    }
    outputs = tuple((output, rendered[name]) for name, output in sorted(_OUTPUTS.items()))
    try:
        manifest = load_generated_manifest(root, _MANIFEST)
        generator_digest = digest_file(root, Path("tools/codegen/generator.py")).sha256
        artifact = GeneratedArtifact(
            artifact_id="http-python-client",
            generator="tools.codegen",
            tool_version=f"1+{generator_digest}",
            command="python3 -m tools.codegen --root . --write",
            inputs=tuple(digest_file(root, path) for path in _INPUTS),
            outputs=tuple(digest_bytes(path, content.encode()) for path, content in outputs),
        )
    except GeneratedManifestError as error:
        raise CodegenError(str(error)) from error
    return _Rendered(outputs, render_generated_manifest(manifest.upsert(artifact)))


def _load_openapi(root: Path) -> dict[str, object]:
    try:
        payload: object = json.loads((root / _OPENAPI).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CodegenError(f"cannot load authored OpenAPI: {error}") from error
    if not isinstance(payload, dict):
        raise CodegenError("authored OpenAPI must be an object")
    document = cast(dict[str, object], payload)
    operations = _operation_ids(document)
    schemas = _schema_names(document)
    if operations != _EXPECTED_OPERATIONS:
        raise CodegenError(f"unexpected operation set: {sorted(operations)}")
    if schemas != _EXPECTED_SCHEMAS:
        raise CodegenError(f"unexpected schema set: {sorted(schemas)}")
    return document


def _operation_ids(document: dict[str, object]) -> set[str]:
    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise CodegenError("OpenAPI paths must be an object")
    identifiers: set[str] = set()
    for value in paths.values():
        if not isinstance(value, dict):
            raise CodegenError("each OpenAPI path must be an object")
        for method, operation in value.items():
            if method not in {"get", "post"}:
                continue
            if not isinstance(operation, dict) or not isinstance(operation.get("operationId"), str):
                raise CodegenError("each HTTP operation needs an operationId")
            identifiers.add(operation["operationId"])
    return identifiers


def _schema_names(document: dict[str, object]) -> set[str]:
    components = document.get("components")
    if not isinstance(components, dict) or not isinstance(components.get("schemas"), dict):
        raise CodegenError("OpenAPI components.schemas must be an object")
    return set(cast(dict[str, object], components["schemas"]))


def _with_telemetry_schema(root: Path, contract: dict[str, object]) -> dict[str, object]:
    try:
        telemetry: object = json.loads((root / _TELEMETRY).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CodegenError(f"cannot load authored telemetry context: {error}") from error
    if not isinstance(telemetry, dict) or not isinstance(telemetry.get("$defs"), dict):
        raise CodegenError("authored telemetry context must contain $defs")
    definitions = cast(dict[str, object], telemetry["$defs"])
    resolved = _resolve_local_definitions(telemetry, definitions)
    if not isinstance(resolved, dict):
        raise CodegenError("resolved telemetry context must be an object")
    for metadata in ("$schema", "$id", "$defs", "title", "description"):
        resolved.pop(metadata, None)
    generated = cast(dict[str, object], json.loads(json.dumps(contract)))
    components = cast(dict[str, object], generated["components"])
    schemas = cast(dict[str, object], components["schemas"])
    schemas["TelemetryContext"] = resolved
    return generated


def _resolve_local_definitions(value: object, definitions: dict[str, object]) -> object:
    if isinstance(value, list):
        return [_resolve_local_definitions(item, definitions) for item in value]
    if not isinstance(value, dict):
        return value
    reference = value.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/"):
        name = reference.removeprefix("#/$defs/")
        if name not in definitions:
            raise CodegenError(f"unknown telemetry definition {name}")
        return _resolve_local_definitions(definitions[name], definitions)
    return {key: _resolve_local_definitions(item, definitions) for key, item in value.items()}
