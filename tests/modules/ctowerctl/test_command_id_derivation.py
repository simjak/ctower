"""Command-ID derivation coverage across every mutation command family."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from ctowerctl._parser import parse_arguments

_COMMAND_ID_DERIVATION_CASES = (
    pytest.param(
        [
            "bootstrap",
            "first-tenant",
            "--tenant-name",
            "Derived Tenant",
            "--tenant-slug",
            "derived-tenant",
            "--operator-name",
            "Derived Operator",
            "--operator-credential-ref",
            "credential-ref:derived/operator",
            "--operator-vault-ref",
            "vault-ref:derived/operator",
            "--commander-name",
            "Derived Commander",
            "--commander-vault-ref",
            "vault-ref:derived/commander",
        ],
        id="bootstrap first-tenant",
    ),
    pytest.param(
        [
            "credential",
            "seat",
            "issue",
            "--credential-digest",
            "sha256:" + "a" * 64,
            "--credential-ref",
            "secret-ref:seat/derived",
            "--display-name",
            "Derived Seat",
            "--project-key",
            "ctower",
            "--scope",
            "capture",
            "--seat-key",
            "derived-seat",
        ],
        id="credential seat issue",
    ),
    pytest.param(
        [
            "intake",
            "submit",
            "--project-key",
            "ctower",
            "--source-kind",
            "mission-control",
            "--source-ref",
            "R2809-intake",
            "--content-file",
            "content.txt",
        ],
        id="intake submit",
    ),
    pytest.param(
        [
            "ticket",
            "assign",
            str(uuid4()),
            "--expected-version",
            "1",
            "--kind",
            "current_assignee",
            "--to-principal-id",
            str(uuid4()),
            "--reason",
            "derived command id",
        ],
        id="ticket assign",
    ),
    pytest.param(
        [
            "session",
            "start",
            str(uuid4()),
            "--branch-ref",
            "refs/heads/derived",
            "--crew-name",
            "engineer-derived",
            "--harness-ref",
            "codex",
            "--model-ref",
            "gpt",
            "--seat-key",
            "derived-seat",
            "--worktree-ref",
            "derived-worktree",
        ],
        id="session start",
    ),
    pytest.param(
        [
            "ops",
            "outbox",
            "poison",
            "dispose",
            str(uuid4()),
            "--consumer-key",
            "derived-consumer",
            "--topic",
            "derived-topic",
            "--action",
            "retry",
            "--reason",
            "derived dispose",
        ],
        id="ops outbox poison dispose",
    ),
    pytest.param(
        [
            "company",
            "bundle",
            "apply",
            "bundle.yaml",
            "--expected-active-version",
            "0",
            "--plan-digest",
            "sha256:" + "a" * 64,
        ],
        id="company bundle apply",
    ),
    pytest.param(
        [
            "migration",
            "ctower-project",
            "inventory",
            "--request-file",
            "request.json",
        ],
        id="migration ctower-project inventory",
    ),
)


@pytest.mark.parametrize("argv", _COMMAND_ID_DERIVATION_CASES)
def test_every_mutation_family_derives_command_id_when_omitted(argv: list[str]) -> None:
    first = parse_arguments(argv)
    second = parse_arguments(argv)
    explicit_command_id = uuid4()
    explicit = parse_arguments([*argv, "--command-id", str(explicit_command_id)])

    assert isinstance(first.command_id, UUID)
    assert first.command_id != second.command_id
    assert explicit.command_id == explicit_command_id
