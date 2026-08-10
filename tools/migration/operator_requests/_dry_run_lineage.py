"""Replay validation for append-only Mission Control Request lineages."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping
from itertools import pairwise
from typing import cast

from tools.migration.operator_requests._dry_run_source import (
    SourceLine,
    optional_text,
    request_id,
    source_timestamp,
    status,
)

__all__ = ["latest_and_lineage"]

_REQUEST_ID = re.compile(r"^R([1-9][0-9]*)$")
_SOURCE_REQUEST_ID = re.compile(r"^R(0*[1-9][0-9]*)$")
_OPEN = frozenset({"NEW", "TRIAGED", "WIP", "BLOCKED"})
_TERMINAL = frozenset({"DONE", "SUPERSEDED", "MERGED", "WONT-DO"})


def latest_and_lineage(rows: list[SourceLine]) -> tuple[dict[str, SourceLine], list[str]]:
    grouped: dict[str, list[SourceLine]] = defaultdict(list)
    blockers: list[str] = []
    for item in rows:
        source_id = request_id(item.value)
        if _SOURCE_REQUEST_ID.fullmatch(source_id) is None:
            blockers.append(f"request-id-invalid:{item.line_number}")
            continue
        if _REQUEST_ID.fullmatch(source_id) is None:
            blockers.append(f"request-id-noncanonical:{source_id}")
        grouped[source_id].append(item)
    for source_id, lineage in grouped.items():
        blockers.extend(_lineage_blockers(source_id, lineage))
    return {source_id: lineage[-1] for source_id, lineage in grouped.items()}, blockers


def _lineage_blockers(source_id: str, lineage: list[SourceLine]) -> list[str]:
    problems = _immutable_field_blockers(source_id, lineage)
    problems.extend(_project_blockers(source_id, lineage))
    problems.extend(_history_blockers(source_id, lineage))
    return problems


def _immutable_field_blockers(source_id: str, lineage: list[SourceLine]) -> list[str]:
    problems: list[str] = []
    if _diverged(lineage, "text"):
        problems.append(f"lineage-text-diverged:{source_id}")
    if _diverged(lineage, "created"):
        problems.append(f"lineage-created-diverged:{source_id}")
    return problems


def _diverged(lineage: list[SourceLine], field: str) -> bool:
    values = {optional_text(item.value.get(field)) for item in lineage}
    return len(values) != 1 or None in values


def _project_blockers(source_id: str, lineage: list[SourceLine]) -> list[str]:
    problems: list[str] = []
    project: str | None = None
    for item in lineage:
        observed = optional_text(item.value.get("project"))
        problem = _project_problem(project, observed)
        if problem is not None:
            problems.append(f"{problem}:{source_id}")
        if observed is not None:
            project = observed
    return problems


def _project_problem(previous: str | None, observed: str | None) -> str | None:
    if previous is not None and observed is None:
        return "lineage-project-regressed"
    if previous is not None and observed != previous:
        return "lineage-project-diverged"
    return None


def _history_blockers(source_id: str, lineage: list[SourceLine]) -> list[str]:
    histories = [item.value.get("history") for item in lineage]
    if any(not isinstance(history, list) or not history for history in histories):
        return [f"lineage-history-missing:{source_id}"]
    typed = [cast(list[object], history) for history in histories]
    problems = _history_schema_blockers(source_id, typed)
    problems.extend(_history_progression_blockers(source_id, typed))
    problems.extend(_history_row_blockers(source_id, lineage, typed))
    return problems


def _history_schema_blockers(source_id: str, histories: list[list[object]]) -> list[str]:
    return [
        f"{problem}:{source_id}"
        for history in histories
        if (problem := _history_schema_problem(history)) is not None
    ]


def _history_progression_blockers(source_id: str, histories: list[list[object]]) -> list[str]:
    problems: list[str] = []
    for previous, current in pairwise(histories):
        if previous != current[: len(previous)]:
            problems.append(f"lineage-history-fork:{source_id}")
        elif len(current) <= len(previous):
            problems.append(f"lineage-history-no-causal-advance:{source_id}")
    return problems


def _history_row_blockers(
    source_id: str,
    lineage: list[SourceLine],
    histories: list[list[object]],
) -> list[str]:
    problems: list[str] = []
    for item, history in zip(lineage, histories, strict=True):
        problems.extend(_history_row_problem(source_id, item, history))
    return problems


def _history_row_problem(source_id: str, item: SourceLine, history: list[object]) -> list[str]:
    problems: list[str] = []
    state = _history_state(history)
    if state is not None and state != status(item.value.get("status")):
        problems.append(f"lineage-history-field-mismatch:{source_id}")
    final = cast(dict[str, object], history[-1]) if isinstance(history[-1], dict) else {}
    if source_timestamp(item.value.get("updated")) != source_timestamp(final.get("at")):
        problems.append(f"lineage-history-timestamp-mismatch:{source_id}")
    return problems


def _history_schema_problem(history: list[object]) -> str | None:
    state: str | None = None
    previous_at: str | None = None
    for index, value in enumerate(history):
        problem, previous_at, state = _history_event_problem(
            value,
            index,
            state,
            previous_at,
        )
        if problem is not None:
            return problem
    return None


def _history_event_problem(
    value: object,
    index: int,
    state: str | None,
    previous_at: str | None,
) -> tuple[str | None, str | None, str | None]:
    if not isinstance(value, dict):
        return "lineage-history-event-invalid", None, state
    problem, timestamp = _history_event_header(value, previous_at)
    if problem is not None:
        return problem, timestamp, state
    if index == 0:
        return _creation_event(value, timestamp, state)
    event = value.get("event")
    return _transition_problem(value, event, state), timestamp, status(value.get("to"))


def _history_event_header(
    value: Mapping[str, object], previous_at: str | None
) -> tuple[str | None, str | None]:
    fields = value.get("event"), value.get("actor"), value.get("at")
    if not all(isinstance(item, str) and item.strip() for item in fields):
        return "lineage-history-event-invalid", None
    timestamp = source_timestamp(value.get("at"))
    if timestamp is None or (previous_at is not None and timestamp < previous_at):
        return "lineage-history-order-invalid", timestamp
    return None, timestamp


def _creation_event(
    value: Mapping[str, object], timestamp: str | None, state: str | None
) -> tuple[str | None, str | None, str | None]:
    valid = value.get("event") == "created"
    valid = valid and value.get("to") == "NEW" and value.get("from") is None
    if valid:
        return None, timestamp, "NEW"
    return "lineage-creation-invalid", timestamp, state


def _transition_problem(item: Mapping[str, object], event: object, state: str | None) -> str | None:
    if event == "created":
        return "lineage-second-creation"
    if event not in {"status_set", "merged", "wont_do"}:
        return "lineage-history-event-unknown"
    target = status(item.get("to"))
    valid = item.get("field") == "status" and status(item.get("from")) == state
    return None if valid and target in _OPEN | _TERMINAL else "lineage-history-transition-invalid"


def _history_state(history: list[object]) -> str | None:
    if _history_schema_problem(history) is not None:
        return None
    return status(cast(dict[str, object], history[-1]).get("to"))
