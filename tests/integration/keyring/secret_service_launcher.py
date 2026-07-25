"""Launch the isolated Secret Service harness with the invoking Python."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

__all__: tuple[str, ...] = ()


def main() -> int:
    wrapper = Path(__file__).resolve().with_name("run-secret-service")
    environment = os.environ.copy()
    environment["CTOWER_SECRET_SERVICE_COMMAND"] = json.dumps(
        (str(wrapper), sys.executable, *sys.argv[1:])
    )
    result = subprocess.run(
        (
            sys.executable,
            "-I",
            "-c",
            "import json,os; "
            "command=json.loads(os.environ.pop('CTOWER_SECRET_SERVICE_COMMAND')); "
            "os.execv('/usr/bin/bash', ['/usr/bin/bash', *command])",
        ),
        check=False,
        env=environment,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
