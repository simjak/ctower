"""Closed argparse surface for the authored ctower CLI command families."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import TypeAdapter

from ctower_client.client import ProjectKey
from ctower_client.models import (
    BoardLane,
    IntakeIntent,
    IntakePromotionIntent,
    IntakeTaint,
    PoisonDispositionAction,
    Priority,
    RelationKind,
    SessionOutcome,
    SessionState,
    VerdictDecision,
)
from ctowerctl._argument_types import (
    _assertions,
    _aware_datetime,
    _nonnegative_int,
    _positive_int,
    _safe_base_url,
    _sha256_digest,
)
from ctowerctl._context_set_parser import attention_parser, ticket_context_sets
from ctowerctl._digest_parser import digest_parser
from ctowerctl._dispatch_parser import (
    beat_dispatch_parser,
    dream_dispatch_parser,
    dream_lane_parser,
)
from ctowerctl._knowledge_parser import knowledge_parser
from ctowerctl._parser_support import (
    AUTHORED_COMMAND_NAMES,
    _command_id,
    _Parser,
    _review_dispatch,
    _session_id,
    _ticket_id,
    _ticket_reference,
    _version,
    _version_reason,
)
from ctowerctl._pool_parser import pools_parser
from ctowerctl._request_parser import request_parser
from ctowerctl._ruling_parser import ruling_parser
from ctowerctl._spawn_parser import spawn_parser

__all__: tuple[str, ...] = ()

_ASSIGNMENT_KINDS = ("current_assignee", "stage_owner", "reviewer")
_BLOCKER_KINDS = ("dependency", "operator_action", "policy", "resource", "technical")
_SPOOL_STATES = ("pending", "accepted_archive", "quarantine")
_PROJECT_KEY: TypeAdapter[str] = TypeAdapter(ProjectKey)


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse only explicit authored commands; unknown operations are usage errors."""

    _validate_ceremony_principal(parsed := _parser().parse_args(argv))
    if getattr(parsed, "command_id", None) is None and hasattr(parsed, "command_id"):
        parsed.command_id = uuid4()
    return parsed


def authored_command_names() -> frozenset[str]:
    return AUTHORED_COMMAND_NAMES


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="ctowerctl", allow_abbrev=False)
    parser.add_argument("--base-url", required=False, default=None, type=_safe_base_url)
    parser.add_argument(
        "--as",
        dest="ceremony_principal",
        choices=("operator",),
        default=None,
    )
    areas = parser.add_subparsers(dest="area", required=True, parser_class=_Parser)
    _bootstrap_parser(areas.add_parser("bootstrap"))
    _credential_parser(areas.add_parser("credential"))
    _intake_parser(areas.add_parser("intake"))
    digest_parser(areas.add_parser("digest"))
    request_parser(areas.add_parser("request"))
    ruling_parser(areas.add_parser("ruling"))
    spawn_parser(areas.add_parser("spawn"))
    _inbox_parser(areas.add_parser("inbox"))
    knowledge_parser(areas.add_parser("knowledge"))
    pools_parser(areas.add_parser("pools"))
    _ticket_parser(areas.add_parser("ticket"))
    _session_parser(areas.add_parser("session"))
    _board_parser(areas.add_parser("board"))
    _control_parser(areas.add_parser("control"))
    _ops_parser(areas.add_parser("ops"))
    _company_parser(areas.add_parser("company"))
    _synthetic_parser(areas.add_parser("synthetic"))
    _migration_parser(areas.add_parser("migration"))
    _project_parser(areas.add_parser("project"))
    _spool_parser(areas.add_parser("spool"))
    attention_parser(areas.add_parser("attention"))
    dream_dispatch_parser(areas.add_parser("dream-dispatch"))
    beat_dispatch_parser(areas.add_parser("beat-dispatch"))
    dream_lane_parser(areas.add_parser("dream-lane"))
    return parser


def _validate_ceremony_principal(arguments: argparse.Namespace) -> None:
    """Keep the explicit operator selector confined to its one ceremony."""

    is_binding = getattr(arguments, "cli_name", None) == "dream-lane bind"
    if is_binding and arguments.ceremony_principal != "operator":
        raise ValueError("usage: dream-lane bind requires --as operator")
    if not is_binding and arguments.ceremony_principal is not None:
        raise ValueError("usage: --as operator is only valid for dream-lane bind")


def _bootstrap_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    first = actions.add_parser("first-tenant")
    first.set_defaults(cli_name="bootstrap first-tenant")
    _command_id(first)
    first.add_argument("--tenant-name", required=True)
    first.add_argument("--tenant-slug", required=True)
    first.add_argument("--operator-name", required=True)
    first.add_argument("--operator-credential-ref", required=True)
    first.add_argument("--operator-vault-ref", required=True)
    first.add_argument("--commander-name", required=True)
    first.add_argument("--commander-vault-ref", required=True)


def _credential_parser(parser: argparse.ArgumentParser) -> None:
    subjects = parser.add_subparsers(dest="subject", required=True, parser_class=_Parser)
    actions = subjects.add_parser("seat").add_subparsers(
        dest="credential_action", required=True, parser_class=_Parser
    )
    issue = actions.add_parser("issue")
    issue.set_defaults(cli_name="credential seat issue")
    _command_id(issue)
    issue.add_argument("--credential-digest", required=True, type=_sha256_digest)
    issue.add_argument("--credential-ref", required=True)
    issue.add_argument("--display-name", required=True)
    issue.add_argument("--project-key", required=True)
    issue.add_argument(
        "--scope",
        dest="scopes",
        required=True,
        action="append",
        choices=("capture", "transition", "evidence"),
    )
    issue.add_argument("--seat-key", required=True)
    revoke = actions.add_parser("revoke")
    revoke.set_defaults(cli_name="credential seat revoke")
    revoke.add_argument("credential_id", type=UUID)
    _command_id(revoke)
    revoke.add_argument("--reason", required=True)


def _ticket_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    _ticket_capture_and_reads(actions)
    _ticket_authority(actions)
    _ticket_work(actions)
    _ticket_proof(actions)
    _ticket_workflow(actions)
    _review_dispatch(actions)
    ticket_context_sets(actions)


def _intake_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    submit = actions.add_parser("submit")
    submit.set_defaults(cli_name="intake submit")
    _command_id(submit)
    submit.add_argument("--project-key", required=True)
    submit.add_argument("--source-kind", required=True)
    submit.add_argument("--source-ref", required=True)
    submit.add_argument("--content-file", required=True, type=Path)
    submit.add_argument("--intent", choices=tuple(IntakeIntent), default="discussion")
    submit.add_argument("--taint", choices=tuple(IntakeTaint), default="authenticated")
    submit.add_argument("--thread-id", type=UUID)
    submit.add_argument("--expected-thread-version", type=_positive_int)
    _intake_ticket_fields(submit)

    promote = actions.add_parser("promote")
    promote.set_defaults(cli_name="intake promote")
    promote.add_argument("inbound_event_id", type=UUID)
    _command_id(promote)
    promote.add_argument("--expected-thread-version", required=True, type=_positive_int)
    promote.add_argument("--intent", required=True, choices=tuple(IntakePromotionIntent))
    _intake_ticket_fields(promote)


def _inbox_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    send = actions.add_parser("send")
    send.set_defaults(cli_name="inbox send")
    _command_id(send)
    send.add_argument("--to", required=True)
    send.add_argument("--severity", required=True, choices=("P0", "P1", "info"))
    send.add_argument("--project-key", required=True)
    send.add_argument("--thread", dest="thread_id", type=UUID)
    send.add_argument("text")
    notify = actions.add_parser("notify")
    notify.set_defaults(cli_name="inbox notify")
    _command_id(notify)
    notify.add_argument("--to", required=True)
    notify.add_argument("--severity", required=True, choices=("P0", "P1", "info"))
    notify.add_argument("--project-key", required=True)
    notify.add_argument("text")
    acknowledge = actions.add_parser("ack")
    acknowledge.set_defaults(cli_name="inbox ack")
    _command_id(acknowledge)
    acknowledge.add_argument("--state", required=True, choices=("delivered", "read"))
    acknowledge.add_argument("message_id", type=UUID)
    promote = actions.add_parser("promote")
    promote.set_defaults(cli_name="inbox promote")
    _command_id(promote)
    promote.add_argument("thread_id", type=UUID)
    promote.add_argument("--ticket", dest="ticket_id", type=_ticket_reference)
    list_parser = actions.add_parser("list")
    list_parser.set_defaults(cli_name="inbox list")
    list_parser.add_argument("--unread", action="store_true")
    correspondents = actions.add_parser("correspondents")
    correspondents.set_defaults(cli_name="inbox correspondents")
    correspondents.add_argument("--project-key")
    read = actions.add_parser("read")
    read.set_defaults(cli_name="inbox read")
    read.add_argument("thread_id", type=UUID)
    read_state = actions.add_parser("read-state")
    read_state.set_defaults(cli_name="inbox read-state")
    read_state.add_argument("thread_id", type=UUID)


def _intake_ticket_fields(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--initial-custodian-id", type=UUID)
    parser.add_argument("--priority", choices=tuple(Priority))
    parser.add_argument("--title")
    parser.add_argument("--target-ticket-id", type=_ticket_reference)
    parser.add_argument("--expected-ticket-version", type=_positive_int)


def _ticket_capture_and_reads(actions: argparse._SubParsersAction[_Parser]) -> None:
    for name in ("capture", "create"):
        capture = actions.add_parser(name)
        capture.set_defaults(cli_name=f"ticket {name}")
        _command_id(capture)
        capture.add_argument("--initial-custodian-id", type=UUID)
        capture.add_argument("--priority", required=True, choices=tuple(Priority))
        capture.add_argument("--project-key", required=True)
        capture.add_argument("--source-kind", required=True)
        capture.add_argument("--source-ref", required=True)
        capture.add_argument("--title", required=True)
    for name in ("query", "show"):
        query = actions.add_parser(name)
        query.set_defaults(cli_name=f"ticket {name}")
        _ticket_id(query)
        query.add_argument("--project-key", required=True)
    for name in ("timeline", "assignments"):
        read = actions.add_parser(name)
        read.set_defaults(cli_name=f"ticket {name}")
        _ticket_id(read)
        read.add_argument("--project-key", required=True)
    audit = actions.add_parser("audit")
    audit.set_defaults(cli_name="ticket audit")
    _ticket_id(audit)
    audit.add_argument("--project-key", required=True)
    audit.add_argument("--cursor", type=_nonnegative_int)
    audit.add_argument("--limit", type=_positive_int)


def _ticket_authority(actions: argparse._SubParsersAction[_Parser]) -> None:
    comment_actions = actions.add_parser("comment").add_subparsers(
        dest="comment_action", required=True, parser_class=_Parser
    )
    comment = comment_actions.add_parser("add")
    comment.set_defaults(cli_name="ticket comment add")
    _ticket_id(comment)
    _command_id(comment)
    comment.add_argument("--body", required=True)

    assign = actions.add_parser("assign")
    assign.set_defaults(cli_name="ticket assign")
    _ticket_id(assign)
    _command_id(assign)
    _version_reason(assign)
    assign.add_argument("--kind", required=True, choices=_ASSIGNMENT_KINDS)
    assign.add_argument("--to-principal-id", required=True, type=UUID)
    assign.add_argument("--scope-ref")

    custody_actions = actions.add_parser("custody").add_subparsers(
        dest="custody_action", required=True, parser_class=_Parser
    )
    transfer = custody_actions.add_parser("transfer")
    transfer.set_defaults(cli_name="ticket custody transfer")
    _ticket_id(transfer)
    _command_id(transfer)
    _version_reason(transfer)
    transfer.add_argument("--from-custodian-id", required=True, type=UUID)
    transfer.add_argument("--to-custodian-id", required=True, type=UUID)
    transfer.add_argument("--protected-transfer", action="store_true", required=True)


def _ticket_work(actions: argparse._SubParsersAction[_Parser]) -> None:
    prioritize = actions.add_parser("prioritize")
    prioritize.set_defaults(cli_name="ticket prioritize")
    _ticket_id(prioritize)
    _command_id(prioritize)
    _version_reason(prioritize)
    prioritize.add_argument("--priority", required=True, choices=tuple(Priority))
    prioritize.add_argument("--urgent-evidence-ref")

    for name in ("admit", "reopen"):
        intent = actions.add_parser(name)
        intent.set_defaults(cli_name=f"ticket {name}")
        _ticket_id(intent)
        _command_id(intent)
        _version_reason(intent)
    defer = actions.add_parser("defer")
    defer.set_defaults(cli_name="ticket defer")
    _ticket_id(defer)
    _command_id(defer)
    _version_reason(defer)
    defer.add_argument("--review-after", required=True, type=_aware_datetime)
    _block_parser(actions)
    _unblock_parser(actions)
    _relation_parser(actions)


def _block_parser(actions: argparse._SubParsersAction[_Parser]) -> None:
    block = actions.add_parser("block")
    block.set_defaults(cli_name="ticket block")
    _ticket_id(block)
    _command_id(block)
    _version_reason(block)
    block.add_argument("--blocker-id", required=True, type=UUID)
    block.add_argument("--blocker-kind", required=True, choices=_BLOCKER_KINDS)
    block.add_argument("--reason-class", required=True)
    block.add_argument("--owner-principal-id", required=True, type=UUID)
    block.add_argument("--source-ref", required=True)
    block.add_argument("--affected-stage")
    block.add_argument("--resolution-condition", required=True)
    block.add_argument("--next-check-at", type=_aware_datetime)
    block.add_argument("--dependency-ref")
    block.add_argument(
        "--board-impact",
        action=argparse.BooleanOptionalAction,
        required=True,
    )


def _unblock_parser(actions: argparse._SubParsersAction[_Parser]) -> None:
    unblock = actions.add_parser("unblock")
    unblock.set_defaults(cli_name="ticket unblock")
    _ticket_id(unblock)
    _command_id(unblock)
    _version_reason(unblock)
    unblock.add_argument("--blocker-id", required=True, type=UUID)
    unblock.add_argument("--resolution-evidence-ref", required=True)


def _relation_parser(actions: argparse._SubParsersAction[_Parser]) -> None:
    relation_actions = actions.add_parser("relation").add_subparsers(
        dest="relation_action", required=True, parser_class=_Parser
    )
    relation = relation_actions.add_parser("add")
    relation.set_defaults(cli_name="ticket relation add")
    _ticket_id(relation)
    _command_id(relation)
    _version_reason(relation)
    relation.add_argument("--kind", required=True, choices=tuple(RelationKind))
    relation.add_argument("--target-ticket-id", required=True, type=UUID)


def _ticket_proof(actions: argparse._SubParsersAction[_Parser]) -> None:
    criteria_actions = actions.add_parser("criteria").add_subparsers(
        dest="criteria_action", required=True, parser_class=_Parser
    )
    criteria = criteria_actions.add_parser("freeze")
    criteria.set_defaults(cli_name="ticket criteria freeze")
    _ticket_id(criteria)
    _command_id(criteria)
    criteria.add_argument("--expected-version", required=True, type=_nonnegative_int)
    candidate = criteria.add_mutually_exclusive_group(required=True)
    candidate.add_argument("--candidate-digest")
    candidate.add_argument("--candidate-content")
    criteria.add_argument("--criteria-file", type=Path)

    evidence_actions = actions.add_parser("evidence").add_subparsers(
        dest="evidence_action", required=True, parser_class=_Parser
    )
    evidence = evidence_actions.add_parser("add")
    evidence.set_defaults(cli_name="ticket evidence add")
    _ticket_id(evidence)
    _command_id(evidence)
    _version(evidence)
    evidence.add_argument("--evidence-id", required=True, type=UUID)
    evidence.add_argument("--criterion-key")
    evidence.add_argument("--candidate-digest")
    evidence.add_argument("--artifact-digest")
    content = evidence.add_mutually_exclusive_group(required=True)
    content.add_argument("--content")
    content.add_argument("--content-file", type=Path)
    _verdict_parser(actions)


def _verdict_parser(actions: argparse._SubParsersAction[_Parser]) -> None:
    gate_actions = actions.add_parser("gate").add_subparsers(
        dest="gate_action", required=True, parser_class=_Parser
    )
    verdict = gate_actions.add_parser("verdict")
    verdict.set_defaults(cli_name="ticket gate verdict")
    _ticket_id(verdict)
    _command_id(verdict)
    _version(verdict)
    verdict.add_argument("--verdict-id", required=True, type=UUID)
    verdict.add_argument("--criterion-key")
    verdict.add_argument("--candidate-digest")
    verdict.add_argument("--decision", required=True, choices=tuple(VerdictDecision))


def _ticket_workflow(actions: argparse._SubParsersAction[_Parser]) -> None:
    workflow_actions = actions.add_parser("workflow").add_subparsers(
        dest="workflow_action", required=True, parser_class=_Parser
    )
    workflow_actions.add_parser("list").set_defaults(local_command="ticket workflow list")
    start = workflow_actions.add_parser("start")
    start.set_defaults(cli_name="ticket workflow start")
    _ticket_id(start)
    _command_id(start)
    for name in ("workflow", "execution-policy", "gate-policy", "evidence-policy"):
        start.add_argument(f"--{name}-ref")
        start.add_argument(f"--{name}-digest")
    transition = actions.add_parser("transition")
    transition.set_defaults(cli_name="ticket transition")
    _ticket_id(transition)
    _command_id(transition)
    transition.add_argument("--expected-version", required=True, type=_nonnegative_int)
    transition.add_argument("--workflow-ref", required=True)
    transition.add_argument("--source-stage", required=True)
    transition.add_argument("--destination-stage", required=True)
    resolve = actions.add_parser("resolve")
    resolve.set_defaults(cli_name="ticket resolve")
    _ticket_id(resolve)
    _command_id(resolve)
    _version(resolve)
    resolve.add_argument("--workflow-ref")


def _board_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    query = actions.add_parser("query")
    query.set_defaults(cli_name="board query")
    query.add_argument("project_key")
    query.add_argument("--lane", choices=tuple(BoardLane))
    query.add_argument("--priority", choices=tuple(Priority))
    query.add_argument("--stage-key")
    query.add_argument("--custodian-id", type=UUID)
    query.add_argument("--assignee-id", type=UUID)
    query.add_argument("--source-kind")
    query.add_argument("--source-ref")


def _control_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    health = actions.add_parser("health")
    health.set_defaults(cli_name="control health")


def _ops_parser(parser: argparse.ArgumentParser) -> None:
    outbox = parser.add_subparsers(dest="subject", required=True, parser_class=_Parser)
    poison = outbox.add_parser("outbox").add_subparsers(
        dest="outbox_subject", required=True, parser_class=_Parser
    )
    dispose = (
        poison.add_parser("poison")
        .add_subparsers(dest="poison_action", required=True, parser_class=_Parser)
        .add_parser("dispose")
    )
    dispose.set_defaults(cli_name="ops outbox poison dispose")
    dispose.add_argument("outbox_id", type=UUID)
    _command_id(dispose)
    dispose.add_argument("--consumer-key", required=True)
    dispose.add_argument("--topic", required=True)
    dispose.add_argument("--action", required=True, choices=tuple(PoisonDispositionAction))
    dispose.add_argument("--reason", required=True)


def _company_parser(parser: argparse.ArgumentParser) -> None:
    bundle = parser.add_subparsers(dest="subject", required=True, parser_class=_Parser)
    actions = bundle.add_parser("bundle").add_subparsers(
        dest="bundle_action", required=True, parser_class=_Parser
    )
    for name in ("validate", "plan"):
        operation = actions.add_parser(name)
        operation.set_defaults(cli_name=f"company bundle {name}")
        operation.add_argument("bundle_file", type=Path)
    apply = actions.add_parser("apply")
    apply.set_defaults(cli_name="company bundle apply")
    apply.add_argument("bundle_file", type=Path)
    _command_id(apply)
    apply.add_argument("--expected-active-version", required=True, type=_nonnegative_int)
    apply.add_argument("--plan-digest", required=True)
    export = actions.add_parser("export")
    export.set_defaults(cli_name="company bundle export")


def _synthetic_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    run = actions.add_parser("run")
    run.set_defaults(cli_name="synthetic run")
    run.add_argument(
        "--workflow",
        dest="workflow_ref",
        required=True,
        choices=("ctower.trust-spine-four-stage@1",),
    )
    _command_id(run)
    run.add_argument("--wait", action="store_true", required=True)
    run.add_argument("--assert", dest="assertions", required=True, type=_assertions)
    query = actions.add_parser("query")
    query.set_defaults(cli_name="synthetic query")
    query.add_argument("run_id", type=UUID)


def _migration_parser(parser: argparse.ArgumentParser) -> None:
    projects = parser.add_subparsers(dest="subject", required=True, parser_class=_Parser)
    actions = projects.add_parser("ctower-project").add_subparsers(
        dest="migration_action", required=True, parser_class=_Parser
    )
    for name in (
        "inventory",
        "export",
        "plan",
        "import",
        "reconcile",
        "prepare",
        "commit-development-epoch",
    ):
        phase = actions.add_parser(name)
        phase.set_defaults(cli_name=f"migration ctower-project {name}")
        _command_id(phase)
        phase.add_argument("--request-file", required=True, type=Path)
    run = actions.add_parser("run").add_subparsers(
        dest="run_action", required=True, parser_class=_Parser
    )
    run_get = run.add_parser("get")
    run_get.set_defaults(cli_name="migration ctower-project run get")
    run_get.add_argument("run_id", type=UUID)
    correction = actions.add_parser("correction").add_subparsers(
        dest="correction_action", required=True, parser_class=_Parser
    )
    correction_append = correction.add_parser("append")
    correction_append.set_defaults(cli_name="migration ctower-project correction append")
    _command_id(correction_append)
    correction_append.add_argument("--request-file", required=True, type=Path)
    fence = actions.add_parser("fence").add_subparsers(
        dest="fence_action", required=True, parser_class=_Parser
    )
    fence_observe = fence.add_parser("observe")
    fence_observe.set_defaults(cli_name="migration ctower-project fence observe")
    _command_id(fence_observe)
    fence_observe.add_argument("--request-file", required=True, type=Path)
    actions.add_parser("verify").set_defaults(cli_name="migration ctower-project verify")

    for subject in (
        "ctower-inbox",
        "ctower-ruling",
        "ctower-knowledge",
        "ctower-company-record",
    ):
        estate_actions = projects.add_parser(subject).add_subparsers(
            dest="migration_action", required=True, parser_class=_Parser
        )
        import_command = estate_actions.add_parser("import")
        import_command.set_defaults(cli_name=f"migration {subject} import")
        _command_id(import_command)
        import_command.add_argument("--request-file", required=True, type=Path)


def _session_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="session_action", required=True, parser_class=_Parser)
    start = actions.add_parser("start")
    start.set_defaults(cli_name="session start")
    _ticket_id(start)
    _command_id(start)
    start.add_argument("--branch-ref", required=True)
    start.add_argument("--crew-name", required=True)
    start.add_argument("--harness-ref", required=True)
    start.add_argument("--model-ref", required=True)
    start.add_argument("--seat-key", required=True)
    start.add_argument("--worktree-ref", required=True)

    transition = actions.add_parser("transition")
    transition.set_defaults(cli_name="session transition")
    _ticket_id(transition)
    _session_id(transition)
    _command_id(transition)
    transition.add_argument("--reason", required=True)
    transition.add_argument("--to-state", required=True, choices=tuple(SessionState))

    close = actions.add_parser("close")
    close.set_defaults(cli_name="session close")
    _ticket_id(close)
    _session_id(close)
    _command_id(close)
    close.add_argument("--outcome", required=True, choices=tuple(SessionOutcome))
    close.add_argument("--input-tokens", required=True, type=_nonnegative_int)
    close.add_argument("--output-tokens", required=True, type=_nonnegative_int)
    close.add_argument("--evidence-ref")

    ticket = actions.add_parser("ticket")
    ticket.set_defaults(cli_name="session ticket")
    _ticket_id(ticket)
    ticket.add_argument("--project-key", required=True)

    project = actions.add_parser("project")
    project.set_defaults(cli_name="session project")
    project.add_argument("project_key", type=_PROJECT_KEY.validate_python)
    project.add_argument("--cursor", type=_nonnegative_int)
    project.add_argument("--limit", type=_positive_int)


def _project_parser(parser: argparse.ArgumentParser) -> None:
    subjects = parser.add_subparsers(dest="subject", required=True, parser_class=_Parser)
    actions = subjects.add_parser("delivery").add_subparsers(
        dest="delivery_action", required=True, parser_class=_Parser
    )
    query = actions.add_parser("query")
    query.set_defaults(cli_name="project delivery query")
    query.add_argument("project_key", type=_PROJECT_KEY.validate_python)
    query.add_argument("--output", choices=("text", "json"), default="text")

    events = subjects.add_parser("events")
    events.set_defaults(cli_name="project events")
    events.add_argument("project_key", type=_PROJECT_KEY.validate_python)
    events.add_argument("--cursor", type=_nonnegative_int)
    events.add_argument("--limit", type=_positive_int)


def _spool_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    actions.add_parser("status").set_defaults(local_command="spool status")
    listing = actions.add_parser("list")
    listing.set_defaults(local_command="spool list")
    listing.add_argument("--state", choices=_SPOOL_STATES)
    listing.add_argument("--limit", type=_positive_int, default=1000)
    actions.add_parser("doctor").set_defaults(local_command="spool doctor")
    actions.add_parser("drain").set_defaults(local_command="spool drain")
    quarantine = actions.add_parser("quarantine").add_subparsers(
        dest="quarantine_action", required=True, parser_class=_Parser
    )
    quarantine_list = quarantine.add_parser("list")
    quarantine_list.set_defaults(local_command="spool quarantine list")
    quarantine_list.add_argument("--limit", type=_positive_int, default=1000)
    for name in ("retry", "discard"):
        disposition = actions.add_parser(name)
        disposition.set_defaults(local_command=f"spool {name}")
        disposition.add_argument("sequence", type=_positive_int)
        disposition.add_argument("--reason", required=True)
        if name == "discard":
            disposition.add_argument("--artifact-digest")
