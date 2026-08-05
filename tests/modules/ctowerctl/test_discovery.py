"""Found/missing/ambiguous/invalid branch coverage for env-free instance discovery."""

from __future__ import annotations

import argparse
import io
from pathlib import Path

import pytest

from ctowerctl import discovery, interface
from ctowerctl._output import ExitCode

__all__: tuple[str, ...] = ()

_OWNER_ONLY_FILE_MODE = 0o600


def _catalog(*instances: dict[str, object]) -> discovery.CliInstanceCatalog:
    return discovery.CliInstanceCatalog.model_validate(
        {"schema": "ctower.cli-instances/v1", "instances": instances}
    )


def test_missing_catalog_refuses_by_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    with pytest.raises(discovery.DiscoveryError, match="no ctower instance is configured") as error:
        discovery.resolve_base_url()

    assert error.value.reason == "missing"


def test_empty_catalog_refuses_as_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    discovery.write_catalog(_catalog())

    with pytest.raises(discovery.DiscoveryError, match="declares no instance") as error:
        discovery.resolve_base_url()

    assert error.value.reason == "missing"


def test_one_instance_resolves(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = discovery.write_catalog(
        _catalog({"name": "development", "base_url": "http://127.0.0.1:8091"})
    )

    assert path == discovery.catalog_path()
    assert path.stat().st_mode & 0o777 == _OWNER_ONLY_FILE_MODE
    assert discovery.resolve_base_url() == "http://127.0.0.1:8091"


def test_two_instances_are_ambiguous(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    discovery.write_catalog(
        _catalog(
            {"name": "development", "base_url": "http://127.0.0.1:8091"},
            {"name": "staging", "base_url": "http://127.0.0.1:8092"},
        )
    )

    with pytest.raises(discovery.DiscoveryError, match="declares 2 instances") as error:
        discovery.resolve_base_url()

    assert error.value.reason == "ambiguous"
    assert "development" in str(error.value)
    assert "staging" in str(error.value)


def test_malformed_catalog_is_invalid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    catalog_path = discovery.catalog_path()
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_text("not json", encoding="utf-8")

    with pytest.raises(discovery.DiscoveryError, match="is not a valid instance catalog") as error:
        discovery.resolve_base_url()

    assert error.value.reason == "invalid"


def test_instance_rejects_a_non_loopback_http_url() -> None:
    with pytest.raises(ValueError, match="loopback"):
        discovery.CliInstance.model_validate(
            {"name": "remote", "base_url": "http://ctower.example"}
        )


def test_main_resolves_omitted_base_url_from_the_catalog(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    discovery.write_catalog(_catalog({"name": "development", "base_url": "http://127.0.0.1:8091"}))
    observed: list[str | None] = []

    def _capture(
        arguments: argparse.Namespace,
        _input_stream: object,
        _output_stream: object,
        _error_stream: object,
    ) -> int:
        observed.append(arguments.base_url)
        return int(ExitCode.SUCCESS)

    monkeypatch.setattr(interface, "_run_command", _capture)

    code = interface.main(["control", "health"])

    assert code == int(ExitCode.SUCCESS)
    assert observed == ["http://127.0.0.1:8091"]


def test_main_reports_a_named_usage_error_when_discovery_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    stderr = io.StringIO()

    code = interface.main(["control", "health"], stderr=stderr)

    assert code == int(ExitCode.USAGE)
    assert stderr.getvalue().startswith("usage: no ctower instance is configured")


def test_main_reports_a_named_usage_error_when_discovery_is_ambiguous(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    discovery.write_catalog(
        _catalog(
            {"name": "development", "base_url": "http://127.0.0.1:8091"},
            {"name": "staging", "base_url": "http://127.0.0.1:8092"},
        )
    )
    stderr = io.StringIO()

    code = interface.main(["control", "health"], stderr=stderr)

    assert code == int(ExitCode.USAGE)
    assert "declares 2 instances" in stderr.getvalue()


def test_main_never_consults_discovery_when_base_url_is_explicit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    observed: list[str | None] = []

    def _capture(
        arguments: argparse.Namespace,
        _input_stream: object,
        _output_stream: object,
        _error_stream: object,
    ) -> int:
        observed.append(arguments.base_url)
        return int(ExitCode.SUCCESS)

    monkeypatch.setattr(interface, "_run_command", _capture)

    code = interface.main(["--base-url", "https://ctower.example", "control", "health"])

    assert code == int(ExitCode.SUCCESS)
    assert observed == ["https://ctower.example"]
    assert not discovery.catalog_path().exists()
