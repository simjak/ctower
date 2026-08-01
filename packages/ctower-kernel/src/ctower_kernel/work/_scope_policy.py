"""Work-owned enforcement for issued project-seat mutation scopes."""

from __future__ import annotations

from uuid import UUID

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.credentials import CredentialScope

__all__: tuple[str, ...] = ()


def credential_scope_refusal(
    actor: Actor,
    scope: CredentialScope,
    *,
    command_id: UUID | None = None,
) -> RecordProblem | None:
    """Return the stable refusal for a seat bearer missing one named scope."""

    if actor.seat_credential_id is None or scope in actor.credential_scopes:
        return None
    return RecordProblem(
        code="credential-scope-denied",
        detail=f"The project-seat credential does not grant the {scope.value} scope.",
        status=403,
        title="Credential scope denied",
        command_id=command_id,
    )
