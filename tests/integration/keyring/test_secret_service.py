"""Non-skipped Linux Secret Service creation, process reload, and absence evidence."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import keyring

from ctowerctl.spool._keyring import create_master_key

__all__: tuple[str, ...] = ()

ROOT = Path(__file__).parents[3]
EXIT_LOCAL_FAILURE = 74
_SERVICE = "ctower-spool-v1"


def test_secret_service_creates_and_loads_key_across_processes() -> None:
    _assert_isolated_service()
    backend = keyring.get_keyring()
    identity = (backend.__class__.__module__, backend.__class__.__name__)
    assert identity == ("keyring.backends.SecretService", "Keyring")
    assert backend.priority > 0

    spool_uuid = uuid4()
    created = False
    try:
        expected_digest = hashlib.sha256(create_master_key(spool_uuid)).hexdigest()
        created = True
        loaded = _keyring_child(spool_uuid, expected_digest, with_session_bus=True)
        absent = _keyring_child(spool_uuid, expected_digest, with_session_bus=False)

        assert loaded.returncode == 0, loaded.stderr
        assert absent.returncode == EXIT_LOCAL_FAILURE, absent.stderr
        assert loaded.stdout == absent.stdout == ""
    finally:
        if created:
            keyring.delete_password(_SERVICE, str(spool_uuid))
    assert backend.get_password(_SERVICE, str(spool_uuid)) is None


def _assert_isolated_service() -> None:
    service_root = Path(os.environ["CTOWER_TEST_SERVICE_ROOT"]).resolve()
    home = Path.home().resolve()
    runtime = Path(os.environ["XDG_RUNTIME_DIR"]).resolve()
    assert home.is_relative_to(service_root)
    assert runtime.is_relative_to(service_root)
    assert home != Path(os.environ["CTOWER_TEST_HOST_HOME"]).resolve()
    assert os.environ["DBUS_SESSION_BUS_ADDRESS"] != os.environ["CTOWER_TEST_HOST_BUS"]


def _keyring_child(
    spool_uuid: object,
    expected_digest: str,
    *,
    with_session_bus: bool,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        str(ROOT / relative)
        for relative in (
            "apps/ctowerctl/src",
            "generated/python",
        )
    )
    if not with_session_bus:
        environment.pop("DBUS_SESSION_BUS_ADDRESS", None)
        environment.pop("GNOME_KEYRING_CONTROL", None)
    environment["CTOWER_KEYRING_CHILD"] = _child_command(spool_uuid, expected_digest)
    return subprocess.run(
        (
            sys.executable,
            "-I",
            "-c",
            "import json, os; "
            "command = json.loads(os.environ.pop('CTOWER_KEYRING_CHILD')); "
            "os.execv(command[0], command)",
        ),
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _child_command(spool_uuid: object, expected_digest: str) -> str:
    return json.dumps((sys.executable, "-c", _CHILD, str(spool_uuid), expected_digest))


_CHILD = """
import hashlib
import sys
from uuid import UUID
from ctowerctl.spool._keyring import KeyringError, load_master_key
try:
    digest = hashlib.sha256(load_master_key(UUID(sys.argv[1]))).hexdigest()
except KeyringError:
    raise SystemExit(74)
raise SystemExit(0 if digest == sys.argv[2] else 1)
"""
