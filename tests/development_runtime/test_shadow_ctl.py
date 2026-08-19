"""Protected shadow-CLI forwarding regressions for the E2 development runtime."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from types import FunctionType
from typing import Literal, Self, TextIO, cast
from uuid import UUID

import pytest
from pydantic import BaseModel

import tools.development_runtime.ctl as shadow_ctl

__all__: tuple[str, ...] = ()

_R2948_COMMAND_ID = UUID("46ab63d6-f7a3-40d1-815f-aff7a0bc4abe")
_R2948_EVENT_ID = UUID("019ff8ba-6f34-7da0-9d91-8ade1ad316a3")
_R2948_PRINCIPAL_ID = UUID("019fad30-d644-7536-8b9c-48d30a87a7e5")
_R2948_PROBE_EVIDENCE = "sha256:a5fac2cbbd9311b1a1e8efa37f15e57605606a164ddbfd5b085ddd1091576806"
_USAGE_EXIT_CODE = 64


def test_shadow_ctl_dispatches_the_recorded_r2948_operator_bind(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = _DreamLaneClient()
    loaded_references: list[str] = []
    monkeypatch.setattr(
        shadow_ctl,
        "load_config",
        _shadow_config,
    )

    def load_secret(reference: str) -> str:
        loaded_references.append(reference)
        return "recorded-operator-authority"

    monkeypatch.setattr(shadow_ctl, "load_secret", load_secret)
    ctowerctl_main = cast(FunctionType, shadow_ctl.main.__globals__["ctowerctl_main"])
    monkeypatch.setitem(
        ctowerctl_main.__globals__,
        "CtowerClient",
        lambda base_url, *, credential: client.bind(base_url, credential),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["ctower-shadow-ctl", *_r2948_arguments("operator")],
    )

    with pytest.raises(SystemExit) as raised:
        shadow_ctl.main()

    assert raised.value.code == 0
    assert loaded_references == ["secret-service:ctower-development/operator"]
    assert client.base_url == "http://127.0.0.1:8091"
    assert client.credential == "recorded-operator-authority"
    assert client.command_id == _R2948_COMMAND_ID
    assert client.request == {
        "lane_ref": "dream-lane:writer-r2881-dream",
        "crew_name": "writer-r2881-dream",
        "harness_ref": "codex",
        "model_ref": "gpt-5.6-sol",
        "reasoning_effort": "max",
        "fallback_model_ref": "qwen3.8-max",
        "model_tier": "hard",
    }
    assert json.loads(capsys.readouterr().out) == {
        "binding_source": "operator-ceremony",
        "bound_at": "2026-08-13T01:26:35.572441Z",
        "command_id": str(_R2948_COMMAND_ID),
        "crew_name": "writer-r2881-dream",
        "durability_state": "accepted",
        "event_id": str(_R2948_EVENT_ID),
        "harness_ref": "codex",
        "lane_ref": "dream-lane:writer-r2881-dream",
        "model_family": "codex",
        "model_ref": "gpt-5.6-sol",
        "model_tier": "hard",
        "principal_id": str(_R2948_PRINCIPAL_ID),
        "probe_evidence": _R2948_PROBE_EVIDENCE,
        "reasoning_effort": "max",
    }


@pytest.mark.parametrize(
    ("arguments", "remaining", "secret_reference"),
    [
        (
            ["spool", "status"],
            ["spool", "status"],
            "secret-service:ctower-development/operator",
        ),
        (
            ["spool", "list"],
            ["spool", "list"],
            "secret-service:ctower-development/operator",
        ),
        (
            ["--as", "commander", "dream-dispatch", "list"],
            ["dream-dispatch", "list"],
            "secret-service:ctower-development/commander",
        ),
        (
            ["ticket", "query", "019ff8ba-6f34-7da0-9d91-8ade1ad316a3"],
            ["ticket", "query", "019ff8ba-6f34-7da0-9d91-8ade1ad316a3"],
            "secret-service:ctower-development/operator",
        ),
    ],
)
def test_shadow_ctl_keeps_non_ceremony_arguments_byte_identical(
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
    remaining: list[str],
    secret_reference: str,
) -> None:
    calls: list[tuple[list[str], str]] = []
    loaded_references: list[str] = []
    monkeypatch.setattr(shadow_ctl, "load_config", _shadow_config)

    def load_secret(reference: str) -> str:
        loaded_references.append(reference)
        return "selected-authority"

    def ctowerctl_main(
        forwarded: Sequence[str] | None = None,
        *,
        stdin: TextIO | None = None,
        **_streams: TextIO,
    ) -> int:
        assert stdin is not None
        calls.append((list(forwarded or ()), stdin.read()))
        return 0

    monkeypatch.setattr(shadow_ctl, "load_secret", load_secret)
    monkeypatch.setattr(shadow_ctl, "ctowerctl_main", ctowerctl_main)
    monkeypatch.setattr(sys, "argv", ["ctower-shadow-ctl", *arguments])

    with pytest.raises(SystemExit) as raised:
        shadow_ctl.main()

    assert raised.value.code == 0
    assert loaded_references == [secret_reference]
    assert calls == [
        (
            ["--base-url", "http://127.0.0.1:8091", *remaining],
            "selected-authority\n",
        )
    ]


def test_shadow_ctl_forwards_the_selected_commander_identity_for_a_bind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forwarded: list[str] = []
    monkeypatch.setattr(shadow_ctl, "load_config", _shadow_config)
    monkeypatch.setattr(shadow_ctl, "load_secret", lambda _reference: "commander-authority")

    def ctowerctl_main(
        arguments: Sequence[str] | None = None,
        *,
        stdin: TextIO | None = None,
        **_streams: TextIO,
    ) -> int:
        assert stdin is not None
        assert stdin.read() == "commander-authority\n"
        forwarded.extend(arguments or ())
        return 64

    monkeypatch.setattr(shadow_ctl, "ctowerctl_main", ctowerctl_main)
    monkeypatch.setattr(sys, "argv", ["ctower-shadow-ctl", *_r2948_arguments("commander")])

    with pytest.raises(SystemExit) as raised:
        shadow_ctl.main()

    assert raised.value.code == _USAGE_EXIT_CODE
    assert forwarded == [
        "--base-url",
        "http://127.0.0.1:8091",
        "--as",
        "commander",
        *_r2948_arguments("commander")[2:],
    ]


def test_shadow_ctl_refuses_no_command_before_loading_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        shadow_ctl,
        "load_config",
        lambda: (_ for _ in ()).throw(AssertionError("config must not be loaded")),
    )
    monkeypatch.setattr(sys, "argv", ["ctower-shadow-ctl"])

    with pytest.raises(SystemExit, match="usage: ctower-shadow-ctl"):
        shadow_ctl.main()


def _shadow_config() -> _ShadowConfig:
    return _ShadowConfig(
        "127.0.0.1",
        8091,
        "secret-service:ctower-development/operator",
        "secret-service:ctower-development/commander",
    )


def _r2948_arguments(identity: str) -> list[str]:
    return [
        "--as",
        identity,
        "dream-lane",
        "bind",
        "--command-id",
        str(_R2948_COMMAND_ID),
        "--lane",
        "dream-lane:writer-r2881-dream",
        "--crew",
        "writer-r2881-dream",
        "--harness",
        "codex",
        "--model",
        "gpt-5.6-sol",
        "--effort",
        "max",
        "--fallback",
        "qwen3.8-max",
        "--tier",
        "hard",
    ]


class _RecordedDreamLaneReceipt(BaseModel):
    binding_source: Literal["operator-ceremony"]
    bound_at: datetime
    command_id: UUID
    crew_name: str
    durability_state: Literal["accepted"]
    event_id: UUID
    harness_ref: Literal["codex"]
    lane_ref: str
    model_family: Literal["codex"]
    model_ref: Literal["gpt-5.6-sol"]
    model_tier: Literal["hard"]
    principal_id: UUID
    probe_evidence: str
    reasoning_effort: Literal["max"]


@dataclass(frozen=True, slots=True)
class _ShadowConfig:
    api_host: str
    api_port: int
    operator_secret_ref: str
    commander_secret_ref: str


class _DreamLaneClient:
    def __init__(self) -> None:
        self.base_url: str | None = None
        self.credential: str | None = None
        self.command_id: UUID | None = None
        self.request: dict[str, object] | None = None

    def bind(self, base_url: str, credential: str) -> Self:
        self.base_url = base_url
        self.credential = credential
        return self

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def bind_dream_lane(self, request: object, *, command_id: UUID) -> _RecordedDreamLaneReceipt:
        self.command_id = command_id
        self.request = cast(BaseModel, request).model_dump()
        return _RecordedDreamLaneReceipt(
            binding_source="operator-ceremony",
            bound_at=datetime(2026, 8, 13, 1, 26, 35, 572441, tzinfo=UTC),
            command_id=command_id,
            crew_name=cast(str, self.request["crew_name"]),
            durability_state="accepted",
            event_id=_R2948_EVENT_ID,
            harness_ref="codex",
            lane_ref=cast(str, self.request["lane_ref"]),
            model_family="codex",
            model_ref="gpt-5.6-sol",
            model_tier="hard",
            principal_id=_R2948_PRINCIPAL_ID,
            probe_evidence=_R2948_PROBE_EVIDENCE,
            reasoning_effort="max",
        )
