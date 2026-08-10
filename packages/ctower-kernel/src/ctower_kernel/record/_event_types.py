"""Closed canonical event kind and origin vocabularies."""

from __future__ import annotations

from enum import StrEnum

__all__ = ["EventKind", "EventOrigin"]


class EventKind(StrEnum):
    BOOTSTRAP_CREATED = "bootstrap.first_tenant_created"
    TICKET_CREATED = "ticket.created"
    CUSTODY_TRANSFERRED = "ticket.custody_transferred"
    TICKET_COMMENT_ADDED = "ticket.comment_added"
    CATALOG_COMPONENT_PUBLISHED = "catalog.component_published"
    CATALOG_BUNDLE_ACTIVATED = "catalog.bundle_activated"
    PROOF_CHANGED = "proof.changed"
    WORKFLOW_CHANGED = "workflow.changed"
    WORK_CHANGED = "work.changed"
    ROUTINE_OCCURRENCE_RECORDED = "routine.occurrence_recorded"
    DREAM_DISPATCH_CONSUMED = "runtime.dream_dispatch_consumed"
    DREAM_LANE_BOUND = "runtime.dream_lane_bound"
    POISON_DISPOSITION_RECORDED = "attention.poison_disposition_recorded"
    MIGRATION_CHANGED = "migration.changed"
    INBOUND_EVENT_RECORDED = "intake.inbound_event_recorded"
    INBOUND_EVENT_PROMOTED = "intake.inbound_event_promoted"
    INBOX_THREAD_OPENED = "thread.opened"
    INBOX_MESSAGE_APPENDED = "message.appended"
    INBOX_MESSAGE_DELIVERED = "message.delivered"
    INBOX_MESSAGE_READ = "message.read"
    INBOX_THREAD_PROMOTED_TO_TICKET = "thread.promoted_to_ticket"
    SEAT_CREDENTIAL_ISSUED = "access.seat_credential_issued"
    SEAT_CREDENTIAL_REVOKED = "access.seat_credential_revoked"
    SESSION_STARTED = "session.started"
    SESSION_TRANSITIONED = "session.transitioned"
    SESSION_CLOSED = "session.closed"
    CHANGE_REFERENCE_RECORDED = "ticket.change_reference_recorded"
    LABEL_APPLIED = "ticket.label_applied"
    ATTENTION_FINDING_APPENDED = "attention.finding_appended"
    ATTENTION_FINDING_DISPOSITION_RECORDED = "attention.finding_disposition_recorded"
    KNOWLEDGE_DOCUMENT_REGISTERED = "knowledge.document_registered"
    REQUEST_CHANGED = "request.changed"
    RULING_RECORDED = "ruling.recorded"


class EventOrigin(StrEnum):
    API = "api"
    BOOTSTRAP = "bootstrap"
    CONTROL_WORKER = "control_worker"
    MIGRATION_IMPORTER = "migration_importer"
