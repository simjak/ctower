"""What the console typing ceremony renders and does, read out of a real browser.

The states this suite walks are the approved compare board's contract, and four
of their claims exist only in a running document.

*The walk is one control.* Read-only, ceremony, granted, expired and revoked are
five states of one composer, not five components. Pressing through them is the
only way to show that the confirmed text reaches the granted field, that expiry
keeps it, and that a spent grant returns the box to read-only rather than
leaving a live one on screen.

*The countdown is a clock.* Markup carries a number; only a browser shows that
the number moves, and only a served grant shows it moving towards a stamp the
server chose.

*Expiry is the server's.* This mints a grant the stub ends in seconds and waits
past it without touching the control, then asserts what it says — because the
one sentence that must survive that wait is that nothing was injected.

*Refusal copy is composed at render time.* What an operator reads when the
record says no is the answer's own sentence carried into a rendered note, so a
grep over the sources cannot see it and a source-text assertion would pass while
the screen showed a status code.

The suite serves the dogfood surface on an ephemeral loopback port against two
doubles: a stub record source for the console contract, and a tmux stand-in for
the fleet listing, so the fleet under test is this file's four crews rather than
whatever the host is running. It runs under the same D41/D42/D44 dogfood
exception as the inbox suite, and stays inside it — the browser presses this
server's own Server Actions, holds no credential, and addresses no instance.

`CT-C01` is asserted from the other side as well: the surface must reach the
console only through the console contract, so this proves the affordance is
absent entirely when the record answers none, which is the state the shadow
instance is in today.
"""

from __future__ import annotations

import http.client
import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from collections.abc import Iterator
from contextlib import ExitStack, closing, contextmanager, suppress
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar, cast

from .console_fleet_double import CREWS

__all__ = ()

_ROOT = Path(__file__).resolve().parents[2]
_SURFACE = _ROOT / "apps/ctower-ui"
_NEXT = _SURFACE / "node_modules/.bin/next"
_DRIVER = Path(__file__).with_name("console_render_driver.ts")
_FLEET = Path(__file__).with_name("console_fleet_double.py")

_BUILD_TIMEOUT_SECONDS = 600
_DRIVE_TIMEOUT_SECONDS = 600
_READY_TIMEOUT_SECONDS = 120
_READY_POLL_SECONDS = 0.25
_STOP_GRACE_SECONDS = 10
_OK = 200
_CREATED = 201
_UNPROCESSABLE = 422
_NOT_FOUND = 404

_WIDTHS = (375, 768, 1440)
_CREDENTIAL = "loopback-console-probe"
_TEXT = "just verify"
_DIGEST = "sha256:9f2c41ab…d7e0"
_GRANT_ID = "018f0d5e-7b9a-7c01-8000-000000000901"
_COMMAND_ID = "018f0d5e-7b9a-7c01-8000-000000000902"

_WALKED = "mc-engineer-371-console"
_EXPIRING = "mc-qa-m1-rerun2"
_REVOKED = "mc-designer-3388-callcard"
_REFUSED = "mc-review-390-verdict"
# short enough that the driver can wait it out, long enough that the granted
# screenshot is taken before it lands
_SHORT_GRANT_SECONDS = 2
_FULL_GRANT_SECONDS = 60
_FULL_COUNTDOWN = "1:00"

_REFUSAL_SENTENCE = (
    "This crew restarted since you confirmed the command, so no grant was minted "
    "and nothing was typed. Confirm it again for the new session."
)
_REFUSAL = {
    "code": "console_runner_epoch_changed",
    "detail": _REFUSAL_SENTENCE,
    "status": _UNPROCESSABLE,
    "title": "Console type grant refused",
    "type": "https://ctower.invalid/problems/console-type-grant-refused",
}
_NOTHING_INJECTED = "Nothing was injected."
_UNACKNOWLEDGED = "injected (unacknowledged)"
_ACK_REASON = "acknowledged needs a harness ACK this runner protocol does not supply"
_CHAT_CONTRAST = "Chat is in the right rail. This box reaches the terminal."
_NOT_AUTHORITY = "Confirming is not authority. The server mints the grant, or refuses."
_PLANNED_WHY = "the plan carries the one ASCII space bin/mux prepends"
_BYTES = "11 requested · 12 planned"
_REVOKED_FACT = "console_session_revoked"
# claims this control must never make; `delivered` and `acknowledged` are the
# two the specification singles out, and a countdown may never call itself one
_FORBIDDEN = ("delivered", "acknowledged by", "typed successfully", "grant guaranteed")


def _binding(crew: str) -> dict[str, Any]:
    return {
        "crew": crew,
        "incarnation": 7,
        "runner_epoch": 12,
        "assignment_sequence": 7,
    }


def _ceremony(crew: str) -> dict[str, Any]:
    return {
        "action": "paste_text",
        "requested_bytes": 11,
        "planned_bytes": 12,
        "digest": _DIGEST,
        "into": _binding(crew),
        "reauthenticated": "confirmed 8m ago",
    }


def _typing(crew: str, *, revoked: bool) -> dict[str, Any]:
    return {
        "session": _binding(crew),
        "actor": {
            "role": "operator",
            "role_binding_revision": 7,
            "reauthenticated": "8m ago",
            "freshness": "10m freshness",
        },
        "budget": {"paste_used": 1, "paste_limit": 4, "submit_used": 0, "submit_limit": 6},
        "revocation": {
            "fact": _REVOKED_FACT,
            "cause": "assignment interval changed",
            "appended_at": "2026-08-10T03:52:08Z",
            "streams_closed_at": "2026-08-10T03:52:10Z",
        }
        if revoked
        else None,
        "grant": None,
        "last_dispatch": None,
    }


class _Console:
    """The stub record source's state, and the four sessions it answers for."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.commands: list[dict[str, Any]] = []

    def typing(self, session: str) -> dict[str, Any] | None:
        if session not in {name for name, _ in CREWS}:
            return None
        return _typing(session.removeprefix("mc-"), revoked=session == _REVOKED)

    def record(self, path: str, payload: dict[str, Any], key: str | None) -> None:
        with self._lock:
            self.commands.append({"path": path, "payload": payload, "idempotency_key": key})

    def grant(self, session: str) -> dict[str, Any]:
        """A grant whose expiry is a server stamp, not a duration the browser trusts."""
        seconds = _SHORT_GRANT_SECONDS if session == _EXPIRING else _FULL_GRANT_SECONDS
        expires = datetime.now(UTC) + timedelta(seconds=seconds)
        return {
            "grant_id": _GRANT_ID,
            "expires_at": expires.isoformat().replace("+00:00", "Z"),
            "granted_seconds": _FULL_GRANT_SECONDS,
        }


class _ConsoleStub(BaseHTTPRequestHandler):
    """The one read this surface asks for and the three commands it sends."""

    protocol_version = "HTTP/1.1"
    console: ClassVar[_Console]

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        prefix, _, suffix = path.partition("/v1/console/sessions/")
        session, slash, leaf = suffix.partition("/")
        if prefix == "" and slash == "/" and leaf == "typing":
            typing = self.console.typing(session)
            if typing is None:
                self._answer(_NOT_FOUND, {"detail": "the stub holds no such console session"})
            else:
                self._answer(_OK, typing)
            return
        self._answer(_NOT_FOUND, {"detail": f"the stub record source holds no {path}"})

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length", "0"))
        payload = cast("dict[str, Any]", json.loads(self.rfile.read(length) or b"{}"))
        self.console.record(path, payload, self.headers.get("Idempotency-Key"))
        session = str(payload.get("session_ref", ""))
        if path == "/v1/console/typing/confirmations":
            self._answer(_CREATED, _ceremony(session.removeprefix("mc-")))
        elif path == "/v1/console/typing/grants":
            if session == _REFUSED:
                self._answer(_UNPROCESSABLE, _REFUSAL, content_type="application/problem+json")
            else:
                self._answer(_CREATED, self.console.grant(session))
        elif path == "/v1/console/typing/dispatches":
            self._answer(
                _CREATED,
                {"client_command_id": _COMMAND_ID, "state": "injected_unacknowledged"},
            )
        else:
            self._answer(_NOT_FOUND, {"detail": "the stub accepts no such command"})

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - inherited signature
        """Keep the suite's output the driver's report, not an access log."""

    def _answer(
        self, status: int, document: dict[str, Any], *, content_type: str = "application/json"
    ) -> None:
        body = json.dumps(document).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _free_port() -> int:
    with closing(socket.socket()) as probe:
        probe.bind(("127.0.0.1", 0))
        return cast("int", probe.getsockname()[1])


def _executable(path: Path, install: str) -> str:
    """A declared tool, or a named failure — never a quiet pass."""
    if not path.is_file():
        raise RuntimeError(f"{path} is missing; run {install}")
    return str(path)


@contextmanager
def _console_stub(console: _Console) -> Iterator[str]:
    """The stub record source, on its own ephemeral loopback port."""
    _ConsoleStub.console = console
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ConsoleStub)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port:d}"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=_STOP_GRACE_SECONDS)


@contextmanager
def _fleet_root() -> Iterator[Path]:
    """A Mission Control tree holding exactly this suite's four crews."""
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        (root / "state").mkdir()
        (root / "personas").mkdir()
        (root / "coordination").mkdir()
        for name, _ in CREWS:
            (root / "personas" / f"{name.removeprefix('mc-').split('-')[0]}.md").write_text(
                "a declared seat\n", encoding="utf-8"
            )
        (root / "state" / "escapes.jsonl").write_text("", encoding="utf-8")
        (root / "state" / "crew-log.jsonl").write_text(
            "".join(
                json.dumps(
                    {
                        "at": "2026-08-10 03:41:00",
                        "crew": name.removeprefix("mc-"),
                        "event": "dispatched",
                        "note": "the console typing ceremony",
                    }
                )
                + "\n"
                for name, _ in CREWS
            ),
            encoding="utf-8",
        )
        yield root


@contextmanager
def _dogfood_server(record_base_url: str, fleet_root: Path, *, console: bool) -> Iterator[int]:
    """Build the dogfood server and serve it against the two doubles.

    `console` decides whether the record answers a console contract at all. The
    run with it off is how the shadow instance stands today, and proving the
    affordance is absent there is the CT-C01 assertion.
    """
    next_binary = _executable(_NEXT, "pnpm install --frozen-lockfile")
    environment = {
        **os.environ,
        "CTOWER_UI_API_BASE_URL": record_base_url if console else "http://127.0.0.1:1",
        "CTOWER_UI_API_TOKEN": _CREDENTIAL,
        "CTOWER_UI_INSTANCE_LABEL": "console-render-probe",
        "CTOWER_UI_INSTANCE_POSTURE": "SHADOW_ONLY_CP3_D_NOT_PROVEN",
        "CTOWER_UI_MC_ROOT": str(fleet_root),
        "CTOWER_UI_EXEC_TMUX": _executable(_FLEET, "git checkout tests/dogfood"),
        "NODE_ENV": "production",
    }
    subprocess.run(  # noqa: S603 - a declared binary from the checkout, no shell, no caller argv
        (next_binary, "build"),
        cwd=_SURFACE,
        env=environment,
        timeout=_BUILD_TIMEOUT_SECONDS,
        check=True,
        capture_output=True,
        text=True,
    )
    port = _free_port()
    served = subprocess.Popen(  # noqa: S603 - the same declared binary, held open as the server
        (next_binary, "start", "--port", str(port), "--hostname", "127.0.0.1"),
        cwd=_SURFACE,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        _await_ready(served, port)
        yield port
    finally:
        with suppress(ProcessLookupError):
            os.killpg(served.pid, signal.SIGTERM)
        try:
            served.wait(timeout=_STOP_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            with suppress(ProcessLookupError):
                os.killpg(served.pid, signal.SIGKILL)
            served.wait(timeout=_STOP_GRACE_SECONDS)


def _await_ready(served: subprocess.Popen[bytes], port: int) -> None:
    """Poll the served route under a finite deadline; a dead server fails now."""
    route = f"/crew/{_WALKED.removeprefix('mc-')}"
    deadline = time.monotonic() + _READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if served.poll() is not None:
            raise RuntimeError(f"the dogfood server exited with {served.returncode:d} before ready")
        if _served(port, route) is not None:
            return
        time.sleep(_READY_POLL_SECONDS)
    raise RuntimeError(f"the dogfood server did not serve {route} in {_READY_TIMEOUT_SECONDS:d}s")


def _served(port: int, route: str) -> str | None:
    """The bytes one route answered with, or `None` when it did not answer."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=_READY_POLL_SECONDS * 8)
    try:
        connection.request("GET", route)
        response = connection.getresponse()
        body = response.read().decode("utf-8", errors="replace")
    except (OSError, http.client.HTTPException):
        return None
    else:
        return body if response.status == _OK else None
    finally:
        connection.close()


def _drive(port: int, screenshots: Path) -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        # not a skip: this is a required suite, and a verification host without
        # the toolchain it declares is a failure, not a reason to pass quietly
        raise RuntimeError("node is not on PATH; the console ceremony cannot be driven")
    try:
        completed = subprocess.run(  # noqa: S603 - a resolved interpreter and a checked-in driver
            (node, "--no-warnings", str(_DRIVER), f"http://127.0.0.1:{port:d}", str(screenshots)),
            cwd=_ROOT,
            timeout=_DRIVE_TIMEOUT_SECONDS,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as failed:
        # what the browser could not find is the whole diagnosis; an exit status
        # on its own sends the next reader back to run it by hand
        raise RuntimeError(f"the console render driver failed:\n{failed.stderr}") from failed
    return cast("dict[str, Any]", json.loads(completed.stdout))


class ConsoleCeremonyRenderTests(unittest.TestCase):
    """Assertions about the rendered ceremony and what it did, not its sources."""

    walks: ClassVar[list[dict[str, Any]]] = []
    console: ClassVar[_Console]
    without_console: ClassVar[str] = ""
    _stack: ClassVar[ExitStack]

    @classmethod
    def setUpClass(cls) -> None:
        cls._stack = ExitStack()
        cls.console = _Console()
        try:
            base_url = cls._stack.enter_context(_console_stub(cls.console))
            fleet = cls._stack.enter_context(_fleet_root())
            shots = Path(cls._stack.enter_context(tempfile.TemporaryDirectory()))
            with _dogfood_server(base_url, fleet, console=True) as port:
                cls.walks = cast("list[dict[str, Any]]", _drive(port, shots)["walks"])
            # the same surface against a record that answers no console path:
            # what an operator sees on the shadow instance today
            with _dogfood_server(base_url, fleet, console=False) as port:
                cls.without_console = _served(port, f"/crew/{_WALKED.removeprefix('mc-')}") or ""
        except BaseException:
            cls._stack.close()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls._stack.close()

    def test_every_width_walked_every_state(self) -> None:
        self.assertEqual([walk["width"] for walk in self.walks], list(_WIDTHS))
        for walk in self.walks:
            with self.subTest(width=walk["width"]):
                self.assertEqual(walk["readOnly"]["phase"], "read-only")
                self.assertEqual(walk["composing"]["phase"], "ceremony")
                self.assertEqual(walk["confirmed"]["phase"], "ceremony")
                self.assertEqual(walk["granted"]["phase"], "granted")
                self.assertEqual(walk["expired"]["phase"], "expired")
                self.assertEqual(walk["revoked"]["phase"], "revoked")

    def test_read_only_composer_is_inert_and_says_what_unlocks_it(self) -> None:
        for walk in self.walks:
            with self.subTest(width=walk["width"]):
                shot = walk["readOnly"]
                self.assertTrue(shot["fieldDisabled"])
                self.assertEqual(shot["field"], "")
                self.assertEqual(shot["counter"], "no type grant")
                self.assertIn(_CHAT_CONTRAST, shot["text"])
                self.assertIn("4 paste · 6 submit", shot["text"])

    def test_ceremony_shows_server_derived_bytes_digest_and_binding(self) -> None:
        for walk in self.walks:
            with self.subTest(width=walk["width"]):
                shot = walk["confirmed"]
                self.assertIn(_BYTES, shot["text"])
                self.assertIn(_PLANNED_WHY, shot["text"])
                self.assertIn(_DIGEST, shot["text"])
                self.assertIn("incarnation 7 · runner epoch 12 · assignment seq 7", shot["text"])
                self.assertIn(_NOT_AUTHORITY, shot["text"])

    def test_granted_carries_the_confirmed_text_and_a_moving_countdown(self) -> None:
        for walk in self.walks:
            with self.subTest(width=walk["width"]):
                shot = walk["granted"]
                self.assertEqual(shot["field"], _TEXT)
                self.assertFalse(shot["fieldDisabled"])
                # a full minute, and never more than one: a browser behind the
                # server's clock may not read `1:01` off a sixty-second grant
                self.assertEqual(shot["counter"], f"type grant {_FULL_COUNTDOWN}")
                # the same chip, read again a moment later: a countdown that did
                # not move is a number, and a number is not what this promises
                self.assertNotEqual(walk["tickedTo"], shot["counter"])

    def test_dispatch_stops_at_injected_unacknowledged_and_says_why(self) -> None:
        for walk in self.walks:
            with self.subTest(width=walk["width"]):
                chain = walk["dispatched"]["chain"]
                self.assertIn(_UNACKNOWLEDGED, chain)
                self.assertIn(_ACK_REASON, chain)
                # a spent grant is spent: the composer may not still offer one
                self.assertEqual(walk["dispatched"]["phase"], "read-only")

    def test_expiry_keeps_the_words_locks_the_field_and_injects_nothing(self) -> None:
        for walk in self.walks:
            with self.subTest(width=walk["width"]):
                shot = walk["expired"]
                self.assertEqual(shot["field"], _TEXT)
                self.assertTrue(shot["fieldDisabled"])
                self.assertEqual(shot["counter"], "type grant expired")
                self.assertIn(_NOTHING_INJECTED, shot["note"])
                self.assertIn("Request a new grant", [b["label"] for b in shot["buttons"]])

    def test_revocation_shows_the_fact_its_cause_and_both_times(self) -> None:
        for walk in self.walks:
            with self.subTest(width=walk["width"]):
                shot = walk["revoked"]
                self.assertEqual(shot["counter"], "session revoked")
                self.assertIn(_REVOKED_FACT, shot["text"])
                self.assertIn("assignment interval changed", shot["text"])
                self.assertIn("03:52:08", shot["text"])
                self.assertIn("03:52:10", shot["text"])
                # nothing to mint against, so nothing may offer to mint
                self.assertEqual([b["label"] for b in shot["buttons"]], [])

    def test_a_refused_mint_reaches_the_operator_as_the_servers_own_sentence(self) -> None:
        for walk in self.walks:
            with self.subTest(width=walk["width"]):
                shot = walk["refused"]
                self.assertIn(_REFUSAL_SENTENCE, shot["note"])
                # the refusal is the server's words, not a status code or a path
                self.assertNotIn("422", shot["text"])
                self.assertNotIn("console_runner_epoch_changed", shot["text"])
                self.assertNotIn("/v1/console", shot["text"])
                # and it never costs the operator the command they wrote
                self.assertEqual(shot["phase"], "ceremony")
                self.assertEqual(shot["field"], _TEXT)
                self.assertFalse(shot["fieldDisabled"])

    def test_no_state_claims_delivery_or_acknowledgement(self) -> None:
        for walk in self.walks:
            for state in ("readOnly", "composing", "confirmed", "granted", "dispatched", "expired"):
                said = cast("str", walk[state]["text"]).lower()
                for claim in _FORBIDDEN:
                    with self.subTest(width=walk["width"], state=state, claim=claim):
                        self.assertNotIn(claim, said)

    def test_the_ceremony_is_contained_at_every_width(self) -> None:
        for walk in self.walks:
            with self.subTest(width=walk["width"]):
                self.assertFalse(walk["overflowed"])

    def test_the_browser_never_canonicalizes_or_names_its_own_target(self) -> None:
        """Every count and digest came from the server, and the session did not."""
        confirmations = [
            command
            for command in self.console.commands
            if command["path"] == "/v1/console/typing/confirmations"
        ]
        self.assertTrue(confirmations)
        for command in confirmations:
            self.assertEqual(sorted(command["payload"]), ["action", "session_ref", "text"])
            self.assertNotIn("digest", command["payload"])
            self.assertNotIn("planned_bytes", command["payload"])
        for command in self.console.commands:
            # one key per command, minted before the first attempt
            self.assertIsNotNone(command["idempotency_key"])

    def test_a_record_serving_no_console_renders_no_affordance_at_all(self) -> None:
        """CT-C01 from the other side: the read-only reader grows no writable path."""
        self.assertNotEqual(self.without_console, "")
        for claim in ("Request type grant", "type grant", "data-console-phase"):
            with self.subTest(claim=claim):
                self.assertNotIn(claim, self.without_console)


if __name__ == "__main__":
    unittest.main()
