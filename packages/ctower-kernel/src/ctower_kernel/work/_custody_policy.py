"""Shared Work policy for establishing initial ticket custody."""

from __future__ import annotations

from uuid import UUID

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem

__all__: tuple[str, ...] = ()


def initial_custody_refusal(
    actor: Actor,
    command_id: UUID,
    custodian_id: UUID,
) -> RecordProblem | None:
    """Authorize who may establish normal Commander custody."""

    commander_self_custody = (
        actor.kind is PrincipalKind.COMMANDER and custodian_id == actor.principal_id
    )
    operator_placing_commander = (
        actor.kind is PrincipalKind.OPERATOR and custodian_id != actor.principal_id
    )
    if commander_self_custody or operator_placing_commander:
        return None
    return RecordProblem(
        code="unauthorized",
        detail=(
            "Initial custody requires Commander self-custody or an operator placing "
            "custody with an eligible Commander."
        ),
        status=403,
        title="Initial custody refused",
        command_id=command_id,
    )
