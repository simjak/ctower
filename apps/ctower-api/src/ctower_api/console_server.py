"""Fail-closed direct-HTTPS server composition for the private Console listener."""

from __future__ import annotations

import ssl
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from ctower_api.console_routes import ConsoleRuntime

__all__ = ["serve_console"]


def serve_console(
    app: FastAPI,
    runtime: ConsoleRuntime,
    *,
    certificate_file: Path,
    private_key_file: Path,
) -> None:
    """Serve only the literal private endpoint embedded in the exact HTTPS origin."""

    uvicorn.run(
        app,
        host=runtime.listener_host,
        port=runtime.listener_port,
        ssl_certfile=str(certificate_file),
        ssl_keyfile=str(private_key_file),
        ssl_version=ssl.PROTOCOL_TLS_SERVER,
        proxy_headers=False,
        forwarded_allow_ips="",
        server_header=False,
        access_log=False,
    )
