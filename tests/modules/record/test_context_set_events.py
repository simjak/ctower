from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

import pytest

from ctower_kernel.record.context_set_events import (
    ChangeReferenceRecordedPayload,
    LabelAppliedPayload,
)

_DIGEST = "sha256:" + "a" * 64
_TICKET_ID = UUID(int=1)


def test_change_reference_payload_is_a_strict_recorded_fact() -> None:
    payload = ChangeReferenceRecordedPayload(
        change_reference_id=uuid4(),
        ticket_id=uuid4(),
        repository="simjak/ctower",
        change_identity="284",
        reference="https://github.com/simjak/ctower/pull/284",
    )

    assert payload.to_mapping()["repository"] == "simjak/ctower"


def test_change_reference_payload_rejects_every_malformed_field() -> None:
    with pytest.raises(TypeError, match="must be UUIDs"):
        _change_reference(ticket_id=cast(UUID, "not-a-uuid"))
    with pytest.raises(ValueError, match="repository is outside"):
        _change_reference(repository="")
    with pytest.raises(ValueError, match="identity is outside"):
        _change_reference(change_identity="")
    with pytest.raises(ValueError, match="reference is outside"):
        _change_reference(reference="")


def test_label_applied_payload_is_a_strict_recorded_fact() -> None:
    payload = LabelAppliedPayload(
        ticket_label_id=uuid4(),
        ticket_id=uuid4(),
        label_key="security",
        catalog_key="board.ticket-labels",
        catalog_revision=1,
        catalog_digest=_DIGEST,
    )

    assert payload.to_mapping()["label_key"] == "security"


def test_label_applied_payload_rejects_every_malformed_field() -> None:
    with pytest.raises(TypeError, match="must be UUIDs"):
        _label_applied(ticket_id=cast(UUID, "not-a-uuid"))
    with pytest.raises(ValueError, match="label key is outside"):
        _label_applied(label_key="Not Valid")
    with pytest.raises(ValueError, match="catalog key is outside"):
        _label_applied(catalog_key="Not Valid")
    with pytest.raises(ValueError, match="revision must be positive"):
        _label_applied(catalog_revision=0)
    with pytest.raises(ValueError, match="content addressed"):
        _label_applied(catalog_digest="not-a-digest")


def _change_reference(
    *,
    ticket_id: UUID = _TICKET_ID,
    repository: str = "simjak/ctower",
    change_identity: str = "284",
    reference: str = "https://github.com/simjak/ctower/pull/284",
) -> ChangeReferenceRecordedPayload:
    return ChangeReferenceRecordedPayload(
        change_reference_id=uuid4(),
        ticket_id=ticket_id,
        repository=repository,
        change_identity=change_identity,
        reference=reference,
    )


def _label_applied(
    *,
    ticket_id: UUID = _TICKET_ID,
    label_key: str = "security",
    catalog_key: str = "board.ticket-labels",
    catalog_revision: int = 1,
    catalog_digest: str = _DIGEST,
) -> LabelAppliedPayload:
    return LabelAppliedPayload(
        ticket_label_id=uuid4(),
        ticket_id=ticket_id,
        label_key=label_key,
        catalog_key=catalog_key,
        catalog_revision=catalog_revision,
        catalog_digest=catalog_digest,
    )
