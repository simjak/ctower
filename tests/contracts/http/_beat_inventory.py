"""Expected CLI metadata for fleet-beat HTTP operations."""

from __future__ import annotations

BEAT_OPERATION_METADATA: dict[str, tuple[object, bool, str, object, bool]] = {
    "listBeatDispatchEffects": ("beat-dispatch list", False, "forbidden", None, False),
    "listBeatRoutines": ("beat-dispatch routines", False, "forbidden", None, False),
    "retireBeatRoutine": ("beat-dispatch retire", True, "forbidden", "operator", False),
}

BEAT_PROBLEM_CODES = {
    "beat-routine-already-retired",
    "beat-routine-not-found",
    "beat-routine-retire-forbidden",
}
