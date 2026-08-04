"""Strict recorded-work-session payload, lifecycle, and read-model contracts."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin, event_catalog
from ctower_kernel.record.session_events import (
    INITIAL_SESSION_STATE,
    SessionClosedPayload,
    SessionOutcome,
    SessionStartedPayload,
    SessionState,
    SessionTransitionedPayload,
    session_payload_from_mapping,
    session_transition_allowed,
)
from ctower_kernel.record.sessions import (
    ProjectSessionPage,
    SessionCloseCommand,
    SessionReceipt,
    SessionStartCommand,
    SessionTokenUsage,
    SessionTransitionCommand,
    TicketSessionList,
    WorkSession,
    session_authored_text,
)

__all__: tuple[str, ...] = ()

SESSION_ID = UUID("019fbeff-df75-70e4-b3ca-130b438ec8be")
TICKET_ID = UUID("019fbeff-dc39-7231-a960-23161ea5fc32")
NOW = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)
_AUTHORED_TRANSITIONS = (
    (SessionState.DISPATCHED, SessionState.BRIEFED),
    (SessionState.BRIEFED, SessionState.WORKING),
    (SessionState.WORKING, SessionState.GATED),
    (SessionState.GATED, SessionState.WORKING),
)


def _started() -> SessionStartedPayload:
    return SessionStartedPayload(
        branch_ref="feat/200-session-facts",
        crew_name="engineer-g5-sessions",
        harness_ref="claude-code",
        model_ref="claude-opus-5",
        seat_key="engineer",
        session_id=SESSION_ID,
        ticket_id=TICKET_ID,
        worktree_ref="/srv/projects/ctower/.worktrees/g5-sessions",
    )


def _closed(**overrides: object) -> SessionClosedPayload:
    fields: dict[str, object] = {
        "duration_seconds": 5_400,
        "evidence_ref": "pr:simjak/ctower#200",
        "input_tokens": 412_000,
        "outcome": "delivered",
        "output_tokens": 38_500,
        "session_id": SESSION_ID,
        "ticket_id": TICKET_ID,
    }
    return SessionClosedPayload(**{**fields, **overrides})  # type: ignore[arg-type]


class TestAuthoredLifecycle:
    def test_a_started_session_is_dispatched(self) -> None:
        assert INITIAL_SESSION_STATE is SessionState.DISPATCHED

    @pytest.mark.parametrize(("from_state", "to_state"), _AUTHORED_TRANSITIONS)
    def test_every_authored_pair_is_allowed(
        self, from_state: SessionState, to_state: SessionState
    ) -> None:
        assert session_transition_allowed(from_state, to_state)

    def test_no_unauthored_pair_is_allowed(self) -> None:
        every_pair = {
            (from_state, to_state) for from_state in SessionState for to_state in SessionState
        }

        allowed = {pair for pair in every_pair if session_transition_allowed(*pair)}

        assert allowed == set(_AUTHORED_TRANSITIONS)


class TestPayloadsRefuseUnauthoredValues:
    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("crew_name", "Engineer G5"),
            ("seat_key", ""),
            ("harness_ref", "h" * 65),
            ("model_ref", ""),
            ("branch_ref", "b" * 257),
            ("worktree_ref", "w" * 257),
        ],
    )
    def test_started_refuses_an_out_of_contract_reference(self, field: str, value: str) -> None:
        with pytest.raises(ValueError, match="authored event contract"):
            replace(_started(), **{field: value})  # type: ignore[arg-type]

    def test_started_refuses_a_non_uuid_identity(self) -> None:
        with pytest.raises(TypeError, match="session_id must be a UUID"):
            SessionStartedPayload(
                branch_ref="main",
                crew_name="engineer",
                harness_ref="claude-code",
                model_ref="claude-opus-5",
                seat_key="engineer",
                session_id="019fbeff-df75-70e4-b3ca-130b438ec8be",  # type: ignore[arg-type]
                ticket_id=TICKET_ID,
                worktree_ref="/srv",
            )

    def test_transition_refuses_an_unauthored_state_pair(self) -> None:
        with pytest.raises(ValueError, match="outside the authored lifecycle"):
            SessionTransitionedPayload(
                from_state="dispatched",
                reason="Skip the brief",
                session_id=SESSION_ID,
                ticket_id=TICKET_ID,
                to_state="working",
                transition_number=1,
            )

    def test_transition_refuses_an_unknown_state(self) -> None:
        with pytest.raises(ValueError, match="outside the authored event contract"):
            SessionTransitionedPayload(
                from_state="dispatched",
                reason="Unknown target",
                session_id=SESSION_ID,
                ticket_id=TICKET_ID,
                to_state="finished",
                transition_number=1,
            )

    def test_transition_refuses_a_nonpositive_number(self) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            SessionTransitionedPayload(
                from_state="dispatched",
                reason="Brief read",
                session_id=SESSION_ID,
                ticket_id=TICKET_ID,
                to_state="briefed",
                transition_number=0,
            )

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("outcome", "shipped"),
            ("duration_seconds", -1),
            ("input_tokens", 1_000_000_001),
            ("output_tokens", -1),
            ("evidence_ref", ""),
        ],
    )
    def test_closed_refuses_an_out_of_contract_value(self, field: str, value: object) -> None:
        with pytest.raises(ValueError, match="authored event contract"):
            _closed(**{field: value})

    def test_closed_refuses_a_non_integer_count(self) -> None:
        with pytest.raises(TypeError, match="input_tokens must be an integer"):
            _closed(input_tokens=True)

    def test_closed_accepts_an_absent_evidence_reference(self) -> None:
        assert _closed(evidence_ref=None).to_mapping()["evidence_ref"] is None


class TestPersistenceBoundaryRebuild:
    @pytest.mark.parametrize(
        ("kind", "payload"),
        [
            (EventKind.SESSION_STARTED, _started()),
            (
                EventKind.SESSION_TRANSITIONED,
                SessionTransitionedPayload(
                    from_state="briefed",
                    reason="Building",
                    session_id=SESSION_ID,
                    ticket_id=TICKET_ID,
                    to_state="working",
                    transition_number=2,
                ),
            ),
            (EventKind.SESSION_CLOSED, _closed()),
        ],
    )
    def test_every_session_payload_round_trips(self, kind: EventKind, payload: object) -> None:
        mapping = payload.to_mapping()  # type: ignore[attr-defined]

        assert session_payload_from_mapping(kind, mapping) == payload

    def test_a_foreign_kind_is_refused(self) -> None:
        with pytest.raises(ValueError, match="not a recorded work-session event"):
            session_payload_from_mapping(EventKind.TICKET_CREATED, {})

    def test_an_extra_field_is_refused(self) -> None:
        with pytest.raises(ValueError, match="do not match the authored variant"):
            session_payload_from_mapping(
                EventKind.SESSION_STARTED, {**_started().to_mapping(), "pid": "4711"}
            )

    def test_a_wrongly_typed_field_is_refused(self) -> None:
        with pytest.raises(TypeError, match="crew_name must be a string"):
            session_payload_from_mapping(
                EventKind.SESSION_STARTED, {**_started().to_mapping(), "crew_name": 7}
            )

    def test_a_non_integer_token_count_is_refused(self) -> None:
        with pytest.raises(TypeError, match="input_tokens must be an integer"):
            session_payload_from_mapping(
                EventKind.SESSION_CLOSED, {**_closed().to_mapping(), "input_tokens": "412000"}
            )


class TestEnvelopeIdentity:
    def _envelope(self, aggregate_id: UUID) -> EventEnvelope:
        return EventEnvelope(
            actor_principal_id=TICKET_ID,
            aggregate_id=aggregate_id,
            causation_id=None,
            client_command_id=TICKET_ID,
            correlation_id=TICKET_ID,
            event_id=SESSION_ID,
            kind=EventKind.SESSION_STARTED,
            origin=EventOrigin.API,
            payload=_started(),
            prev_hash=bytes(32),
            request_sha256=bytes(32),
            sequence=1,
            server_time=NOW,
            stream_id=f"session:{aggregate_id}",
            tenant_id=TICKET_ID,
        )

    def test_the_session_aggregate_is_the_session_identity(self) -> None:
        assert self._envelope(SESSION_ID).stream_id == f"session:{SESSION_ID}"

    def test_a_foreign_aggregate_is_refused(self) -> None:
        with pytest.raises(ValueError, match="session aggregate and payload identity"):
            self._envelope(uuid4())

    def test_a_control_worker_origin_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unauthorized origin"):
            EventEnvelope(
                actor_principal_id=TICKET_ID,
                aggregate_id=SESSION_ID,
                causation_id=None,
                client_command_id=TICKET_ID,
                correlation_id=TICKET_ID,
                event_id=SESSION_ID,
                kind=EventKind.SESSION_STARTED,
                origin=EventOrigin.CONTROL_WORKER,
                payload=_started(),
                prev_hash=bytes(32),
                request_sha256=bytes(32),
                sequence=1,
                server_time=NOW,
                stream_id=f"session:{SESSION_ID}",
                tenant_id=TICKET_ID,
            )

    def test_the_session_kind_set_is_derived_from_the_catalog(self) -> None:
        derived = tuple(entry.kind for entry in event_catalog() if entry.session_fact)

        assert derived == (
            EventKind.SESSION_STARTED,
            EventKind.SESSION_TRANSITIONED,
            EventKind.SESSION_CLOSED,
        )
        assert all(
            entry.stream_prefix == "session" for entry in event_catalog() if entry.session_fact
        )


class TestCommandsAndReadModels:
    def _start_command(self) -> SessionStartCommand:
        return SessionStartCommand(
            client_command_id=TICKET_ID,
            ticket_id=TICKET_ID,
            branch_ref="feat/200-session-facts",
            crew_name="engineer-g5-sessions",
            harness_ref="claude-code",
            model_ref="claude-opus-5",
            seat_key="engineer",
            worktree_ref="/srv/worktrees/g5-sessions",
        )

    def test_close_refuses_an_out_of_contract_token_count(self) -> None:
        with pytest.raises(ValueError, match="authored session contract"):
            SessionCloseCommand(
                client_command_id=TICKET_ID,
                ticket_id=TICKET_ID,
                session_id=SESSION_ID,
                evidence_ref=None,
                input_tokens=-1,
                outcome=SessionOutcome.DELIVERED,
                output_tokens=0,
            )

    def test_every_command_exposes_only_its_own_authored_text(self) -> None:
        transition = SessionTransitionCommand(
            client_command_id=TICKET_ID,
            ticket_id=TICKET_ID,
            session_id=SESSION_ID,
            reason="Brief read",
            to_state=SessionState.BRIEFED,
        )
        close = SessionCloseCommand(
            client_command_id=TICKET_ID,
            ticket_id=TICKET_ID,
            session_id=SESSION_ID,
            evidence_ref="pr:simjak/ctower#200",
            input_tokens=1,
            outcome=SessionOutcome.DELIVERED,
            output_tokens=2,
        )

        assert session_authored_text(self._start_command()) == (
            "feat/200-session-facts",
            "engineer-g5-sessions",
            "claude-code",
            "claude-opus-5",
            "engineer",
            "/srv/worktrees/g5-sessions",
        )
        assert session_authored_text(transition) == ("Brief read",)
        assert session_authored_text(close) == ("pr:simjak/ctower#200",)
        assert transition.request_payload()["kind"] == "transition"
        assert close.request_payload()["kind"] == "close"
        assert "session_id" not in self._start_command().request_payload()

    def test_a_receipt_reports_pending_durability_until_the_envelope_overlays_it(self) -> None:
        receipt = SessionReceipt(
            command_id=TICKET_ID,
            event_id=SESSION_ID,
            session_id=SESSION_ID,
            state=SessionState.DISPATCHED,
            ticket_id=TICKET_ID,
        )

        assert receipt.response_payload()["durability_state"] == "durability_pending"

    def test_a_half_closed_session_is_refused(self) -> None:
        with pytest.raises(ValueError, match="outcome, duration, and token facts"):
            _work_session(outcome=SessionOutcome.DELIVERED)

    def test_an_open_session_reports_every_cost_fact_as_absent(self) -> None:
        payload = _work_session().response_payload()

        assert (
            payload["outcome"],
            payload["duration_seconds"],
            payload["tokens"],
            payload["closed_at"],
        ) == (None, None, None, None)
        assert payload["state"] == "dispatched"

    def test_a_closed_session_reports_its_total_token_cost(self) -> None:
        closed = _work_session(
            closed_at=NOW,
            duration_seconds=5_400,
            outcome=SessionOutcome.DELIVERED,
            tokens=SessionTokenUsage(input_tokens=412_000, output_tokens=38_500),
        )

        assert closed.response_payload()["tokens"] == {
            "input_tokens": 412_000,
            "output_tokens": 38_500,
            "total_tokens": 450_500,
        }

    def test_the_two_pages_carry_their_own_scope(self) -> None:
        session = _work_session()

        assert TicketSessionList(ticket_id=TICKET_ID, sessions=(session,)).response_payload()[
            "ticket_id"
        ] == str(TICKET_ID)
        assert ProjectSessionPage(
            project_key="ctower", sessions=(session,), next_cursor=17
        ).response_payload() == {
            "next_cursor": 17,
            "project_key": "ctower",
            "sessions": [session.response_payload()],
        }


def _work_session(**overrides: object) -> WorkSession:
    fields: dict[str, object] = {
        "branch_ref": "feat/200-session-facts",
        "closed_at": None,
        "crew_name": "engineer-g5-sessions",
        "duration_seconds": None,
        "evidence_ref": None,
        "harness_ref": "claude-code",
        "model_ref": "claude-opus-5",
        "outcome": None,
        "project_key": "ctower",
        "seat_key": "engineer",
        "session_id": SESSION_ID,
        "started_at": NOW,
        "state": SessionState.DISPATCHED,
        "ticket_id": TICKET_ID,
        "tokens": None,
        "transition_count": 0,
        "worktree_ref": "/srv/worktrees/g5-sessions",
    }
    return WorkSession(**{**fields, **overrides})  # type: ignore[arg-type]
