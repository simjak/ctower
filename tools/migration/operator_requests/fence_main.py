"""Create a signed Request source-fence artifact from observed filesystem state."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

import rfc8785

from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner
from tools.migration.operator_requests.source_fence import observe_source_fence

__all__: tuple[str, ...] = ()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--caller-root", required=True, type=Path)
    parser.add_argument("--caller", required=True, action="append", type=Path)
    parser.add_argument("--phase", required=True, choices=("freeze", "batch", "final"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--signing-key-map", required=True, type=Path)
    parser.add_argument("--signing-key-ref", required=True)
    parser.add_argument("--signing-key-version", required=True, type=int)
    arguments = parser.parse_args(argv)
    signer = ArtifactSigner.from_reference_map(
        arguments.signing_key_map,
        arguments.signing_key_ref,
        key_version=arguments.signing_key_version,
    )
    artifact = observe_source_fence(
        arguments.ledger,
        caller_root=arguments.caller_root,
        caller_paths=tuple(cast(list[Path], arguments.caller)),
        phase=arguments.phase,
        signer=signer,
    )
    arguments.output.write_bytes(rfc8785.dumps(artifact))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
