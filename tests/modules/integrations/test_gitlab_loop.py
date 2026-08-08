from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

import ctower_api.gitlab_loop as gitlab_loop_module
from ctower_api.gitlab_loop import (
    GitLabRuntimeRevision,
    GitLabSyncLoop,
    build_active_gitlab_sync_loops,
)
from ctower_client import CompanyBundleExportResult
from ctower_kernel.catalog.interface import JsonValue
from ctower_kernel.record import Actor, PrincipalKind

_PROJECT_ID = 42


def _payload() -> dict[str, JsonValue]:
    return {
        "schema": "ctower.integration/v2",
        "key": "gitlab.feedback",
        "adapter": "gitlab-issues",
        "authority": "co_source",
        "execution": "standing_sync",
        "gitlab": {
            "base_url": "https://gitlab.example.test",
            "project_id": _PROJECT_ID,
            "import_updated_after": "2026-08-08T08:00:00Z",
            "page_size": 50,
            "poll_interval_seconds": 60,
        },
        "ctower": {
            "project_key": "ctower",
            "initial_custodian_id": "11111111-1111-4111-8111-111111111111",
        },
        "label_map": [{"gitlab": "bug", "ctower": "type.bug"}],
        "token_binding": "GITLAB_FEEDBACK_TOKEN",
    }


_ACTIVE_EXPORT = CompanyBundleExportResult.model_validate_json(
    json.dumps(
        {
            "active_version": 1,
            "bundle_digest": "sha256:" + "b" * 64,
            "metadata": {
                "activated_at": datetime(2026, 8, 8, tzinfo=UTC).isoformat(),
                "actor_principal_id": str(uuid4()),
                "checks": [],
                "command_id": str(uuid4()),
            },
            "bundle": {
                "schema": "ctower.company-bundle/v1",
                "company": {"key": "ctower", "display_name": "Ctower"},
                "resources": [
                    {
                        "component": {
                            "schema": "ctower.versioned-component/v1",
                            "kind": "integration",
                            "key": "gitlab.feedback",
                            "scope": {"tenant": "ctower", "project": None},
                            "revision": 1,
                            "content_digest": "sha256:" + "a" * 64,
                            "schema_ref": "ctower.integration/v2",
                            "lifecycle": "published",
                            "compatibility": {"ctower": "0.0.0", "requires": []},
                            "provenance": [
                                {
                                    "kind": "reviewed-contract",
                                    "source": "SPEC.md#d39",
                                    "digest": "sha256:" + "c" * 64,
                                }
                            ],
                            "supersedes": None,
                            "payload_ref": "object:sha256:" + "a" * 64,
                        },
                        "payload": _payload(),
                    }
                ],
                "assignments": [],
                "secret_binding_refs": [
                    {
                        "name": "GITLAB_FEEDBACK_TOKEN",
                        "reference_class": "runtime-binding",
                    }
                ],
            },
        }
    )
)


def test_catalog_revision_becomes_typed_runtime_binding_without_secret_value() -> None:
    revision = GitLabRuntimeRevision.from_catalog(
        _payload(),
        revision_id=UUID("22222222-2222-4222-8222-222222222222"),
        revision_digest="sha256:" + "a" * 64,
    )

    assert revision.base_url == "https://gitlab.example.test"
    assert revision.token_binding == _payload()["token_binding"]
    assert revision.binding.project_id == _PROJECT_ID
    assert "token" not in revision.binding.to_mapping()


def test_catalog_runtime_parser_refuses_unknown_or_secret_value_fields() -> None:
    payload = _payload()
    payload["resolved_value"] = uuid4().hex

    with pytest.raises(ValidationError, match="resolved_value"):
        GitLabRuntimeRevision.from_catalog(
            payload,
            revision_id=UUID("22222222-2222-4222-8222-222222222222"),
            revision_digest="sha256:" + "a" * 64,
        )


def test_active_catalog_revision_and_deployment_secret_compose_one_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("22222222-2222-4222-8222-222222222222")
    actor = Actor(uuid4(), uuid4(), PrincipalKind.COMMANDER)
    observed: dict[str, object] = {}
    expected_loop = cast(GitLabSyncLoop, object())
    resolved_value = str(uuid4())

    class _Store:
        def __init__(self, dsn: str) -> None:
            assert dsn == "postgresql://runtime-reference"

        def active_revision_id(
            self,
            requested_actor: Actor,
            *,
            integration_key: str,
            revision_digest: str,
        ) -> UUID:
            assert requested_actor == actor
            assert integration_key == "gitlab.feedback"
            assert revision_digest == "sha256:" + "a" * 64
            return revision_id

    def fake_build(
        revision: GitLabRuntimeRevision,
        *,
        resolved_token: str,
        actor: Actor,
        runtime_dsn: str,
    ) -> GitLabSyncLoop:
        observed.update(
            revision=revision,
            resolved_token=resolved_token,
            actor=actor,
            runtime_dsn=runtime_dsn,
        )
        return expected_loop

    resolved: list[str] = []

    def resolve_secret(reference: str) -> str:
        resolved.append(reference)
        return resolved_value

    monkeypatch.setattr(gitlab_loop_module, "PostgresGitLabIntegrationStore", _Store)
    monkeypatch.setattr(gitlab_loop_module, "build_gitlab_sync_loop", fake_build)

    loops = build_active_gitlab_sync_loops(
        _ACTIVE_EXPORT,
        actor=actor,
        runtime_dsn="postgresql://runtime-reference",
        resolve_secret=resolve_secret,
    )

    assert loops == (expected_loop,)
    assert resolved == ["GITLAB_FEEDBACK_TOKEN"]
    assert observed["resolved_token"] == resolved_value
    assert observed["actor"] == actor
    assert observed["runtime_dsn"] == "postgresql://runtime-reference"
    revision = cast(GitLabRuntimeRevision, observed["revision"])
    assert revision.binding.revision_id == revision_id
    assert revision.binding.revision_digest == "sha256:" + "a" * 64
