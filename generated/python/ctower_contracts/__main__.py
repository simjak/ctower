"""DO NOT EDIT: generated file; regenerate from declared inputs.

<<<<<<< HEAD
Authored contract digest: sha256:b9e18b8de81f88230c1e1001e0483842b82174b13bf5bbb2f472baf6e86ef529
=======
Authored contract digest: sha256:57df5d8338e17a39e4f5e34719855a5968f90b0b3873c0d8582c06d2529bb493
>>>>>>> 34c42ed2 (fix(spawn): surface pending durability outcomes)
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
