"""Closed online-only CLI evidence for the operator dream-lane ceremony."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from typing import Self, cast
from uuid import UUID, uuid4

import pytest

from ctower_client import CtowerClient
from ctower_client.models import (
    DreamLaneBindingReceipt,
    DreamLaneBindRequest,
    DurabilityState,
)
from ctowerctl import _dream_lane_commands, interface
from ctowerctl._output import ExitCode
from ctowerctl._parser import parse_arguments
from ctowerctl.spool import Spool

__all__: tuple[str, ...] = ()


def test_cli_executes_the_exact_binding_online_without_touching_spool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _DreamLaneClient()
    monkeypatch.setattr(interface, "CtowerClient", lambda *_args, **_kwargs: client)

    def spool_refused(*_args: object, **_kwargs: object) -> Spool:
        raise AssertionError("online-only dream-lane command touched the replay spool")

    monkeypatch.setattr(Spool, "for_origin", spool_refused)
    command_id = uuid4()
    output = io.StringIO()

    code = interface.main(
        _arguments(command_id),
        stdin=io.StringIO("ephemeral-authority\n"),
        stdout=output,
        stderr=io.StringIO(),
    )

    assert code == int(ExitCode.TEMPORARY)
    assert json.loads(output.getvalue())["lane_ref"] == "dream-lane:writer-r2881-dream"
    assert client.command_id == command_id
    assert client.request is not None
    assert client.request.model_dump() == {
        "lane_ref": "dream-lane:writer-r2881-dream",
        "crew_name": "writer-r2881-dream",
        "harness_ref": "codex",
        "model_ref": "gpt-5.6-sol",
        "reasoning_effort": "max",
        "fallback_model_ref": "qwen3.8-max",
        "model_tier": "hard",
    }


def test_cli_refuses_a_selection_outside_the_closed_registry() -> None:
    arguments = parse_arguments(_arguments(uuid4(), model="unregistered-model"))

    with pytest.raises(ValueError, match="outside the ceremony registry"):
        _dream_lane_commands.execute_online(arguments, cast("CtowerClient", _DreamLaneClient()))


def test_cli_requires_the_operator_selector_only_for_the_binding_ceremony() -> None:
    without_selector = _arguments(uuid4())
    del without_selector[2:4]

    with pytest.raises(ValueError, match="requires --as operator"):
        parse_arguments(without_selector)
    with pytest.raises(ValueError, match="only valid for dream-lane bind"):
        parse_arguments(["--as", "operator", "control", "health"])


def _arguments(command_id: UUID, *, model: str = "gpt-5.6-sol") -> list[str]:
    return [
        "--base-url",
        "https://ctower.example",
        "--as",
        "operator",
        "dream-lane",
        "bind",
        "--command-id",
        str(command_id),
        "--lane",
        "dream-lane:writer-r2881-dream",
        "--crew",
        "writer-r2881-dream",
        "--harness",
        "codex",
        "--model",
        model,
        "--effort",
        "max",
        "--fallback",
        "qwen3.8-max",
        "--tier",
        "hard",
    ]


class _DreamLaneClient:
    def __init__(self) -> None:
        self.command_id: UUID | None = None
        self.request: DreamLaneBindRequest | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def bind_dream_lane(
        self,
        request: DreamLaneBindRequest,
        *,
        command_id: UUID,
    ) -> DreamLaneBindingReceipt:
        self.command_id = command_id
        self.request = request
        return DreamLaneBindingReceipt.model_validate(
            {
                "binding_source": "operator-ceremony",
                "bound_at": datetime(2026, 8, 9, tzinfo=UTC),
                "command_id": command_id,
                "crew_name": request.crew_name,
                "durability_state": DurabilityState.DURABILITY_PENDING,
                "event_id": uuid4(),
                "harness_ref": request.harness_ref,
                "lane_ref": request.lane_ref,
                "model_family": "codex",
                "model_ref": request.model_ref,
                "model_tier": request.model_tier,
                "principal_id": uuid4(),
                "probe_evidence": "sha256:" + "a" * 64,
                "reasoning_effort": request.reasoning_effort,
            }
        )
