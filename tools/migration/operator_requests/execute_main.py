"""Execute or complete the separately authorized Request cutover epoch."""

from __future__ import annotations

import argparse
import json
import stat
from pathlib import Path
from typing import cast

import httpx

from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner
from tools.migration.operator_requests.execute import (
    complete_reconciled_import,
    execute_reconciled_import,
)

__all__: tuple[str, ...] = ()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("import", "complete"))
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--auth-reference", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--fence", type=Path)
    parser.add_argument("--final-fence", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--reviewer-public-key", required=True, type=Path)
    parser.add_argument("--signing-key-map", required=True, type=Path)
    parser.add_argument("--signing-key-ref", required=True)
    parser.add_argument("--signing-key-version", required=True, type=int)
    arguments = parser.parse_args(argv)
    signer = ArtifactSigner.from_reference_map(
        arguments.signing_key_map,
        arguments.signing_key_ref,
        key_version=arguments.signing_key_version,
    )
    public_key = arguments.reviewer_public_key.read_text(encoding="utf-8")
    authorization = _authorization(arguments.auth_reference)
    with httpx.Client(
        base_url=arguments.base_url,
        headers={"Authorization": authorization},
        timeout=30,
    ) as client:
        if arguments.mode == "import":
            _require(arguments, "ledger", "fence", "evidence_dir")
            result = execute_reconciled_import(
                client,
                ledger_path=cast(Path, arguments.ledger),
                manifest_path=arguments.manifest,
                fence_path=cast(Path, arguments.fence),
                evidence_dir=cast(Path, arguments.evidence_dir),
                signer=signer,
                reviewer_public_key_pem=public_key,
            )
        else:
            _require(arguments, "final_fence")
            result = complete_reconciled_import(
                client,
                manifest_path=arguments.manifest,
                final_fence_path=cast(Path, arguments.final_fence),
                signer=signer,
                reviewer_public_key_pem=public_key,
            )
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


def _authorization(path: Path) -> str:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError("request-cutover-auth-reference-insecure")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {"authorization"}:
        raise ValueError("request-cutover-auth-reference-invalid")
    authorization = value["authorization"]
    if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
        raise ValueError("request-cutover-auth-reference-invalid")
    return authorization


def _require(arguments: argparse.Namespace, *names: str) -> None:
    missing = [name for name in names if getattr(arguments, name) is None]
    if missing:
        raise ValueError(f"request-cutover-arguments-missing:{','.join(missing)}")


if __name__ == "__main__":
    raise SystemExit(main())
