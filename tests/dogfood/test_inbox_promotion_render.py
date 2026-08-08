"""What the dogfood Inbox surface actually renders, read out of a real browser.

The copy D40 clause 3 governs is not a fact about any one file. It is composed
at render time from a frame component, a rail constant and a screen, so a test
that greps those sources can pass while the page an operator looks at still
carries a retired claim. This suite therefore builds the separate dogfood
server, serves it on an ephemeral loopback port against a stub record source on
another one, and asserts on the text headless Chromium reports back.

Nothing here touches a running instance. The record source is a local stub, both
ports are ephemeral, and the browser only reads: the promotion transport is
proved against the real module in ``tests/repository/test_inbox_promotion_ui``,
and a browser that submitted the command would be exactly the product browser
authority D40 withholds.

This is the one suite the D40/D41 dogfood exception activates. It is deliberately
outside ``tests/repository`` so the warm ``just check`` gate never pays for a
production build and a browser; the release gate runs it through the expected-
suite manifest.
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar, cast

__all__ = ()

_ROOT = Path(__file__).resolve().parents[2]
_SURFACE = _ROOT / "apps/ctower-ui"
_NEXT = _SURFACE / "node_modules/.bin/next"
_DRIVER = Path(__file__).with_name("inbox_render_driver.ts")

_BUILD_TIMEOUT_SECONDS = 600
_DRIVE_TIMEOUT_SECONDS = 300
_READY_TIMEOUT_SECONDS = 120
_READY_POLL_SECONDS = 0.25
_STOP_GRACE_SECONDS = 10
_OK = 200
_NOT_FOUND = 404

_WIDTHS = (375, 768, 1440)
_INSTANCE_LABEL = "render-probe"
_THREAD_ID = "018f0d5e-7b9a-7c01-8000-000000000600"
_PREVIEW = "The reviewer asked for the rendered surface, not the source text."
_RETIRED_CLAIM = "no mutation path exists on this surface"
_SCOPED_FOOT = "server-authorized Inbox promotion path · browser holds no write authority"
_NEW_TICKET_VERDICT = "read-only v1 · disabled"

_INBOX_PROJECTION: dict[str, Any] = {
    "recipient": "seat:designer",
    "threads": [
        {
            "thread_id": _THREAD_ID,
            "other_agent": "seat:reviewer",
            "last_message_preview": _PREVIEW,
            "last_message_at": "2026-08-08T12:00:00Z",
            "unread_count": 2,
            "promoted_ticket_id": None,
        }
    ],
    "total_unread": 2,
    "unread_only": False,
}

_INBOX_THREAD: dict[str, Any] = {
    "thread_id": _THREAD_ID,
    "participants": ["seat:designer", "seat:reviewer"],
    "messages": [
        {
            "message_id": "018f0d5e-7b9a-7c01-8000-000000000601",
            "position": 1,
            "from": "seat:reviewer",
            "to": "seat:designer",
            "text": _PREVIEW,
            "sent_at": "2026-08-08T12:00:00Z",
        }
    ],
    "read_through_position": 1,
    "promoted_ticket_id": None,
}

_BOARD: dict[str, Any] = {
    "cards": [],
    "health": "CURRENT",
    "projection_watermark": 0,
    "source_watermark": 0,
}


class _RecordStub(BaseHTTPRequestHandler):
    """The read paths this screen asks for, and nothing else."""

    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/v1/inbox/threads":
            self._answer(_OK, _INBOX_PROJECTION)
        elif path == f"/v1/inbox/threads/{_THREAD_ID}":
            self._answer(_OK, _INBOX_THREAD)
        elif path == "/v1/board":
            self._answer(_OK, _BOARD)
        else:
            self._answer(_NOT_FOUND, {"detail": f"the stub record source holds no {path}"})

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - inherited signature
        """Keep the suite's output the driver's report, not an access log."""

    def _answer(self, status: int, document: dict[str, Any]) -> None:
        body = json.dumps(document).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
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
def _record_stub() -> Iterator[str]:
    """The stub record source, on its own ephemeral loopback port."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordStub)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port:d}"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=_STOP_GRACE_SECONDS)


@contextmanager
def _dogfood_server(record_base_url: str) -> Iterator[str]:
    """Build the separate dogfood server and serve it on an ephemeral port."""
    next_binary = _executable(_NEXT, "pnpm install --frozen-lockfile")
    environment = {
        **os.environ,
        "CTOWER_UI_API_BASE_URL": record_base_url,
        "CTOWER_UI_API_TOKEN": "loopback-render-probe",
        "CTOWER_UI_INSTANCE_LABEL": _INSTANCE_LABEL,
        "CTOWER_UI_INSTANCE_POSTURE": "SHADOW_ONLY_CP3_D_NOT_PROVEN",
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
        yield f"http://127.0.0.1:{port:d}"
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
    deadline = time.monotonic() + _READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if served.poll() is not None:
            raise RuntimeError(f"the dogfood server exited with {served.returncode:d} before ready")
        if _answered(port):
            return
        time.sleep(_READY_POLL_SECONDS)
    raise RuntimeError(
        f"the dogfood server did not serve /inbox within {_READY_TIMEOUT_SECONDS:d}s"
    )


def _answered(port: int) -> bool:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=_READY_POLL_SECONDS * 4)
    try:
        connection.request("GET", "/inbox")
        return connection.getresponse().status == _OK
    except (OSError, http.client.HTTPException):
        return False
    finally:
        connection.close()


def _drive(base_url: str, screenshots: Path) -> list[dict[str, Any]]:
    node = shutil.which("node")
    if node is None:
        # not a skip: this is a required suite, and a verification host without
        # the toolchain it declares is a failure, not a reason to pass quietly
        raise RuntimeError("node is not on PATH; the dogfood surface cannot be driven")
    completed = subprocess.run(  # noqa: S603 - a resolved interpreter and a checked-in driver
        (node, "--no-warnings", str(_DRIVER), base_url, _THREAD_ID, str(screenshots)),
        cwd=_ROOT,
        timeout=_DRIVE_TIMEOUT_SECONDS,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout)
    return cast("list[dict[str, Any]]", report["captures"])


class InboxSurfaceRenderTests(unittest.TestCase):
    """Assertions about the rendered page, not about the files behind it."""

    captures: ClassVar[list[dict[str, Any]]] = []
    _stack: ClassVar[ExitStack]

    @classmethod
    def setUpClass(cls) -> None:
        cls._stack = ExitStack()
        try:
            record = cls._stack.enter_context(_record_stub())
            served = cls._stack.enter_context(_dogfood_server(record))
            screenshots = Path(cls._stack.enter_context(tempfile.TemporaryDirectory()))
            cls.captures = _drive(served, screenshots)
        except BaseException:
            cls._stack.close()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls._stack.close()

    def test_every_width_and_route_rendered(self) -> None:
        self.assertEqual(
            [(capture["route"], capture["width"]) for capture in self.captures],
            [(route, width) for width in _WIDTHS for route in ("list", "thread")],
        )

    def test_the_rendered_surface_carries_no_global_read_only_claim(self) -> None:
        for capture in self.captures:
            with self.subTest(route=capture["route"], width=capture["width"]):
                self.assertNotIn(_RETIRED_CLAIM, capture["rendered"])
                self.assertIn(_SCOPED_FOOT, capture["foot"])
                self.assertNotIn("read-only", capture["foot"])

    def test_the_only_surviving_read_only_claim_names_the_disabled_affordance(self) -> None:
        for capture in self.captures:
            with self.subTest(route=capture["route"], width=capture["width"]):
                affordance = cast("dict[str, Any]", capture["newTicket"])
                self.assertEqual(affordance["label"], "New ticket")
                self.assertTrue(affordance["disabled"])
                self.assertEqual(affordance["verdict"], _NEW_TICKET_VERDICT)
                self.assertIn("ctowerctl ticket capture", affordance["reason"])
                self.assertEqual(capture["rendered"].count("read-only"), 1)

    def test_the_surface_rendered_the_recorded_threads_and_the_promotion_control(self) -> None:
        for capture in self.captures:
            with self.subTest(route=capture["route"], width=capture["width"]):
                self.assertIn(_PREVIEW, capture["visible"])
                self.assertIn(f"ctower · {_INSTANCE_LABEL} instance", capture["foot"])
                if capture["route"] == "thread":
                    self.assertIn("Promote thread", capture["visible"])
                    self.assertIn("Create a new ticket from this thread", capture["visible"])


if __name__ == "__main__":
    unittest.main()
