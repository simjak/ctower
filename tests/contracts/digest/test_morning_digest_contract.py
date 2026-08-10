"""Authored boundary rules for the native morning digest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

ROOT = Path(__file__).parents[3]
__all__: tuple[str, ...] = ()


def test_morning_digest_is_one_strict_read_only_generated_surface() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    paths = cast(dict[str, dict[str, dict[str, object]]], document["paths"])
    operation = paths["/v1/digests/morning"]["get"]
    schemas = cast(dict[str, dict[str, object]], document["components"]["schemas"])
    artifact = schemas["MorningDigest"]
    choice = cast(dict[str, dict[str, object]], schemas["DigestDecisionChoice"]["properties"])

    assert operation["operationId"] == "getMorningDigest"
    assert operation["x-ctower-cli"] == "digest morning"
    assert operation["x-ctower-mutation"] is False
    assert operation["x-ctower-spool"] == "forbidden"
    assert set(cast(dict[str, object], artifact["properties"])) == {
        "artifact_key",
        "artifact_sha256",
        "digest_date",
        "observed_at",
        "open_decisions",
        "proof",
        "request_watermark",
        "ruling_watermark",
        "state",
        "timezone",
        "yesterday_rulings",
    }
    assert artifact["additionalProperties"] is False
    assert choice["completeness"] == {"type": "integer", "minimum": 0, "maximum": 10}


def test_every_digest_section_distinguishes_unknown_total_from_measured_zero() -> None:
    document = json.loads((ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    schemas = cast(dict[str, dict[str, object]], document["components"]["schemas"])

    for name in (
        "MorningDigestDecisionSection",
        "MorningDigestRulingSection",
        "MorningDigestProofSection",
    ):
        properties = cast(dict[str, dict[str, object]], schemas[name]["properties"])
        assert properties["total_count"]["type"] == ["integer", "null"]
        assert properties["unreached"]["items"] == {
            "$ref": "#/components/schemas/DigestUnreachedScope"
        }
