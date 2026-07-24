"""Generated-client behavior for the Proof-gated Workflow slice."""

from __future__ import annotations

from uuid import uuid4

import pytest
from support.server import running_api
from support.tenant_fixture import TenantFixture

from ctower_client import (
    CtowerClient,
    CtowerProblemError,
    FreezeCriteriaRequest,
    ProofCriterion,
)

__all__: tuple[str, ...] = ()


def test_generated_client_exposes_a_typed_missing_ticket_problem(
    tenant: TenantFixture,
) -> None:
    missing_ticket_id = uuid4()
    with (
        running_api(tenant.database.runtime_dsn) as base_url,
        CtowerClient(base_url, credential=tenant.commander_credential) as client,
        pytest.raises(CtowerProblemError) as refused,
    ):
        client.freeze_proof_criteria(
            missing_ticket_id,
            FreezeCriteriaRequest(
                expected_version=0,
                candidate_digest="sha256:" + "e" * 64,
                criteria=(
                    ProofCriterion(
                        key="artifact-current",
                        description="Artifact evidence matches the current candidate.",
                        candidate_dependent=True,
                        requires_verdict=True,
                    ),
                ),
            ),
            command_id=uuid4(),
        )

    assert refused.value.problem.code == "tenant-scope-denied"
    assert refused.value.problem.detail == "Ticket not found"
    assert str(refused.value) == "tenant-scope-denied: Ticket not found"
