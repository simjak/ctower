"""Exact scalar-profile and intake boundaries in the public HTTP contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

_ROOT = Path(__file__).parents[3]


def test_scalar_profiles_are_exact_root_contracts() -> None:
    document = json.loads((_ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    expected = {
        "x-ctower-free-form-json-profile": {
            "containers": "recursive-arrays-and-objects",
            "duplicate-object-members": "last-member-wins",
            "fraction-exponent-negative-zero": "preserve-sign",
            "fraction-exponent-semantics": "finite-ieee-754-binary64",
            "integer-lexemes": "x-ctower-json-integer-profile",
            "nonfinite": "rejected",
            "overflow": "rejected",
            "trust": "opaque-until-component-schema-validation",
            "underflow": "preserve-binary64-signed-zero",
        },
        "x-ctower-json-integer-profile": {
            "maximum": 9_007_199_254_740_991,
            "minimum": -9_007_199_254_740_991,
            "negative-zero": "normalize-to-zero",
            "semantics": "exact-integer-interoperability",
            "token-syntax": "minus-zero-or-nonzero-decimal-digits-only",
        },
        "x-ctower-absolute-uri-profile": {
            "characters": "ascii-rfc3986",
            "fragment": "allowed",
            "grammar": "rfc3986-uri-with-required-scheme",
            "http-authority": "required-with-nonempty-host",
            "normalization": "none-return-original",
            "percent-encoding": "complete-two-hex-digit-triplets",
            "raw-backslash": "rejected",
            "raw-whitespace-controls": "rejected",
        },
    }

    assert {key: document[key] for key in expected} == expected
    nested = json.dumps({key: value for key, value in document.items() if key not in expected})
    assert all(key not in nested for key in expected)


def test_intake_contract_is_explicit_and_has_no_classifier_or_dispatch_surface() -> None:
    document = json.loads((_ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    paths = cast(dict[str, object], document["paths"])
    schemas = cast(dict[str, object], document["components"]["schemas"])
    intake = {
        "paths": {key: value for key, value in paths.items() if key.startswith("/v1/intake")},
        "schemas": {key: value for key, value in schemas.items() if key.startswith("Intake")},
    }
    rendered = json.dumps(intake, sort_keys=True).casefold()

    assert '"default": "discussion"' in rendered
    for forbidden in ("classifier", "fuzzy", "commander override", "agent dispatch"):
        assert forbidden not in rendered


def test_problem_boundary_objects_are_strict() -> None:
    document = json.loads((_ROOT / "contracts/http/openapi.yaml").read_text(encoding="utf-8"))
    schemas = cast(dict[str, dict[str, object]], document["components"]["schemas"])
    for name, schema in schemas.items():
        if schema.get("type") == "object":
            assert schema.get("additionalProperties") is False, name
