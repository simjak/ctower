"""Small refusal predicates for Console Postgres authority decisions."""

from __future__ import annotations

from datetime import datetime
from typing import cast

from ctower_kernel.console.models import (
    ConsoleBackendObservation,
    ConsolePolicy,
    ConsoleSessionRef,
)
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem

__all__: tuple[str, ...] = ()


def stream_claim_refusal(
    row: dict[str, object],
    actor: Actor,
    policy: ConsolePolicy,
    *,
    now: datetime,
) -> RecordProblem | None:
    """Return the first stable refusal for an exact stream claim."""

    checks = (
        _grant_refusal(row, policy, now=now),
        _human_refusal(row, now=now),
        _project_refusal(row, actor),
        _session_refusal(row),
    )
    return next((refusal for refusal in checks if refusal is not None), None)


def stream_close_reason(
    row: dict[str, object] | None,
    policy: ConsolePolicy,
    *,
    now: datetime,
) -> str | None:
    """Map current authority facts to one typed active-stream closure."""

    if row is None or _human_authority_stale(row, now=now):
        return "reauthentication_required"
    if cast(datetime, row["expires_at"]) <= now:
        return "expired"
    if bool(row["global_enabled"]):
        return "globally_disabled"
    if str(row["policy_revision"]) != policy.policy_revision:
        return "fenced"
    if _session_authority_stale(row):
        return "revoked"
    return None


def session_join_refusal(
    row: dict[str, object] | None, ref: ConsoleSessionRef
) -> RecordProblem | None:
    """Require the exact current non-Commander assignment/session join."""

    if row is None:
        return _problem(
            "console-session-join-stale",
            "The recorded session does not join the exact assignment interval.",
        )
    if not _session_join_matches(row, ref):
        return _problem(
            "console-session-join-stale",
            "The recorded session is not the current exact assignment/session join.",
        )
    return None


def _allow_request_refusal(
    actor: Actor,
    ref: ConsoleSessionRef,
    observation: ConsoleBackendObservation,
) -> RecordProblem | None:
    refusal = _allow_authority_refusal(actor, ref)
    return refusal if refusal is not None else _observation_refusal(ref, observation)


def _allow_authority_refusal(actor: Actor, ref: ConsoleSessionRef) -> RecordProblem | None:
    if actor.kind is not PrincipalKind.OPERATOR:
        return _problem(
            "console-allowlist-refused", "Console allowlisting requires operator authority."
        )
    if actor.tenant_id != ref.tenant_id:
        return _problem("console-session-unavailable", "The recorded session is unavailable.", 404)
    return None


def _observation_refusal(
    ref: ConsoleSessionRef, observation: ConsoleBackendObservation
) -> RecordProblem | None:
    checks = (
        (observation.project_key != ref.project_key, "console-project-fence-mismatch"),
        (
            observation.runtime_attempt_id != ref.runtime_attempt_id,
            "console-runtime-attempt-fenced",
        ),
        (observation.runner_id != ref.runner_id, "console-runner-fenced"),
        (observation.runner_epoch != ref.runner_epoch, "console-runner-epoch-fenced"),
        (observation.opaque_backend_ref != ref.opaque_backend_ref, "console-backend-fenced"),
        (observation.backend_incarnation != ref.backend_incarnation, "console-incarnation-fenced"),
    )
    for refused, code in checks:
        if refused:
            return _problem(
                code, "The live Adapter facts do not match the exact session reference."
            )
    return None


def _observation_from_ref(ref: ConsoleSessionRef) -> ConsoleBackendObservation:
    return ConsoleBackendObservation(
        project_key=ref.project_key,
        runtime_attempt_id=ref.runtime_attempt_id,
        runner_id=ref.runner_id,
        runner_epoch=ref.runner_epoch,
        opaque_backend_ref=ref.opaque_backend_ref,
        backend_incarnation=ref.backend_incarnation,
    )


def _grant_refusal(
    row: dict[str, object], policy: ConsolePolicy, *, now: datetime
) -> RecordProblem | None:
    suspended_until = cast(datetime | None, row.get("suspended_until"))
    if suspended_until is not None and suspended_until > now:
        return _problem(
            "console-actor-suspended",
            "The Actor is temporarily suspended after repeated denials.",
        )
    if cast(datetime, row["expires_at"]) <= now:
        return _problem("console-grant-expired", "The ConsoleViewGrant has expired.", 401)
    if cast(datetime, row["not_before"]) > now or bool(row["grant_used"]):
        return _problem("console-grant-unavailable", "No active unused grant is available.", 401)
    if str(row["policy_revision"]) != policy.policy_revision:
        return _problem("console-policy-stale", "The Console policy revision changed.")
    if bool(row["global_enabled"]):
        return _problem("console-globally-disabled", "Console viewing is disabled.")
    return None


def _human_refusal(row: dict[str, object], *, now: datetime) -> RecordProblem | None:
    if not _human_authority_stale(row, now=now):
        return None
    return _problem(
        "console-reauthentication-required",
        "The exact human authorization is no longer current.",
        401,
    )


def _project_refusal(row: dict[str, object], actor: Actor) -> RecordProblem | None:
    if (
        actor.kind is not PrincipalKind.COMMANDER
        and str(row["project_key"]) in actor.project_grants
    ):
        return None
    return _problem("console-project-refused", "The Project is unavailable.", 404)


def _session_refusal(row: dict[str, object]) -> RecordProblem | None:
    if not _session_authority_stale(row):
        return None
    return _problem("console-session-revoked", "The console session is revoked.")


def _human_authority_stale(row: dict[str, object], *, now: datetime) -> bool:
    return (
        bool(row["human_session_revoked"])
        or bool(row["binding_revoked"])
        or cast(datetime, row["human_session_expires_at"]) <= now
    )


def _session_authority_stale(row: dict[str, object]) -> bool:
    return (
        bool(row["grant_revoked"])
        or bool(row["session_revoked"])
        or not bool(row["assignment_current"])
        or not bool(row["work_session_current"])
    )


def _session_join_matches(row: dict[str, object], ref: ConsoleSessionRef) -> bool:
    return (
        str(row["project_key"]) == ref.project_key
        and str(row["crew_name"]) == ref.crew_name
        and row["started_by"] == ref.seat_principal_id
        and row["principal_id"] == ref.seat_principal_id
        and str(row["kind"]) != "commander"
        and not bool(row["disabled"])
        and row["released_at"] is None
        and not bool(row["closed"])
    )


def _problem(code: str, detail: str, status: int = 403) -> RecordProblem:
    return RecordProblem(code=code, detail=detail, status=status, title="Console operation refused")
