"""The stub record source and the served dogfood surface this suite drives.

The suite's claims are about a rendered page; everything here is the apparatus
that produces one. It stands the record source up on a loopback port, builds and
serves the separate `ctower-ui` server against it, and runs the checked-in
browser driver — none of which is an assertion, and all of which was crowding
out the assertions that are.

The record source is deliberately not a mock that answers whatever it is asked.
It folds the way the real projection folds, it derives a notification thread
from a seat pair the way the real pair-grouped path does, and it refuses an
unaddressable send by the API's own stable code — because a suite whose stub is
more capable than the product proves something the product cannot do.
"""

from __future__ import annotations

import http.client
import json
import os
import shutil
import signal
import socket
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager, suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar, cast

__all__ = (
    "ADDRESSABLE",
    "COMPOSED_THREAD_ID",
    "COMPOSE_SEAT",
    "CREDENTIAL",
    "INSTANCE_LABEL",
    "OTHER_SEAT",
    "PREVIEW",
    "REFUSAL_DETAIL",
    "REFUSED_THREAD_ID",
    "SELF_SEAT",
    "STRANGER_SEAT",
    "THREAD_ID",
    "UNCONFIRMED_THREAD_ID",
    "UNDURABLE_SEAT",
    "WIDTHS",
    "Record",
    "dogfood_server",
    "drive_surface",
    "record_stub",
    "route_body",
)

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

WIDTHS = (375, 768, 1440)
INSTANCE_LABEL = "render-probe"
CREDENTIAL = "loopback-render-probe"
THREAD_ID = "018f0d5e-7b9a-7c01-8000-000000000600"
REFUSED_THREAD_ID = "018f0d5e-7b9a-7c01-8000-000000000610"
UNCONFIRMED_THREAD_ID = "018f0d5e-7b9a-7c01-8000-000000000620"
COMPOSED_THREAD_ID = "018f0d5e-7b9a-7c01-8000-000000000630"
SELF_SEAT = "designer"
OTHER_SEAT = "reviewer"
STRANGER_SEAT = "unseated-agent"
UNDURABLE_SEAT = "commander"
COMPOSE_SEAT = "director"
PREVIEW = "The reviewer asked for the rendered surface, not the source text."
REFUSAL_DETAIL = "The authenticated principal has no addressable project seat."
# every seat the stub record lists, in the order it lists them; the first has no
# thread with this principal yet, which is the whole point of a compose control
ADDRESSABLE = (COMPOSE_SEAT, OTHER_SEAT, STRANGER_SEAT, UNDURABLE_SEAT)


def _thread(thread_id: str, other: str) -> dict[str, Any]:
    return {
        "thread_id": thread_id,
        "participants": [SELF_SEAT, other],
        "messages": [
            {
                "message_id": "018f0d5e-7b9a-7c01-8000-000000000601",
                "position": 1,
                "from": other,
                "to": SELF_SEAT,
                "text": PREVIEW,
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
        "last_message_preview": PREVIEW,
        "last_message_at": "2026-08-08T12:00:00Z",
        "unread_count": 2,
        "promoted_ticket_id": None,
    }


def _answer(payload: dict[str, Any], position: int, durability: str) -> dict[str, Any]:
    """One send result, in the authored shape both durability states share."""
    return _result(str(payload["thread_id"]), str(payload["to"]), position, durability)


def _result(thread_id: str, to: str, position: int, durability: str) -> dict[str, Any]:
    return {
        "command_id": f"018f0d5e-7b9a-7c01-8000-0000000008{position:02d}",
        "durability_state": durability,
        "event_ids": [f"018f0d5e-7b9a-7c01-8000-0000000009{position:02d}"],
        "from": SELF_SEAT,
        "message_id": f"018f0d5e-7b9a-7c01-8000-0000000007{position:02d}",
        "position": position,
        "sent_at": "2026-08-09T03:05:00Z",
        "thread_id": thread_id,
        "thread_version": position + 1,
        "to": to,
    }


_BOARD: dict[str, Any] = {
    "cards": [],
    "health": "CURRENT",
    "projection_watermark": 0,
    "source_watermark": 0,
}

_REFUSAL: dict[str, Any] = {
    "code": "inbox-sender-unaddressable",
    "detail": REFUSAL_DETAIL,
    "status": _UNPROCESSABLE,
    "title": "Inbox command refused",
    "type": "https://ctower.invalid/problems/inbox-sender-unaddressable",
}


class Record:
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
            THREAD_ID: _thread(THREAD_ID, OTHER_SEAT),
            REFUSED_THREAD_ID: _thread(REFUSED_THREAD_ID, STRANGER_SEAT),
            UNCONFIRMED_THREAD_ID: _thread(UNCONFIRMED_THREAD_ID, UNDURABLE_SEAT),
        }
        self._unfolded: list[tuple[str, dict[str, Any]]] = []
        self.commands: list[dict[str, Any]] = []
        self.composes: list[dict[str, Any]] = []

    def projection(self) -> dict[str, Any]:
        opened = self._threads.get(COMPOSED_THREAD_ID)
        composed = (
            []
            if opened is None or not cast("list[object]", opened["messages"])
            else [_summary(COMPOSED_THREAD_ID, COMPOSE_SEAT)]
        )
        return {
            "recipient": SELF_SEAT,
            "threads": [
                _summary(THREAD_ID, OTHER_SEAT),
                _summary(REFUSED_THREAD_ID, STRANGER_SEAT),
                _summary(UNCONFIRMED_THREAD_ID, UNDURABLE_SEAT),
                *composed,
            ],
            "total_unread": 6 + 2 * len(composed),
            "unread_only": False,
        }

    def correspondents(self) -> dict[str, Any]:
        """The closed world the picker offers, as the record itself lists it."""
        return {
            "sender": SELF_SEAT,
            "correspondents": [{"project_key": "ctower", "seat_key": seat} for seat in ADDRESSABLE],
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
                "from": SELF_SEAT,
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

    def compose(self, payload: dict[str, Any], key: str | None) -> tuple[int, dict[str, Any]]:
        """Open or continue the one thread this seat pair has, from the seat alone.

        The thread identity is the record's answer, never the caller's: this
        stub derives one per unordered seat pair the way the real pair-grouped
        path does, so a compose to a seat this principal already has a thread
        with continues that thread rather than opening a second one. The seat
        also decides which of the three answers comes back, because a compose
        has to tell an accepted conversation from an unconfirmed one and from a
        refusal.
        """
        with self._lock:
            self.composes.append({"payload": payload, "idempotency_key": key})
            to = str(payload["to"])
            if to == STRANGER_SEAT:
                return _UNPROCESSABLE, _REFUSAL
            if to == UNDURABLE_SEAT:
                # the pair already has a thread; nothing is folded into it,
                # because nothing here is a fact anyone has promised to keep
                joined = self._threads[UNCONFIRMED_THREAD_ID]
                settled = len(cast("list[object]", joined["messages"]))
                return _PENDING_DURABILITY, _result(
                    UNCONFIRMED_THREAD_ID, to, settled + 1, "durability_pending"
                )
            thread = self._threads.setdefault(
                COMPOSED_THREAD_ID,
                {
                    "thread_id": COMPOSED_THREAD_ID,
                    "participants": [SELF_SEAT, to],
                    "messages": [],
                    "read_through_position": 0,
                    "promoted_ticket_id": None,
                },
            )
            position = len(cast("list[object]", thread["messages"])) + len(self._unfolded) + 1
            self._unfolded.append(
                (
                    COMPOSED_THREAD_ID,
                    {
                        "message_id": f"018f0d5e-7b9a-7c01-8000-0000000007{position:02d}",
                        "position": position,
                        "from": SELF_SEAT,
                        "to": to,
                        "text": str(payload["text"]),
                        "sent_at": "2026-08-09T03:05:00Z",
                    },
                )
            )
            return _CREATED, _result(COMPOSED_THREAD_ID, to, position, "accepted")


class _RecordStub(BaseHTTPRequestHandler):
    """The read paths this screen asks for, the one command it sends, nothing else."""

    protocol_version = "HTTP/1.1"
    record: ClassVar[Record]

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/v1/inbox/threads":
            self._answer(_OK, self.record.projection())
        elif path == "/v1/inbox/correspondents":
            self._answer(_OK, self.record.correspondents())
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
        path = self.path.split("?", 1)[0]
        if path not in {"/v1/inbox/messages", "/v1/inbox/notifications"}:
            self._answer(_NOT_FOUND, {"detail": "the stub record source accepts no such command"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = cast("dict[str, Any]", json.loads(self.rfile.read(length)))
        key = self.headers.get("Idempotency-Key")
        if path == "/v1/inbox/notifications":
            status, document = self.record.compose(payload, key)
            problem = "application/problem+json"
            self._answer(
                status,
                document,
                content_type=problem if status == _UNPROCESSABLE else "application/json",
            )
            return
        thread_id = str(payload.get("thread_id"))
        if thread_id == REFUSED_THREAD_ID:
            self.record.refuse(payload, key)
            self._answer(_UNPROCESSABLE, _REFUSAL, content_type="application/problem+json")
            return
        if thread_id == UNCONFIRMED_THREAD_ID:
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
def record_stub(record: Record) -> Iterator[str]:
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
def dogfood_server(record_base_url: str) -> Iterator[int]:
    """Build the separate dogfood server and serve it on an ephemeral port."""
    next_binary = _executable(_NEXT, "pnpm install --frozen-lockfile")
    environment = {
        **os.environ,
        "CTOWER_UI_API_BASE_URL": record_base_url,
        "CTOWER_UI_API_TOKEN": CREDENTIAL,
        "CTOWER_UI_INSTANCE_LABEL": INSTANCE_LABEL,
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
        if route_body(port, "/inbox") is not None:
            return
        time.sleep(_READY_POLL_SECONDS)
    raise RuntimeError(
        f"the dogfood server did not serve /inbox within {_READY_TIMEOUT_SECONDS:d}s"
    )


def route_body(port: int, route: str) -> str | None:
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


def drive_surface(port: int, screenshots: Path) -> dict[str, Any]:
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
                THREAD_ID,
                REFUSED_THREAD_ID,
                UNCONFIRMED_THREAD_ID,
                COMPOSE_SEAT,
                STRANGER_SEAT,
                UNDURABLE_SEAT,
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
