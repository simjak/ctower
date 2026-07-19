"""Access Module behavior through its public Interface."""

from __future__ import annotations

import hashlib
from typing import cast
from uuid import uuid4

from ctower_kernel.access import Access
from ctower_kernel.record import Actor, PrincipalKind, Record, RecordProblem

__all__: tuple[str, ...] = ()


class _CredentialRecord:
    def __init__(self, actor: Actor | None) -> None:
        self.actor = actor
        self.observed_digest: bytes | None = None

    def actor_for_credential(self, credential_digest: bytes) -> Actor | None:
        self.observed_digest = credential_digest
        return self.actor


def test_authenticate_passes_only_a_digest_to_record() -> None:
    actor = Actor(uuid4(), uuid4(), PrincipalKind.OPERATOR)
    record = _CredentialRecord(actor)

    outcome = Access(cast(Record, record)).authenticate("Bearer opaque-runtime-input")

    assert outcome == actor
    assert record.observed_digest == hashlib.sha256(b"opaque-runtime-input").digest()


def test_authenticate_refuses_missing_malformed_and_unknown_credentials() -> None:
    record = _CredentialRecord(None)
    access = Access(cast(Record, record))

    outcomes = (
        access.authenticate(None),
        access.authenticate("Basic value"),
        access.authenticate("Bearer "),
        access.authenticate("Bearer padded "),
        access.authenticate("Bearer unknown"),
    )

    assert all(isinstance(outcome, RecordProblem) for outcome in outcomes)
    assert {cast(RecordProblem, outcome).code for outcome in outcomes} == {"unauthorized"}
