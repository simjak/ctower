"""One synthetic checkpoint definition shared by source and Catalog fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import rfc8785

from ctower_kernel.migration import _checkpoint_expectation_sql

_ROOT = Path(__file__).parents[3]


def checkpoint_keys() -> tuple[str, ...]:
    """Read the authored checkpoint set; never restate its size as a literal."""

    return tuple(cast(list[str], _vectors()["checkpoint_keys"]))


def _vectors() -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(
            (_ROOT / "contracts/domain/project-delivery/project-delivery-vectors.json").read_text(
                encoding="utf-8"
            )
        ),
    )


def checkpoint_resource(
    checkpoint_key: str,
    *,
    outcome: str | None = None,
) -> dict[str, Any]:
    vectors = _vectors()
    configured_criteria = cast(
        dict[str, list[str]],
        vectors["configured_checkpoint_criteria"],
    )
    criterion_keys = configured_criteria[checkpoint_key]
    key = checkpoint_key.casefold().replace(".", "-")
    payload: dict[str, Any] = {
        "schema": "ctower.checkpoint/v1",
        "key": f"ctower.{key}",
        "checkpoint_key": checkpoint_key,
        "display_name": f"ctower checkpoint {checkpoint_key}",
        "outcome": outcome or f"ctower establishes the declared {checkpoint_key} outcome",
        "accountable_owner": "ctower-operator",
        "criteria": [
            {
                "key": criterion,
                "description": f"Current proof for {criterion}",
                "required": True,
                "evidence_policy_refs": [],
            }
            for criterion in criterion_keys
        ],
        "dependency_refs": [],
    }
    digest = f"sha256:{hashlib.sha256(rfc8785.dumps(payload)).hexdigest()}"
    return {
        "component": {
            "schema": "ctower.versioned-component/v1",
            "kind": "checkpoint",
            "key": f"ctower.{key}",
            "scope": {"tenant": "ctower", "project": "ctower"},
            "revision": 1,
            "content_digest": digest,
            "schema_ref": "ctower.checkpoint/v1",
            "lifecycle": "published",
            "compatibility": {"ctower": ">=0.0.0,<1.0.0", "requires": []},
            "provenance": [
                {
                    "kind": "reviewed-contract",
                    "source": "SPEC#project-delivery-projection",
                    "digest": digest,
                }
            ],
            "payload_ref": f"object:{digest}",
        },
        "payload": payload,
    }


def checkpoint_identity(checkpoint_key: str) -> dict[str, str]:
    """Identity for `checkpoint_key`, with `criteria_digest` produced by the real kernel hash.

    `criteria_digest` calls `_checkpoint_expectation_sql._criteria_digest` — the exact function
    the server compares against at reconciliation — rather than a fixture-local reimplementation
    of its material shape and hash, so a drift in the kernel's digest definition shows up here too.
    """
    resource = checkpoint_resource(checkpoint_key)
    component = cast(dict[str, Any], resource["component"])
    payload = cast(dict[str, Any], resource["payload"])
    criteria = cast(list[dict[str, Any]], payload["criteria"])
    rows: list[dict[str, object]] = [
        {
            "ordinal": ordinal,
            "criterion_key": criterion["key"],
            "description": criterion["description"],
            "proof_ticket_id": None,
            "proof_criterion_key": None,
            "source_ids": criterion["evidence_policy_refs"],
        }
        for ordinal, criterion in enumerate(criteria, start=1)
    ]
    return {
        "catalog_revision": f"{component['key']}@{component['revision']}",
        "definition_digest": str(component["content_digest"]),
        "criteria_digest": _checkpoint_expectation_sql._criteria_digest(rows),
    }
