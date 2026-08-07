"""Native agent-to-agent inbox aggregate."""

from ctower_kernel.inbox.interface import Inbox
from ctower_kernel.inbox.models import (
    InboxPromotionCommand,
    InboxPromotionResult,
    InboxSendCommand,
    InboxSendResult,
)
from ctower_kernel.inbox.postgres import PostgresInbox

__all__ = [
    "Inbox",
    "InboxPromotionCommand",
    "InboxPromotionResult",
    "InboxSendCommand",
    "InboxSendResult",
    "PostgresInbox",
]
