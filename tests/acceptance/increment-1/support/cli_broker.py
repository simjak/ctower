"""Run one installed ctowerctl executable through a persistent Secret Service session."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast

__all__: tuple[str, ...] = ()

ARGUMENT_COUNT = 2
EXIT_USAGE = 2


def main() -> int:
    if len(sys.argv) != ARGUMENT_COUNT:
        return EXIT_USAGE
    executable = Path(sys.argv[1]).resolve(strict=True)
    for line in sys.stdin:
        request = json.loads(line)
        if request is None:
            print(json.dumps({"stopped": True}), flush=True)
            return 0
        command = cast(dict[str, object], request)
        completed = subprocess.run(  # noqa: S603 - fixed installed executable
            (
                str(executable),
                "--base-url",
                cast(str, command["base_url"]),
                *cast(list[str], command["arguments"]),
            ),
            input=cast(str, command["credential"]) + "\n",
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        print(
            json.dumps(
                {
                    "status": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                }
            ),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
