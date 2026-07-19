"""Build-time CLI for deterministic contract traceability artifacts."""

import argparse as _argparse
import sys as _sys
from collections.abc import Sequence as _Sequence
from pathlib import Path as _Path

from tools.checks._impl.generated import GeneratedManifestError as _GeneratedManifestError
from tools.checks._impl.traceability import (
    TraceabilityError as _TraceabilityError,
)
from tools.checks._impl.traceability import (
    check_traceability_artifacts as _check_traceability_artifacts,
)
from tools.checks._impl.traceability import (
    write_traceability_artifacts as _write_traceability_artifacts,
)

__all__ = ["main"]


def _parser() -> _argparse.ArgumentParser:
    parser = _argparse.ArgumentParser(description="Build or verify contract traceability")
    parser.add_argument("--root", type=_Path, default=_Path.cwd())
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--write", action="store_true", help="write the deterministic index")
    action.add_argument("--check", action="store_true", help="fail when the index differs")
    return parser


def main(argv: _Sequence[str] | None = None) -> int:
    """Run the sole command Interface for traceability generation and checking."""

    args = _parser().parse_args(argv)
    root = args.root.resolve()
    try:
        if args.write:
            _write_traceability_artifacts(root)
        else:
            _check_traceability_artifacts(root)
    except (_GeneratedManifestError, _TraceabilityError, OSError) as error:
        print(f"traceability error: {error}", file=_sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
