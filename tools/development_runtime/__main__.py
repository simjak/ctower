"""Allow ``python -m tools.development_runtime`` as an alias for the console script."""

from __future__ import annotations

import sys

from tools.development_runtime import main

if __name__ == "__main__":
    sys.argv[0] = "ctower-private-vps"
    main()
