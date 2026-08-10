"""Deterministic operator-text evidence for the morning digest."""

from __future__ import annotations

import json

from ctower_client.models import MorningDigest
from ctowerctl._digest_commands import morning_text

__all__: tuple[str, ...] = ()


def test_partial_digest_text_never_turns_unreached_sources_into_zero() -> None:
    digest = MorningDigest.model_validate_json(
        json.dumps(
            {
                "artifact_key": "morning-digest:2026-08-10:Europe/Vilnius",
                "artifact_sha256": f"sha256:{'a' * 64}",
                "digest_date": "2026-08-10",
                "observed_at": "2026-08-10T05:00:00+00:00",
                "open_decisions": {
                    "items": [],
                    "state": "unknown",
                    "total_count": None,
                    "unreached": [{"key": "requests", "reason": "request-source-unavailable"}],
                    "visible_count": 0,
                },
                "proof": {
                    "items": [],
                    "state": "unknown",
                    "total_count": None,
                    "unreached": [{"key": "requests", "reason": "request-source-unavailable"}],
                    "visible_count": 0,
                },
                "request_watermark": None,
                "ruling_watermark": 12,
                "state": "partial",
                "timezone": "Europe/Vilnius",
                "yesterday_rulings": {
                    "items": [],
                    "state": "complete",
                    "total_count": 0,
                    "unreached": [],
                    "visible_count": 0,
                },
            }
        )
    )

    rendered = morning_text(digest)

    assert "Open decisions — UNKNOWN total; 0 visible; UNKNOWN" in rendered
    assert "Unreached: requests (request-source-unavailable)" in rendered
    assert "Yesterday's rulings — 0; COMPLETE" in rendered
    assert "Proof — UNKNOWN total; 0 visible; UNKNOWN" in rendered
    assert "Open decisions — 0" not in rendered
    assert rendered.endswith(f"SHA-256: sha256:{'a' * 64}")
