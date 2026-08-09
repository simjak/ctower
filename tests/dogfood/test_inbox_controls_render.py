"""What the dogfood Inbox surface renders and does, read out of a real browser.

Three of this boundary's claims are only true in a running browser.

The copy D41 clause 3 governs is not a fact about any one file. It is composed
at render time from a frame component, a rail constant and a screen, so a test
that greps those sources can pass while the page an operator looks at still
carries a retired claim.

The send box's claim is stronger still: a message typed into it appears in the
thread *without a reload*. That is a statement about one document's lifetime,
and no source file can carry it. D44 therefore permits this suite — and only
this suite, and only for the send control — to submit the box from the browser.
It stays a dogfood claim: the browser posts to this server's own Server Action,
receives no credential, and never addresses a running instance.

The third is the same claim's other half: a message the record has *not*
accepted must not appear as one. A `202`/`durability_pending` answer carries the
same identity, position and timestamp an accepted answer does, so only a
rendered page can show whether the surface drew a row anyway, kept the sender's
words, and retried under the identity the first attempt minted.

This suite builds the separate dogfood server, serves it on an ephemeral
loopback port against a stub record source on another one, and asserts on what
headless Chromium reports back at the three widths the design bar names.

The promotion form is still never submitted here: its transport is proved
against the real module in ``tests/repository/test_inbox_promotion_ui``, and the
send transport is proved the same way in ``test_inbox_send_ui``.

This is the one suite the D41/D42/D44 dogfood exception activates. It is
deliberately outside ``tests/repository`` so the warm ``just check`` gate never
pays for a production build and a browser; the release gate runs it through the
expected-suite manifest.
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
_CREATED = 201
_PENDING_DURABILITY = 202
_UNPROCESSABLE = 422
_NOT_FOUND = 404

_WIDTHS = (375, 768, 1440)
_INSTANCE_LABEL = "render-probe"
_CREDENTIAL = "loopback-render-probe"
_THREAD_ID = "018f0d5e-7b9a-7c01-8000-000000000600"
_REFUSED_THREAD_ID = "018f0d5e-7b9a-7c01-8000-000000000610"
_UNCONFIRMED_THREAD_ID = "018f0d5e-7b9a-7c01-8000-000000000620"
_SELF_SEAT = "designer"
_OTHER_SEAT = "reviewer"
_STRANGER_SEAT = "unseated-agent"
_UNDURABLE_SEAT = "commander"
_PREVIEW = "The reviewer asked for the rendered surface, not the source text."
_RETIRED_CLAIM = "no mutation path exists on this surface"
_SCOPED_FOOT = "server-authorized Inbox send and promotion paths · browser holds no write authority"
_NEW_TICKET_VERDICT = "read-only v1 · disabled"
_REFUSAL_DETAIL = "The authenticated principal has no addressable project seat."
_UNCONFIRMED_SENTENCE = (
    "The server has not confirmed this message, so it is not sent yet. "
    "Press Retry to send the same message again."
)
# what the line under the box reads, chip included; the chip's own stylesheet
# upper-cases it on screen
_UNCONFIRMED_NOTICE = f"not confirmed {_UNCONFIRMED_SENTENCE}"
_SEND_FIELDS = ("text", "thread_id", "to")


def _thread(thread_id: str, other: str) -> dict[str, Any]:
    return {
        "thread_id": thread_id,
        "participants": [_SELF_SEAT, other],
        "messages": [
            {
                "message_id": "018f0d5e-7b9a-7c01-8000-000000000601",
                "position": 1,
                "from": other,
                "to": _SELF_SEAT,
                "text": _PREVIEW,
                "sent_at": "2026-08-08T12:00:00Z",
            }
        ],
        "read_through_position": 1,
        "promoted_ticket_id": None,
    }


def _summary(thread_id: str, other: str) -> dict[str, Any]:
    return {
        "thread_id": thread_id,
        "other_agent": other,
        "last_message_preview": _PREVIEW,
        "last_message_at": "2026-08-08T12:00:00Z",
        "unread_count": 2,
        "promoted_ticket_id": None,
    }


def _answer(payload: dict[str, Any], position: int, durability: str) -> dict[str, Any]:
    """One send result, in the authored shape both durability states share."""
    return {
        "command_id": f"018f0d5e-7b9a-7c01-8000-0000000008{position:02d}",
        "durability_state": durability,
        "event_ids": [f"018f0d5e-7b9a-7c01-8000-0000000009{position:02d}"],
        "from": _SELF_SEAT,
        "message_id": f"018f0d5e-7b9a-7c01-8000-0000000007{position:02d}",
        "position": position,
        "sent_at": "2026-08-09T03:05:00Z",
        "thread_id": str(payload["thread_id"]),
        "thread_version": position + 1,
        "to": str(payload["to"]),
    }


_BOARD: dict[str, Any] = {
    "cards": [],
    "health": "CURRENT",
    "projection_watermark": 0,
    "source_watermark": 0,
}

_REFUSAL: dict[str, Any] = {
    "code": "inbox-sender-unaddressable",
    "detail": _REFUSAL_DETAIL,
    "status": _UNPROCESSABLE,
    "title": "Inbox command refused",
    "type": "https://ctower.invalid/problems/inbox-sender-unaddressable",
}


class _Record:
    """The stub record source's state, folded the way the real one folds.

    The thread read is a *projection*: the real one is folded from events after
    the command commits, so the message a send has just accepted is briefly
    absent from it. A stub that answered instantly would make this suite prove
    something the product does not do, so a sent message is held out of the
    thread read until one read has gone by — the smallest fold latency that is
    still latency.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._threads = {
            _THREAD_ID: _thread(_THREAD_ID, _OTHER_SEAT),
            _REFUSED_THREAD_ID: _thread(_REFUSED_THREAD_ID, _STRANGER_SEAT),
            _UNCONFIRMED_THREAD_ID: _thread(_UNCONFIRMED_THREAD_ID, _UNDURABLE_SEAT),
        }
        self._unfolded: list[tuple[str, dict[str, Any]]] = []
        self.commands: list[dict[str, Any]] = []

    def projection(self) -> dict[str, Any]:
        return {
            "recipient": _SELF_SEAT,
            "threads": [
                _summary(_THREAD_ID, _OTHER_SEAT),
                _summary(_REFUSED_THREAD_ID, _STRANGER_SEAT),
                _summary(_UNCONFIRMED_THREAD_ID, _UNDURABLE_SEAT),
            ],
            "total_unread": 6,
            "unread_only": False,
        }

    def thread(self, thread_id: str) -> dict[str, Any] | None:
        with self._lock:
            found = self._threads.get(thread_id)
            answer = (
                None if found is None else cast("dict[str, Any]", json.loads(json.dumps(found)))
            )
            self._fold()
            return answer

    def _fold(self) -> None:
        """Move everything accepted since the last read into the projection."""
        for thread_id, message in self._unfolded:
            cast("list[dict[str, Any]]", self._threads[thread_id]["messages"]).append(message)
        self._unfolded.clear()

    def refuse(self, payload: dict[str, Any], key: str | None) -> None:
        with self._lock:
            self.commands.append({"payload": payload, "idempotency_key": key})

    def append(self, payload: dict[str, Any], key: str | None) -> dict[str, Any]:
        """Record one send exactly as the authored command answers it."""
        with self._lock:
            self.commands.append({"payload": payload, "idempotency_key": key})
            thread_id = str(payload["thread_id"])
            thread = self._threads[thread_id]
            position = (
                len(cast("list[dict[str, Any]]", thread["messages"])) + len(self._unfolded) + 1
            )
            accepted = {
                "message_id": f"018f0d5e-7b9a-7c01-8000-0000000007{position:02d}",
                "position": position,
                "from": _SELF_SEAT,
                "to": str(payload["to"]),
                "text": str(payload["text"]),
                "sent_at": "2026-08-09T03:05:00Z",
            }
            self._unfolded.append((thread_id, accepted))
            return _answer(payload, position, "accepted")

    def undurable(self, payload: dict[str, Any], key: str | None) -> dict[str, Any]:
        """Answer the way the record answers without its off-host acknowledgement.

        The command committed here, but the durable acknowledgement acceptance
        requires did not, so the answer is the same authored envelope carrying
        the state it is really in. Nothing is folded into the thread read: this
        message is not a fact anyone has promised to keep, and a replay under
        the same key gets the same non-accepted answer back.
        """
        with self._lock:
            self.commands.append({"payload": payload, "idempotency_key": key})
            thread = self._threads[str(payload["thread_id"])]
            position = len(cast("list[dict[str, Any]]", thread["messages"])) + 1
            return _answer(payload, position, "durability_pending")


class _RecordStub(BaseHTTPRequestHandler):
    """The read paths this screen asks for, the one command it sends, nothing else."""

    protocol_version = "HTTP/1.1"
    record: ClassVar[_Record]

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/v1/inbox/threads":
            self._answer(_OK, self.record.projection())
        elif path.startswith("/v1/inbox/threads/"):
            thread = self.record.thread(path.rsplit("/", 1)[-1])
            if thread is None:
                self._answer(_NOT_FOUND, {"detail": "the stub record source holds no such thread"})
            else:
                self._answer(_OK, thread)
        elif path == "/v1/board":
            self._answer(_OK, _BOARD)
        else:
            self._answer(_NOT_FOUND, {"detail": f"the stub record source holds no {path}"})

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != "/v1/inbox/messages":
            self._answer(_NOT_FOUND, {"detail": "the stub record source accepts no such command"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = cast("dict[str, Any]", json.loads(self.rfile.read(length)))
        key = self.headers.get("Idempotency-Key")
        thread_id = str(payload.get("thread_id"))
        if thread_id == _REFUSED_THREAD_ID:
            self.record.refuse(payload, key)
            self._answer(_UNPROCESSABLE, _REFUSAL, content_type="application/problem+json")
            return
        if thread_id == _UNCONFIRMED_THREAD_ID:
            self._answer(_PENDING_DURABILITY, self.record.undurable(payload, key))
            return
        self._answer(_CREATED, self.record.append(payload, key))

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
def _record_stub(record: _Record) -> Iterator[str]:
    """The stub record source, on its own ephemeral loopback port."""
    _RecordStub.record = record
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
def _dogfood_server(record_base_url: str) -> Iterator[int]:
    """Build the separate dogfood server and serve it on an ephemeral port."""
    next_binary = _executable(_NEXT, "pnpm install --frozen-lockfile")
    environment = {
        **os.environ,
        "CTOWER_UI_API_BASE_URL": record_base_url,
        "CTOWER_UI_API_TOKEN": _CREDENTIAL,
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
    deadline = time.monotonic() + _READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if served.poll() is not None:
            raise RuntimeError(f"the dogfood server exited with {served.returncode:d} before ready")
        if _served(port, "/inbox") is not None:
            return
        time.sleep(_READY_POLL_SECONDS)
    raise RuntimeError(
        f"the dogfood server did not serve /inbox within {_READY_TIMEOUT_SECONDS:d}s"
    )


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
        raise RuntimeError("node is not on PATH; the dogfood surface cannot be driven")
    try:
        completed = subprocess.run(  # noqa: S603 - a resolved interpreter and a checked-in driver
            (
                node,
                "--no-warnings",
                str(_DRIVER),
                f"http://127.0.0.1:{port:d}",
                _THREAD_ID,
                _REFUSED_THREAD_ID,
                _UNCONFIRMED_THREAD_ID,
                str(screenshots),
            ),
            cwd=_ROOT,
            timeout=_DRIVE_TIMEOUT_SECONDS,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as failed:
        # what the browser could not find is the whole diagnosis; an exit status
        # on its own sends the next reader back to run it by hand
        raise RuntimeError(f"the render driver failed:\n{failed.stderr}") from failed
    return cast("dict[str, Any]", json.loads(completed.stdout))


class InboxSurfaceRenderTests(unittest.TestCase):
    """Assertions about the rendered page and what it did, not about its sources."""

    captures: ClassVar[list[dict[str, Any]]] = []
    drives: ClassVar[list[dict[str, Any]]] = []
    record: ClassVar[_Record]
    thread_source: ClassVar[str] = ""
    _stack: ClassVar[ExitStack]

    @classmethod
    def setUpClass(cls) -> None:
        cls._stack = ExitStack()
        try:
            cls.record = _Record()
            stub = cls._stack.enter_context(_record_stub(cls.record))
            port = cls._stack.enter_context(_dogfood_server(stub))
            screenshots = Path(cls._stack.enter_context(tempfile.TemporaryDirectory()))
            cls.thread_source = _served(port, f"/inbox?thread={_THREAD_ID}") or ""
            report = _drive(port, screenshots)
            cls.captures = cast("list[dict[str, Any]]", report["captures"])
            cls.drives = cast("list[dict[str, Any]]", report["drives"])
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

    def test_the_surface_rendered_the_recorded_threads_and_both_controls(self) -> None:
        for capture in self.captures:
            with self.subTest(route=capture["route"], width=capture["width"]):
                self.assertIn(_PREVIEW, capture["visible"])
                self.assertIn(f"ctower · {_INSTANCE_LABEL} instance", capture["foot"])
                if capture["route"] == "thread":
                    self.assertIn("Promote thread", capture["visible"])
                    self.assertIn("Create a new ticket from this thread", capture["visible"])
                    # the design system upper-cases this label, so the assertion
                    # is on the words a reader actually sees
                    self.assertIn(f"SEND TO {_OTHER_SEAT.upper()}", capture["visible"])
                    self.assertIn(
                        f"as {_SELF_SEAT} · the server authorizes and records every message",
                        capture["visible"],
                    )

    def test_a_typed_message_appears_in_the_thread_without_a_reload(self) -> None:
        """The claim the send box exists to make, made in a browser at every width.

        The stub's thread read lags one read behind its accepted commands, the
        way a folded projection lags a committed event. So the row that shows
        up in the submitting document can only have come from the command's own
        answer, and it carries the marker that says so.
        """
        sends = [drive for drive in self.drives if drive["outcome"] == "sent"]
        self.assertEqual([drive["width"] for drive in sends], list(_WIDTHS))
        for drive in sends:
            with self.subTest(width=drive["width"]):
                self.assertIn(drive["typed"], drive["messages"])
                self.assertEqual(drive["unfolded"], [drive["typed"]])
                self.assertTrue(drive["sameDocument"])
                self.assertEqual(drive["fieldAfter"], "")
                self.assertEqual(drive["button"], "Send")

    def test_the_projection_takes_the_message_over_and_the_marker_goes_away(self) -> None:
        """One message, never two: the row is the command's until the read has it."""
        for drive in (item for item in self.drives if item["outcome"] == "sent"):
            with self.subTest(width=drive["width"]):
                reloaded = cast("list[str]", drive["messagesReloaded"])
                self.assertIn(drive["typed"], reloaded)
                self.assertEqual(reloaded.count(drive["typed"]), 1)
                self.assertEqual(drive["unfoldedReloaded"], [])

    def test_a_non_accepted_answer_is_never_rendered_as_a_sent_message(self) -> None:
        """`202`/`durability_pending` is the record saying it has not accepted.

        Its answer carries the same message identity, position and timestamp an
        accepted one does, so a surface that reads the envelope instead of the
        discriminator shows an unkept message as a recorded fact. Here the row
        is not drawn at all: the words stay in the box, and the box says the
        server has not confirmed them.
        """
        held = [drive for drive in self.drives if drive["outcome"] == "unconfirmed"]
        self.assertEqual([drive["width"] for drive in held], list(_WIDTHS))
        for drive in held:
            with self.subTest(width=drive["width"]):
                self.assertNotIn(drive["typed"], drive["messages"])
                self.assertEqual(drive["unfolded"], [])
                self.assertEqual(drive["notice"], _UNCONFIRMED_NOTICE)
                self.assertEqual(drive["refusal"], "")
                # the draft survives, and the control names the retry it offers
                self.assertEqual(drive["fieldAfter"], drive["typed"])
                self.assertEqual(drive["button"], "Retry")
                self.assertTrue(drive["sameDocument"])
                self.assertNotIn(drive["typed"], drive["messagesReloaded"])

    def test_the_retry_of_an_unconfirmed_send_reuses_one_command_identity(self) -> None:
        """Pressing the box again replays one command; it does not send a second."""
        for drive in (item for item in self.drives if item["outcome"] == "unconfirmed"):
            with self.subTest(width=drive["width"]):
                retried = cast("dict[str, Any]", drive["retried"])
                self.assertEqual(retried["notice"], _UNCONFIRMED_NOTICE)
                self.assertEqual(retried["fieldAfter"], drive["typed"])
                self.assertEqual(retried["button"], "Retry")
                self.assertNotIn(drive["typed"], retried["messages"])

        keys = [
            command["idempotency_key"]
            for command in self.record.commands
            if str(cast("dict[str, Any]", command["payload"])["thread_id"])
            == _UNCONFIRMED_THREAD_ID
        ]
        self.assertEqual(len(keys), len(_WIDTHS) * 2)
        self.assertEqual(len(set(keys)), len(_WIDTHS))
        for first, second in zip(keys[::2], keys[1::2], strict=True):
            self.assertEqual(first, second)

    def test_the_command_carried_the_message_and_no_claimed_identity(self) -> None:
        commands = self.record.commands
        # one accepted send, one refused send, and two attempts at one
        # unconfirmed send, at each width
        self.assertEqual(len(commands), len(_WIDTHS) * 4)
        keys = [command["idempotency_key"] for command in commands]
        self.assertEqual(len(set(keys)), len(_WIDTHS) * 3)
        for command in commands:
            payload = cast("dict[str, Any]", command["payload"])
            with self.subTest(text=payload.get("text")):
                self.assertEqual(tuple(sorted(payload)), _SEND_FIELDS)
                self.assertIn(payload["to"], (_OTHER_SEAT, _STRANGER_SEAT, _UNDURABLE_SEAT))
                self.assertRegex(cast("str", command["idempotency_key"]), r"^[0-9a-f-]{36}$")

    def test_a_refused_send_renders_the_servers_own_sentence(self) -> None:
        refusals = [drive for drive in self.drives if drive["outcome"] == "refused"]
        self.assertEqual([drive["width"] for drive in refusals], list(_WIDTHS))
        for drive in refusals:
            with self.subTest(width=drive["width"]):
                self.assertEqual(drive["refusal"], _REFUSAL_DETAIL)
                self.assertNotIn(drive["typed"], drive["messages"])
                self.assertNotIn(drive["typed"], drive["messagesReloaded"])
                self.assertTrue(drive["sameDocument"])
                # the words survive the refusal: nobody retypes a rejected send
                self.assertEqual(drive["fieldAfter"], drive["typed"])
                # a refused command has no identity to replay, so this is a fresh send
                self.assertEqual(drive["button"], "Send")

    def test_the_served_document_carries_no_credential(self) -> None:
        """D41 clause 1: the browser receives no bearer, in markup or in props."""
        self.assertIn(_THREAD_ID, self.thread_source)
        self.assertNotIn(_CREDENTIAL, self.thread_source)
        self.assertNotIn("Bearer", self.thread_source)


if __name__ == "__main__":
    unittest.main()
