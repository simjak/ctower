"""Removal of orphaned runtime-replacement directories left by an interrupted upgrade.

`_replace_runtime` (installation.py) builds a candidate under a sibling
`runtime-replacement-<uuid>` pathname and only links it into `runtime`/`runtime-previous` once
it is fully built and verified. An uncatchable termination (SIGKILL) during that build leaves the
sibling directory on disk with nothing referencing it; nothing later inventories or removes it.
This module is that later inventory pass, run under the same directory lock the installer and
rollback verbs use so it can never race a change in progress.
"""

from __future__ import annotations

import fcntl
import os
import shutil
from pathlib import Path

from tools.development_runtime.installation import runtime_home, runtime_previous

__all__ = ["reconcile_runtime"]

_REPLACEMENT_GLOB = "runtime-replacement-*"


def reconcile_runtime() -> dict[str, object]:
    """Remove `runtime-replacement-*` siblings not referenced by `runtime`/`runtime-previous`."""

    home = runtime_home()
    parent = home.parent
    if not parent.is_dir():
        return {"schema": "ctower.runtime-reconcile/v1", "removed": []}
    removed: list[str] = []
    directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        fcntl.flock(directory, fcntl.LOCK_EX)
        live = _live_replacement_names(home)
        for candidate in sorted(parent.glob(_REPLACEMENT_GLOB)):
            if candidate.name in live or candidate.is_symlink() or not candidate.is_dir():
                continue
            shutil.rmtree(candidate)
            removed.append(candidate.name)
    finally:
        os.close(directory)
    return {"schema": "ctower.runtime-reconcile/v1", "removed": removed}


def _live_replacement_names(home: Path) -> set[str]:
    names: set[str] = set()
    for path in (home, runtime_previous()):
        if not path.is_symlink():
            continue
        target = path.readlink()
        if target.is_absolute() or target.parent != Path():
            continue
        names.add(target.name)
    return names
