"""CLI for the pinned development runtime manifest."""

from __future__ import annotations

import argparse
from pathlib import Path

from tools.runtime_manifest import build_manifest, verify_manifest


def main() -> None:
    parser = argparse.ArgumentParser(prog="ctower-runtime-manifest")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--source-root", type=Path, required=True)
    build.add_argument("--wheel", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--python", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--wheel", type=Path, required=True)
    verify.add_argument("--packs", type=Path, required=True)
    verify.add_argument("--source-root", type=Path, required=True)
    verify.add_argument("--python", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.command == "build":
        build_manifest(
            arguments.source_root,
            arguments.wheel,
            arguments.output,
            python_executable=arguments.python,
        )
    else:
        verify_manifest(
            arguments.manifest,
            arguments.wheel,
            arguments.packs,
            source_root=arguments.source_root,
            python_executable=arguments.python,
        )


if __name__ == "__main__":
    main()
