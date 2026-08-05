from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

import pytest

from ctower_kernel.record.attention_events import (
    AttentionFindingAppendedPayload,
    AttentionFindingDispositionRecordedPayload,
)

_DIGEST = "sha256:" + "a" * 64
_UUID_1 = UUID(int=1)


def test_attention_finding_appended_payload_is_a_strict_recorded_fact() -> None:
    payload = _finding()

    assert payload.to_mapping()["kind_key"] == "needs_decision"


def test_attention_finding_appended_payload_rejects_every_malformed_field() -> None:
    with pytest.raises(TypeError, match="must be UUIDs"):
        _finding(subject_ticket_id=cast(UUID, "not-a-uuid"))
    with pytest.raises(ValueError, match="kind is outside"):
        _finding(kind_key="Not Valid")
    with pytest.raises(ValueError, match="catalog key is outside"):
        _finding(catalog_key="Not Valid")
    with pytest.raises(ValueError, match="revision must be positive"):
        _finding(catalog_revision=0)
    with pytest.raises(ValueError, match="content addressed"):
        _finding(catalog_digest="not-a-digest")
    with pytest.raises(ValueError, match="reason code is outside"):
        _finding(reason_code="Not Valid")
    with pytest.raises(ValueError, match="owner is outside"):
        _finding(effective_owner="auditor")
    with pytest.raises(ValueError, match="recommendation is outside"):
        _finding(recommendation="")
    with pytest.raises(ValueError, match="consequence is outside"):
        _finding(consequence="")
    with pytest.raises(ValueError, match="dedupe key is outside"):
        _finding(dedupe_key="!!")
    with pytest.raises(ValueError, match="timezone-aware"):
        _finding(deadline=datetime(2026, 8, 5))  # noqa: DTZ001


def test_attention_finding_disposition_payload_is_a_strict_recorded_fact() -> None:
    payload = _disposition()

    assert payload.to_mapping()["outcome"] == "resolved"


def test_attention_finding_disposition_payload_rejects_every_malformed_field() -> None:
    with pytest.raises(TypeError, match="must be UUIDs"):
        _disposition(finding_id=cast(UUID, "not-a-uuid"))
    with pytest.raises(ValueError, match="disposition is outside"):
        _disposition(outcome="withdrawn")
    with pytest.raises(ValueError, match="reason is outside"):
        _disposition(reason="")


def _finding(
    *,
    subject_ticket_id: UUID = _UUID_1,
    kind_key: str = "needs_decision",
    catalog_key: str = "attention.needs-you-kinds",
    catalog_revision: int = 1,
    catalog_digest: str = _DIGEST,
    reason_code: str = "gate_decision",
    effective_owner: str = "operator",
    recommendation: str = "Approve the release train",
    consequence: str = "Release stays blocked",
    deadline: datetime | None = None,
    dedupe_key: str = "release-gate-1",
) -> AttentionFindingAppendedPayload:
    return AttentionFindingAppendedPayload(
        finding_id=uuid4(),
        subject_ticket_id=subject_ticket_id,
        kind_key=kind_key,
        catalog_key=catalog_key,
        catalog_revision=catalog_revision,
        catalog_digest=catalog_digest,
        reason_code=reason_code,
        effective_owner=effective_owner,
        recommendation=recommendation,
        alternatives=(),
        consequence=consequence,
        deadline=deadline,
        dedupe_key=dedupe_key,
        source_facts=(),
    )


def _disposition(
    *,
    finding_id: UUID = _UUID_1,
    outcome: str = "resolved",
    reason: str = "Decision made",
) -> AttentionFindingDispositionRecordedPayload:
    return AttentionFindingDispositionRecordedPayload(
        disposition_id=uuid4(),
        finding_id=finding_id,
        outcome=outcome,
        reason=reason,
    )
