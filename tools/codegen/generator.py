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

__all__ = ["CodegenError", "check", "write"]

_MANIFEST = Path("generated/.generated-manifest.json")
_OPENAPI = Path("contracts/http/openapi.yaml")
_TEMPLATES = Path("tools/codegen/templates")
_OUTPUTS = {
    "__init__.py": Path("generated/python/ctower_client/__init__.py"),
    "client.py": Path("generated/python/ctower_client/client.py"),
    "models.py": Path("generated/python/ctower_client/models.py"),
}
_INPUTS = (
    _OPENAPI,
    Path("contracts/domain/events/event-envelope.schema.json"),
    Path("contracts/domain/tickets/ticket-event.schema.json"),
    Path("tools/codegen/__init__.py"),
    Path("tools/codegen/__main__.py"),
    Path("tools/codegen/generator.py"),
    Path("tools/checks/generated.py"),
    *tuple(_TEMPLATES / name for name in sorted(_OUTPUTS)),
)
_EXPECTED_OPERATIONS = {
    "bootstrapFirstTenant",
    "createTicket",
    "getTicket",
    "getTicketTimeline",
    "transferTicketCustody",
}
_EXPECTED_SCHEMAS = {
    "BootstrapReceipt",
    "BootstrapRequest",
    "CustodyTransferredPayload",
    "CustodyTransferRequest",
    "DurabilityState",
    "Priority",
    "Problem",
    "SourceReference",
    "TicketCommandResult",
    "TicketCreateRequest",
    "TicketCreatedPayload",
    "TicketResource",
    "TimelineEvent",
    "TimelineResponse",
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
    contract_digest = hashlib.sha256(
        json.dumps(contract, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    outputs = tuple(
        (output, _render_template(root, name, contract_digest))
        for name, output in sorted(_OUTPUTS.items())
    )
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


def _render_template(root: Path, name: str, contract_digest: str) -> str:
    path = root / _TEMPLATES / name
    try:
        template = path.read_text(encoding="utf-8")
    except OSError as error:
        raise CodegenError(f"cannot read generator template {path}: {error}") from error
    marker = "@@CONTRACT_SHA256@@"
    if template.count(marker) != 1:
        raise CodegenError(f"generator template {path} must contain one contract digest marker")
    return template.replace(marker, contract_digest)
