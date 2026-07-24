"""Command-line boundary for source validation, rendering, and host preflight."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Literal, cast

from tools.cp3d_packet.compose import ComposeRenderError, render_compose_config
from tools.cp3d_packet.interface import PacketError, canonical_manifest, load_bindings
from tools.cp3d_packet.models import PacketBindings
from tools.cp3d_packet.preflight import (
    PreflightError,
    validate_binding_document,
    validate_local_role,
)

__all__ = ["main"]

Role = Literal["primary", "standby"]
ROLES: tuple[Role, ...] = ("primary", "standby")


def main(argv: list[str] | None = None) -> int:
    """Run one bounded packet action and never echo rejected input values."""
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        bindings = load_bindings(arguments.bindings)
        if arguments.action == "validate":
            sys.stdout.buffer.write(canonical_manifest(bindings, {}))
            return 0
        if arguments.action == "compose-config":
            role = cast("Role", arguments.role)
            document = render_compose_config(
                _compose_path(arguments.packet_root, role), role, bindings
            )
            sys.stdout.write(_canonical_json(document))
            return 0
        documents = _render_both(arguments.packet_root, bindings)
        if arguments.action == "preflight":
            validate_binding_document(arguments.bindings)
            validate_local_role(bindings, cast("Role", arguments.role))
        sys.stdout.buffer.write(canonical_manifest(bindings, documents))
    except (ComposeRenderError, PacketError, PreflightError) as error:
        print(f"cp3d-packet: {error}", file=sys.stderr)
        return 2
    return 0


def _parser() -> argparse.ArgumentParser:
    packet_root = Path(__file__).parents[2] / "deploy/private-vps/cp3d"
    parser = argparse.ArgumentParser(prog="python -m tools.cp3d_packet")
    actions = parser.add_subparsers(dest="action", required=True)
    for action in ("validate", "render"):
        command = actions.add_parser(action)
        _common_arguments(command, packet_root)
    compose = actions.add_parser("compose-config")
    _common_arguments(compose, packet_root)
    compose.add_argument("--role", choices=("primary", "standby"), required=True)
    preflight = actions.add_parser("preflight")
    _common_arguments(preflight, packet_root)
    preflight.add_argument("--role", choices=("primary", "standby"), required=True)
    return parser


def _common_arguments(parser: argparse.ArgumentParser, packet_root: Path) -> None:
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--packet-root", type=Path, default=packet_root)


def _render_both(
    packet_root: Path,
    bindings: PacketBindings,
) -> dict[str, dict[str, Any]]:
    return {
        role: render_compose_config(_compose_path(packet_root, role), role, bindings)
        for role in ROLES
    }


def _compose_path(packet_root: Path, role: Role) -> Path:
    return packet_root / f"{role}.compose.yaml"


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
