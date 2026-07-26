"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:a5866983d52055111283a4b0b9e7f71624524cf2a34c18869479d3b1d6430aff
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
