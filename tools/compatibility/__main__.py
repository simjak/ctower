from __future__ import annotations

import argparse
from pathlib import Path

from tools.compatibility import load_matrix, write_report
from tools.compatibility.schema import read_json_object


def main(argv: tuple[str, ...] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate ctower compatibility evidence")
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    matrix = load_matrix(arguments.matrix)
    report = read_json_object(arguments.report, label="compatibility report")
    write_report(arguments.output, matrix, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
