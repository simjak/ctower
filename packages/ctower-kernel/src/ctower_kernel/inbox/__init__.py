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
    "PostgresInbox",
]
