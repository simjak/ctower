"""Parser builders for dispatch and lane-binding command families."""

from __future__ import annotations

import argparse
from uuid import UUID

from ctowerctl._argument_types import _sha256_digest
from ctowerctl._parser_support import _command_id, _Parser


def dream_dispatch_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    list_parser = actions.add_parser("list")
    list_parser.set_defaults(cli_name="dream-dispatch list")
    consume = actions.add_parser("consume")
    consume.set_defaults(cli_name="dream-dispatch consume")
    _command_id(consume)
    consume.add_argument("effect_id", type=UUID)
    consume.add_argument("--output-digest", required=True, type=_sha256_digest)


def dream_lane_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    bind = actions.add_parser("bind")
    bind.set_defaults(cli_name="dream-lane bind")
    _command_id(bind)
    bind.add_argument("--lane", dest="lane_ref", required=True)
    bind.add_argument("--crew", dest="crew_name", required=True)
    bind.add_argument("--harness", dest="harness_ref", required=True)
    bind.add_argument("--model", dest="model_ref", required=True)
    bind.add_argument("--effort", dest="reasoning_effort", required=True)
    bind.add_argument("--fallback", dest="fallback_model_ref", required=True)
    bind.add_argument("--tier", dest="model_tier", required=True)
