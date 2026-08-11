"""Serialized transport requests for one claimed Console event stream."""

from __future__ import annotations

from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass, field
from threading import Event, Lock

from ctower_kernel.console.models import ConsoleStreamLease

__all__ = ["ConsoleEventStream"]


@dataclass(frozen=True, slots=True)
class ConsoleEventStream:
    """Claimed stream plus its lazily driven SSE body."""

    lease: ConsoleStreamLease
    events: Iterator[bytes]
    maximum_pending_bytes: int
    maximum_stall_seconds: int
    _slow_consumer_request: Callable[[], None]
    _client_disconnected_request: Callable[[], None]
    _slow_consumer_close: Callable[[], tuple[bytes, ...]]
    _client_disconnected_close: Callable[[], tuple[bytes, ...]]
    _event_lock: Lock = field(default_factory=Lock, repr=False, compare=False)

    def next_event(self) -> bytes | None:
        """Advance the synchronous generator through its one serialized owner."""

        with self._event_lock:
            try:
                return next(self.events)
            except StopIteration:
                return None

    def request_slow_consumer(self) -> None:
        """Wake the serialized generator so its own thread commits the typed close."""

        self._slow_consumer_request()

    def close_slow_consumer(self) -> tuple[bytes, ...]:
        """Close after the HTTP transport proves its unsent queue crossed the bound."""

        self.request_slow_consumer()
        with self._event_lock:
            return self._slow_consumer_close()

    def request_client_disconnected(self) -> None:
        """Wake the serialized generator after the transport proves disconnection."""

        self._client_disconnected_request()

    def close_client_disconnected(self) -> tuple[bytes, ...]:
        """Drain the generator on its owner thread and persist one disconnect close."""

        self.request_client_disconnected()
        with self._event_lock:
            return self._client_disconnected_close()


@dataclass(slots=True)
class _TransportRequests:
    slow_consumer: Event
    client_disconnected: Event
    wake: Event

    @classmethod
    def create(cls) -> _TransportRequests:
        return cls(Event(), Event(), Event())

    def request_slow_consumer(self) -> None:
        self.slow_consumer.set()
        self.wake.set()

    def request_client_disconnected(self) -> None:
        self.client_disconnected.set()
        self.wake.set()


def _drain_events(events: Iterator[bytes]) -> tuple[bytes, ...]:
    generator = events if isinstance(events, Generator) else None
    if generator is None:
        raise RuntimeError("Console stream events do not accept transport closure")
    closed: list[bytes] = []
    try:
        while True:
            closed.append(next(generator))
    except StopIteration:
        return tuple(closed)
