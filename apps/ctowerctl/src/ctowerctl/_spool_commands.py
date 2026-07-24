"""Local encrypted spool status, drain, and explicit disposition commands."""

from __future__ import annotations

import argparse
from typing import Literal, TextIO, cast

from pydantic import BaseModel, ConfigDict

from ctower_client import CtowerClient
from ctowerctl._auth import read_authority
from ctowerctl._generated_replay import GeneratedReplayExecutor
from ctowerctl._output import ExitCode
from ctowerctl.spool import Spool, SpoolEntry, SpoolState

__all__: tuple[str, ...] = ()


class _OutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SpoolEntries(_OutputModel):
    entries: tuple[SpoolEntry, ...]


class SpoolDisposition(_OutputModel):
    action: Literal["retry", "discard"]
    sequence: int


def execute(
    base_url: str,
    arguments: argparse.Namespace,
    authority_stream: TextIO,
) -> tuple[BaseModel, ExitCode]:
    """Execute one closed local spool operation."""

    spool = Spool.for_origin(base_url)
    command = cast(str, arguments.local_command)
    if command == "spool status":
        return _status(spool)
    if command in {"spool list", "spool quarantine list"}:
        return _list(spool, command, arguments)
    if command == "spool doctor":
        return _doctor(spool)
    return _modify(spool, base_url, command, arguments, authority_stream)


def _status(spool: Spool) -> tuple[BaseModel, ExitCode]:
    status = spool.status()
    healthy = status.chain_status == "healthy" and status.health != "state_unknown"
    return status, ExitCode.SUCCESS if healthy else ExitCode.LOCAL_FAILURE


def _list(
    spool: Spool,
    command: str,
    arguments: argparse.Namespace,
) -> tuple[BaseModel, ExitCode]:
    state = (
        SpoolState.QUARANTINE
        if command == "spool quarantine list"
        else _state(cast(str | None, arguments.state))
    )
    entries = spool.list_entries(state, limit=cast(int, arguments.limit))
    return SpoolEntries(entries=entries), ExitCode.SUCCESS


def _doctor(spool: Spool) -> tuple[BaseModel, ExitCode]:
    doctor = spool.doctor()
    return doctor, ExitCode.SUCCESS if doctor.healthy else ExitCode.LOCAL_FAILURE


def _modify(
    spool: Spool,
    base_url: str,
    command: str,
    arguments: argparse.Namespace,
    authority_stream: TextIO,
) -> tuple[BaseModel, ExitCode]:
    if command == "spool drain":
        with CtowerClient(base_url, credential=read_authority(authority_stream)) as client:
            report = spool.drain(GeneratedReplayExecutor(client))
        return report, _drain_code(report.remaining_pending, report.barrier_sequence)
    if command == "spool retry":
        entry = spool.retry(cast(int, arguments.sequence), cast(str, arguments.reason))
        return entry, ExitCode.SUCCESS
    if command == "spool discard":
        sequence = cast(int, arguments.sequence)
        spool.discard(sequence, cast(str, arguments.reason))
        return SpoolDisposition(action="discard", sequence=sequence), ExitCode.SUCCESS
    raise ValueError("usage: unsupported local spool command")


def _state(value: str | None) -> SpoolState | None:
    return SpoolState(value) if value is not None else None


def _drain_code(remaining: int, barrier: int | None) -> ExitCode:
    if barrier is not None:
        return ExitCode.PERMANENT
    if remaining:
        return ExitCode.TEMPORARY
    return ExitCode.SUCCESS
