"""RED-first tests for per-object envelope custody and reader separation."""

from __future__ import annotations

from uuid import UUID

import pytest

from ctower_kernel.console import AesGcmConsoleCipher, ConsoleCiphertext

MASTER_KEY = bytes(range(32))
OBJECT_ONE = UUID("10000000-0000-0000-0000-000000000001")
OBJECT_TWO = UUID("10000000-0000-0000-0000-000000000002")


def _cipher() -> AesGcmConsoleCipher:
    return AesGcmConsoleCipher(
        wrapping_key=MASTER_KEY,
        wrapping_key_reference="secret-service:ctower-development/console-output-kek",
    )


def test_every_object_has_a_distinct_wrapped_data_key_and_no_plaintext() -> None:
    first = _cipher().encrypt(OBJECT_ONE, b"RESTRICTED pane bytes", aad=b"tenant/session/1")
    second = _cipher().encrypt(OBJECT_TWO, b"RESTRICTED pane bytes", aad=b"tenant/session/2")
    assert isinstance(first, ConsoleCiphertext)
    assert first.data_key_reference != second.data_key_reference
    assert first.wrapped_data_key != second.wrapped_data_key
    assert b"RESTRICTED pane bytes" not in first.ciphertext


def test_only_the_dedicated_console_output_reader_can_decrypt() -> None:
    envelope = _cipher().encrypt(OBJECT_ONE, b"pane bytes", aad=b"tenant/session/1")
    with pytest.raises(PermissionError, match="console_output_reader"):
        _cipher().decrypt(envelope, reader="ctower_svc", aad=b"tenant/session/1")
    assert (
        _cipher().decrypt(envelope, reader="console_output_reader", aad=b"tenant/session/1")
        == b"pane bytes"
    )


def test_ciphertext_is_bound_to_its_exact_tenant_session_cursor_aad() -> None:
    envelope = _cipher().encrypt(OBJECT_ONE, b"pane bytes", aad=b"tenant/session/1")
    with pytest.raises(ValueError, match="authentication"):
        _cipher().decrypt(
            envelope,
            reader="console_output_reader",
            aad=b"other-tenant/session/1",
        )


def test_wrapping_key_must_be_exactly_256_bits_and_reference_is_not_a_value() -> None:
    with pytest.raises(ValueError, match="256-bit"):
        AesGcmConsoleCipher(wrapping_key=b"short", wrapping_key_reference="secret-ref")
    with pytest.raises(ValueError, match="reference"):
        AesGcmConsoleCipher(wrapping_key=MASTER_KEY, wrapping_key_reference="plaintext-secret")
