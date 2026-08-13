"""Protected public-CLI entry point for the persistent E2 shadow runtime."""

from __future__ import annotations

import argparse
import io
from typing import NoReturn

from ctower_api.development_config import load_config
from ctower_api.development_secrets import load_secret
from ctowerctl import main as ctowerctl_main

_BASE_URL_OPTION = "--base-url"
_LONG_OPTION_MARKER = "--"


def main() -> NoReturn:
    """Resolve one local identity and invoke only the generated public CLI."""

    parser = argparse.ArgumentParser(
        prog="ctower-shadow-ctl",
        add_help=False,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--as", dest="identity", choices=("operator", "commander"), default="operator"
    )
    known, remaining = parser.parse_known_args()
    if not remaining or any(_is_base_url_override(argument) for argument in remaining):
        raise SystemExit("usage: ctower-shadow-ctl [--as operator|commander] COMMAND")
    config = load_config()
    reference = (
        config.operator_secret_ref if known.identity == "operator" else config.commander_secret_ref
    )
    ceremony_principal = ["--as", known.identity] if remaining[:2] == ["dream-lane", "bind"] else []
    code = ctowerctl_main(
        [
            "--base-url",
            f"http://{config.api_host}:{config.api_port}",
            *ceremony_principal,
            *remaining,
        ],
        stdin=io.StringIO(load_secret(reference) + "\n"),
    )
    raise SystemExit(code)


def _is_base_url_override(argument: str) -> bool:
    option = argument.partition("=")[0]
    return (
        option != _LONG_OPTION_MARKER
        and option.startswith(_LONG_OPTION_MARKER)
        and _BASE_URL_OPTION.startswith(option)
    )
