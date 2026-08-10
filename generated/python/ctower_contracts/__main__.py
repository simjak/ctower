"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:9162a2f2dfd4c43f871e05e1bfb8a12caa22173e68c6e8284fceab606a9e75c1
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from ctower_contracts.catalog import verify_all

__all__ = ["main"]


def main(argv: Sequence[str] | None = None) -> int:
    """Verify every generated local schema and reference without network access."""

    parser = argparse.ArgumentParser(prog="python -m ctower_contracts")
    parser.add_argument("command", choices=("verify",))
    parser.add_argument("--all", action="store_true", required=True, dest="all_schemas")
    parser.parse_args(argv)
    count = verify_all()
    print(f"verified {count} authored schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
