"""Deep Access Module for trust-root authentication and authorization."""

from __future__ import annotations

import hashlib
import ipaddress
import json
from collections.abc import Callable
from datetime import UTC, datetime

from ctower_kernel.record import Actor, BootstrapCommand, BootstrapReceipt, Record, RecordProblem

__all__ = ["Access", "digest_capability"]


class Access:
    """Authenticate bootstrap transport authority before invoking Record."""

    def __init__(
        self,
        record: Record,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._record = record
        self._clock = clock or (lambda: datetime.now(UTC))

    def bootstrap_first_tenant(
        self,
        command: BootstrapCommand,
        *,
        capability: str,
        origin: str,
    ) -> BootstrapReceipt | RecordProblem:
        """Refuse non-loopback origins and pass only digests into Record."""

        if not _is_loopback(origin):
            return RecordProblem(
                code="bootstrap-origin",
                detail="The first-tenant route accepts only its configured local origin.",
                status=403,
                title="Bootstrap origin refused",
                command_id=command.client_command_id,
            )
        request_digest = hashlib.sha256(_canonical_json(command.request_payload())).digest()
        return self._record.bootstrap_first_tenant(
            command,
            capability_digest=digest_capability(capability),
            request_digest=request_digest,
            origin=origin,
            now=self._clock(),
        )

    def authenticate(self, authorization: str | None) -> Actor | RecordProblem:
        """Resolve one opaque bearer credential without retaining plaintext."""

        prefix = "Bearer "
        if authorization is None or not authorization.startswith(prefix):
            return _unauthorized()
        credential = authorization.removeprefix(prefix)
        if not credential or credential.strip() != credential:
            return _unauthorized()
        actor = self._record.actor_for_credential(hashlib.sha256(credential.encode()).digest())
        return actor if actor is not None else _unauthorized()


def digest_capability(capability: str) -> bytes:
    """Reduce plaintext bootstrap authority to its one-way Record representation."""

    return hashlib.sha256(capability.encode()).digest()


def _is_loopback(origin: str) -> bool:
    try:
        return ipaddress.ip_address(origin).is_loopback
    except ValueError:
        return False


def _canonical_json(payload: dict[str, str]) -> bytes:
    """Encode the string-only bootstrap contract in RFC 8785 canonical order."""

    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _unauthorized() -> RecordProblem:
    return RecordProblem(
        code="unauthorized",
        detail="A valid tenant credential is required.",
        status=401,
        title="Authentication refused",
    )
