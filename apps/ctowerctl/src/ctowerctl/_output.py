"""Stable machine output and process exit semantics for ctowerctl."""

from __future__ import annotations

import json
from enum import IntEnum
from typing import Annotated, Literal, TextIO
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ctowerctl.spool import ServerRefusal

__all__: tuple[str, ...] = ()

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None
type JsonObject = dict[str, JsonValue]


class ExitCode(IntEnum):
    """Process results fixed by the protected CLI contract."""

    SUCCESS = 0
    USAGE = 64
    PERMANENT = 69
    LOCAL_FAILURE = 74
    TEMPORARY = 75


class _OutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CommandOutcome(_OutputModel):
    """Stable local disposition for one durable-before-send mutation."""

    command_id: UUID
    state: Literal["accepted", "queued", "quarantined", "local_failure"]
    reason_code: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
    sequence: int | None
    result: JsonObject | None = None
    server_refusal: ServerRefusal | None = None


class LocalFailure(_OutputModel):
    """Redacted local failure when no authoritative result is available."""

    command_id: UUID | None
    state: Literal["local_failure"] = "local_failure"
    reason_code: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]


def write_json(stream: TextIO, result: BaseModel) -> None:
    """Write one deterministic generated or local model."""

    stream.write(
        json.dumps(
            result.model_dump(mode="json", by_alias=True, exclude_none=True),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )


def write_text(stream: TextIO, text: str) -> None:
    """Write already-canonical text exactly once."""

    stream.write(text)


def reason_code(value: str) -> str:
    """Normalize one local exception code without exposing detail."""

    normalized = "".join(
        character if character.isalnum() else "_" for character in value.casefold()
    )
    result = "_".join(part for part in normalized.split("_") if part) or "local_failure"
    if not result[0].isalpha():
        result = f"local_{result}"
    return result[:64]
