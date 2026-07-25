"""Focused typed payloads for canonical tenant Catalog-stream events."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

__all__ = [
    "CatalogBundleActivatedPayload",
    "CatalogComponentPublishedPayload",
    "CatalogComponentReference",
    "CatalogEventPayload",
]

_COMPONENT_KEY = re.compile(r"^[a-z][a-z0-9.-]{2,127}$")
_COMPONENT_KIND = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_PAYLOAD_REF = re.compile(r"^object:sha256:[0-9a-f]{64}$")
_MAX_OBJECT_VERSION_LENGTH = 256


@dataclass(frozen=True, slots=True)
class CatalogComponentReference:
    content_digest: str
    key: str
    kind: str
    revision: int

    def __post_init__(self) -> None:
        _matches("component content digest", self.content_digest, _DIGEST)
        _matches("component key", self.key, _COMPONENT_KEY)
        _matches("component kind", self.kind, _COMPONENT_KIND)
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("component revision must be a positive integer")

    def to_mapping(self) -> dict[str, object]:
        return {
            "content_digest": self.content_digest,
            "key": self.key,
            "kind": self.kind,
            "revision": self.revision,
        }


@dataclass(frozen=True, slots=True)
class CatalogComponentPublishedPayload:
    component: CatalogComponentReference
    object_version: str
    payload_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.component, CatalogComponentReference):
            raise TypeError("component must be a CatalogComponentReference")
        if (
            not isinstance(self.object_version, str)
            or not 1 <= len(self.object_version) <= _MAX_OBJECT_VERSION_LENGTH
        ):
            raise ValueError("object version is outside the authored event contract")
        _matches("payload reference", self.payload_ref, _PAYLOAD_REF)
        if self.payload_ref.removeprefix("object:") != self.component.content_digest:
            raise ValueError("payload reference and component digest must match")

    def to_mapping(self) -> dict[str, object]:
        return {
            "component": self.component.to_mapping(),
            "object_version": self.object_version,
            "payload_ref": self.payload_ref,
        }


@dataclass(frozen=True, slots=True)
class CatalogBundleActivatedPayload:
    active_version: int
    bundle_digest: str
    member_event_ids: tuple[UUID, ...]
    plan_digest: str

    def __post_init__(self) -> None:
        if type(self.active_version) is not int or self.active_version < 1:
            raise ValueError("active bundle version must be a positive integer")
        _matches("bundle digest", self.bundle_digest, _DIGEST)
        _matches("plan digest", self.plan_digest, _DIGEST)
        if (
            not isinstance(self.member_event_ids, tuple)
            or not self.member_event_ids
            or not all(isinstance(item, UUID) for item in self.member_event_ids)
        ):
            raise TypeError("member event IDs must be a non-empty UUID tuple")
        if len(set(self.member_event_ids)) != len(self.member_event_ids):
            raise ValueError("member event IDs must be unique")

    def to_mapping(self) -> dict[str, object]:
        return {
            "active_version": self.active_version,
            "bundle_digest": self.bundle_digest,
            "member_event_ids": [str(item) for item in self.member_event_ids],
            "plan_digest": self.plan_digest,
        }


type CatalogEventPayload = CatalogComponentPublishedPayload | CatalogBundleActivatedPayload


def _matches(label: str, value: object, pattern: re.Pattern[str]) -> None:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ValueError(f"{label} is outside the authored event contract")
