"""Meaningful branch coverage for the explicit protected ticket command family."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ConfigDict

from ctower_client import CtowerClient
from ctower_client.models import (
    EvidenceRequest,
    FreezeCriteriaRequest,
    PriorityChangeRequest,
    RelationRequest,
    ResolveCloseRequest,
    TicketIntentRequest,
    VerdictRequest,
    WorkflowStartRequest,
    WorkflowTransitionRequest,
)
from ctowerctl import _ticket_commands

__all__: tuple[str, ...] = ()

_DIGEST = "sha256:" + ("a" * 64)
_OTHER_DIGEST = "sha256:" + ("b" * 64)


def test_builds_each_protected_work_request() -> None:
    priority = _ticket_commands.build_mutation(
        _arguments("ticket prioritize", priority="P0", urgent_evidence_ref="evidence:urgent")
    )
    intent_payloads = [
        _ticket_commands.build_mutation(_arguments("ticket admit")),
        _ticket_commands.build_mutation(
            _arguments(
                "ticket defer",
                review_after=datetime(2026, 7, 25, tzinfo=UTC),
            )
        ),
        _ticket_commands.build_mutation(_arguments("ticket reopen")),
        _ticket_commands.build_mutation(
            _arguments(
                "ticket block",
                blocker_id=uuid4(),
                blocker_kind="dependency",
                reason_class="external",
                owner_principal_id=uuid4(),
                source_ref="ticket:dependency",
                affected_stage="verification",
                resolution_condition="Dependency is released.",
                next_check_at=datetime(2026, 7, 25, tzinfo=UTC),
                dependency_ref="ticket:upstream",
                board_impact=True,
            )
        ),
        _ticket_commands.build_mutation(
            _arguments(
                "ticket unblock",
                blocker_id=uuid4(),
                resolution_evidence_ref="evidence:dependency-released",
            )
        ),
    ]
    relation = _ticket_commands.build_mutation(
        _arguments(
            "ticket relation add",
            kind="depends_on",
            target_ticket_id=uuid4(),
        )
    )

    assert isinstance(priority.request, PriorityChangeRequest)
    assert priority.request.priority == "P0"
    assert [
        cast(TicketIntentRequest, payload.request).intent.kind for payload in intent_payloads
    ] == ["admit", "defer", "reopen", "block", "unblock"]
    assert isinstance(relation.request, RelationRequest)
    assert relation.request.relation_kind == "depends_on"
    payloads = [priority, *intent_payloads, relation]
    assert all(payload.path_parameters == {"ticket_id": str(_TICKET_ID)} for payload in payloads)


def test_builds_each_protected_proof_request(tmp_path: Path) -> None:
    criteria_file = tmp_path / "criteria.json"
    criteria_file.write_text(
        json.dumps(
            [
                {
                    "key": "release",
                    "description": "Release proof is independently verified.",
                    "candidate_dependent": True,
                    "requires_verdict": True,
                }
            ]
        ),
        encoding="utf-8",
    )
    evidence_file = tmp_path / "evidence.txt"
    evidence_file.write_text("artifact was independently observed", encoding="utf-8")

    criteria = _ticket_commands.build_mutation(
        _arguments("ticket criteria freeze", criteria_file=criteria_file)
    )
    evidence = _ticket_commands.build_mutation(
        _arguments(
            "ticket evidence add",
            evidence_id=uuid4(),
            criterion_key="release",
            artifact_digest=_OTHER_DIGEST,
            content_file=evidence_file,
        )
    )
    verdict = _ticket_commands.build_mutation(
        _arguments(
            "ticket gate verdict",
            verdict_id=uuid4(),
            criterion_key="release",
            decision="pass",
        )
    )

    assert isinstance(criteria.request, FreezeCriteriaRequest)
    assert criteria.request.criteria[0].key == "release"
    assert isinstance(evidence.request, EvidenceRequest)
    assert evidence.request.content == "artifact was independently observed"
    assert isinstance(verdict.request, VerdictRequest)
    assert verdict.request.decision == "pass"
    payloads = [criteria, evidence, verdict]
    assert all(payload.path_parameters == {"ticket_id": str(_TICKET_ID)} for payload in payloads)


def test_builds_each_protected_workflow_request() -> None:
    workflow = _ticket_commands.build_mutation(
        _arguments(
            "ticket workflow start",
            workflow_ref="release@1",
            workflow_digest=_DIGEST,
            execution_policy_ref="execution@1",
            execution_policy_digest=_DIGEST,
            gate_policy_ref="gate@1",
            gate_policy_digest=_DIGEST,
            evidence_policy_ref="evidence@1",
            evidence_policy_digest=_DIGEST,
        )
    )
    transition = _ticket_commands.build_mutation(
        _arguments(
            "ticket transition",
            workflow_ref="release@1",
            source_stage="build",
            destination_stage="verify",
        )
    )
    resolve = _ticket_commands.build_mutation(
        _arguments("ticket resolve", workflow_ref="release@1")
    )

    assert isinstance(workflow.request, WorkflowStartRequest)
    assert workflow.request.workflow_ref == "release@1"
    assert isinstance(transition.request, WorkflowTransitionRequest)
    assert transition.request.destination_stage == "verify"
    assert isinstance(resolve.request, ResolveCloseRequest)
    assert resolve.request.workflow_ref == "release@1"
    payloads = [workflow, transition, resolve]
    assert all(payload.path_parameters == {"ticket_id": str(_TICKET_ID)} for payload in payloads)


def test_ticket_dispatch_refuses_unknown_mutation_query_and_intent() -> None:
    with pytest.raises(ValueError, match="unsupported ticket mutation"):
        _ticket_commands.build_mutation(_arguments("ticket invent"))
    with pytest.raises(ValueError, match="unsupported ticket query"):
        _ticket_commands.execute_query(
            argparse.Namespace(cli_name="ticket invent"),
            cast(CtowerClient, object()),
        )
    with pytest.raises(ValueError, match="unsupported ticket intent"):
        _ticket_commands._intent(_arguments("ticket invent"))


def test_ticket_queries_call_only_the_explicit_generated_methods() -> None:
    client = _TicketQueryClient()
    ticket_id = uuid4()

    for cli_name in ("ticket query", "ticket show"):
        result = _ticket_commands.execute_query(
            argparse.Namespace(cli_name=cli_name, ticket_id=ticket_id),
            cast(CtowerClient, client),
        )
        assert cast(_QueryResult, result).marker == "ticket"
    timeline = _ticket_commands.execute_query(
        argparse.Namespace(cli_name="ticket timeline", ticket_id=ticket_id),
        cast(CtowerClient, client),
    )
    assignments = _ticket_commands.execute_query(
        argparse.Namespace(cli_name="ticket assignments", ticket_id=ticket_id),
        cast(CtowerClient, client),
    )
    audit = _ticket_commands.execute_query(
        argparse.Namespace(
            cli_name="ticket audit",
            ticket_id=ticket_id,
            cursor=11,
            limit=7,
        ),
        cast(CtowerClient, client),
    )

    assert cast(_QueryResult, timeline).marker == "timeline"
    assert cast(_QueryResult, assignments).marker == "assignments"
    assert cast(_QueryResult, audit).marker == "audit"
    assert client.calls == [
        ("ticket", ticket_id, None, None),
        ("ticket", ticket_id, None, None),
        ("timeline", ticket_id, None, None),
        ("assignments", ticket_id, None, None),
        ("audit", ticket_id, 11, 7),
    ]


_TICKET_ID = uuid4()


def _arguments(cli_name: str, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "cli_name": cli_name,
        "ticket_id": _TICKET_ID,
        "expected_version": 3,
        "reason": "Explicit protected operation.",
        "candidate_digest": _DIGEST,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class _QueryResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    marker: str


class _TicketQueryClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, UUID, int | None, int | None]] = []

    def get_ticket(self, ticket_id: UUID) -> _QueryResult:
        self.calls.append(("ticket", ticket_id, None, None))
        return _QueryResult(marker="ticket")

    def get_ticket_timeline(self, ticket_id: UUID) -> _QueryResult:
        self.calls.append(("timeline", ticket_id, None, None))
        return _QueryResult(marker="timeline")

    def list_ticket_assignments(self, ticket_id: UUID) -> _QueryResult:
        self.calls.append(("assignments", ticket_id, None, None))
        return _QueryResult(marker="assignments")

    def list_ticket_audit_events(
        self,
        ticket_id: UUID,
        *,
        cursor: int | None,
        limit: int | None,
    ) -> _QueryResult:
        self.calls.append(("audit", ticket_id, cursor, limit))
        return _QueryResult(marker="audit")
