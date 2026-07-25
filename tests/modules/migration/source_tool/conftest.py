from __future__ import annotations

import sys
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parents[4] / "tools" / "migration" / "ctower-project"
sys.path.insert(0, str(TOOL_ROOT))
