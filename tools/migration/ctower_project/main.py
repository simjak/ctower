#!/usr/bin/env python3
"""Read-only command surface for the dormant CT-I1.7B source tool."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast
from uuid import UUID

from tools.migration.ctower_project.ctower_project_source.canonical import (
    JsonValue,
    canonical_bytes,
    strict_json,
)
from tools.migration.ctower_project.ctower_project_source.exporter import freeze_export
from tools.migration.ctower_project.ctower_project_source.refusal import (
    MigrationRefusal,
    RefusalCode,
)
from tools.migration.ctower_project.ctower_project_source.signing import ArtifactVerifier
from tools.migration.ctower_project.ctower_project_source.source import ReadOnlySourceRoot

__all__: tuple[str, ...] = ()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministic read-only ctower-project synthetic exporter"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    export = subparsers.add_parser("export")
    export.add_argument("--source-root", type=Path, required=True)
    export.add_argument("--selection", required=True)
    export.add_argument("--target-inventory", required=True)
    export.add_argument("--reviewer-public-key", type=Path, required=True)
    export.add_argument("--cutover-id", type=UUID, required=True)
    export.add_argument(
        "--exporter-pass",
        dest="export_stage",
        choices=("export_a", "export_b"),
        required=True,
    )
    export.add_argument("--emit", choices=("manifest", "semantic"), default="manifest")
    return parser


def _export(arguments: argparse.Namespace) -> bytes:
    root = ReadOnlySourceRoot(arguments.source_root)
    selection = strict_json(root.read(arguments.selection).data, context="source selection")
    target = strict_json(
        root.read(arguments.target_inventory).data,
        context="target inventory",
    )
    if not isinstance(selection, dict) or not isinstance(target, dict):
        raise MigrationRefusal(RefusalCode.CONTRACT_INVALID, "artifact root")
    frozen = freeze_export(
        cast(dict[str, object], selection),
        root,
        cast(dict[str, object], target),
        cutover_id=arguments.cutover_id,
        export_stage=arguments.export_stage,
        verifier=ArtifactVerifier.from_path(arguments.reviewer_public_key),
    )
    if arguments.emit == "semantic":
        return frozen.semantic_bytes
    return canonical_bytes(cast(JsonValue, frozen.manifest))


def main() -> int:
    arguments = _parser().parse_args()
    try:
        output = _export(arguments)
    except MigrationRefusal as refusal:
        sys.stderr.buffer.write(canonical_bytes(refusal.as_dict()) + b"\n")
        return 2
    sys.stdout.buffer.write(output + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
