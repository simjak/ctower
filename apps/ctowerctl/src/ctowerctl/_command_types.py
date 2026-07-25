"""Small internal command plans shared by explicit CLI families."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

__all__: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MutationPayload:
    """One generated request plus its exact authored path parameters."""

    request: BaseModel
    path_parameters: dict[str, str]
