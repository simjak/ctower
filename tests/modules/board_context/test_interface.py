from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

import pytest

from ctower_kernel.board_context.change_references import ChangeReferenceCommand
from ctower_kernel.board_context.labels import ApplyLabelCommand

_TICKET_ID = UUID(int=1)


def test_change_reference_command_is_a_strict_authenticated_request() -> None:
    command = _change_reference()

    assert command.request_payload()["repository"] == "simjak/ctower"


def test_change_reference_command_rejects_every_malformed_field() -> None:
    with pytest.raises(TypeError, match="must be UUIDs"):
        _change_reference(ticket_id=cast(UUID, "not-a-uuid"))
    with pytest.raises(ValueError, match="repository is outside"):
        _change_reference(repository="")
    with pytest.raises(ValueError, match="identity is outside"):
        _change_reference(change_identity="")
    with pytest.raises(ValueError, match="reference is outside"):
        _change_reference(reference="")


def test_apply_label_command_is_a_strict_authenticated_request() -> None:
    command = _apply_label()

    assert command.request_payload()["label_key"] == "security"


def test_apply_label_command_rejects_every_malformed_field() -> None:
    with pytest.raises(TypeError, match="must be UUIDs"):
        _apply_label(ticket_id=cast(UUID, "not-a-uuid"))
    with pytest.raises(ValueError, match="label key is outside"):
        _apply_label(label_key="Not Valid")


def _change_reference(
    *,
    ticket_id: UUID = _TICKET_ID,
    repository: str = "simjak/ctower",
    change_identity: str = "284",
    reference: str = "https://github.com/simjak/ctower/pull/284",
) -> ChangeReferenceCommand:
    return ChangeReferenceCommand(
        client_command_id=uuid4(),
        ticket_id=ticket_id,
        repository=repository,
        change_identity=change_identity,
        reference=reference,
    )


def _apply_label(
    *,
    ticket_id: UUID = _TICKET_ID,
    label_key: str = "security",
) -> ApplyLabelCommand:
    return ApplyLabelCommand(
        client_command_id=uuid4(),
        ticket_id=ticket_id,
        label_key=label_key,
    )
