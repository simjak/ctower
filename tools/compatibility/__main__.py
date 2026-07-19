from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

from tools.compatibility import execute_matrix, load_matrix, write_report
from tools.compatibility.contract import EnvironmentName
from tools.compatibility.process import ExecutionPort


def main(
    argv: tuple[str, ...] | None = None, *, execution_port: ExecutionPort | None = None
) -> int:
    parser = argparse.ArgumentParser(description="Execute ctower runtime compatibility evidence")
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--environment",
        action="append",
        choices=("macos-host", "linux-container"),
        dest="environments",
    )
    arguments = parser.parse_args(argv)
    matrix = load_matrix(arguments.matrix)
    environments = cast(
        "tuple[EnvironmentName, ...]",
        tuple(arguments.environments or ("macos-host", "linux-container")),
    )
    report = execute_matrix(matrix, environments=environments, execution_port=execution_port)
    write_report(arguments.output, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
