"""Command-line entry point for deterministic generated clients."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.codegen.generator import CodegenError, check, write


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.write:
            write(args.root)
        else:
            check(args.root)
    except CodegenError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
