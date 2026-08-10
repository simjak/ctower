"""RED-first tests for fail-closed console bind validation and archived ss sweeps."""

from __future__ import annotations

import pytest

from ctower_api._console_network import ConsoleListenerProblem, inspect_ss_sweep, validate_bind_host


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "100.84.252.114", "fd7a:115c:a1e0::1"])
def test_loopback_and_tailnet_bind_hosts_are_admitted(host: str) -> None:
    assert validate_bind_host(host) == host


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.0.2.10", "example.com"])
def test_wildcard_public_and_hostname_binds_fail_closed(host: str) -> None:
    with pytest.raises(ConsoleListenerProblem):
        validate_bind_host(host)


def test_ss_sweep_detects_direct_and_docker_proxy_wildcard_console_ports() -> None:
    direct = 'LISTEN 0 2048 0.0.0.0:8443 0.0.0.0:* users:(("uvicorn",pid=4,fd=3))'
    proxy = 'LISTEN 0 4096 [::]:8443 [::]:* users:(("docker-proxy",pid=5,fd=4))'
    assert inspect_ss_sweep(direct, console_ports=frozenset({8443})).wildcard_listeners
    assert inspect_ss_sweep(proxy, console_ports=frozenset({8443})).wildcard_listeners


def test_ss_sweep_retains_positive_tailnet_inventory_without_false_wildcard() -> None:
    output = (
        'LISTEN 0 2048 100.84.252.114:8443 0.0.0.0:* users:(("uvicorn",pid=4,fd=3))\n'
        'LISTEN 0 2048 127.0.0.1:8091 0.0.0.0:* users:(("uvicorn",pid=6,fd=3))\n'
    )
    result = inspect_ss_sweep(output, console_ports=frozenset({8443}))
    assert not result.wildcard_listeners
    assert result.private_listeners == ("100.84.252.114:8443",)

