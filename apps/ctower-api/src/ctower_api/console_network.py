"""Private-bind validation and machine-readable ``ss`` sweep parsing."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

__all__ = [
    "ConsoleListenerError",
    "ConsoleListenerSweep",
    "inspect_ss_sweep",
    "validate_bind_host",
]

_TAILSCALE_V4 = ipaddress.ip_network("100.64.0.0/10")
_TAILSCALE_V6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")
_LOCAL_ENDPOINT = re.compile(r"\s(?P<endpoint>\[[^]]+\]:\d+|\S+:\d+)\s")
_WILDCARD_V4 = ipaddress.IPv4Address(0).compressed
_WILDCARD_V6 = ipaddress.IPv6Address(0).compressed


class ConsoleListenerError(ValueError):
    """The configured console listener could be publicly reachable."""


@dataclass(frozen=True, slots=True)
class ConsoleListenerSweep:
    """Exact console-port findings retained from one ``ss -tlnp`` snapshot."""

    private_listeners: tuple[str, ...]
    wildcard_listeners: tuple[str, ...]


def validate_bind_host(host: str) -> str:
    """Admit only loopback or literal Tailscale address space; no DNS defaults."""

    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise ConsoleListenerError("console bind host must be a literal private address") from error
    if address.is_loopback or address in _TAILSCALE_V4 or address in _TAILSCALE_V6:
        return host
    raise ConsoleListenerError("console bind host must be loopback or tailnet-only")


def inspect_ss_sweep(ss_output: str, *, console_ports: frozenset[int]) -> ConsoleListenerSweep:
    """Classify every listener on a declared console port, including docker-proxy."""

    private: list[str] = []
    wildcard: list[str] = []
    for line in ss_output.splitlines():
        match = _LOCAL_ENDPOINT.search(line)
        if match is None:
            continue
        endpoint = match.group("endpoint")
        host, separator, port_text = endpoint.rpartition(":")
        if not separator or not port_text.isdigit() or int(port_text) not in console_ports:
            continue
        normalized_host = host.removeprefix("[").removesuffix("]")
        if normalized_host in {_WILDCARD_V4, _WILDCARD_V6, "*"}:
            wildcard.append(endpoint)
            continue
        try:
            validate_bind_host(normalized_host)
        except ConsoleListenerError:
            wildcard.append(endpoint)
        else:
            private.append(endpoint)
    return ConsoleListenerSweep(
        private_listeners=tuple(private), wildcard_listeners=tuple(wildcard)
    )
