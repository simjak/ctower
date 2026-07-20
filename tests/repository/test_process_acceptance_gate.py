"""Required-gate ownership for the separate-process acceptance matrix."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import cast

ROOT = Path(__file__).parents[2]
__all__: tuple[str, ...] = ()


def test_process_boundary_matrix_is_a_current_required_suite() -> None:
    manifest = tomllib.loads(
        (ROOT / "tools/checks/expected-suites.toml").read_text(encoding="utf-8")
    )
    suites = cast(list[dict[str, object]], manifest["suite"])
    matching = [suite for suite in suites if suite["id"] == "process-boundary-acceptance"]

    assert len(matching) == 1
    suite = matching[0]
    assert suite["status"] == "required"
    assert suite["phase"] == "CT-I1-004"
    command = cast(list[str], suite["command"])
    assert "tests/acceptance/increment-1/test_process_boundary.py" in command
    assert "tests/acceptance/increment-1/test_postgres_isolation.py" in command
