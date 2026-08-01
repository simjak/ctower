"""Atomic checkpoint-definition materialization inside Catalog activation."""

from __future__ import annotations

from datetime import datetime
from typing import cast

import psycopg

from ctower_kernel.catalog._postgres_revisions import RevisionState
from ctower_kernel.catalog.interface import CompanyBundle, CompanyBundleResource, ComponentKind
from ctower_kernel.record import Actor

__all__: tuple[str, ...] = ()

_APPLICABLE_STATES = (
    "planned",
    "in_progress",
    "ready_to_land",
    "merged",
    "verified",
    "released",
    "blocked",
    "done",
)


def materialize_checkpoints(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    bundle: CompanyBundle,
    states: tuple[RevisionState, ...],
    *,
    now: datetime,
) -> None:
    """Insert every newly published definition and its criteria in one transaction."""

    positions = _checkpoint_positions(bundle)
    for state in states:
        if not state.is_new or state.resource.component.kind is not ComponentKind.CHECKPOINT:
            continue
        _insert_definition(connection, actor, state, positions, now=now)


def _checkpoint_positions(bundle: CompanyBundle) -> dict[tuple[str, str], int]:
    projects: dict[str, list[tuple[str, CompanyBundleResource]]] = {}
    for resource in bundle.resources:
        if resource.component.kind is not ComponentKind.CHECKPOINT:
            continue
        project_key = resource.component.scope.project
        if project_key is None:
            raise RuntimeError("validated checkpoint is missing its project scope")
        reference = f"{resource.component.key}@{resource.component.revision}"
        projects.setdefault(project_key, []).append((reference, resource))

    positions: dict[tuple[str, str], int] = {}
    for project_key, resources in projects.items():
        references = {reference for reference, _resource in resources}
        remaining = {
            reference: {
                str(dependency)
                for dependency in cast(list[object], resource.payload["dependency_refs"])
                if str(dependency) in references
            }
            for reference, resource in resources
        }
        ordered: list[str] = []
        while remaining:
            ready = sorted(
                reference for reference, dependencies in remaining.items() if not dependencies
            )
            if not ready:
                raise RuntimeError("validated checkpoint dependencies contain a cycle")
            ordered.extend(ready)
            for reference in ready:
                del remaining[reference]
            for dependencies in remaining.values():
                dependencies.difference_update(ready)
        for position, reference in enumerate(ordered, start=1):
            resource = next(item for candidate, item in resources if candidate == reference)
            checkpoint_key = str(resource.payload["checkpoint_key"])
            positions[(project_key, checkpoint_key)] = position
    return positions


def _insert_definition(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    state: RevisionState,
    positions: dict[tuple[str, str], int],
    *,
    now: datetime,
) -> None:
    resource = state.resource
    component = resource.component
    payload = resource.payload
    checkpoint_key = str(payload["checkpoint_key"])
    publication_event_id = state.publication_event_id
    if publication_event_id is None or component.scope.project is None:
        raise RuntimeError("new checkpoint publication facts are incomplete")
    position = positions[(component.scope.project, checkpoint_key)]
    connection.execute(
        """
        INSERT INTO project_delivery_checkpoint_definitions (
            checkpoint_definition_id, tenant_id, company_key, project_key,
            checkpoint_key, definition_revision, ordered_position,
            checkpoint_label, outcome, accountable_owner, applicable_states,
            catalog_revision, catalog_digest, event_id, actor_principal_id,
            recorded_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s
        )
        """,
        (
            state.revision_id,
            actor.tenant_id,
            component.scope.tenant,
            component.scope.project,
            checkpoint_key,
            component.revision,
            position,
            payload["display_name"],
            payload["outcome"],
            payload["accountable_owner"],
            list(_APPLICABLE_STATES),
            f"{component.key}@{component.revision}",
            bytes.fromhex(component.content_digest.removeprefix("sha256:")),
            publication_event_id,
            actor.principal_id,
            now,
        ),
    )
    criteria = cast(list[dict[str, object]], payload["criteria"])
    connection.cursor().executemany(
        """
        INSERT INTO project_delivery_exit_criteria (
            checkpoint_definition_id, tenant_id, criterion_key, ordinal,
            description, proof_ticket_id, proof_criterion_key, source_ids
        ) VALUES (%s, %s, %s, %s, %s, NULL, NULL, %s)
        """,
        tuple(
            (
                state.revision_id,
                actor.tenant_id,
                str(criterion["key"]),
                ordinal,
                str(criterion["description"]),
                list(cast(list[str], criterion["evidence_policy_refs"])),
            )
            for ordinal, criterion in enumerate(criteria, start=1)
        ),
    )
