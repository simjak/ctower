from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

import ctower_api.connector_loop as connector_loop_module
from ctower_api.connector_loop import ConnectorLoop, build_active_connector_loops
from ctower_api.connectors.gitlab import GitLabRuntimeRegistration
from ctower_api.connectors.registry import (
    CONNECTOR_REGISTRATIONS,
    _closed_registry,
)
from ctower_client import CompanyBundleExportResult
from ctower_kernel.catalog.interface import JsonValue
from ctower_kernel.integrations import IssueConnector
from ctower_kernel.record import Actor, PrincipalKind

__all__: tuple[str, ...] = ()

_REVISION_A = UUID("22222222-2222-4222-8222-222222222222")
_REVISION_B = UUID("33333333-3333-4333-8333-333333333333")
_CREDENTIAL_REFERENCE_A = "GITLAB_FEEDBACK_A_TOKEN"
_CREDENTIAL_REFERENCE_B = "GITLAB_FEEDBACK_B_TOKEN"


def _payload(
    key: str = "gitlab.feedback-a",
    *,
    project_id: int = 42,
    credential_reference: str = _CREDENTIAL_REFERENCE_A,
) -> dict[str, JsonValue]:
    return {
        "schema": "ctower.integration/v2",
        "key": key,
        "adapter": "gitlab-issues",
        "authority": "co_source",
        "execution": "standing_sync",
        "gitlab": {
            "base_url": "https://gitlab.example.test",
            "project_id": project_id,
            "import_updated_after": "2026-08-08T08:00:00Z",
            "page_size": 50,
            "poll_interval_seconds": 60,
        },
        "ctower": {
            "project_key": "ctower",
            "initial_custodian_id": "11111111-1111-4111-8111-111111111111",
        },
        "label_map": [{"gitlab": "bug", "ctower": "type.bug"}],
        "token_binding": credential_reference,
    }


def _active_export() -> CompanyBundleExportResult:
    resources = [
        _resource(
            key="gitlab.feedback-a",
            digest="sha256:" + "a" * 64,
            payload=_payload(),
        ),
        _resource(
            key="gitlab.feedback-b",
            digest="sha256:" + "b" * 64,
            payload=_payload(
                "gitlab.feedback-b",
                project_id=84,
                credential_reference=_CREDENTIAL_REFERENCE_B,
            ),
        ),
    ]
    return CompanyBundleExportResult.model_validate_json(
        json.dumps(
            {
                "active_version": 1,
                "bundle_digest": "sha256:" + "d" * 64,
                "metadata": {
                    "activated_at": datetime(2026, 8, 8, tzinfo=UTC).isoformat(),
                    "actor_principal_id": str(uuid4()),
                    "checks": [],
                    "command_id": str(uuid4()),
                },
                "bundle": {
                    "schema": "ctower.company-bundle/v1",
                    "company": {"key": "ctower", "display_name": "Ctower"},
                    "resources": resources,
                    "assignments": [],
                    "secret_binding_refs": [
                        {
                            "name": _CREDENTIAL_REFERENCE_A,
                            "reference_class": "runtime-binding",
                        },
                        {
                            "name": _CREDENTIAL_REFERENCE_B,
                            "reference_class": "runtime-binding",
                        },
                    ],
                },
            }
        )
    )


def _resource(*, key: str, digest: str, payload: dict[str, JsonValue]) -> dict[str, object]:
    return {
        "component": {
            "schema": "ctower.versioned-component/v1",
            "kind": "integration",
            "key": key,
            "scope": {"tenant": "ctower", "project": None},
            "revision": 1,
            "content_digest": digest,
            "schema_ref": "ctower.integration/v2",
            "lifecycle": "published",
            "compatibility": {"ctower": "0.0.0", "requires": []},
            "provenance": [
                {
                    "kind": "reviewed-contract",
                    "source": "docs/internal/specs/connectors.md#cx-01",
                    "digest": "sha256:" + "c" * 64,
                }
            ],
            "supersedes": None,
            "payload_ref": "object:" + digest,
        },
        "payload": payload,
    }


def test_catalog_revision_becomes_typed_registration_without_secret_value() -> None:
    runtime = GitLabRuntimeRegistration.from_catalog(
        _payload(),
        revision_id=_REVISION_A,
        revision_digest="sha256:" + "a" * 64,
    )

    assert runtime.config.base_url == "https://gitlab.example.test"
    assert runtime.token_binding == _CREDENTIAL_REFERENCE_A
    assert runtime.registration.connector_kind == "gitlab-issue"
    assert runtime.registration.source_display_name == "GitLab"
    assert "token" not in runtime.registration.to_mapping()


def test_static_registry_refuses_duplicate_kinds_and_schema_identifiers() -> None:
    factory = next(iter(CONNECTOR_REGISTRATIONS.values()))

    with pytest.raises(RuntimeError, match="adapter kind"):
        _closed_registry(factory, factory)
    with pytest.raises(RuntimeError, match="schema identifier"):
        _closed_registry(factory, replace(factory, adapter_kind="gitlab.second"))


def test_catalog_parser_refuses_unknown_or_secret_value_fields() -> None:
    payload = _payload()
    payload["resolved_value"] = uuid4().hex

    with pytest.raises(ValidationError, match="resolved_value"):
        GitLabRuntimeRegistration.from_catalog(
            payload,
            revision_id=_REVISION_A,
            revision_digest="sha256:" + "a" * 64,
        )


def test_composition_refuses_parser_that_changes_catalog_revision_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = Actor(uuid4(), uuid4(), PrincipalKind.COMMANDER)
    factory = CONNECTOR_REGISTRATIONS["gitlab-issues"]

    class _Store:
        def __init__(self, _dsn: str) -> None:
            pass

        def active_revision_id(
            self,
            _actor: Actor,
            *,
            registration_key: str,
            revision_digest: str,
        ) -> UUID:
            del registration_key, revision_digest
            return _REVISION_A

    def faulty_parser(
        payload: dict[str, JsonValue],
        *,
        revision_id: UUID,
        revision_digest: str,
    ) -> GitLabRuntimeRegistration:
        runtime = GitLabRuntimeRegistration.from_catalog(
            payload,
            revision_id=revision_id,
            revision_digest=revision_digest,
        )
        return replace(
            runtime,
            registration=runtime.registration.model_copy(update={"revision_id": _REVISION_B}),
        )

    monkeypatch.setattr(connector_loop_module, "PostgresConnectorStore", _Store)
    monkeypatch.setattr(
        connector_loop_module,
        "CONNECTOR_REGISTRATIONS",
        {"gitlab-issues": replace(factory, from_catalog=faulty_parser)},
    )

    with pytest.raises(RuntimeError, match="changed its pinned Catalog identity"):
        build_active_connector_loops(
            _active_export(),
            actor=actor,
            runtime_dsn="postgresql://runtime-reference",
            resolve_secret=lambda _reference: "not-reached",
        )


def test_active_catalog_composes_two_independent_static_connector_loops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = Actor(uuid4(), uuid4(), PrincipalKind.COMMANDER)
    observed: list[tuple[GitLabRuntimeRegistration, IssueConnector, Actor, str]] = []
    expected = (cast(ConnectorLoop, object()), cast(ConnectorLoop, object()))

    class _Store:
        def __init__(self, dsn: str) -> None:
            assert dsn == "postgresql://runtime-reference"

        def active_revision_id(
            self,
            requested_actor: Actor,
            *,
            registration_key: str,
            revision_digest: str,
        ) -> UUID:
            assert requested_actor == actor
            assert revision_digest.startswith("sha256:")
            return _REVISION_A if registration_key.endswith("-a") else _REVISION_B

    def fake_build(
        runtime: GitLabRuntimeRegistration,
        *,
        connector: IssueConnector,
        actor: Actor,
        runtime_dsn: str,
    ) -> ConnectorLoop:
        observed.append((runtime, connector, actor, runtime_dsn))
        return expected[len(observed) - 1]

    resolved: list[str] = []

    def resolve_secret(reference: str) -> str:
        resolved.append(reference)
        return f"resolved-{reference}"

    monkeypatch.setattr(connector_loop_module, "PostgresConnectorStore", _Store)
    monkeypatch.setattr(connector_loop_module, "build_connector_loop", fake_build)

    loops = build_active_connector_loops(
        _active_export(),
        actor=actor,
        runtime_dsn="postgresql://runtime-reference",
        resolve_secret=resolve_secret,
    )

    assert loops == expected
    assert resolved == ["GITLAB_FEEDBACK_A_TOKEN", "GITLAB_FEEDBACK_B_TOKEN"]
    assert [item[0].registration.revision_id for item in observed] == [
        _REVISION_A,
        _REVISION_B,
    ]
    assert [item[0].registration.registration_key for item in observed] == [
        "gitlab.feedback-a",
        "gitlab.feedback-b",
    ]
    assert all(item[2:] == (actor, "postgresql://runtime-reference") for item in observed)
