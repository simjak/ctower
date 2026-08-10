"""RED-first tests for the console's exact browser session + CSRF authority."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from ctower_api.console_routes import validate_console_origin
from ctower_kernel.access.human_auth import HumanAuthentication, HumanBrowserSession
from ctower_kernel.record import PrincipalKind, RecordProblem
from ctower_kernel.record.human_identity import HumanIdentityRecord
from modules.access._fakes import FakeHumanIdentity, FakeRecord


def test_browser_authentication_binds_human_session_binding_actor_and_csrf() -> None:
    now = datetime.now(UTC)
    store = FakeHumanIdentity()
    principal_id, binding_id, token, csrf = uuid4(), uuid4(), "session-token", "csrf-token"
    store.issue_session(
        principal_id,
        store.tenant_id,
        binding_id,
        "viewer",
        session_digest=hashlib.sha256(token.encode()).digest(),
        csrf_digest=hashlib.sha256(csrf.encode()).digest(),
        now=now,
        ttl_seconds=3600,
    )
    authentication = HumanAuthentication(
        cast(HumanIdentityRecord, FakeRecord(human_identity=store)), clock=lambda: now
    )

    outcome = authentication.authenticate_browser_session(token, csrf_token=csrf)

    assert isinstance(outcome, HumanBrowserSession)
    assert outcome.actor.principal_id == principal_id
    assert outcome.actor.kind is PrincipalKind.VIEWER
    assert outcome.human_binding_id == binding_id
    assert outcome.human_session_id


def test_missing_wrong_or_whitespace_csrf_is_a_named_refusal() -> None:
    now = datetime.now(UTC)
    store = FakeHumanIdentity()
    token, csrf = "session-token", "csrf-token"
    store.issue_session(
        uuid4(),
        store.tenant_id,
        uuid4(),
        "viewer",
        session_digest=hashlib.sha256(token.encode()).digest(),
        csrf_digest=hashlib.sha256(csrf.encode()).digest(),
        now=now,
        ttl_seconds=3600,
    )
    authentication = HumanAuthentication(
        cast(HumanIdentityRecord, FakeRecord(human_identity=store)), clock=lambda: now
    )

    for presented in (None, "wrong", f" {csrf}"):
        outcome = authentication.authenticate_browser_session(token, csrf_token=presented)
        assert isinstance(outcome, RecordProblem)
        assert outcome.code == "auth-csrf-invalid"


def test_console_origin_requires_the_one_configured_same_origin() -> None:
    assert (
        validate_console_origin(
            "https://ctower.tailnet.example", expected="https://ctower.tailnet.example"
        )
        is None
    )
    refusal = validate_console_origin(
        "https://foreign.example", expected="https://ctower.tailnet.example"
    )
    assert isinstance(refusal, RecordProblem)
    assert refusal.code == "console-origin-refused"
