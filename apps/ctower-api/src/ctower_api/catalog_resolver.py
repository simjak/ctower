"""Composition adapter from exact Catalog bytes to Workflow and Proof values."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Protocol, cast
from uuid import UUID

from ctower_kernel.catalog.interface import ComponentKind
from ctower_kernel.proof import ProofPolicy
from ctower_kernel.workflow import WorkflowGraph

__all__ = ["CatalogComponentResolver"]


class _CatalogComponents(Protocol):
    def component_bytes(
        self,
        tenant_id: UUID,
        kind: ComponentKind,
        key: str,
        revision: int,
        *,
        content_digest: str | None = None,
    ) -> bytes | None: ...


class CatalogComponentResolver:
    """Parse domain values only from exact historical Catalog component bytes."""

    def __init__(self, catalog: _CatalogComponents) -> None:
        self._catalog = catalog

    def workflow_graph(
        self,
        tenant_id: UUID,
        reference: str,
        semantic_digest: str,
    ) -> WorkflowGraph | None:
        content = self._read(tenant_id, ComponentKind.WORKFLOW, reference)
        if content is None:
            return None
        try:
            payload = json.loads(content)
            if not isinstance(payload, Mapping):
                return None
            graph = WorkflowGraph.from_mapping(cast(Mapping[str, object], payload))
        except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        return graph if graph.reference == reference and graph.digest == semantic_digest else None

    def policy_matches(
        self,
        tenant_id: UUID,
        policy_kind: str,
        reference: str,
        content_digest: str,
    ) -> bool:
        try:
            kind = ComponentKind(policy_kind)
        except ValueError:
            return False
        return (
            self._read(
                tenant_id,
                kind,
                reference,
                content_digest=content_digest,
            )
            is not None
        )

    def proof_policy(
        self,
        tenant_id: UUID,
        pin: tuple[str, str, str, str, str],
    ) -> ProofPolicy | None:
        workflow_ref, gate_ref, gate_digest, evidence_ref, evidence_digest = pin
        gate = self._read(
            tenant_id,
            ComponentKind.GATE_POLICY,
            gate_ref,
            content_digest=gate_digest,
        )
        evidence = self._read(
            tenant_id,
            ComponentKind.EVIDENCE_POLICY,
            evidence_ref,
            content_digest=evidence_digest,
        )
        if gate is None or evidence is None:
            return None
        try:
            policy = ProofPolicy.from_bytes(
                gate,
                evidence,
                expected_gate_policy_digest=gate_digest,
                expected_evidence_policy_digest=evidence_digest,
            )
        except (TypeError, ValueError):
            return None
        return policy if policy.pin == pin and policy.workflow_ref == workflow_ref else None

    def _read(
        self,
        tenant_id: UUID,
        kind: ComponentKind,
        reference: str,
        *,
        content_digest: str | None = None,
    ) -> bytes | None:
        parsed = _reference(reference)
        if parsed is None:
            return None
        key, revision = parsed
        return self._catalog.component_bytes(
            tenant_id,
            kind,
            key,
            revision,
            content_digest=content_digest,
        )


def _reference(value: str) -> tuple[str, int] | None:
    try:
        key, revision = value.rsplit("@", 1)
        parsed = int(revision)
    except (ValueError, AttributeError):
        return None
    return (key, parsed) if key and parsed >= 1 else None
