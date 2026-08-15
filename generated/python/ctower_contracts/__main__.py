"""DO NOT EDIT: generated file; regenerate from declared inputs.

<<<<<<< HEAD
Authored contract digest: sha256:4208ed95a16a9bcec349edcf1c8d002f135665367ad1de4131be5b93c46de71e
=======
Authored contract digest: sha256:b15cd812b396627a264217134e14b9138e5a476ff2652f93594e7c958de52818
>>>>>>> 650210f4 (feat(spawn): publish generated HTTP and CLI surfaces)
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
