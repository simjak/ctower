"""Read-only Request cutover preflight; execution is a separate explicit command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

import httpx
import rfc8785

from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner
from tools.migration.operator_requests.dry_run import analyze_cutover

__all__: tuple[str, ...] = ()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--owner-map", type=Path)
    parser.add_argument("--fence-proof", type=Path)
    parser.add_argument("--shadow-openapi")
    parser.add_argument("--signing-key-map", type=Path)
    parser.add_argument("--signing-key-ref")
    parser.add_argument("--signing-key-version", type=int)
    parser.add_argument("--manifest-output", type=Path)
    arguments = parser.parse_args(argv)
    signer = _signer(arguments)
    try:
        report = analyze_cutover(
            arguments.ledger,
            owner_map_path=arguments.owner_map,
            fence_proof_path=arguments.fence_proof,
            signer=signer,
            shadow_observation=_shadow(arguments.shadow_openapi),
        )
    except (OSError, TypeError, ValueError) as error:
        print(
            json.dumps(
                {
                    "schema": "ctower.request-cutover-dry-run/v1",
                    "mode": "DRY-RUN",
                    "eligible": False,
                    "error": str(error),
                    "writes_attempted": 0,
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    manifest = report.get("manifest")
    if arguments.manifest_output is not None and isinstance(manifest, dict):
        arguments.manifest_output.write_bytes(rfc8785.dumps(manifest))
    return 0 if report["eligible"] else 3


def _signer(arguments: argparse.Namespace) -> ArtifactSigner | None:
    supplied = (
        arguments.signing_key_map,
        arguments.signing_key_ref,
        arguments.signing_key_version,
    )
    if all(value is None for value in supplied):
        return None
    if any(value is None for value in supplied):
        raise ValueError("signing arguments must be supplied together")
    return ArtifactSigner.from_reference_map(
        cast(Path, arguments.signing_key_map),
        cast(str, arguments.signing_key_ref),
        key_version=cast(int, arguments.signing_key_version),
    )


def _shadow(url: str | None) -> dict[str, object]:
    if url is None:
        return {}
    try:
        response = httpx.get(url, timeout=5)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as error:
        return {"openapi_reachable": False, "reason": type(error).__name__}
    if not isinstance(payload, dict):
        return {"openapi_reachable": False, "reason": "UnexpectedPayload"}
    paths = cast(dict[str, object], cast(dict[str, object], payload).get("paths", {}))
    request_paths = sorted(path for path in paths if path.startswith("/v1/requests"))
    return {
        "openapi_reachable": True,
        "request_operation_present": bool(request_paths),
        "request_paths": request_paths,
    }


if __name__ == "__main__":
    raise SystemExit(main())
