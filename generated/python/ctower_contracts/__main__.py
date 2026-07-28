"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:ea8f83c472216ed3641c511e2bd6c29da7b384180ef6e8e5dbd39a15829e1192
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
