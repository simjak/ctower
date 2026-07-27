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
from tools.codegen._free_form_json_codegen import require_free_form_json_profile
from tools.codegen._inventory import EXPECTED_OPERATIONS, EXPECTED_SCHEMAS
from tools.codegen._model_codegen import render_init, render_models
from tools.codegen._operation_codegen import render_operations
from tools.codegen._schema_codegen import render_schema_resources
from tools.codegen._typescript_codegen import render_typescript

__all__ = ["CodegenError", "check", "render_typescript_fixture", "write"]

_MANIFEST = Path("generated/.generated-manifest.json")
_README = Path("generated/README.md")
_OPENAPI = Path("contracts/http/openapi.yaml")
_TELEMETRY = Path("contracts/observability/telemetry-context.schema.json")
_CLIENT_OUTPUTS = {
    "__init__.py": Path("generated/python/ctower_client/__init__.py"),
    "client.py": Path("generated/python/ctower_client/client.py"),
    "models.py": Path("generated/python/ctower_client/models.py"),
    "operations.py": Path("generated/python/ctower_client/operations.py"),
}
_TYPESCRIPT_ROOT = Path("generated/typescript/ctower-client")
_TYPESCRIPT_OUTPUTS = {
    "client.ts": _TYPESCRIPT_ROOT / "src/client.ts",
    "index.ts": _TYPESCRIPT_ROOT / "src/index.ts",
    "models.ts": _TYPESCRIPT_ROOT / "src/models.ts",
    "operations.ts": _TYPESCRIPT_ROOT / "src/operations.ts",
    "response-json.ts": _TYPESCRIPT_ROOT / "src/response-json.ts",
    "validators.ts": _TYPESCRIPT_ROOT / "src/validators.ts",
    "package.json": _TYPESCRIPT_ROOT / "package.json",
    "tsconfig.json": _TYPESCRIPT_ROOT / "tsconfig.json",
}
_BASE_INPUTS = (
    _OPENAPI,
    _TELEMETRY,
    Path("tools/codegen/__init__.py"),
    Path("tools/codegen/__main__.py"),
    Path("tools/codegen/_absolute_uri_codegen.py"),
    Path("tools/codegen/_client_codegen.py"),
    Path("tools/codegen/_free_form_json_codegen.py"),
    Path("tools/codegen/_inventory.py"),
    Path("tools/codegen/_json_integer_codegen.py"),
    Path("tools/codegen/_model_codegen.py"),
    Path("tools/codegen/_operation_codegen.py"),
    Path("tools/codegen/_rfc3339_codegen.py"),
    Path("tools/codegen/_schema_codegen.py"),
    Path("tools/codegen/_typescript_codegen.py"),
    Path("tools/codegen/_typescript_json_codegen.py"),
    Path("tools/codegen/_typescript_validation_codegen.py"),
    Path("tools/codegen/generator.py"),
    Path("tools/checks/generated.py"),
)


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


def render_typescript_fixture(
    document: dict[str, object],
    contract_digest: str,
) -> dict[str, str]:
    """Render one in-memory TypeScript contract fixture through production codegen."""

    try:
        free_form_profile = require_free_form_json_profile(document)
        return render_typescript(
            document,
            contract_digest,
            free_form_profile=free_form_profile,
        )
    except (TypeError, ValueError) as error:
        raise CodegenError(str(error)) from error


def _render(root: Path) -> _Rendered:
    contract = _load_openapi(root)
    generated_contract = _with_telemetry_schema(root, contract)
    contract_digest = hashlib.sha256(
        json.dumps(generated_contract, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    try:
        rendered, typescript = _render_clients(generated_contract, contract_digest)
        contract_resources = render_schema_resources(root, contract_digest)
    except (TypeError, ValueError) as error:
        raise CodegenError(str(error)) from error
    client_outputs = tuple(
        (output, rendered[name]) for name, output in sorted(_CLIENT_OUTPUTS.items())
    )
    typescript_outputs = tuple(
        (output, typescript[name]) for name, output in sorted(_TYPESCRIPT_OUTPUTS.items())
    )
    outputs = tuple(
        sorted(
            (
                *client_outputs,
                *typescript_outputs,
                *contract_resources.outputs,
                (_README, _render_readme()),
            )
        )
    )
    inputs = tuple(sorted({*_BASE_INPUTS, *contract_resources.inputs}))
    try:
        manifest = load_generated_manifest(root, _MANIFEST)
        generator_digest = digest_file(root, Path("tools/codegen/generator.py")).sha256
        artifact = GeneratedArtifact(
            artifact_id="http-python-client",
            generator="tools.codegen",
            tool_version=f"1+{generator_digest}",
            command="python3 -m tools.codegen --root . --write",
            inputs=tuple(digest_file(root, path) for path in inputs),
            outputs=tuple(digest_bytes(path, content.encode()) for path, content in outputs),
        )
    except GeneratedManifestError as error:
        raise CodegenError(str(error)) from error
    return _Rendered(outputs, render_generated_manifest(manifest.upsert(artifact)))


def _render_clients(
    document: dict[str, object],
    contract_digest: str,
) -> tuple[dict[str, str], dict[str, str]]:
    free_form_profile = require_free_form_json_profile(document)
    python = {
        "__init__.py": render_init(document, contract_digest),
        "client.py": render_client(document, contract_digest),
        "models.py": render_models(
            document,
            contract_digest,
            free_form_profile=free_form_profile,
        ),
        "operations.py": render_operations(document, contract_digest),
    }
    typescript = render_typescript(
        document,
        contract_digest,
        free_form_profile=free_form_profile,
    )
    return python, typescript


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
    if operations != EXPECTED_OPERATIONS:
        raise CodegenError(f"unexpected operation set: {sorted(operations)}")
    if schemas != EXPECTED_SCHEMAS:
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


def _render_readme() -> str:
    return """# Generated artifacts

Do not edit files in this directory. Regenerate them from authored contracts with:

```text
python3 -m tools.codegen --root . --write
```

`python/ctower_client` and `typescript/ctower-client` are strict OpenAPI client/model
packages. The Python operation registry is the closed replay inventory for the protected CLI;
it is not an arbitrary dispatcher. Both clients expose the same authored operation set and
validate operation-specific success and problem payloads at runtime before returning them.

`python/ctower_contracts` vendors authored JSON schemas into a local-only runtime resource.
Resolution rejects network references and paths that escape the authored contract tree.

Both packages and `ctower_contracts/schemas.json` are included in the verified development
wheel. Generated presence does not establish a stable external API, supported package release,
deployment, or runtime/effect activation. Exact source/output digests are owned by
`.generated-manifest.json`.
"""


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
