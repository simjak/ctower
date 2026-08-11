"""Bounded ASGI delivery for Console SSE events."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from threading import Event
from typing import cast

from starlette.responses import StreamingResponse
from starlette.types import Send

from ctower_kernel.console import ConsoleEventStream

__all__ = ["console_streaming_response"]


@dataclass(frozen=True, slots=True)
class _QueuedEvent:
    body: bytes
    decoded_bytes: int


_END = object()


class _ConsoleStreamingResponse(StreamingResponse):
    def __init__(self, stream: ConsoleEventStream) -> None:
        self._stream = stream
        self._slow_close_requested = Event()
        self._client_disconnected_requested = Event()
        self._console_body = _bounded_events(
            stream,
            self._slow_close_requested,
            self._client_disconnected_requested,
        )
        super().__init__(
            self._console_body,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )
        self._stall_seconds = float(stream.maximum_stall_seconds)

    async def stream_response(self, send: Send) -> None:
        try:
            await send(
                {
                    "type": "http.response.start",
                    "status": self.status_code,
                    "headers": self.raw_headers,
                }
            )
            async for chunk in self.body_iterator:
                await asyncio.wait_for(
                    send({"type": "http.response.body", "body": chunk, "more_body": True}),
                    timeout=self._stall_seconds,
                )
            await asyncio.wait_for(
                send({"type": "http.response.body", "body": b"", "more_body": False}),
                timeout=self._stall_seconds,
            )
        except TimeoutError as error:
            self._slow_close_requested.set()
            self._stream.request_slow_consumer()
            async for _discarded in self.body_iterator:
                pass
            raise OSError("Console SSE transport exceeded its bounded send deadline") from error
        except OSError:
            self._request_client_disconnected()
            raise
        except asyncio.CancelledError:
            self._request_client_disconnected()
            raise
        finally:
            await self._console_body.aclose()
            if self._client_disconnected_requested.is_set():
                await asyncio.to_thread(self._stream.close_client_disconnected)

    def _request_client_disconnected(self) -> None:
        self._client_disconnected_requested.set()
        self._stream.request_client_disconnected()


def console_streaming_response(stream: ConsoleEventStream) -> StreamingResponse:
    """Build the only HTTP response that may consume a Console event stream."""

    return _ConsoleStreamingResponse(stream)


async def _bounded_events(
    stream: ConsoleEventStream,
    slow_close_requested: Event,
    client_disconnected_requested: Event,
) -> AsyncGenerator[bytes, None]:
    queue: asyncio.Queue[_QueuedEvent | object] = asyncio.Queue()
    pending = [0]
    producer = asyncio.create_task(
        _produce(
            stream,
            queue,
            pending,
            slow_close_requested,
            client_disconnected_requested,
        )
    )
    try:
        while True:
            item = await queue.get()
            if item is _END:
                return
            queued = cast(_QueuedEvent, item)
            try:
                yield queued.body
            finally:
                pending[0] -= queued.decoded_bytes
    finally:
        if not producer.done():
            stream.request_client_disconnected()
        await asyncio.gather(producer, return_exceptions=True)


async def _produce(
    stream: ConsoleEventStream,
    queue: asyncio.Queue[_QueuedEvent | object],
    pending: list[int],
    slow_close_requested: Event,
    client_disconnected_requested: Event,
) -> None:
    try:
        while True:
            if client_disconnected_requested.is_set():
                await _queue_client_close(stream, queue, pending)
                return
            if slow_close_requested.is_set():
                await _queue_slow_close(stream, queue, pending, client_disconnected_requested)
                return
            event = await asyncio.to_thread(_next_event, stream)
            if client_disconnected_requested.is_set():
                await _queue_client_close(stream, queue, pending)
                return
            if slow_close_requested.is_set():
                await _queue_slow_close(
                    stream,
                    queue,
                    pending,
                    client_disconnected_requested,
                    first_event=event,
                )
                return
            if event is None:
                return
            queued = _QueuedEvent(event, _decoded_chunk_bytes(event))
            if pending[0] + queued.decoded_bytes > stream.maximum_pending_bytes:
                await _queue_slow_close(stream, queue, pending, client_disconnected_requested)
                return
            pending[0] += queued.decoded_bytes
            queue.put_nowait(queued)
    finally:
        queue.put_nowait(_END)


async def _queue_slow_close(
    stream: ConsoleEventStream,
    queue: asyncio.Queue[_QueuedEvent | object],
    pending: list[int],
    client_disconnected_requested: Event,
    *,
    first_event: bytes | None = None,
) -> None:
    await asyncio.sleep(0)
    if client_disconnected_requested.is_set():
        await _queue_client_close(stream, queue, pending)
        return
    _discard_waiting(queue, pending)
    stream.request_slow_consumer()
    closing = await asyncio.to_thread(stream.close_slow_consumer)
    if first_event is not None and _is_slow_consumer_gap(first_event):
        closing = (first_event, *closing)
    for terminal in closing:
        queue.put_nowait(_QueuedEvent(terminal, 0))


async def _queue_client_close(
    stream: ConsoleEventStream,
    queue: asyncio.Queue[_QueuedEvent | object],
    pending: list[int],
) -> None:
    _discard_waiting(queue, pending)
    stream.request_client_disconnected()
    await asyncio.to_thread(stream.close_client_disconnected)


def _is_slow_consumer_gap(event: bytes) -> bool:
    return b"event: gap\n" in event and b'"reason":"slow_consumer"' in event


def _next_event(stream: ConsoleEventStream) -> bytes | None:
    try:
        return next(stream.events)
    except StopIteration:
        return None


def _decoded_chunk_bytes(event: bytes) -> int:
    if b"event: chunk\n" not in event:
        return 0
    for line in event.splitlines():
        if line.startswith(b"data: "):
            payload = json.loads(line.removeprefix(b"data: "))
            encoded = payload["data"]
            if not isinstance(encoded, str):
                raise RuntimeError("Console chunk data is not encoded text")
            padding = len(encoded) - len(encoded.rstrip("="))
            return (len(encoded) * 3 // 4) - padding
    raise RuntimeError("Console chunk has no data frame")


def _discard_waiting(queue: asyncio.Queue[_QueuedEvent | object], pending: list[int]) -> None:
    while True:
        try:
            item = queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        if item is not _END:
            pending[0] -= cast(_QueuedEvent, item).decoded_bytes
