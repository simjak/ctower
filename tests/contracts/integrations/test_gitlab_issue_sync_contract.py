from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[3]


def _validator() -> Draft202012Validator:
    schema = cast(
        dict[str, object],
        json.loads(
            (ROOT / "contracts/domain/integrations/gitlab-issue-sync.schema.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _issue() -> dict[str, object]:
    return {
        "schema": "ctower.gitlab-issue/v1",
        "project_id": 42,
        "iid": 7,
        "title": "Feedback title",
        "body": "Feedback body",
        "labels": ["feedback", "bug"],
        "reporter": {"username": "reporter", "name": "Report Person"},
        "state": "opened",
        "web_url": "https://gitlab.example.test/group/project/-/issues/7",
        "updated_at": "2026-08-08T08:00:00Z",
    }


def test_gitlab_issue_sync_payloads_are_strict_and_typed() -> None:
    validator = _validator()
    payloads = (
        {
            "schema": "ctower.gitlab-issue-cursor/v1",
            "updated_after": "2026-08-08T08:00:00Z",
            "page": 1,
            "project_event_cursor": 0,
        },
        _issue(),
        {
            "schema": "ctower.gitlab-close-command/v1",
            "delivery_id": "11111111-1111-4111-8111-111111111111",
            "comment": "ctower proof-gated close",
        },
        {
            "schema": "ctower.gitlab-close-receipt/v1",
            "delivery_id": "11111111-1111-4111-8111-111111111111",
            "comment_created": True,
            "issue_closed": True,
        },
    )

    assert all(not list(validator.iter_errors(payload)) for payload in payloads)
    assert list(validator.iter_errors({**_issue(), "token": "forbidden"}))
    assert list(validator.iter_errors({**_issue(), "project_id": "42"}))
    assert list(validator.iter_errors({**_issue(), "state": "done"}))


def test_gitlab_integration_component_is_revisioned_co_source_configuration() -> None:
    schema = cast(
        dict[str, object],
        json.loads((ROOT / "contracts/components/integration-v2.schema.json").read_text()),
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    payload = {
        "schema": "ctower.integration/v2",
        "key": "gitlab.feedback",
        "adapter": "gitlab-issues",
        "authority": "co_source",
        "execution": "standing_sync",
        "gitlab": {
            "base_url": "https://gitlab.example.test",
            "project_id": 42,
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

    assert not list(validator.iter_errors(payload))
    assert list(validator.iter_errors({**payload, "token": "secret-value"}))
    assert list(validator.iter_errors({**payload, "execution": "poll-forever"}))
