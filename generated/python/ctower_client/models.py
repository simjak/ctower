"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:28a28df4d6ebd5d86f6486df4b69bab7d8cf69235160bba9175cdeb7ad0700c8
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import StrEnum
import math
import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

__all__ = [
    "ActivityClass",
    "AdmitIntent",
    "AdmittedAuditData",
    "AppendFindingRequest",
    "AppliedLabel",
    "ApplyLabelRequest",
    "ApplyLabelResult",
    "AssignmentChangeRequest",
    "AssignmentChangedAuditData",
    "AssignmentInterval",
    "AssignmentKind",
    "AssignmentList",
    "AttentionFindingResult",
    "AuditEvent",
    "AuditPage",
    "BlockIntent",
    "BlockerOpenedAuditData",
    "BlockerResolvedAuditData",
    "BoardCard",
    "BoardLane",
    "BoardView",
    "BootstrapReceipt",
    "BootstrapRequest",
    "BundleAction",
    "BundleActionKind",
    "BundleCheck",
    "ChangeReference",
    "ChangeReferenceRequest",
    "ChangeReferenceResult",
    "CompanyBundleApplyRequest",
    "CompanyBundleAssignment",
    "CompanyBundleCommandResult",
    "CompanyBundleDocument",
    "CompanyBundleExportMetadata",
    "CompanyBundleExportResult",
    "CompanyBundlePlan",
    "CompanyBundleRequest",
    "CompanyBundleResource",
    "CompanyBundleValidationResult",
    "CompanyIdentity",
    "ComponentCompatibility",
    "ComponentKind",
    "ComponentProvenance",
    "ComponentReference",
    "ComponentScope",
    "ControlHealth",
    "CredentialScope",
    "CtowerProjectAliasPlanBindRequest",
    "CtowerProjectCutoverHealth",
    "CtowerProjectEpochRefusalRequest",
    "CtowerProjectExactAliasOperation",
    "CtowerProjectExportEqualityBindRequest",
    "CtowerProjectFenceObservationRequest",
    "CtowerProjectImportBatchRequest",
    "CtowerProjectImportBatchResult",
    "CtowerProjectImportCorrectionRequest",
    "CtowerProjectImportFinalizeRequest",
    "CtowerProjectImportOperation",
    "CtowerProjectImportRun",
    "CtowerProjectImportRunCreateRequest",
    "CtowerProjectMigrationReceipt",
    "CtowerProjectReconciliationResult",
    "CtowerProjectSourceLinkOperation",
    "CtowerProjectTicketRelationOperation",
    "CtowerProjectTicketSeedOperation",
    "CustodyTransferRequest",
    "CustodyTransferredAuditEvent",
    "CustodyTransferredPayload",
    "DeferIntent",
    "DeferredAuditData",
    "DeliverySurfaceAvailability",
    "DeliverySurfaceAvailabilityNoQualifyingCheckpoint",
    "DeliverySurfaceAvailabilityQualifyingCheckpoint",
    "DreamDispatchConsumeRequest",
    "DreamDispatchConsumption",
    "DreamDispatchEffect",
    "DreamDispatchEffectList",
    "DreamDispatchReceipt",
    "DreamDispatchScope",
    "DreamLaneBindRequest",
    "DreamLaneBindingReceipt",
    "DreamModelRequirement",
    "DreamModelSelection",
    "DurabilityState",
    "EvidenceRequest",
    "FindingDispositionRequest",
    "FindingDispositionResult",
    "FreezeCriteriaRequest",
    "HealthContributor",
    "HealthContributorKey",
    "HealthDimension",
    "HealthStatus",
    "HumanWaiting",
    "HumanWaitingNotWaiting",
    "HumanWaitingWaiting",
    "InboxAcknowledgeRequest",
    "InboxAcknowledgeResult",
    "InboxMessage",
    "InboxMessageReadState",
    "InboxNotificationRequest",
    "InboxPromotionOutcome",
    "InboxPromotionRequest",
    "InboxPromotionResult",
    "InboxReadState",
    "InboxSendRequest",
    "InboxSendResult",
    "InboxThread",
    "InboxThreadList",
    "InboxThreadSummary",
    "IntakeCommandResult",
    "IntakeIntent",
    "IntakeOutcome",
    "IntakePromotionIntent",
    "IntakePromotionRequest",
    "IntakeSubmitRequest",
    "IntakeTaint",
    "KnowledgeAddRequest",
    "KnowledgeAddResult",
    "KnowledgeDocument",
    "KnowledgeDocumentList",
    "KnowledgeScope",
    "MigrationAliasCorrection",
    "MigrationConservation",
    "MigrationCorrectionReplacement",
    "MigrationCorrectionRevision",
    "MigrationDetachedSignature",
    "MigrationDispositions",
    "MigrationFenceFileIdentity",
    "MigrationHealthDigests",
    "MigrationImportCounts",
    "MigrationImportOperationResult",
    "MigrationImporterBinding",
    "MigrationOperationIdentity",
    "MigrationPassTwoMeasurement",
    "MigrationPinnedDigests",
    "MigrationReconciliationGraph",
    "MigrationRefusal",
    "MigrationRelationCorrection",
    "MigrationReview",
    "MigrationReviewerKey",
    "MigrationSourceIdentity",
    "MigrationSourceLinkCorrection",
    "MigrationWatermarks",
    "MutableAssignmentKind",
    "PoisonDispositionAction",
    "PoisonDispositionReceipt",
    "PoisonDispositionRequest",
    "Priority",
    "PriorityChangeRequest",
    "PriorityChangedAuditData",
    "Problem",
    "ProhibitedDataClass",
    "ProjectDeliveryAssignedSeatAssignment",
    "ProjectDeliveryCriteria",
    "ProjectDeliveryRow",
    "ProjectDeliverySeat",
    "ProjectDeliverySeatAssignment",
    "ProjectDeliverySlot",
    "ProjectDeliverySurfaceDeclaration",
    "ProjectDeliveryUnassignedSeatAssignment",
    "ProjectDeliveryView",
    "ProjectEvent",
    "ProjectEventPage",
    "ProjectSessionPage",
    "ProjectionHealth",
    "ProofChangedAuditEvent",
    "ProofChangedAuditPayload",
    "ProofCriterion",
    "ProofReceipt",
    "RelationAddedAuditData",
    "RelationKind",
    "RelationRequest",
    "ReopenIntent",
    "ReopenedAuditData",
    "RequestBlockerRequest",
    "RequestCaptureRequest",
    "RequestCaptureResult",
    "RequestChangeResult",
    "RequestClosureEvaluationRequest",
    "RequestList",
    "RequestOwnerRequest",
    "RequestPriorityRequest",
    "RequestRow",
    "RequestTicketRelationRequest",
    "RequestTriageRequest",
    "ResolveCloseRequest",
    "ReviewDispatchConsumeRequest",
    "ReviewDispatchConsumption",
    "ReviewDispatchEffect",
    "ReviewDispatchEffectList",
    "SeatCatalogRevision",
    "SeatCredentialIssueRequest",
    "SeatCredentialReceipt",
    "SeatCredentialRevocationRequest",
    "SecretBindingReference",
    "SessionCloseFact",
    "SessionClosedAuditEvent",
    "SessionClosedPayload",
    "SessionFactRequest",
    "SessionOutcome",
    "SessionReceipt",
    "SessionStartRequest",
    "SessionStartedAuditEvent",
    "SessionStartedPayload",
    "SessionState",
    "SessionTokenUsage",
    "SessionTransitionFact",
    "SessionTransitionedAuditEvent",
    "SessionTransitionedPayload",
    "SourceReference",
    "SurfaceDeclarationState",
    "SurfaceEnvironmentsField",
    "SurfaceIdentityField",
    "SyntheticRunReceipt",
    "SyntheticRunRequest",
    "SyntheticRunResource",
    "SyntheticRunState",
    "TelemetryContext",
    "TenantDisplayIdentity",
    "TenantDisplayIdentityKnown",
    "TenantDisplayIdentityUnknown",
    "TicketCommandResult",
    "TicketCommentAddedAuditEvent",
    "TicketCommentAddedPayload",
    "TicketCommentRequest",
    "TicketCommentResult",
    "TicketCreateRequest",
    "TicketCreatedAuditEvent",
    "TicketCreatedPayload",
    "TicketIntentRequest",
    "TicketResource",
    "TicketSession",
    "TicketSessionList",
    "TimelineEvent",
    "TimelineResponse",
    "UnblockIntent",
    "VerdictDecision",
    "VerdictRequest",
    "VersionedComponent",
    "WorkAdmittedAuditPayload",
    "WorkAssignmentChangedAuditPayload",
    "WorkBlockerOpenedAuditPayload",
    "WorkBlockerResolvedAuditPayload",
    "WorkChangedAuditEvent",
    "WorkChangedAuditPayload",
    "WorkDeferredAuditPayload",
    "WorkPriorityChangedAuditPayload",
    "WorkReceipt",
    "WorkRelationAddedAuditPayload",
    "WorkReopenedAuditPayload",
    "WorkflowChangedAuditEvent",
    "WorkflowChangedAuditPayload",
    "WorkflowReceipt",
    "WorkflowStartRequest",
    "WorkflowTransitionRequest",
]


_RFC3339_PATTERN = re.compile(
    r"^(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})"
    r"T(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
    r"(?:\.(?P<fraction>[0-9]{1,6}))?"
    r"(?P<zone>Z|(?P<sign>[+-])(?P<offset_hour>[0-9]{2}):"
    r"(?P<offset_minute>[0-9]{2}))$"
)


def _validate_rfc3339(value: object) -> datetime:
    if isinstance(value, datetime):
        offset = value.utcoffset()
        if offset is None:
            raise ValueError("RFC 3339 timestamps require a timezone")
        offset_seconds = offset.total_seconds()
        if offset_seconds % 60 != 0 or abs(offset_seconds) > 86_340:
            raise ValueError("RFC 3339 timestamp has an invalid numeric offset")
        return value
    if not isinstance(value, str):
        raise ValueError("RFC 3339 timestamp must be a string or datetime")
    match = _RFC3339_PATTERN.fullmatch(value)
    if match is None or match.group("zone") == "-00:00":
        raise ValueError("timestamp is outside the authored RFC 3339 profile")
    parts = {name: int(match.group(name)) for name in (
        "year", "month", "day", "hour", "minute", "second"
    )}
    if not 1 <= parts["year"] <= 9999:
        raise ValueError("RFC 3339 timestamp year is outside 0001-9999")
    if parts["hour"] > 23 or parts["minute"] > 59 or parts["second"] > 59:
        raise ValueError("RFC 3339 timestamp has an invalid time")
    offset_hour = int(match.group("offset_hour") or 0)
    offset_minute = int(match.group("offset_minute") or 0)
    if offset_hour > 23 or offset_minute > 59:
        raise ValueError("RFC 3339 timestamp has an invalid numeric offset")
    offset = timedelta(hours=offset_hour, minutes=offset_minute)
    if match.group("sign") == "-":
        offset = -offset
    zone = timezone.utc if match.group("zone") == "Z" else timezone(offset)
    fraction = (match.group("fraction") or "").ljust(6, "0")
    try:
        return datetime(
            parts["year"],
            parts["month"],
            parts["day"],
            parts["hour"],
            parts["minute"],
            parts["second"],
            int(fraction or 0),
            zone,
        )
    except ValueError as error:
        raise ValueError("timestamp is outside the proleptic Gregorian calendar") from error


def _validate_absolute_uri(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("absolute URI must be a string")
    if not _is_absolute_uri(value):
        raise ValueError("string is not an absolute URI")
    return value


_AbsoluteUri = Annotated[str, BeforeValidator(_validate_absolute_uri)]
_Rfc3339DateTime = Annotated[datetime, BeforeValidator(_validate_rfc3339)]

_URI_UNRESERVED = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~')
_URI_SUB_DELIMITERS = frozenset("!$&'()*+,;=")
_URI_HEX_DIGITS = frozenset('0123456789ABCDEFabcdef')
_URI_PCHAR = _URI_UNRESERVED | _URI_SUB_DELIMITERS | frozenset(":@")


def _is_absolute_uri(value: str) -> bool:
    if not value or any(ord(char) <= 32 or ord(char) >= 127 or char == "\\" for char in value):
        return False
    colon = value.find(":")
    if colon <= 0 or not _is_uri_scheme(value[:colon]):
        return False
    scheme = value[:colon]
    remainder = value[colon + 1:]
    fragment_at = remainder.find("#")
    if fragment_at >= 0:
        fragment = remainder[fragment_at + 1:]
        remainder = remainder[:fragment_at]
        if not _valid_uri_component(fragment, allow_slash=True, allow_question=True):
            return False
    query_at = remainder.find("?")
    if query_at >= 0:
        query = remainder[query_at + 1:]
        remainder = remainder[:query_at]
        if not _valid_uri_component(query, allow_slash=True, allow_question=True):
            return False
    has_authority = remainder.startswith("//")
    host = ""
    if has_authority:
        authority_and_path = remainder[2:]
        slash_at = authority_and_path.find("/")
        authority = authority_and_path if slash_at < 0 else authority_and_path[:slash_at]
        path = "" if slash_at < 0 else authority_and_path[slash_at:]
        valid_authority, host = _parse_uri_authority(authority)
        if not valid_authority:
            return False
    else:
        path = remainder
    if not _valid_uri_component(path, allow_slash=True, allow_question=False):
        return False
    return scheme.lower() not in {"http", "https"} or (has_authority and bool(host))


def _is_uri_scheme(value: str) -> bool:
    return (
        bool(value)
        and _ascii_alpha(value[0])
        and all(_ascii_alpha(char) or _ascii_digit(char) or char in "+-." for char in value[1:])
    )


def _valid_uri_component(value: str, *, allow_slash: bool, allow_question: bool) -> bool:
    allowed = _URI_PCHAR
    if allow_slash:
        allowed = allowed | frozenset("/")
    if allow_question:
        allowed = allowed | frozenset("?")
    return _valid_uri_token(value, allowed)


def _valid_uri_token(value: str, allowed: frozenset[str]) -> bool:
    index = 0
    while index < len(value):
        char = value[index]
        if char == "%":
            if (
                index + 2 >= len(value)
                or value[index + 1] not in _URI_HEX_DIGITS
                or value[index + 2] not in _URI_HEX_DIGITS
            ):
                return False
            index += 3
        elif char in allowed:
            index += 1
        else:
            return False
    return True


def _parse_uri_authority(value: str) -> tuple[bool, str]:
    if value.count("@") > 1:
        return False, ""
    if "@" in value:
        userinfo, host_port = value.rsplit("@", 1)
        if not _valid_uri_token(
            userinfo, _URI_UNRESERVED | _URI_SUB_DELIMITERS | frozenset(":")
        ):
            return False, ""
    else:
        host_port = value
    if host_port.startswith("["):
        close = host_port.find("]")
        if close < 0 or not _valid_ip_literal(host_port[1:close]):
            return False, ""
        suffix = host_port[close + 1:]
        if suffix and (not suffix.startswith(":") or not _valid_port(suffix[1:])):
            return False, ""
        return True, host_port[:close + 1]
    if "[" in host_port or "]" in host_port or host_port.count(":") > 1:
        return False, ""
    if ":" in host_port:
        host, port = host_port.rsplit(":", 1)
        if not _valid_port(port):
            return False, ""
    else:
        host = host_port
    if not _valid_uri_token(host, _URI_UNRESERVED | _URI_SUB_DELIMITERS):
        return False, ""
    return True, host


def _valid_ip_literal(value: str) -> bool:
    if len(value) >= 4 and value[0] in "vV":
        version, separator, address = value[1:].partition(".")
        allowed = _URI_UNRESERVED | _URI_SUB_DELIMITERS | frozenset(":")
        return (
            separator == "."
            and bool(version)
            and all(char in _URI_HEX_DIGITS for char in version)
            and bool(address)
            and all(char in allowed for char in address)
        )
    return _valid_ipv6(value)


def _valid_ipv6(value: str) -> bool:
    if not value or value.count("::") > 1:
        return False
    if "::" not in value:
        groups = _ipv6_side_groups(value, allow_ipv4=True)
        return groups == 8
    left, right = value.split("::", 1)
    left_groups = _ipv6_side_groups(left, allow_ipv4=False)
    right_groups = _ipv6_side_groups(right, allow_ipv4=True)
    return (
        left_groups is not None
        and right_groups is not None
        and left_groups + right_groups < 8
    )


def _ipv6_side_groups(value: str, *, allow_ipv4: bool) -> int | None:
    if not value:
        return 0
    parts = value.split(":")
    if any(not part for part in parts):
        return None
    count = 0
    for index, part in enumerate(parts):
        if "." in part:
            if not allow_ipv4 or index != len(parts) - 1 or not _valid_ipv4(part):
                return None
            count += 2
        elif len(part) > 4 or any(char not in _URI_HEX_DIGITS for char in part):
            return None
        else:
            count += 1
    return count


def _valid_ipv4(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 4 and all(
        _ascii_digits(part)
        and (len(part) == 1 or not part.startswith("0"))
        and int(part) <= 255
        for part in parts
    )


def _ascii_alpha(value: str) -> bool:
    return "A" <= value <= "Z" or "a" <= value <= "z"


def _ascii_digit(value: str) -> bool:
    return "0" <= value <= "9"


def _ascii_digits(value: str) -> bool:
    return bool(value) and all(_ascii_digit(char) for char in value)


def _valid_port(value: str) -> bool:
    return not value or _ascii_digits(value)

def _validate_free_form_json(value: object) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if type(value) is int:
        if -9007199254740991 <= value <= 9007199254740991:
            return
        raise ValueError("free-form JSON integer is outside the lossless JSON range")
    if type(value) is float:
        if math.isfinite(value):
            return
        raise ValueError("free-form JSON number must be finite")
    if isinstance(value, list):
        for item in value:
            _validate_free_form_json(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("free-form JSON object keys must be strings")
            _validate_free_form_json(item)
        return
    raise ValueError("free-form JSON contains a non-JSON value")


def _validate_free_form_json_object(value: object) -> object:
    if not isinstance(value, dict):
        raise ValueError("free-form JSON object must be a dictionary")
    _validate_free_form_json(value)
    return value


_FreeFormJsonObject = Annotated[
    dict[str, object],
    BeforeValidator(_validate_free_form_json_object),
]


class _BoundaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True, strict=True)


class ActivityClass(StrEnum):
    WORK = "work"
    VERIFICATION = "verification"


class AdmitIntent(_BoundaryModel):
    kind: Literal["admit"]
    expected_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class AdmittedAuditData(_BoundaryModel):
    episode_number: Annotated[int, Field(ge=1, le=9007199254740991)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class AppendFindingRequest(_BoundaryModel):
    subject_ticket_id: UUID
    kind_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    reason_code: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    effective_owner: Literal["operator", "commander"]
    recommendation: Annotated[str, Field(min_length=1, max_length=500)]
    alternatives: tuple[Annotated[str, Field(min_length=1, max_length=500)], ...]
    consequence: Annotated[str, Field(min_length=1, max_length=500)]
    deadline: _Rfc3339DateTime | None
    dedupe_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,127}$")]
    source_facts: tuple[Annotated[str, Field(min_length=1)], ...]


class AppliedLabel(_BoundaryModel):
    label_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    label: Annotated[str, Field(min_length=1, max_length=128)]
    vocabulary_revision: Annotated[int, Field(ge=1, le=9007199254740991)]
    applied_at: _Rfc3339DateTime


class ApplyLabelRequest(_BoundaryModel):
    label_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]


class AssignmentChangedAuditData(_BoundaryModel):
    assignment_kind: Literal["current_assignee", "stage_owner", "reviewer_assignment"]
    from_principal_id: UUID | None
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    scope_ref: Annotated[str, Field(min_length=1, max_length=256)] | None
    to_principal_id: UUID


class AssignmentKind(StrEnum):
    TICKET_CUSTODIAN = "ticket_custodian"
    CURRENT_ASSIGNEE = "current_assignee"
    STAGE_OWNER = "stage_owner"
    REVIEWER_ASSIGNMENT = "reviewer_assignment"
    RUNNER_LEASE_OWNER = "runner_lease_owner"


class BlockIntent(_BoundaryModel):
    kind: Literal["block"]
    expected_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    blocker_id: UUID
    blocker_kind: Literal["dependency", "operator_action", "policy", "resource", "technical"]
    reason_class: Annotated[str, Field(min_length=1, max_length=64)]
    owner_principal_id: UUID
    source_ref: Annotated[str, Field(min_length=1, max_length=256)]
    affected_stage: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")] | None
    resolution_condition: Annotated[str, Field(min_length=1, max_length=500)]
    next_check_at: _Rfc3339DateTime | None
    dependency_ref: Annotated[str, Field(max_length=256)] | None
    board_impact: bool


class BlockerOpenedAuditData(_BoundaryModel):
    blocker_id: UUID
    board_impact: bool
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class BlockerResolvedAuditData(_BoundaryModel):
    blocker_id: UUID
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    resolution_evidence_ref: Annotated[str, Field(min_length=1, max_length=256)]


class BoardLane(StrEnum):
    BACKLOG = "backlog"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    BLOCKED = "blocked"
    COMPLETE = "complete"


class BootstrapRequest(_BoundaryModel):
    commander_name: Annotated[str, Field(min_length=1, max_length=120)]
    commander_vault_ref: Annotated[str, Field(pattern="^vault-ref:[a-z0-9/_-]+$")]
    operator_credential_ref: Annotated[str, Field(pattern="^credential-ref:[a-z0-9/_-]+$")]
    operator_name: Annotated[str, Field(min_length=1, max_length=120)]
    operator_vault_ref: Annotated[str, Field(pattern="^vault-ref:[a-z0-9/_-]+$")]
    tenant_name: Annotated[str, Field(min_length=1, max_length=120)]
    tenant_slug: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{1,62}$")]


class BundleActionKind(StrEnum):
    CREATE = "create"
    REUSE_EXACT = "reuse_exact"
    SUPERSEDE = "supersede"
    DEPRECATE = "deprecate"
    ASSIGNMENT_CHANGE = "assignment_change"
    POINTER_CHANGE = "pointer_change"
    NO_OP = "no_op"


class BundleCheck(_BoundaryModel):
    code: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    status: Literal["passed", "warning"]


class ChangeReference(_BoundaryModel):
    repository: Annotated[str, Field(min_length=1, max_length=256)]
    change_identity: Annotated[str, Field(min_length=1, max_length=128)]
    reference: Annotated[str, Field(min_length=1, max_length=256)]
    recorded_at: _Rfc3339DateTime


class ChangeReferenceRequest(_BoundaryModel):
    repository: Annotated[str, Field(min_length=1, max_length=256)]
    change_identity: Annotated[str, Field(min_length=1, max_length=128)]
    reference: Annotated[str, Field(min_length=1, max_length=256)]


class CompanyIdentity(_BoundaryModel):
    display_name: Annotated[str, Field(min_length=1, max_length=128)]
    key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")]


class ComponentKind(StrEnum):
    WORKFLOW = "workflow"
    EXECUTION_POLICY = "execution_policy"
    GATE_POLICY = "gate_policy"
    EVIDENCE_POLICY = "evidence_policy"
    GOAL = "goal"
    PROJECT = "project"
    AGENT_PROFILE = "agent_profile"
    PERSONA = "persona"
    SKILL = "skill"
    TOOL = "tool"
    CAPABILITY = "capability"
    ENVIRONMENT = "environment"
    IMAGE = "image"
    HARNESS = "harness"
    SUPERVISOR = "supervisor"
    TARGET = "target"
    WORKSPACE = "workspace"
    TELEMETRY = "telemetry"
    PLACEMENT_POLICY = "placement_policy"
    EXTENSION = "extension"
    CADENCE_POLICY = "cadence_policy"
    NOTIFICATION = "notification"
    INTEGRATION = "integration"
    ADAPTER = "adapter"
    CHECKPOINT = "checkpoint"


class ComponentProvenance(_BoundaryModel):
    digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    kind: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,63}$")]
    source: Annotated[str, Field(min_length=1, max_length=512)]


class ComponentScope(_BoundaryModel):
    project: Annotated[str, Field(pattern="^[a-z][a-z0-9.-]{2,127}$")] | None
    tenant: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")]


class CredentialScope(StrEnum):
    CAPTURE = "capture"
    TRANSITION = "transition"
    EVIDENCE = "evidence"


class CtowerProjectAliasPlanBindRequest(_BoundaryModel):
    run_id: UUID
    cutover_id: UUID
    export_equality_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    alias_map_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    reviewer_key_ref: Annotated[str, Field(pattern="^signing-key-ref:[a-z0-9/_-]{3,255}$")]
    reviewer_key_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    reviewer_public_key_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    attention_required: Literal[0]
    alias_map_artifact: Annotated[str, Field(min_length=2, max_length=4194304)]
    import_plan_artifact: Annotated[str, Field(min_length=2, max_length=8388608)]
    fence_registry_artifact: Annotated[str, Field(min_length=2, max_length=2097152)]
    fence_observer_credential_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    fence_observer_expires_at: _Rfc3339DateTime


class CtowerProjectEpochRefusalRequest(_BoundaryModel):
    cutover_id: UUID
    run_id: UUID
    reconciliation_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    fence_registry_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class CtowerProjectExportEqualityBindRequest(_BoundaryModel):
    run_id: UUID
    cutover_id: UUID
    selection_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    inventory_a_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    inventory_b_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    export_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    equality_report_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    reviewer_key_ref: Annotated[str, Field(pattern="^signing-key-ref:[a-z0-9/_-]{3,255}$")]
    reviewer_key_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    reviewer_public_key_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    result: Literal["equal"]
    export_a_artifact: Annotated[str, Field(min_length=2, max_length=4194304)]
    export_b_artifact: Annotated[str, Field(min_length=2, max_length=4194304)]
    export_equality_artifact: Annotated[str, Field(min_length=2, max_length=2097152)]


class CtowerProjectImportFinalizeRequest(_BoundaryModel):
    run_id: UUID
    cutover_id: UUID
    expected_run_semantic_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    reconciliation_artifact: Annotated[str, Field(min_length=2, max_length=16777216)]


class CtowerProjectImportRunCreateRequest(_BoundaryModel):
    cutover_id: UUID
    tenant_key: Literal["ctower"]
    project_key: Literal["ctower"]
    source_selection_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    source_selection_artifact: Annotated[str, Field(min_length=2, max_length=2097152)]
    build_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    client_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    schema_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    operation_registry_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    reviewer_key_ref: Annotated[str, Field(pattern="^signing-key-ref:[a-z0-9/_-]{3,255}$")]
    reviewer_key_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    reviewer_public_key_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    importer_credential_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    importer_expires_at: _Rfc3339DateTime


class CustodyTransferRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    from_custodian_id: UUID
    protected_transfer: bool
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    to_custodian_id: UUID


class CustodyTransferredPayload(_BoundaryModel):
    from_custodian_id: UUID
    reason: str
    to_custodian_id: UUID


class DeferIntent(_BoundaryModel):
    kind: Literal["defer"]
    expected_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    review_after: _Rfc3339DateTime


class DeferredAuditData(_BoundaryModel):
    episode_number: Annotated[int, Field(ge=1, le=9007199254740991)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    review_after: _Rfc3339DateTime


class DeliverySurfaceAvailabilityNoQualifyingCheckpoint(_BoundaryModel):
    state: Literal["no_qualifying_checkpoint"]


class DreamDispatchConsumeRequest(_BoundaryModel):
    output_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class DreamDispatchConsumption(_BoundaryModel):
    executor_principal_id: UUID
    lane_ref: Annotated[str, Field(min_length=1, max_length=128)]
    crew_name: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    harness_ref: Annotated[str, Field(min_length=1, max_length=128)]
    model_ref: Annotated[str, Field(min_length=1, max_length=128)]
    model_family: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    reasoning_effort: Annotated[str, Field(min_length=1, max_length=32)]
    model_tier: Literal["cheap", "hard"]
    consumed_at: _Rfc3339DateTime
    output_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class DreamDispatchScope(_BoundaryModel):
    kind: Literal["project", "fleet"]
    project_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")] | None


class DreamLaneBindRequest(_BoundaryModel):
    lane_ref: Annotated[str, Field(min_length=1, max_length=128)]
    crew_name: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    harness_ref: Literal["codex"]
    model_ref: Literal["gpt-5.6-sol"]
    reasoning_effort: Literal["max"]
    fallback_model_ref: Literal["qwen3.8-max"]
    model_tier: Literal["hard"]


class DreamModelSelection(_BoundaryModel):
    model_ref: Annotated[str, Field(min_length=1, max_length=128)]
    reasoning_effort: Literal["max"]


class DurabilityState(StrEnum):
    DURABILITY_PENDING = "durability_pending"
    ACCEPTED = "accepted"


class EvidenceRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    evidence_id: UUID
    criterion_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    candidate_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None = None
    artifact_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    content: Annotated[str, Field(min_length=1, max_length=100000)]


class FindingDispositionRequest(_BoundaryModel):
    outcome: Literal["resolved", "snoozed", "expired", "superseded", "cancelled"]
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class HealthContributorKey(StrEnum):
    DURABILITY = "durability"
    SCHEDULER = "scheduler"
    OUTBOX = "outbox"
    PROJECTION = "projection"
    BACKUP = "backup"
    ANCHOR = "anchor"
    OBJECT = "object"
    SYNTHETIC = "synthetic"


class HealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    STATE_UNKNOWN = "STATE_UNKNOWN"


class HumanWaitingNotWaiting(_BoundaryModel):
    state: Literal["not_waiting"]


class HumanWaitingWaiting(_BoundaryModel):
    state: Literal["waiting"]
    finding_id: UUID
    kind_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    reason_code: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]


class InboxAcknowledgeRequest(_BoundaryModel):
    state: Literal["delivered", "read"]


class InboxMessage(_BoundaryModel):
    from_: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")] = Field(
        alias="from", serialization_alias="from"
    )
    message_id: UUID
    position: Annotated[int, Field(ge=1, le=9007199254740991)]
    sent_at: _Rfc3339DateTime
    text: Annotated[str, Field(min_length=1, max_length=65536)]
    to: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]


class InboxMessageReadState(_BoundaryModel):
    delivered_at: _Rfc3339DateTime | None
    delivered_event_id: UUID | None
    message_id: UUID
    position: Annotated[int, Field(ge=1, le=9007199254740991)]
    read_at: _Rfc3339DateTime | None
    read_event_id: UUID | None
    recipient: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    state: Literal["sent", "delivered", "read"]


class InboxNotificationRequest(_BoundaryModel):
    to: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    text: Annotated[str, Field(min_length=1, max_length=65536)]


class InboxPromotionOutcome(StrEnum):
    TICKET_CREATED = "ticket_created"
    TICKET_LINKED = "ticket_linked"


class InboxPromotionRequest(_BoundaryModel):
    ticket_id: UUID | None = None


class InboxSendRequest(_BoundaryModel):
    to: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    thread_id: UUID | None = None
    text: Annotated[str, Field(min_length=1, max_length=65536)]


class InboxThreadSummary(_BoundaryModel):
    last_message_at: _Rfc3339DateTime
    last_message_preview: Annotated[str, Field(min_length=1, max_length=500)]
    other_agent: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    promoted_ticket_id: UUID | None
    thread_id: UUID
    unread_count: Annotated[int, Field(ge=0, le=9007199254740991)]


class IntakeIntent(StrEnum):
    DISCUSSION = "discussion"
    CREATE_REQUEST = "create_request"
    CREATE_TICKET = "create_ticket"
    LINK_TICKET = "link_ticket"


class IntakeOutcome(StrEnum):
    DISCUSSION = "discussion"
    REQUEST_CREATED = "request_created"
    TICKET_CREATED = "ticket_created"
    TICKET_LINKED = "ticket_linked"
    QUARANTINED = "quarantined"


class IntakePromotionIntent(StrEnum):
    CREATE_REQUEST = "create_request"
    CREATE_TICKET = "create_ticket"
    LINK_TICKET = "link_ticket"


class IntakeTaint(StrEnum):
    AUTHENTICATED = "authenticated"
    EXTERNAL_UNTRUSTED = "external_untrusted"
    QUARANTINE_REQUIRED = "quarantine_required"


class KnowledgeScope(StrEnum):
    ORG = "org"
    PROJECT = "project"


class MigrationAliasCorrection(_BoundaryModel):
    kind: Literal["alias"]
    target_ticket_id: UUID
    disposition: Literal["alias_linked_existing", "exact_duplicate", "provenance_only"]


class MigrationConservation(_BoundaryModel):
    selected_logical_items: Annotated[int, Field(ge=1, le=9007199254740991)]
    selected_request_logical: Annotated[int, Field(ge=1, le=9007199254740991)]
    selected_request_physical_snapshots: Annotated[int, Field(ge=1, le=9007199254740991)]
    stable_aliases: Annotated[int, Field(ge=1, le=9007199254740991)]
    checkpoint_definitions: Annotated[int, Field(ge=1, le=9007199254740991)]
    unresolved_aliases: Literal[0]
    alias_forks_or_cycles: Literal[0]
    missing_relation_endpoints: Literal[0]
    forbidden_relation_cycles: Literal[0]
    unresolved_active_claims: Literal[0]
    unexpected_sources: Literal[0]
    forbidden_data_items: Literal[0]
    pass_two_new_domain_facts: Literal[0]
    pass_two_new_events: Literal[0]
    pass_two_new_outbox_rows: Literal[0]
    pass_two_record_position_delta: Literal[0]
    pass_two_projection_semantic_delta: Literal[0]


class MigrationCorrectionRevision(_BoundaryModel):
    object_id: UUID
    revision: Annotated[int, Field(ge=1, le=9007199254740991)]


class MigrationDetachedSignature(_BoundaryModel):
    algorithm: Literal["Ed25519"]
    signed_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    key_ref: Annotated[str, Field(pattern="^signing-key-ref:[a-z0-9/_-]{3,255}$")]
    key_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    public_key_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    signature: Annotated[str, Field(pattern="^[A-Za-z0-9_-]{86}$")]


class MigrationDispositions(_BoundaryModel):
    created_ticket: Annotated[int, Field(ge=0, le=9007199254740991)]
    alias_linked_existing: Annotated[int, Field(ge=0, le=9007199254740991)]
    project_checkpoint_definition: Annotated[int, Field(ge=0, le=9007199254740991)]
    decision_link: Annotated[int, Field(ge=0, le=9007199254740991)]
    external_effect_link: Annotated[int, Field(ge=0, le=9007199254740991)]
    artifact_linked_not_proof: Annotated[int, Field(ge=0, le=9007199254740991)]
    provenance_only: Annotated[int, Field(ge=0, le=9007199254740991)]
    exact_duplicate: Annotated[int, Field(ge=0, le=9007199254740991)]
    excluded_out_of_scope: Annotated[int, Field(ge=0, le=9007199254740991)]
    attention_required: Literal[0]


class MigrationFenceFileIdentity(_BoundaryModel):
    device: Annotated[int, Field(ge=0, le=9007199254740991)]
    inode: Annotated[int, Field(ge=1, le=9007199254740991)]
    scoped_rows_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class MigrationHealthDigests(_BoundaryModel):
    source_selection: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    export_equality: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    alias_map: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    reconciliation: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    fence_registry: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    fence_observation: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None


class MigrationImportCounts(_BoundaryModel):
    planned_operations: Annotated[int, Field(ge=0, le=9007199254740991)]
    applied_operations: Annotated[int, Field(ge=0, le=9007199254740991)]
    replayed_operations: Annotated[int, Field(ge=0, le=9007199254740991)]
    refused_operations: Annotated[int, Field(ge=0, le=9007199254740991)]


class MigrationImportOperationResult(_BoundaryModel):
    command_id: UUID
    operation_kind: Literal["ticket_seed", "exact_alias", "ticket_relation", "source_link"]
    replayed: bool
    target_id: Annotated[str, Field(min_length=1, max_length=256)]
    event_ids: tuple[UUID, ...]
    record_position: Annotated[int, Field(ge=1, le=9007199254740991)]
    occurred_at: _Rfc3339DateTime


class MigrationImporterBinding(_BoundaryModel):
    principal_kind: Literal["migration_importer"]
    credential_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    expires_at: _Rfc3339DateTime
    revoked: bool


class MigrationOperationIdentity(_BoundaryModel):
    namespace: Annotated[str, Field(min_length=1, max_length=128)]
    immutable_source_id: Annotated[str, Field(min_length=1, max_length=512)]
    source_version_or_digest: Annotated[str, Field(min_length=1, max_length=256)]
    operation_kind: Literal["ticket_seed", "exact_alias", "ticket_relation", "source_link"]
    planned_target_ref: Annotated[str, Field(min_length=1, max_length=256)]
    command_id: UUID


class MigrationPassTwoMeasurement(_BoundaryModel):
    start_snapshot_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    end_snapshot_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    start_domain_facts: Annotated[int, Field(ge=0, le=9007199254740991)]
    end_domain_facts: Annotated[int, Field(ge=0, le=9007199254740991)]
    new_domain_facts: Literal[0]
    start_events: Annotated[int, Field(ge=0, le=9007199254740991)]
    end_events: Annotated[int, Field(ge=0, le=9007199254740991)]
    new_events: Literal[0]
    start_outbox_rows: Annotated[int, Field(ge=0, le=9007199254740991)]
    end_outbox_rows: Annotated[int, Field(ge=0, le=9007199254740991)]
    new_outbox_rows: Literal[0]
    start_record_position: Annotated[int, Field(ge=0, le=9007199254740991)]
    end_record_position: Annotated[int, Field(ge=0, le=9007199254740991)]
    record_position_delta: Literal[0]
    start_project_delivery_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    end_project_delivery_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    projection_semantic_delta: Literal[0]


class MigrationPinnedDigests(_BoundaryModel):
    source_selection: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    export_equality: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    alias_map: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    import_plan: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    fence_registry: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    build: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    client: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    schema_id: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] = Field(
        alias="schema", serialization_alias="schema"
    )
    operation_registry: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    reviewer_public_key: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class MigrationReconciliationGraph(_BoundaryModel):
    stable_aliases: tuple[Annotated[str, Field(min_length=1, max_length=8192)], ...]
    operation_identities: tuple[Annotated[str, Field(min_length=1, max_length=8192)], ...]
    operation_results: tuple[Annotated[str, Field(min_length=1, max_length=8192)], ...]
    tickets: tuple[Annotated[str, Field(min_length=1, max_length=8192)], ...]
    lifecycle_facts: tuple[Annotated[str, Field(min_length=1, max_length=8192)], ...]
    priority_facts: tuple[Annotated[str, Field(min_length=1, max_length=8192)], ...]
    custody_intervals: tuple[Annotated[str, Field(min_length=1, max_length=8192)], ...]
    active_claims: tuple[Annotated[str, Field(min_length=1, max_length=8192)], ...]
    alias_revisions: tuple[Annotated[str, Field(min_length=1, max_length=8192)], ...]
    relations: tuple[Annotated[str, Field(min_length=1, max_length=8192)], ...]
    relation_endpoints: tuple[Annotated[str, Field(min_length=1, max_length=8192)], ...]
    source_links: tuple[Annotated[str, Field(min_length=1, max_length=8192)], ...]
    checkpoint_definitions: tuple[Annotated[str, Field(min_length=1, max_length=8192)], ...]
    checkpoint_criteria: tuple[Annotated[str, Field(min_length=1, max_length=8192)], ...]
    project_delivery_rows: tuple[Annotated[str, Field(min_length=1, max_length=8192)], ...]
    events: tuple[Annotated[str, Field(min_length=1, max_length=8192)], ...]
    outbox_rows: tuple[Annotated[str, Field(min_length=1, max_length=8192)], ...]
    unexpected: Annotated[tuple[str, ...], Field(max_length=0)]
    forbidden: Annotated[tuple[str, ...], Field(max_length=0)]
    unresolved: Annotated[tuple[str, ...], Field(max_length=0)]
    cycles: Annotated[tuple[str, ...], Field(max_length=0)]
    graph_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class MigrationRefusal(_BoundaryModel):
    code: Annotated[str, Field(pattern="^[A-Z][A-Z0-9_]{2,95}$")]
    operation_identity: Annotated[str, Field(min_length=1, max_length=512)]


class MigrationRelationCorrection(_BoundaryModel):
    kind: Literal["relation"]
    superseded_relation_active: Literal[False]
    replacement_relation_id: UUID | None


class MigrationReview(_BoundaryModel):
    reviewer_principal_id: UUID
    reviewed_at: _Rfc3339DateTime
    decision: Literal["approved"]


class MigrationReviewerKey(_BoundaryModel):
    public_key_ref: Annotated[str, Field(pattern="^signing-key-ref:[a-z0-9/_-]{3,255}$")]
    key_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    public_key_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class MigrationSourceIdentity(_BoundaryModel):
    namespace: Annotated[str, Field(min_length=1, max_length=128)]
    immutable_source_id: Annotated[str, Field(min_length=1, max_length=512)]
    source_version: Annotated[str, Field(min_length=1, max_length=256)]
    source_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class MigrationSourceLinkCorrection(_BoundaryModel):
    kind: Literal["source_link"]
    target_kind: Literal[
        "ticket",
        "ticket_relation",
        "checkpoint",
        "decision",
        "artifact",
        "external_effect",
    ]
    target_id: Annotated[str, Field(min_length=1, max_length=256)]
    disposition: Literal[
        "decision_link",
        "external_effect_link",
        "artifact_linked_not_proof",
        "provenance_only",
        "excluded_out_of_scope",
    ]


class MigrationWatermarks(_BoundaryModel):
    source_native: Annotated[int, Field(ge=0, le=9007199254740991)]
    export_native: Annotated[int, Field(ge=0, le=9007199254740991)]
    record_position: Annotated[int, Field(ge=0, le=9007199254740991)]
    projection_position: Annotated[int, Field(ge=0, le=9007199254740991)]


class MutableAssignmentKind(StrEnum):
    CURRENT_ASSIGNEE = "current_assignee"
    STAGE_OWNER = "stage_owner"
    REVIEWER_ASSIGNMENT = "reviewer_assignment"


class PoisonDispositionAction(StrEnum):
    RETRY = "retry"
    TOMBSTONE = "tombstone"


class Priority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class ProhibitedDataClass(StrEnum):
    CREDENTIAL_MATERIAL = "credential_material"
    LIVE_INCIDENT_INDICATOR = "live_incident_indicator"
    PHI_HIPAA_COVERED = "phi_hipaa_covered"
    PII_BEYOND_STAFF_IDENTITY = "pii_beyond_staff_identity"
    PRODUCTION_CUSTOMER_DATA = "production_customer_data"


class ProjectDeliveryCriteria(_BoundaryModel):
    proven: Annotated[int, Field(ge=0, le=9007199254740991)]
    declared: Annotated[int, Field(ge=1, le=9007199254740991)]


class ProjectDeliveryUnassignedSeatAssignment(_BoundaryModel):
    state: Literal["unassigned"]


class ProjectionHealth(StrEnum):
    CURRENT = "CURRENT"
    STATE_UNKNOWN = "STATE_UNKNOWN"


class ProofChangedAuditPayload(_BoundaryModel):
    candidate_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    invalidated_evidence_ids: tuple[UUID, ...]
    invalidated_verdict_ids: tuple[UUID, ...]
    operation: Literal["freeze_criteria", "record_evidence", "record_verdict", "change_candidate"]
    proof_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    ticket_id: UUID


class ProofCriterion(_BoundaryModel):
    key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    description: Annotated[str, Field(min_length=1, max_length=500)]
    candidate_dependent: bool
    requires_verdict: bool


class RelationAddedAuditData(_BoundaryModel):
    relation_kind: Literal["parent_of", "depends_on", "blocks", "duplicates", "relates_to", "caused_by"]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    target_ticket_id: UUID


class RelationKind(StrEnum):
    PARENT_OF = "parent_of"
    DEPENDS_ON = "depends_on"
    BLOCKS = "blocks"
    DUPLICATES = "duplicates"
    RELATES_TO = "relates_to"
    CAUSED_BY = "caused_by"


class ReopenIntent(_BoundaryModel):
    kind: Literal["reopen"]
    expected_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    priority_policy: Literal["carry_forward"]


class RequestBlockerRequest(_BoundaryModel):
    active: bool
    blocker_key: Annotated[str, Field(min_length=1, max_length=256)]
    expected_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class RequestCaptureRequest(_BoundaryModel):
    project_key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")]
    text: Annotated[str, Field(min_length=1, max_length=65536)]


class RequestClosureEvaluationRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class RequestOwnerRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    owner_id: UUID
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class RequestTicketRelationRequest(_BoundaryModel):
    active: bool
    expected_ticket_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    expected_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    purpose: Literal["required", "optional"]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    ticket_id: UUID


class RequestTriageRequest(_BoundaryModel):
    canonical_request_id: UUID | None = None
    disposition: Literal["ACCEPTED", "DUPLICATE", "REJECTED"]
    expected_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    reason: Annotated[str, Field(min_length=1, max_length=500)] | None = None


class ResolveCloseRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    workflow_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*@[1-9][0-9]*$")] | None = None


class ReviewDispatchConsumeRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    crew_name: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]


class ReviewDispatchConsumption(_BoundaryModel):
    reviewer_principal_id: UUID
    author_family: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    reviewer_model_ref: Annotated[str, Field(min_length=1, max_length=128)]
    reviewer_family: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    crew_name: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    consumed_by: UUID
    consumed_at: _Rfc3339DateTime


class SeatCatalogRevision(_BoundaryModel):
    catalog_key: Annotated[str, Field(pattern="^[a-z][a-z0-9.-]{2,127}$")]
    revision: Annotated[int, Field(ge=1, le=9007199254740991)]
    content_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class SeatCredentialRevocationRequest(_BoundaryModel):
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class SecretBindingReference(_BoundaryModel):
    name: Annotated[str, Field(pattern="^[A-Z][A-Z0-9_]{2,127}$")]
    reference_class: Literal["os-credential", "vault-path", "runtime-binding"]


class SessionOutcome(StrEnum):
    DELIVERED = "delivered"
    BLOCKED = "blocked"
    ABANDONED = "abandoned"
    FAILED = "failed"


class SessionStartRequest(_BoundaryModel):
    branch_ref: Annotated[str, Field(min_length=1, max_length=256)]
    crew_name: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    harness_ref: Annotated[str, Field(min_length=1, max_length=64)]
    model_ref: Annotated[str, Field(min_length=1, max_length=128)]
    seat_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    worktree_ref: Annotated[str, Field(min_length=1, max_length=256)]


class SessionStartedPayload(_BoundaryModel):
    branch_ref: Annotated[str, Field(min_length=1, max_length=256)]
    crew_name: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    harness_ref: Annotated[str, Field(min_length=1, max_length=64)]
    model_ref: Annotated[str, Field(min_length=1, max_length=128)]
    seat_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    session_id: UUID
    ticket_id: UUID
    worktree_ref: Annotated[str, Field(min_length=1, max_length=256)]


class SessionState(StrEnum):
    DISPATCHED = "dispatched"
    BRIEFED = "briefed"
    WORKING = "working"
    GATED = "gated"


class SessionTokenUsage(_BoundaryModel):
    input_tokens: Annotated[int, Field(ge=0, le=1000000000)]
    output_tokens: Annotated[int, Field(ge=0, le=1000000000)]
    total_tokens: Annotated[int, Field(ge=0, le=2000000000)]


class SourceReference(_BoundaryModel):
    kind: Annotated[str, Field(min_length=1, max_length=64)]
    ref: Annotated[str, Field(min_length=1, max_length=256)]


class SurfaceDeclarationState(StrEnum):
    DECLARED_PRESENT = "declared_present"
    DECLARED_ABSENT = "declared_absent"
    UNDECLARED = "undeclared"


class SyntheticRunRequest(_BoundaryModel):
    workflow_ref: Literal["ctower.trust-spine-four-stage@1"]


class SyntheticRunState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TelemetryContext(_BoundaryModel):
    schema_id: Literal["ctower.telemetry-context/v1"] = Field(
        alias="schema", serialization_alias="schema"
    )
    trace_id: Annotated[str, Field(pattern="^[a-f0-9]{32}$")]
    span_id: Annotated[str, Field(pattern="^[a-f0-9]{16}$")]
    trace_flags: Annotated[int, Field(ge=0, le=255)]
    trace_state: Annotated[str, Field(max_length=512)] | None = None
    correlation_id: Annotated[str, Field(min_length=1, max_length=128)]
    causation_id: Annotated[str, Field(min_length=1, max_length=128)]
    tenant_id: Annotated[str, Field(min_length=1, max_length=128)]
    actor_id: Annotated[str, Field(min_length=1, max_length=128)]
    command_id: Annotated[str, Field(min_length=1, max_length=128)]
    ticket_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    workflow_run_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    stage_attempt_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    job_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    runner_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    fencing_token: Annotated[int, Field(ge=1, le=9007199254740991)] | None = None
    effect_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    component_revision_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    deployment_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None


class TenantDisplayIdentityKnown(_BoundaryModel):
    state: Literal["known"]
    display_name: Annotated[str, Field(min_length=1, max_length=128)]


class TenantDisplayIdentityUnknown(_BoundaryModel):
    state: Literal["unknown"]
    missing_source: Annotated[str, Field(min_length=1)]


class TicketCommentAddedPayload(_BoundaryModel):
    body: Annotated[str, Field(min_length=1, max_length=4000)]
    comment_id: UUID
    ticket_id: UUID


class TicketCommentRequest(_BoundaryModel):
    body: Annotated[str, Field(min_length=1, max_length=4000)]


class UnblockIntent(_BoundaryModel):
    kind: Literal["unblock"]
    expected_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    blocker_id: UUID
    resolution_evidence_ref: Annotated[str, Field(min_length=1, max_length=256)]


class VerdictDecision(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class WorkflowChangedAuditPayload(_BoundaryModel):
    lifecycle_facts: Annotated[tuple[Literal["resolved", "closed"], ...], Field(max_length=2)]
    operation: Literal["start", "transition", "resolve_close"]
    stage: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    ticket_id: UUID
    workflow_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*@[1-9][0-9]*$")]
    workflow_version: Annotated[int, Field(ge=1, le=9007199254740991)]


class WorkflowStartRequest(_BoundaryModel):
    workflow_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*@[1-9][0-9]*$")]
    workflow_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    execution_policy_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*@[1-9][0-9]*$")]
    execution_policy_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    gate_policy_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*@[1-9][0-9]*$")]
    gate_policy_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    evidence_policy_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*@[1-9][0-9]*$")]
    evidence_policy_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class WorkflowTransitionRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=0, le=9007199254740991)]
    workflow_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*@[1-9][0-9]*$")]
    source_stage: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    destination_stage: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]


class ApplyLabelResult(_BoundaryModel):
    command_id: UUID
    ticket_label_id: UUID
    durability_state: DurabilityState
    event_id: UUID
    ticket_id: UUID
    label_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]


class AssignmentChangeRequest(_BoundaryModel):
    assignment_kind: MutableAssignmentKind
    expected_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    scope_ref: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    to_principal_id: UUID


class AssignmentInterval(_BoundaryModel):
    assigned_at: _Rfc3339DateTime
    assignment_kind: AssignmentKind
    changed_by: UUID
    episode_number: Annotated[int, Field(ge=1, le=9007199254740991)]
    principal_id: UUID
    reason: str
    released_at: _Rfc3339DateTime | None
    scope_ref: str | None
    sequence: Annotated[int, Field(ge=1, le=9007199254740991)]


class AttentionFindingResult(_BoundaryModel):
    command_id: UUID
    finding_id: UUID
    durability_state: DurabilityState
    event_ids: tuple[UUID, ...]
    recorded_at: _Rfc3339DateTime


class BootstrapReceipt(_BoundaryModel):
    command_id: UUID
    commander_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    operator_id: UUID
    receipt_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    tenant_id: UUID


class ChangeReferenceResult(_BoundaryModel):
    command_id: UUID
    change_reference_id: UUID
    durability_state: DurabilityState
    event_id: UUID
    ticket_id: UUID


class CompanyBundleCommandResult(_BoundaryModel):
    active_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    bundle_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    command_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    plan_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class CompanyBundleExportMetadata(_BoundaryModel):
    activated_at: _Rfc3339DateTime
    actor_principal_id: UUID
    checks: tuple[BundleCheck, ...]
    command_id: UUID


class CompanyBundleValidationResult(_BoundaryModel):
    bundle_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    checks: tuple[BundleCheck, ...]
    valid: bool
    warnings: tuple[Annotated[str, Field(max_length=500)], ...]


class ComponentReference(_BoundaryModel):
    content_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    key: Annotated[str, Field(pattern="^[a-z][a-z0-9.-]{2,127}$")]
    kind: ComponentKind
    revision: Annotated[int, Field(ge=1, le=9007199254740991)]


class CtowerProjectCutoverHealth(_BoundaryModel):
    schema_id: Literal["ctower.ctower-project-cutover-health/v1"] = Field(
        alias="schema", serialization_alias="schema"
    )
    cutover_id: UUID | None
    authority_mode: Literal["legacy_writable", "development_single_writer", "disaster_safe"]
    phase: Literal[
        "not_started",
        "source_selection_frozen",
        "export_equal",
        "alias_plan_bound",
        "import_in_progress",
        "reconciled",
        "prepared",
        "development_epoch_committed",
        "disaster_safe_active",
    ]
    writes_enabled: bool
    durability_claim: Literal["CP3_D_NOT_PROVEN", "CP3_D_PROVEN"]
    recovery_claim: Literal["EXTERNAL_FAILURE_DOMAIN_UNPROVEN", "EXTERNAL_FAILURE_DOMAIN_PROVEN"]
    data_class: Literal["RECONSTRUCTIBLE_ONLY", "DISASTER_SAFE_CTOWER_ENGINEERING"]
    legacy_writer_fence: Literal["not_armed", "enforced", "unknown"]
    split_brain: Literal["clear", "detected", "unknown"]
    projection_completeness: Literal["current", "stale", "STATE_UNKNOWN"]
    source_watermark: Annotated[int, Field(ge=0, le=9007199254740991)]
    projection_watermark: Annotated[int, Field(ge=0, le=9007199254740991)]
    import_run_id: UUID | None
    migration_digests: MigrationHealthDigests
    banner: Annotated[str, Field(min_length=1)]


class CtowerProjectExactAliasOperation(_BoundaryModel):
    operation: Literal["exact_alias"]
    identity: MigrationOperationIdentity
    project_key: Literal["ctower"]
    source: MigrationSourceIdentity
    target_ticket_id: UUID


class CtowerProjectFenceObservationRequest(_BoundaryModel):
    schema_id: Literal["ctower.ctower-project-fence-observation/v2"] = Field(
        alias="schema", serialization_alias="schema"
    )
    observation_id: UUID
    run_id: UUID
    cutover_id: UUID
    tenant_key: Literal["ctower"]
    project_key: Literal["ctower"]
    registry_id: UUID
    registry_revision: Annotated[int, Field(ge=1, le=9007199254740991)]
    registry_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    source_pointer_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    sequence: Annotated[int, Field(ge=1, le=9007199254740991)]
    previous_observation_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    observed_at: _Rfc3339DateTime
    from_offset: Annotated[int, Field(ge=0, le=9007199254740991)]
    to_offset: Annotated[int, Field(ge=0, le=9007199254740991)]
    file_identity: MigrationFenceFileIdentity
    status: Literal["clear", "detected", "unknown"]
    reason_code: Literal[
        "no_scoped_append",
        "scoped_row_appended",
        "truncated_row",
        "inode_replaced",
        "file_truncated",
        "unreadable_gap",
        "classifier_unknown",
        "monitor_interval_missing",
        "registry_mismatch",
        "observation_stale",
        "observation_from_future",
        "offset_reversed",
        "pointer_mismatch",
    ]
    observation_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    disables_writes: bool
    may_enable_writes: Literal[False]


class CtowerProjectImportBatchResult(_BoundaryModel):
    run_id: UUID
    batch_index: Annotated[int, Field(ge=0, le=9007199254740991)]
    batch_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    results: Annotated[tuple[MigrationImportOperationResult, ...], Field(min_length=1, max_length=64)]
    record_watermark: Annotated[int, Field(ge=1, le=9007199254740991)]
    projection_watermark: Annotated[int, Field(ge=0, le=9007199254740991)]
    durability_state: DurabilityState
    accepted_position: Annotated[int, Field(ge=1, le=9007199254740991)] | None


class CtowerProjectImportRun(_BoundaryModel):
    schema_id: Literal["ctower.ctower-project-import-run/v2"] = Field(
        alias="schema", serialization_alias="schema"
    )
    run_id: UUID
    cutover_id: UUID
    tenant_key: Literal["ctower"]
    project_key: Literal["ctower"]
    state: Literal[
        "created",
        "export_equality_bound",
        "alias_plan_bound",
        "importing",
        "pass_one_complete",
        "pass_two_started",
        "pass_two_noop",
        "reconciled",
    ]
    pinned_digests: MigrationPinnedDigests
    reviewer_key: MigrationReviewerKey
    importer_binding: MigrationImporterBinding
    counts: MigrationImportCounts
    dispositions: MigrationDispositions | None
    conservation: MigrationConservation | None
    reconciliation_graph: MigrationReconciliationGraph | None
    pass_two_measurement: MigrationPassTwoMeasurement | None
    source_native_watermark: Annotated[int, Field(ge=0, le=9007199254740991)]
    export_native_watermark: Annotated[int, Field(ge=0, le=9007199254740991)]
    record_watermark: Annotated[int, Field(ge=0, le=9007199254740991)]
    projection_watermark: Annotated[int, Field(ge=0, le=9007199254740991)]
    refusals: tuple[MigrationRefusal, ...]
    semantic_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    durability_state: DurabilityState
    accepted_position: Annotated[int, Field(ge=1, le=9007199254740991)] | None


class CtowerProjectMigrationReceipt(_BoundaryModel):
    object_id: UUID
    revision: Annotated[int, Field(ge=1, le=9007199254740991)]
    command_id: UUID
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    record_position: Annotated[int, Field(ge=1, le=9007199254740991)]
    semantic_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    durability_state: DurabilityState
    accepted_position: Annotated[int, Field(ge=1, le=9007199254740991)] | None


class CtowerProjectReconciliationResult(_BoundaryModel):
    schema_id: Literal["ctower.ctower-project-reconciliation/v2"] = Field(
        alias="schema", serialization_alias="schema"
    )
    reconciliation_id: UUID
    run_id: UUID
    cutover_id: UUID
    project_key: Literal["ctower"]
    pinned_digests: MigrationPinnedDigests
    reviewer_key: MigrationReviewerKey
    expected_graph: MigrationReconciliationGraph
    actual_graph: MigrationReconciliationGraph
    pass_two_measurement: MigrationPassTwoMeasurement
    watermarks: MigrationWatermarks
    target_semantic_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    reconciled_at: _Rfc3339DateTime
    review: MigrationReview
    report_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    signature: MigrationDetachedSignature
    durability_state: DurabilityState
    accepted_position: Annotated[int, Field(ge=1, le=9007199254740991)] | None


class CtowerProjectSourceLinkOperation(_BoundaryModel):
    operation: Literal["source_link"]
    identity: MigrationOperationIdentity
    project_key: Literal["ctower"]
    source: MigrationSourceIdentity
    link_class: Literal["decision", "external_effect", "artifact_not_proof", "provenance"]
    target_kind: Literal[
        "ticket",
        "ticket_relation",
        "checkpoint",
        "decision",
        "artifact",
        "external_effect",
    ]
    target_id: Annotated[str, Field(min_length=1, max_length=256)]
    reason_code: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{2,95}$")]
    linked_not_proof: Literal[True]


class CtowerProjectTicketRelationOperation(_BoundaryModel):
    operation: Literal["ticket_relation"]
    identity: MigrationOperationIdentity
    project_key: Literal["ctower"]
    relation_id: UUID
    relation_kind: Literal["parent_of", "depends_on", "blocks", "duplicates", "relates_to", "caused_by"]
    source_ticket_id: UUID
    target_ticket_id: UUID
    reason: Annotated[str, Field(min_length=1, max_length=500, pattern="^[^\\u0000-\\u001F\\u007F]+$")]


class CtowerProjectTicketSeedOperation(_BoundaryModel):
    operation: Literal["ticket_seed"]
    identity: MigrationOperationIdentity
    project_key: Literal["ctower"]
    priority: Literal["P2"]
    title: Annotated[str, Field(min_length=1, max_length=200, pattern="^[^\\u0000-\\u001F\\u007F]+$")]
    source: MigrationSourceIdentity
    initial_commander_custodian_id: UUID


class CustodyTransferredAuditEvent(_BoundaryModel):
    actor_principal_id: UUID
    command_id: UUID
    event_hash: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    event_id: UUID
    kind: Literal["ticket.custody_transferred"]
    occurred_at: _Rfc3339DateTime
    payload: CustodyTransferredPayload
    record_position: Annotated[int, Field(ge=1, le=9007199254740991)]
    sequence: Annotated[int, Field(ge=1, le=9007199254740991)]
    stream_id: Annotated[str, Field(pattern="^ticket:[0-9a-f-]{36}$")]


class DreamDispatchReceipt(_BoundaryModel):
    command_id: UUID
    effect_id: UUID
    durability_state: DurabilityState
    event_id: UUID
    output_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class DreamLaneBindingReceipt(_BoundaryModel):
    binding_source: Literal["operator-ceremony"]
    bound_at: _Rfc3339DateTime
    command_id: UUID
    crew_name: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    durability_state: DurabilityState
    event_id: UUID
    harness_ref: Literal["codex"]
    lane_ref: Annotated[str, Field(min_length=1, max_length=128)]
    model_family: Literal["codex"]
    model_ref: Literal["gpt-5.6-sol"]
    model_tier: Literal["hard"]
    principal_id: UUID
    probe_evidence: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    reasoning_effort: Literal["max"]


class DreamModelRequirement(_BoundaryModel):
    primary: DreamModelSelection
    fallback: DreamModelSelection
    minimum_tier: Literal["hard"]
    excluded_families: Annotated[tuple[Literal["claude"], ...], Field(min_length=1, max_length=1)]


class FindingDispositionResult(_BoundaryModel):
    command_id: UUID
    finding_id: UUID
    outcome: Literal["resolved", "snoozed", "expired", "superseded", "cancelled"]
    durability_state: DurabilityState
    event_ids: tuple[UUID, ...]
    recorded_at: _Rfc3339DateTime


class FreezeCriteriaRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=0, le=9007199254740991)]
    candidate_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    criteria: Annotated[tuple[ProofCriterion, ...], Field(min_length=1)]


class HealthContributor(_BoundaryModel):
    key: HealthContributorKey
    status: HealthStatus
    watermark: Annotated[int, Field(ge=0, le=9007199254740991)] | None
    threshold_seconds: Annotated[int, Field(ge=0, le=9007199254740991)]
    observed_at: _Rfc3339DateTime
    owner: Annotated[str, Field(min_length=1, max_length=128)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]


type HumanWaiting = HumanWaitingWaiting | HumanWaitingNotWaiting


class InboxAcknowledgeResult(_BoundaryModel):
    command_id: UUID
    delivered_at: _Rfc3339DateTime
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=2)]
    message_id: UUID
    read_at: _Rfc3339DateTime | None
    state: Literal["delivered", "read"]
    thread_id: UUID
    thread_version: Annotated[int, Field(ge=3, le=9007199254740991)]


class InboxPromotionResult(_BoundaryModel):
    command_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=2)]
    outcome: InboxPromotionOutcome
    thread_id: UUID
    thread_version: Annotated[int, Field(ge=3, le=9007199254740991)]
    ticket_id: UUID


class InboxReadState(_BoundaryModel):
    messages: Annotated[tuple[InboxMessageReadState, ...], Field(min_length=1)]
    thread_id: UUID


class InboxSendResult(_BoundaryModel):
    command_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=2)]
    from_: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")] = Field(
        alias="from", serialization_alias="from"
    )
    message_id: UUID
    position: Annotated[int, Field(ge=1, le=9007199254740991)]
    sent_at: _Rfc3339DateTime
    thread_id: UUID
    thread_version: Annotated[int, Field(ge=2, le=9007199254740991)]
    to: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]


class InboxThread(_BoundaryModel):
    messages: Annotated[tuple[InboxMessage, ...], Field(min_length=1)]
    participants: Annotated[tuple[Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")], ...], Field(min_length=2, max_length=2)]
    promoted_ticket_id: UUID | None
    read_through_position: Annotated[int, Field(ge=0, le=9007199254740991)]
    thread_id: UUID


class InboxThreadList(_BoundaryModel):
    recipient: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    threads: tuple[InboxThreadSummary, ...]
    total_unread: Annotated[int, Field(ge=0, le=9007199254740991)]
    unread_only: bool


class IntakeCommandResult(_BoundaryModel):
    command_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=2)]
    inbound_event_id: UUID
    outcome: IntakeOutcome
    project_key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")]
    quarantine_reason: Annotated[str, Field(max_length=500)] | None
    request_id: UUID | None
    request_number: Annotated[int, Field(ge=1, le=9007199254740991)] | None
    source: SourceReference
    thread_id: UUID
    thread_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    ticket_id: UUID | None
    ticket_version: Annotated[int, Field(ge=1, le=9007199254740991)] | None


class IntakePromotionRequest(_BoundaryModel):
    expected_thread_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    expected_ticket_version: Annotated[int, Field(ge=1, le=9007199254740991)] | None = None
    initial_custodian_id: UUID | None = None
    intent: IntakePromotionIntent
    priority: Priority | None = None
    target_ticket_id: UUID | None = None
    title: Annotated[str, Field(min_length=1, max_length=200)] | None = None


class IntakeSubmitRequest(_BoundaryModel):
    content: Annotated[str, Field(min_length=1, max_length=65536)]
    expected_thread_version: Annotated[int, Field(ge=1, le=9007199254740991)] | None = None
    expected_ticket_version: Annotated[int, Field(ge=1, le=9007199254740991)] | None = None
    initial_custodian_id: UUID | None = None
    intent: IntakeIntent | None = None
    priority: Priority | None = None
    project_key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")]
    source: SourceReference
    taint: IntakeTaint | None = None
    target_ticket_id: UUID | None = None
    thread_id: UUID | None = None
    title: Annotated[str, Field(min_length=1, max_length=200)] | None = None


class KnowledgeAddRequest(_BoundaryModel):
    body: Annotated[str, Field(min_length=1, max_length=1048576)] | None = None
    project_key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")] | None
    scope: KnowledgeScope
    source_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{0,127}$")] | None = None
    title: Annotated[str, Field(min_length=1, max_length=1024)] | None = None


class KnowledgeAddResult(_BoundaryModel):
    command_id: UUID
    document_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=1)]
    project_key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")] | None
    registered_at: _Rfc3339DateTime
    scope: KnowledgeScope
    source_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{0,127}$")] | None
    title: Annotated[str, Field(min_length=1, max_length=1024)]


class KnowledgeDocument(_BoundaryModel):
    body: Annotated[str, Field(min_length=1, max_length=1048576)]
    document_id: UUID
    project_key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")] | None
    registered_at: _Rfc3339DateTime
    registered_by: UUID
    scope: KnowledgeScope
    source_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{0,127}$")] | None
    title: Annotated[str, Field(min_length=1, max_length=1024)]


type MigrationCorrectionReplacement = MigrationAliasCorrection | MigrationSourceLinkCorrection | MigrationRelationCorrection


class PoisonDispositionReceipt(_BoundaryModel):
    command_id: UUID
    outbox_id: UUID
    action: PoisonDispositionAction
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    recorded_at: _Rfc3339DateTime


class PoisonDispositionRequest(_BoundaryModel):
    consumer_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    topic: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    action: PoisonDispositionAction
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class PriorityChangeRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    priority: Priority
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    urgent_evidence_ref: Annotated[str, Field(min_length=1, max_length=256)] | None = None


class PriorityChangedAuditData(_BoundaryModel):
    authority: Literal["commander", "operator"]
    from_priority: Priority
    policy_ref: Literal["ctower.priority-authority@1"]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    to_priority: Priority
    urgent_evidence_ref: Annotated[str, Field(min_length=1, max_length=256)] | None


class Problem(_BoundaryModel):
    code: Literal[
        "attention-finding-already-disposed",
        "attention-finding-not-found",
        "attention-kind-unrecognized",
        "auth-exchange-invalid",
        "auth-identity-unresolved",
        "auth-provider-unavailable",
        "auth-provider-unverifiable",
        "auth-role-denied",
        "auth-session-invalid",
        "bootstrap-consumed",
        "bootstrap-expired",
        "bootstrap-nonempty",
        "bootstrap-origin",
        "bundle-base-conflict",
        "bundle-compatibility-refused",
        "bundle-digest-mismatch",
        "bundle-grant-refused",
        "bundle-independence-refused",
        "bundle-no-effect-refused",
        "bundle-not-active",
        "bundle-plan-mismatch",
        "bundle-recovery-unavailable",
        "bundle-reference-invalid",
        "bundle-schema-invalid",
        "bundle-security-refused",
        "change-reference-duplicate",
        "credential-already-revoked",
        "credential-authentication-unavailable",
        "credential-digest-conflict",
        "credential-issuance-refused",
        "credential-revocation-refused",
        "credential-revoked",
        "credential-scope-denied",
        "dream-dispatch-already-consumed",
        "dream-dispatch-family-excluded",
        "dream-dispatch-lane-unbound",
        "dream-dispatch-model-requirement-mismatch",
        "dream-dispatch-tier-refused",
        "dream-dispatch-unavailable",
        "dream-lane-already-bound",
        "dream-lane-binding-operator-required",
        "durability_pending",
        "i1-7c-required",
        "idempotency-conflict",
        "inbox-already-promoted",
        "inbox-acknowledgement-not-advancing",
        "inbox-message-recipient-mismatch",
        "inbox-recipient-ambiguous",
        "inbox-recipient-not-found",
        "inbox-recipient-self",
        "inbox-sender-unaddressable",
        "inbox-thread-head-invalid",
        "inbox-thread-participant-mismatch",
        "intake-already-promoted",
        "intake-promotion-ineligible",
        "intake-source-project-mismatch",
        "intake-source-conflict",
        "knowledge-invalid-project",
        "knowledge-invalid-scope",
        "knowledge-source-not-found",
        "knowledge-source-unavailable",
        "label-already-applied",
        "label-key-unrecognized",
        "migration-alias-conflict",
        "migration-capability-denied",
        "migration-correction-conflict",
        "migration-digest-mismatch",
        "migration-export-nondeterminism",
        "migration-fence-detected",
        "migration-import-finalization-refused",
        "migration-operation-drift",
        "migration-relation-invalid",
        "migration-run-conflict",
        "migration-signature-invalid",
        "migration-source-selection-drift",
        "migration-source-tainted",
        "poison-not-found",
        "prohibited-data-class",
        "project-delivery-unavailable",
        "project-grant-required",
        "project-scope-denied",
        "request-capture-forbidden",
        "invalid-request",
        "request-import-forbidden",
        "request-owner-forbidden",
        "request-project-unavailable",
        "request-source-forbidden",
        "request-transition-forbidden",
        "request-triage-forbidden",
        "reauthentication-required",
        "request-body-too-large",
        "proof-candidate-author-mismatch",
        "proof-candidate-digest-invalid",
        "proof-candidate-digest-not-current",
        "proof-candidate-unchanged",
        "proof-criteria-already-frozen",
        "proof-criteria-invalid",
        "proof-criteria-policy-mismatch",
        "proof-criterion-unknown",
        "proof-current-evidence-missing",
        "proof-evidence-digest-mismatch",
        "proof-evidence-id-conflict",
        "proof-protected-authority-required",
        "proof-policy-mismatch",
        "proof-policy-pin-mismatch",
        "proof-self-review-refused",
        "proof-verdict-id-conflict",
        "review-dispatch-already-consumed",
        "review-dispatch-family-conflict",
        "review-dispatch-incomplete",
        "review-dispatch-input-missing",
        "review-dispatch-model-unbound",
        "review-dispatch-self-review",
        "review-dispatch-unavailable",
        "seat-binding-conflict",
        "seat-credential-active",
        "seat-credential-unavailable",
        "seat-display-name-conflict",
        "session-ineligible",
        "session-not-found",
        "session-transition-invalid",
        "tenant-scope-denied",
        "ticket-comment-ineligible",
        "ticket-comment-invalid",
        "unauthorized",
        "validation-error",
        "version-conflict",
        "work-assignment-kind-refused",
        "work-assignment-target-ineligible",
        "work-assignment-unchanged",
        "work-priority-unchanged",
        "work-blocker-already-resolved",
        "work-blocker-id-conflict",
        "work-blocker-owner-ineligible",
        "work-blocker-unknown",
        "work-intent-unmet",
        "work-relation-cycle",
        "work-relation-exists",
        "work-reopen-unmet",
        "work-ticket-terminal",
        "workflow-already-started",
        "workflow-pin-mismatch",
        "workflow-predicate-unsatisfied",
        "workflow-run-not-started",
        "proof-incomplete",
        "workflow-state-conflict",
        "workflow-terminal",
        "workflow-transition-not-declared",
        "workflow-version-unknown",
        "workflow-not-terminal",
    ]
    command_id: UUID | None = None
    current_version: Annotated[int, Field(ge=0, le=9007199254740991)] | None = None
    detail: str
    prohibited_classes: tuple[ProhibitedDataClass, ...] | None = None
    status: Annotated[int, Field(ge=400, le=599)]
    title: str
    type_uri: _AbsoluteUri = Field(alias="type", serialization_alias="type")
    unmet_facts: tuple[str, ...] | None = None


class ProjectDeliverySeat(_BoundaryModel):
    seat_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    seat_label: Annotated[str, Field(min_length=1)]
    catalog_revision: SeatCatalogRevision


class ProofChangedAuditEvent(_BoundaryModel):
    actor_principal_id: UUID
    command_id: UUID
    event_hash: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    event_id: UUID
    kind: Literal["proof.changed"]
    occurred_at: _Rfc3339DateTime
    payload: ProofChangedAuditPayload
    record_position: Annotated[int, Field(ge=1, le=9007199254740991)]
    sequence: Annotated[int, Field(ge=1, le=9007199254740991)]
    stream_id: Annotated[str, Field(pattern="^proof:[0-9a-f-]{36}$")]


class ProofReceipt(_BoundaryModel):
    artifact_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    candidate_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    command_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    invalidated_evidence_ids: tuple[UUID, ...]
    invalidated_verdict_ids: tuple[UUID, ...]
    proof_id: UUID
    satisfied: bool
    ticket_id: UUID
    version: Annotated[int, Field(ge=1, le=9007199254740991)]


class RelationRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    relation_kind: RelationKind
    target_ticket_id: UUID


class ReopenedAuditData(_BoundaryModel):
    episode_number: Annotated[int, Field(ge=2, le=9007199254740991)]
    priority: Priority
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class RequestCaptureResult(_BoundaryModel):
    accepted_position: Annotated[int, Field(ge=1, le=9007199254740991)] | None
    command_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=2, max_length=2)]
    inbound_event_id: UUID
    owner_id: UUID
    project_key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")]
    reference: Annotated[str, Field(pattern="^R[1-9][0-9]*$")]
    request_id: UUID
    request_number: Annotated[int, Field(ge=1, le=9007199254740991)]
    submitted_by: UUID
    version: Annotated[int, Field(ge=1, le=9007199254740991)]


class RequestChangeResult(_BoundaryModel):
    accepted_position: Annotated[int, Field(ge=1, le=9007199254740991)] | None
    command_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=1)]
    operation: Literal[
        "priority",
        "triage",
        "owner",
        "ticket_relation",
        "blocker",
        "closure_evaluation",
    ]
    reference: Annotated[str, Field(pattern="^R[1-9][0-9]*$")]
    request_id: UUID
    request_number: Annotated[int, Field(ge=1, le=9007199254740991)]
    state: Literal["NEW", "TRIAGED", "WIP", "BLOCKED", "DONE"]
    version: Annotated[int, Field(ge=2, le=9007199254740991)]


class RequestPriorityRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    priority: Priority
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class RequestRow(_BoundaryModel):
    age_seconds: Annotated[int, Field(ge=0, le=9007199254740991)]
    blocker: str | None
    content: Annotated[str, Field(min_length=1, max_length=65536)]
    content_sha256: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    created_at: _Rfc3339DateTime
    durability_state: Literal["accepted"]
    freshness: Annotated[int, Field(ge=1, le=9007199254740991)]
    optional_ticket_ids: tuple[UUID, ...]
    owner: Annotated[str, Field(min_length=1, max_length=120)]
    owner_id: UUID
    priority: Priority
    priority_default: bool
    project_key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")]
    proof_coverage: Annotated[int, Field(ge=0, le=9007199254740991)] | None
    reference: Annotated[str, Field(pattern="^R[1-9][0-9]*$")]
    request_id: UUID
    request_number: Annotated[int, Field(ge=1, le=9007199254740991)]
    required_ticket_ids: tuple[UUID, ...]
    source_kind: Annotated[str, Field(min_length=1, max_length=64)]
    source_ref: Annotated[str, Field(min_length=1, max_length=512)]
    original_owner_sha256: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    state: Literal["NEW", "TRIAGED", "WIP", "BLOCKED", "DONE"]
    ticket_count: Annotated[int, Field(ge=0, le=9007199254740991)]
    triage: Literal["UNTRIAGED", "ACCEPTED", "DUPLICATE", "REJECTED"]
    unknown_reason: str | None


class ReviewDispatchEffect(_BoundaryModel):
    effect_id: UUID
    workflow_run_id: UUID
    ticket_id: UUID
    workflow_version: Annotated[int, Field(ge=2, le=9007199254740991)]
    destination_stage: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    candidate_digest: Annotated[str, Field(pattern="^sha256:[a-f0-9]{64}$")]
    author_principal_id: UUID
    author_model_ref: Annotated[str, Field(min_length=1, max_length=128)]
    author_family: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    repository: Annotated[str, Field(min_length=1, max_length=256)]
    change_identity: Annotated[str, Field(min_length=1, max_length=128)]
    pr_reference: Annotated[str, Field(min_length=1, max_length=256)]
    routing_policy_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*@[1-9][0-9]*$")]
    reviewer_family_rule: Literal["different_from_author"]
    lenses: Annotated[tuple[Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")], ...], Field(min_length=1)]
    emitted_at: _Rfc3339DateTime
    consumption: ReviewDispatchConsumption | None
    verdict_ids: tuple[UUID, ...]
    status: Literal["emitted", "consumed", "verdict_linked"]


class SeatCredentialIssueRequest(_BoundaryModel):
    credential_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    credential_ref: Annotated[str, Field(min_length=1, max_length=512)]
    display_name: Annotated[str, Field(min_length=1, max_length=120)]
    project_key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")]
    scopes: Annotated[tuple[CredentialScope, ...], Field(min_length=1, max_length=3)]
    seat_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]


class SeatCredentialReceipt(_BoundaryModel):
    command_id: UUID
    credential_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=1)]
    principal_id: UUID
    project_key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")]
    scopes: Annotated[tuple[CredentialScope, ...], Field(min_length=1, max_length=3)]
    seat_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    state: Literal["active", "revoked"]


class SessionCloseFact(_BoundaryModel):
    evidence_ref: Annotated[str, Field(min_length=1, max_length=256)] | None
    input_tokens: Annotated[int, Field(ge=0, le=1000000000)]
    kind: Literal["close"]
    outcome: SessionOutcome
    output_tokens: Annotated[int, Field(ge=0, le=1000000000)]


class SessionClosedPayload(_BoundaryModel):
    duration_seconds: Annotated[int, Field(ge=0, le=31536000)]
    evidence_ref: Annotated[str, Field(min_length=1, max_length=256)] | None
    input_tokens: Annotated[int, Field(ge=0, le=1000000000)]
    outcome: SessionOutcome
    output_tokens: Annotated[int, Field(ge=0, le=1000000000)]
    session_id: UUID
    ticket_id: UUID


class SessionReceipt(_BoundaryModel):
    command_id: UUID
    durability_state: DurabilityState
    event_id: UUID
    session_id: UUID
    state: SessionState
    ticket_id: UUID


class SessionStartedAuditEvent(_BoundaryModel):
    actor_principal_id: UUID
    command_id: UUID
    event_hash: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    event_id: UUID
    kind: Literal["session.started"]
    occurred_at: _Rfc3339DateTime
    payload: SessionStartedPayload
    record_position: Annotated[int, Field(ge=1, le=9007199254740991)]
    sequence: Annotated[int, Field(ge=1, le=9007199254740991)]
    stream_id: Annotated[str, Field(pattern="^session:[0-9a-f-]{36}$")]


class SessionTransitionFact(_BoundaryModel):
    kind: Literal["transition"]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    to_state: SessionState


class SessionTransitionedPayload(_BoundaryModel):
    from_state: SessionState
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    session_id: UUID
    ticket_id: UUID
    to_state: SessionState
    transition_number: Annotated[int, Field(ge=1, le=9007199254740991)]


class SurfaceEnvironmentsField(_BoundaryModel):
    state: SurfaceDeclarationState
    environments: tuple[Annotated[str, Field(min_length=1)], ...]


class SurfaceIdentityField(_BoundaryModel):
    state: SurfaceDeclarationState
    identity: Annotated[str, Field(min_length=1, max_length=200)] | None


class SyntheticRunReceipt(_BoundaryModel):
    command_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    job_id: UUID
    run_id: UUID
    workflow_ref: Literal["ctower.trust-spine-four-stage@1"]


class SyntheticRunResource(_BoundaryModel):
    attempt_count: Annotated[int, Field(ge=0, le=8)]
    completed_at: _Rfc3339DateTime | None
    created_at: _Rfc3339DateTime
    detail_code: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{2,95}$")] | None
    job_id: UUID
    lifecycle_facts: Annotated[tuple[Literal["resolved", "closed"], ...], Field(max_length=2)]
    run_id: UUID
    state: SyntheticRunState
    ticket_id: UUID | None
    workflow_ref: Literal["ctower.trust-spine-four-stage@1"]


type TenantDisplayIdentity = TenantDisplayIdentityKnown | TenantDisplayIdentityUnknown


class TicketCommentAddedAuditEvent(_BoundaryModel):
    actor_principal_id: UUID
    command_id: UUID
    event_hash: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    event_id: UUID
    kind: Literal["ticket.comment_added"]
    occurred_at: _Rfc3339DateTime
    payload: TicketCommentAddedPayload
    record_position: Annotated[int, Field(ge=1, le=9007199254740991)]
    sequence: Annotated[int, Field(ge=1, le=9007199254740991)]
    stream_id: Annotated[str, Field(pattern="^ticket:[0-9a-f-]{36}$")]


class TicketCommentResult(_BoundaryModel):
    command_id: UUID
    comment_id: UUID
    durability_state: DurabilityState
    event_id: UUID
    ticket_id: UUID


class TicketCreateRequest(_BoundaryModel):
    initial_custodian_id: UUID | None = None
    priority: Priority
    project_key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")] | None = None
    source: SourceReference
    title: Annotated[str, Field(min_length=1, max_length=200)]


class TicketCreatedPayload(_BoundaryModel):
    custodian_id: UUID
    priority: Priority
    project_key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")] | None = None
    source_kind: Annotated[str, Field(min_length=1, max_length=64)]
    source_ref: Annotated[str, Field(min_length=1, max_length=256)]
    title: str


class TicketIntentRequest(_BoundaryModel):
    intent: AdmitIntent | DeferIntent | BlockIntent | UnblockIntent | ReopenIntent


class TicketResource(_BoundaryModel):
    created_at: _Rfc3339DateTime
    custodian_id: UUID
    durability_state: DurabilityState
    priority: Priority
    source: SourceReference
    ticket_id: UUID
    title: str
    version: Annotated[int, Field(ge=1, le=9007199254740991)]


class TicketSession(_BoundaryModel):
    branch_ref: Annotated[str, Field(min_length=1, max_length=256)]
    closed_at: _Rfc3339DateTime | None
    crew_name: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    duration_seconds: Annotated[int, Field(ge=0, le=31536000)] | None
    evidence_ref: Annotated[str, Field(min_length=1, max_length=256)] | None
    harness_ref: Annotated[str, Field(min_length=1, max_length=64)]
    model_ref: Annotated[str, Field(min_length=1, max_length=128)]
    outcome: SessionOutcome | None
    project_key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")]
    seat_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    session_id: UUID
    started_at: _Rfc3339DateTime
    state: SessionState
    ticket_id: UUID
    tokens: SessionTokenUsage | None
    transition_count: Annotated[int, Field(ge=0, le=9007199254740991)]
    worktree_ref: Annotated[str, Field(min_length=1, max_length=256)]


class VerdictRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    verdict_id: UUID
    criterion_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    candidate_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None = None
    decision: VerdictDecision


class WorkAdmittedAuditPayload(_BoundaryModel):
    data: AdmittedAuditData
    operation: Literal["admitted"]
    ticket_id: UUID
    work_version: Annotated[int, Field(ge=2, le=9007199254740991)]


class WorkAssignmentChangedAuditPayload(_BoundaryModel):
    data: AssignmentChangedAuditData
    operation: Literal["assignment_changed"]
    ticket_id: UUID
    work_version: Annotated[int, Field(ge=2, le=9007199254740991)]


class WorkBlockerOpenedAuditPayload(_BoundaryModel):
    data: BlockerOpenedAuditData
    operation: Literal["blocker_opened"]
    ticket_id: UUID
    work_version: Annotated[int, Field(ge=2, le=9007199254740991)]


class WorkBlockerResolvedAuditPayload(_BoundaryModel):
    data: BlockerResolvedAuditData
    operation: Literal["blocker_resolved"]
    ticket_id: UUID
    work_version: Annotated[int, Field(ge=2, le=9007199254740991)]


class WorkDeferredAuditPayload(_BoundaryModel):
    data: DeferredAuditData
    operation: Literal["deferred"]
    ticket_id: UUID
    work_version: Annotated[int, Field(ge=2, le=9007199254740991)]


class WorkReceipt(_BoundaryModel):
    command_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    operation: Literal[
        "priority_changed",
        "assignment_changed",
        "admitted",
        "deferred",
        "blocker_opened",
        "blocker_resolved",
        "reopened",
        "relation_added",
    ]
    ticket_id: UUID
    version: Annotated[int, Field(ge=2, le=9007199254740991)]


class WorkRelationAddedAuditPayload(_BoundaryModel):
    data: RelationAddedAuditData
    operation: Literal["relation_added"]
    ticket_id: UUID
    work_version: Annotated[int, Field(ge=2, le=9007199254740991)]


class WorkflowChangedAuditEvent(_BoundaryModel):
    actor_principal_id: UUID
    command_id: UUID
    event_hash: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    event_id: UUID
    kind: Literal["workflow.changed"]
    occurred_at: _Rfc3339DateTime
    payload: WorkflowChangedAuditPayload
    record_position: Annotated[int, Field(ge=1, le=9007199254740991)]
    sequence: Annotated[int, Field(ge=1, le=9007199254740991)]
    stream_id: Annotated[str, Field(pattern="^workflow:[0-9a-f-]{36}$")]


class WorkflowReceipt(_BoundaryModel):
    activity_class: ActivityClass
    command_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    lifecycle_facts: Annotated[tuple[Literal["resolved", "closed"], ...], Field(max_length=2)]
    stage: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    ticket_id: UUID
    version: Annotated[int, Field(ge=1, le=9007199254740991)]
    workflow_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*@[1-9][0-9]*$")]
    workflow_run_id: UUID


class AssignmentList(_BoundaryModel):
    assignments: tuple[AssignmentInterval, ...]
    ticket_id: UUID


class BundleAction(_BoundaryModel):
    component: ComponentReference
    kind: BundleActionKind


class CompanyBundleAssignment(_BoundaryModel):
    component: ComponentReference
    slot: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,63}$")]
    subject: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*:[a-z][a-z0-9._-]*$")]


class ComponentCompatibility(_BoundaryModel):
    ctower: Annotated[str, Field(min_length=1, max_length=80)]
    requires: Annotated[tuple[ComponentReference, ...], Field(max_length=128)]


class CtowerProjectImportCorrectionRequest(_BoundaryModel):
    schema_id: Literal["ctower.ctower-project-import-correction/v1"] = Field(
        alias="schema", serialization_alias="schema"
    )
    correction_id: UUID
    run_id: UUID
    cutover_id: UUID
    tenant_key: Literal["ctower"]
    project_key: Literal["ctower"]
    correction_kind: Literal["alias", "source_link", "relation"]
    superseded_revision: MigrationCorrectionRevision
    expected_current_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    replacement: MigrationCorrectionReplacement
    reason: Annotated[str, Field(min_length=1, max_length=1000)]
    reviewer_id: UUID


type CtowerProjectImportOperation = CtowerProjectTicketSeedOperation | CtowerProjectExactAliasOperation | CtowerProjectTicketRelationOperation | CtowerProjectSourceLinkOperation


class DeliverySurfaceAvailabilityQualifyingCheckpoint(_BoundaryModel):
    state: Literal["qualifying_checkpoint"]
    checkpoint_key: Annotated[str, Field(pattern="^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
    landing_boundary: SurfaceIdentityField
    non_production_environments: SurfaceEnvironmentsField
    externally_effective_outcome: SurfaceIdentityField


class DreamDispatchEffect(_BoundaryModel):
    effect_id: UUID
    occurrence_id: UUID
    routine_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*@[1-9][0-9]*$")]
    revision_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    scheduled_for: _Rfc3339DateTime
    scope: DreamDispatchScope
    skill_path: Literal["skills/dreamer/SKILL.md"]
    model_requirement: DreamModelRequirement
    emitted_at: _Rfc3339DateTime
    consumption: None | DreamDispatchConsumption


class HealthDimension(_BoundaryModel):
    status: HealthStatus
    contributors: Annotated[tuple[HealthContributor, ...], Field(min_length=1)]


class KnowledgeDocumentList(_BoundaryModel):
    documents: tuple[KnowledgeDocument, ...]
    project_key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")] | None
    scope: KnowledgeScope


class ProjectDeliveryAssignedSeatAssignment(_BoundaryModel):
    state: Literal["assigned"]
    seat: ProjectDeliverySeat


class ProjectDeliverySurfaceDeclaration(_BoundaryModel):
    landing_boundary: SurfaceIdentityField
    non_production_environments: SurfaceEnvironmentsField
    externally_effective_outcome: SurfaceIdentityField


class ProjectSessionPage(_BoundaryModel):
    next_cursor: Annotated[int, Field(ge=1, le=9007199254740991)] | None
    project_key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")]
    sessions: tuple[TicketSession, ...]


class RequestList(_BoundaryModel):
    answered_project_count: Annotated[int, Field(ge=0, le=9007199254740991)]
    answered_projects: tuple[Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")], ...]
    observed_at: _Rfc3339DateTime
    requested_project_count: Annotated[int, Field(ge=0, le=9007199254740991)]
    requested_projects: tuple[Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")], ...]
    rows: tuple[RequestRow, ...]
    unanswered_projects: tuple[Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")], ...]
    watermark: Annotated[int, Field(ge=0, le=9007199254740991)]


class ReviewDispatchEffectList(_BoundaryModel):
    ticket_id: UUID
    effects: tuple[ReviewDispatchEffect, ...]


class SessionClosedAuditEvent(_BoundaryModel):
    actor_principal_id: UUID
    command_id: UUID
    event_hash: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    event_id: UUID
    kind: Literal["session.closed"]
    occurred_at: _Rfc3339DateTime
    payload: SessionClosedPayload
    record_position: Annotated[int, Field(ge=1, le=9007199254740991)]
    sequence: Annotated[int, Field(ge=1, le=9007199254740991)]
    stream_id: Annotated[str, Field(pattern="^session:[0-9a-f-]{36}$")]


class SessionFactRequest(_BoundaryModel):
    fact: SessionTransitionFact | SessionCloseFact


class SessionTransitionedAuditEvent(_BoundaryModel):
    actor_principal_id: UUID
    command_id: UUID
    event_hash: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    event_id: UUID
    kind: Literal["session.transitioned"]
    occurred_at: _Rfc3339DateTime
    payload: SessionTransitionedPayload
    record_position: Annotated[int, Field(ge=1, le=9007199254740991)]
    sequence: Annotated[int, Field(ge=1, le=9007199254740991)]
    stream_id: Annotated[str, Field(pattern="^session:[0-9a-f-]{36}$")]


class TicketCommandResult(_BoundaryModel):
    command_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    ticket: TicketResource


class TicketCreatedAuditEvent(_BoundaryModel):
    actor_principal_id: UUID
    command_id: UUID
    event_hash: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    event_id: UUID
    kind: Literal["ticket.created"]
    occurred_at: _Rfc3339DateTime
    payload: TicketCreatedPayload
    record_position: Annotated[int, Field(ge=1, le=9007199254740991)]
    sequence: Annotated[int, Field(ge=1, le=9007199254740991)]
    stream_id: Annotated[str, Field(pattern="^ticket:[0-9a-f-]{36}$")]


class TicketSessionList(_BoundaryModel):
    sessions: tuple[TicketSession, ...]
    ticket_id: UUID


class TimelineEvent(_BoundaryModel):
    actor_principal_id: UUID
    command_id: UUID
    event_id: UUID
    kind: Literal["ticket.created", "ticket.custody_transferred", "ticket.comment_added"]
    occurred_at: _Rfc3339DateTime
    payload: TicketCreatedPayload | CustodyTransferredPayload | TicketCommentAddedPayload
    sequence: Annotated[int, Field(ge=1, le=9007199254740991)]


class WorkPriorityChangedAuditPayload(_BoundaryModel):
    data: PriorityChangedAuditData
    operation: Literal["priority_changed"]
    ticket_id: UUID
    work_version: Annotated[int, Field(ge=2, le=9007199254740991)]


class WorkReopenedAuditPayload(_BoundaryModel):
    data: ReopenedAuditData
    operation: Literal["reopened"]
    ticket_id: UUID
    work_version: Annotated[int, Field(ge=2, le=9007199254740991)]


class CompanyBundlePlan(_BoundaryModel):
    actions: tuple[BundleAction, ...]
    base_bundle_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    base_version: Annotated[int, Field(ge=0, le=9007199254740991)]
    checks: tuple[BundleCheck, ...]
    plan_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    proposed_bundle_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    warnings: tuple[Annotated[str, Field(max_length=500)], ...]


class ControlHealth(_BoundaryModel):
    schema_id: Literal["ctower.health/v1"]
    status: HealthStatus
    observed_at: _Rfc3339DateTime
    availability: HealthDimension
    completeness: HealthDimension
    integrity: HealthDimension


class CtowerProjectImportBatchRequest(_BoundaryModel):
    schema_id: Literal["ctower.ctower-project-import-batch/v1"] = Field(
        alias="schema", serialization_alias="schema"
    )
    run_id: UUID
    cutover_id: UUID
    batch_index: Annotated[int, Field(ge=0, le=9007199254740991)]
    batch_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    operations: Annotated[tuple[CtowerProjectImportOperation, ...], Field(min_length=1, max_length=64)]


type DeliverySurfaceAvailability = DeliverySurfaceAvailabilityNoQualifyingCheckpoint | DeliverySurfaceAvailabilityQualifyingCheckpoint


class DreamDispatchEffectList(_BoundaryModel):
    effects: tuple[DreamDispatchEffect, ...]


type ProjectDeliverySeatAssignment = ProjectDeliveryAssignedSeatAssignment | ProjectDeliveryUnassignedSeatAssignment


class TimelineResponse(_BoundaryModel):
    durability_state: DurabilityState
    events: tuple[TimelineEvent, ...]
    ticket_id: UUID


class VersionedComponent(_BoundaryModel):
    compatibility: ComponentCompatibility
    content_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    key: Annotated[str, Field(pattern="^[a-z][a-z0-9.-]{2,127}$")]
    kind: ComponentKind
    lifecycle: Literal["draft", "published", "deprecated", "revoked"]
    payload_ref: Annotated[str, Field(pattern="^object:sha256:[0-9a-f]{64}$")]
    provenance: Annotated[tuple[ComponentProvenance, ...], Field(min_length=1, max_length=64)]
    revision: Annotated[int, Field(ge=1, le=9007199254740991)]
    schema_id: Literal["ctower.versioned-component/v1"] = Field(
        alias="schema", serialization_alias="schema"
    )
    schema_ref: Annotated[str, Field(pattern="^ctower\\.[a-z][a-z0-9.-]*/v[1-9][0-9]*$")]
    scope: ComponentScope
    supersedes: ComponentReference | None = None


type WorkChangedAuditPayload = WorkPriorityChangedAuditPayload | WorkAssignmentChangedAuditPayload | WorkAdmittedAuditPayload | WorkDeferredAuditPayload | WorkBlockerOpenedAuditPayload | WorkBlockerResolvedAuditPayload | WorkReopenedAuditPayload | WorkRelationAddedAuditPayload


class BoardCard(_BoundaryModel):
    activity_class: Literal["work", "verification", "None"] | None
    applied_labels: tuple[AppliedLabel, ...]
    assignee_id: UUID | None
    blocker_opened_at: _Rfc3339DateTime | None
    blocker_reason: str | None
    change_references: tuple[ChangeReference, ...]
    custodian_id: UUID
    delivery_facts: tuple[str, ...]
    delivery_surface_availability: DeliverySurfaceAvailability
    human_waiting: HumanWaiting
    inbox_thread_ids: tuple[UUID, ...]
    lane: BoardLane
    priority: Priority
    project_key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")]
    risk: str | None
    stage_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")] | None
    stage_label: str | None
    tenant_display_identity: TenantDisplayIdentity
    ticket_id: UUID
    title: str
    underlying_lane: Literal["backlog", "ready", "in_progress", "in_review", "complete", "None"] | None
    version: Annotated[int, Field(ge=1, le=9007199254740991)]


class CompanyBundleResource(_BoundaryModel):
    component: VersionedComponent
    payload: _FreeFormJsonObject


class ProjectDeliverySlot(_BoundaryModel):
    slot_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    state: Literal["filled", "unfilled", "unknown"]
    assigned_seat: ProjectDeliverySeatAssignment
    signing_seat: ProjectDeliverySeat | None


class WorkChangedAuditEvent(_BoundaryModel):
    actor_principal_id: UUID
    command_id: UUID
    event_hash: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    event_id: UUID
    kind: Literal["work.changed"]
    occurred_at: _Rfc3339DateTime
    payload: WorkChangedAuditPayload
    record_position: Annotated[int, Field(ge=1, le=9007199254740991)]
    sequence: Annotated[int, Field(ge=1, le=9007199254740991)]
    stream_id: Annotated[str, Field(pattern="^ticket:[0-9a-f-]{36}$")]


type AuditEvent = TicketCreatedAuditEvent | CustodyTransferredAuditEvent | TicketCommentAddedAuditEvent | WorkChangedAuditEvent | WorkflowChangedAuditEvent | ProofChangedAuditEvent | SessionStartedAuditEvent | SessionTransitionedAuditEvent | SessionClosedAuditEvent


class BoardView(_BoundaryModel):
    cards: tuple[BoardCard, ...]
    health: ProjectionHealth
    projection_watermark: Annotated[int, Field(ge=0, le=9007199254740991)]
    source_watermark: Annotated[int, Field(ge=0, le=9007199254740991)]


class CompanyBundleDocument(_BoundaryModel):
    assignments: Annotated[tuple[CompanyBundleAssignment, ...], Field(max_length=512)]
    company: CompanyIdentity
    resources: Annotated[tuple[CompanyBundleResource, ...], Field(min_length=1, max_length=512)]
    schema_id: Literal["ctower.company-bundle/v1"] = Field(
        alias="schema", serialization_alias="schema"
    )
    secret_binding_refs: Annotated[tuple[SecretBindingReference, ...], Field(max_length=128)]


class ProjectDeliveryRow(_BoundaryModel):
    checkpoint_key: Annotated[str, Field(pattern="^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
    checkpoint_label: Annotated[str, Field(min_length=1)]
    headline_state: Literal[
        "planned",
        "in_progress",
        "ready_to_land",
        "merged",
        "verified",
        "released",
        "blocked",
        "done",
    ]
    underlying_maturity: Literal["planned", "in_progress", "ready_to_land", "merged", "verified", "released"]
    outcome: Annotated[str, Field(min_length=1)]
    accountable_owner: Annotated[str, Field(min_length=1)]
    criteria: ProjectDeliveryCriteria
    delivery_surface: ProjectDeliverySurfaceDeclaration
    qualifying_stage_slots_filled: Annotated[int, Field(ge=0, le=9007199254740991)]
    qualifying_stage_slots_required: Annotated[int, Field(ge=0, le=9007199254740991)]
    qualifying_stage_unfilled_or_unknown_slot_keys: tuple[Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")], ...]
    qualifying_stage_slots: tuple[ProjectDeliverySlot, ...]
    source_watermark: Annotated[int, Field(ge=0, le=9007199254740991)]
    projection_watermark: Annotated[int, Field(ge=0, le=9007199254740991)]
    freshness: Literal["fresh", "stale", "STATE_UNKNOWN"]
    confidence: Literal["development_degraded", "disaster_safe", "STATE_UNKNOWN"]
    health: Literal["CP3_D_NOT_PROVEN", "CURRENT", "STATE_UNKNOWN"]
    durability: Literal["CP3_D_NOT_PROVEN", "CP3_D_PROVEN", "STATE_UNKNOWN"]
    recovery: Literal[
        "EXTERNAL_FAILURE_DOMAIN_UNPROVEN",
        "EXTERNAL_FAILURE_DOMAIN_PROVEN",
        "STATE_UNKNOWN",
    ]
    data_class: Literal["RECONSTRUCTIBLE_ONLY", "DISASTER_SAFE_CTOWER_ENGINEERING", "STATE_UNKNOWN"]
    semantic_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    reconciled_at: _Rfc3339DateTime
    freshness_due_at: _Rfc3339DateTime
    rebuild_generation: Annotated[int, Field(ge=0, le=9007199254740991)]
    source_ids: tuple[Annotated[str, Field(min_length=1)], ...]
    derivation_reasons: Annotated[tuple[Annotated[str, Field(min_length=1)], ...], Field(min_length=1)]


type ProjectEvent = TicketCreatedAuditEvent | CustodyTransferredAuditEvent | TicketCommentAddedAuditEvent | WorkChangedAuditEvent | WorkflowChangedAuditEvent | ProofChangedAuditEvent


class AuditPage(_BoundaryModel):
    events: tuple[AuditEvent, ...]
    next_cursor: Annotated[int, Field(ge=1, le=9007199254740991)] | None
    ticket_id: UUID


class CompanyBundleApplyRequest(_BoundaryModel):
    bundle: CompanyBundleDocument
    expected_active_version: Annotated[int, Field(ge=0, le=9007199254740991)]
    plan_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class CompanyBundleExportResult(_BoundaryModel):
    active_version: Annotated[int, Field(ge=1, le=9007199254740991)]
    bundle: CompanyBundleDocument
    bundle_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    metadata: CompanyBundleExportMetadata


class CompanyBundleRequest(_BoundaryModel):
    bundle: CompanyBundleDocument


class ProjectDeliveryView(_BoundaryModel):
    schema_id: Literal["ctower.project-delivery/v1"] = Field(
        alias="schema", serialization_alias="schema"
    )
    company_key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")]
    project_key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")]
    source_record_position: Annotated[int, Field(ge=0, le=9007199254740991)]
    projection_record_position: Annotated[int, Field(ge=0, le=9007199254740991)]
    reconciled_at: _Rfc3339DateTime
    freshness_due_at: _Rfc3339DateTime
    projection_semantic_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    rebuild_generation: Annotated[int, Field(ge=0, le=9007199254740991)]
    rows: tuple[ProjectDeliveryRow, ...]


class ProjectEventPage(_BoundaryModel):
    events: tuple[ProjectEvent, ...]
    next_cursor: Annotated[int, Field(ge=1, le=9007199254740991)] | None
    project_key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")]
