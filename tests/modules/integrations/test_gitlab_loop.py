from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from ctower_api.gitlab_loop import GitLabRuntimeRevision
from ctower_kernel.catalog.interface import JsonValue

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
