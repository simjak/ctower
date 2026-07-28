"""Protected public-CLI entry point for the persistent E2 shadow runtime."""

from __future__ import annotations

import argparse
import io
from typing import NoReturn

from ctower_api.development_config import load_config, load_secret
from ctowerctl import main as ctowerctl_main


def main() -> NoReturn:
    """Resolve one local identity and invoke only the generated public CLI."""

    parser = argparse.ArgumentParser(prog="ctower-shadow-ctl", add_help=False)
    parser.add_argument(
        "--as", dest="identity", choices=("operator", "commander"), default="operator"
    )
    known, remaining = parser.parse_known_args()
    if not remaining or any(
        argument == "--base-url" or argument.startswith("--base-url=") for argument in remaining
    ):
        raise SystemExit("usage: ctower-shadow-ctl [--as operator|commander] COMMAND")
    config = load_config()
    reference = (
        config.operator_secret_ref if known.identity == "operator" else config.commander_secret_ref
    )
    code = ctowerctl_main(
        ["--base-url", f"http://{config.api_host}:{config.api_port}", *remaining],
        stdin=io.StringIO(load_secret(reference) + "\n"),
    )
    raise SystemExit(code)
