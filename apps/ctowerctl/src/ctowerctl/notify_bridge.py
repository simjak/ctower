"""Additive mission-control notification transport over the generated ctower client."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from ctower_client import CtowerProblemError, InboxNotificationRequest, InboxSendResult

__all__ = [
    "DualRailNotifyBridge",
    "Notification",
    "NotificationDelivery",
    "NotificationMirrorState",
]


class _NotificationClient(Protocol):
    def ingest_inbox_notification(
        self,
        request: InboxNotificationRequest,
        *,
        command_id: UUID,
    ) -> InboxSendResult: ...


class NotificationMirrorState(StrEnum):
    MIRRORED = "mirrored"
    REFUSED = "refused"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class Notification:
    """Strict rail-2 payload; sender identity comes only from the authenticated client."""

    delivery_id: UUID
    to: str
    text: str


@dataclass(frozen=True, slots=True)
class NotificationDelivery:
    rail1_delivered: bool
    mirror_state: NotificationMirrorState
    ctower_result: InboxSendResult | None = None
    refusal_code: str | None = None


class DualRailNotifyBridge:
    """Deliver rail 1 first and make every ctower outcome non-blocking and explicit."""

    def __init__(self, client: _NotificationClient) -> None:
        self._client = client

    def deliver(
        self,
        notification: Notification,
        *,
        deliver_rail1: Callable[[], None],
    ) -> NotificationDelivery:
        deliver_rail1()
        return self._mirror(notification, rail1_delivered=True)

    def redeliver(self, notification: Notification) -> NotificationDelivery:
        """Retry only rail 2 with the original stable delivery identity."""

        return self._mirror(notification, rail1_delivered=False)

    def _mirror(
        self,
        notification: Notification,
        *,
        rail1_delivered: bool,
    ) -> NotificationDelivery:
        try:
            request = InboxNotificationRequest(to=notification.to, text=notification.text)
            result = self._client.ingest_inbox_notification(
                request,
                command_id=notification.delivery_id,
            )
        except CtowerProblemError as error:
            return NotificationDelivery(
                rail1_delivered=rail1_delivered,
                mirror_state=NotificationMirrorState.REFUSED,
                refusal_code=error.problem.code,
            )
        except Exception:  # noqa: BLE001 - rail 2 cannot turn a delivered rail 1 into failure
            return NotificationDelivery(
                rail1_delivered=rail1_delivered,
                mirror_state=NotificationMirrorState.UNAVAILABLE,
                refusal_code="notification-bridge-unavailable",
            )
        return NotificationDelivery(
            rail1_delivered=rail1_delivered,
            mirror_state=NotificationMirrorState.MIRRORED,
            ctower_result=result,
        )
