"""Native agent-to-agent inbox aggregate."""

from ctower_kernel.inbox.interface import Inbox
from ctower_kernel.inbox.models import (
    InboxAcknowledgeCommand,
    InboxAcknowledgementState,
    InboxAcknowledgeResult,
    InboxPromotionCommand,
    InboxPromotionOutcome,
    InboxPromotionResult,
    InboxSendCommand,
    InboxSendResult,
    InboxSeverity,
)
from ctower_kernel.inbox.postgres import PostgresInbox

__all__ = [
    "Inbox",
    "InboxAcknowledgeCommand",
    "InboxAcknowledgeResult",
    "InboxAcknowledgementState",
    "InboxPromotionCommand",
    "InboxPromotionOutcome",
    "InboxPromotionResult",
    "InboxSendCommand",
    "InboxSendResult",
    "InboxSeverity",
    "PostgresInbox",
]
