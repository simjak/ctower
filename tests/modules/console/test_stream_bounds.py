"""RED-first tests for SSE chunk, replay, rolling-rate, and pending-byte bounds."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

import pytest

from ctower_kernel.console import ConsoleStreamWindow, StreamDisposition, encode_console_chunks

NOW = datetime(2026, 8, 10, 22, 0, tzinfo=UTC)


def _window() -> ConsoleStreamWindow:
    return ConsoleStreamWindow(
        delivery_window_bytes=1024 * 1024,
        delivery_window_seconds=60,
        replay_window_bytes=1024 * 1024,
        replay_window_seconds=60,
        pending_bytes=256 * 1024,
    )


def test_chunks_are_base64_and_decode_to_at_most_sixteen_kibibytes() -> None:
    payload = bytes(range(256)) * 257
    chunks = tuple(encode_console_chunks(payload, decoded_chunk_bytes=16 * 1024))
    assert b"".join(base64.b64decode(chunk) for chunk in chunks) == payload
    assert max(len(base64.b64decode(chunk)) for chunk in chunks) == 16 * 1024


def test_delivery_is_limited_to_one_mibibyte_in_a_rolling_sixty_seconds() -> None:
    window = _window()
    assert window.admit_delivery(1024 * 1024, at=NOW) is StreamDisposition.ADMITTED
    assert (
        window.admit_delivery(1, at=NOW + timedelta(seconds=59)) is StreamDisposition.RATE_LIMITED
    )
    assert window.admit_delivery(1, at=NOW + timedelta(seconds=60)) is StreamDisposition.ADMITTED


def test_replay_has_an_independent_one_mibibyte_sixty_second_budget() -> None:
    window = _window()
    assert window.admit_replay(1024 * 1024, at=NOW) is StreamDisposition.ADMITTED
    assert window.admit_replay(1, at=NOW + timedelta(seconds=59)) is StreamDisposition.RATE_LIMITED
    assert window.admit_delivery(1, at=NOW + timedelta(seconds=59)) is StreamDisposition.ADMITTED


def test_pending_output_above_256_kibibytes_closes_as_slow_consumer_with_gap() -> None:
    window = _window()
    assert window.add_pending(256 * 1024) is StreamDisposition.ADMITTED
    assert window.add_pending(1) is StreamDisposition.SLOW_CONSUMER
    assert window.gap_required


def test_flushing_pending_bytes_never_underflows() -> None:
    window = _window()
    assert window.add_pending(10) is StreamDisposition.ADMITTED
    window.flush_pending(10)
    assert window.pending == 0


def test_malformed_cursor_or_unprovable_range_is_an_explicit_gap() -> None:
    window = _window()
    window.mark_gap("cursor-unavailable")
    assert window.gap_required
    assert window.gap_reason == "cursor-unavailable"


def test_stream_window_rejects_negative_and_empty_accounting_inputs() -> None:
    window = _window()
    with pytest.raises(ValueError, match="pending size"):
        window.add_pending(-1)
    with pytest.raises(ValueError, match="pending flush"):
        window.flush_pending(1)
    with pytest.raises(ValueError, match="gap reason"):
        window.mark_gap("")
    with pytest.raises(ValueError, match="stream size"):
        window.admit_delivery(-1, at=NOW)
    with pytest.raises(ValueError, match="rolling byte bounds"):
        ConsoleStreamWindow(
            delivery_window_bytes=0,
            delivery_window_seconds=60,
            replay_window_bytes=1,
            replay_window_seconds=60,
            pending_bytes=1,
        )


@pytest.mark.parametrize("size", [0, 16 * 1024 + 1])
def test_chunk_encoder_refuses_out_of_contract_decoded_bounds(size: int) -> None:
    with pytest.raises(ValueError, match="decoded_chunk_bytes"):
        tuple(encode_console_chunks(b"payload", decoded_chunk_bytes=size))
