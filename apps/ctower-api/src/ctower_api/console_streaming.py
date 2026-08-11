"""Bounded ASGI delivery for Console SSE events."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
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
        self._console_body = _bounded_events(stream)
        super().__init__(
            self._console_body,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )
        self._stall_seconds = float(stream.maximum_stall_seconds)

    async def stream_response(self, send: Send) -> None:
        await send(
            {"type": "http.response.start", "status": self.status_code, "headers": self.raw_headers}
        )
        try:
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
            await self._console_body.aclose()
            raise OSError("Console SSE transport exceeded its bounded send deadline") from error


def console_streaming_response(stream: ConsoleEventStream) -> StreamingResponse:
    """Build the only HTTP response that may consume a Console event stream."""

    return _ConsoleStreamingResponse(stream)


async def _bounded_events(stream: ConsoleEventStream) -> AsyncGenerator[bytes, None]:
    queue: asyncio.Queue[_QueuedEvent | object] = asyncio.Queue()
    pending = [0]
    producer = asyncio.create_task(_produce(stream, queue, pending))
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
            producer.cancel()
        await asyncio.gather(producer, return_exceptions=True)


async def _produce(
    stream: ConsoleEventStream,
    queue: asyncio.Queue[_QueuedEvent | object],
    pending: list[int],
) -> None:
    try:
        while True:
            event = await asyncio.to_thread(_next_event, stream)
            if event is None:
                return
            queued = _QueuedEvent(event, _decoded_chunk_bytes(event))
            if pending[0] + queued.decoded_bytes > stream.maximum_pending_bytes:
                await _queue_slow_close(stream, queue, pending)
                return
            pending[0] += queued.decoded_bytes
            queue.put_nowait(queued)
    finally:
        queue.put_nowait(_END)


async def _queue_slow_close(
    stream: ConsoleEventStream,
    queue: asyncio.Queue[_QueuedEvent | object],
    pending: list[int],
) -> None:
    _discard_waiting(queue, pending)
    closing = await asyncio.to_thread(stream.close_slow_consumer)
    for terminal in closing:
        queue.put_nowait(_QueuedEvent(terminal, 0))


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
