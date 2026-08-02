"""Evidence-manifest typed denominator contract vectors.

The denominator is derived from the capability registry (packs/components/capabilities/)
and the expected-suite registry (tools/checks/expected-suites.toml deferred suites),
never a hand-copied roster.  Adding a registry entry WITHOUT a manifest disposition
fails by name.

The registry derivation and manifest verification are delegated to the
repository-owned generator in ``tools.checks._impl.evidence_manifest`` so the
tests exercise the same code path that the build-time CLI uses.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from tools.checks._impl.evidence_manifest import (
    capability_registry_keys,
    deferred_suite_ids,
    derive_denominator_keys,
    verify_evidence_manifest,
)

_FORMAT_CHECKER = Draft202012Validator.FORMAT_CHECKER

ROOT = Path(__file__).parents[3]
_CAPABILITIES_REL = Path("packs/components/capabilities")
_CAPABILITIES_DIR = ROOT / _CAPABILITIES_REL
_EXPECTED_SUITES_REL = Path("tools/checks/expected-suites.toml")
_EXPECTED_SUITES_PATH = ROOT / _EXPECTED_SUITES_REL
_SCHEMA_PATH = ROOT / "contracts/evidence/evidence-manifest.schema.json"
_FIXTURE_PATH = ROOT / "tests/contracts/evidence/fixtures/i1-complete-manifest.json"

_SHA_A = "sha256:" + "a" * 64
_SHA_B = "sha256:" + "b" * 64
_SHA_C = "sha256:" + "c" * 64
_UUID_1 = "00000000-0000-4000-8000-000000000001"
_UUID_2 = "00000000-0000-4000-8000-000000000002"
_UUID_3 = "00000000-0000-4000-8000-000000000003"
_UUID_4 = "00000000-0000-4000-8000-000000000004"
_UUID_5 = "00000000-0000-4000-8000-000000000005"


# ---------------------------------------------------------------------------
# Manifest builder — uses the generator's registry-derived denominator
# ---------------------------------------------------------------------------


def _deferred_capability_rows(keys: frozenset[str]) -> list[dict[str, Any]]:
    return [
        {
            "capability_key": key,
            "status": "not_exercised",
            "source_count": 0,
            "reason": "deferred for I1/I2; no runtime exists",
        }
        for key in sorted(keys)
    ]


def _schema() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")))


def _validator() -> Draft202012Validator:
    return Draft202012Validator(_schema(), format_checker=_FORMAT_CHECKER)


def _manifest(
    *,
    deferred_keys: frozenset[str] | None = None,
) -> dict[str, Any]:
    if deferred_keys is None:
        deferred_keys = derive_denominator_keys(ROOT)

    return {
        "schema": "ctower.evidence-manifest/v1",
        "status": "development_only",
        "tenant_id": _UUID_1,
        "ticket_id": _UUID_2,
        "candidate_digest": _SHA_A,
        "criteria_revision": 1,
        "criteria": [
            {
                "criterion_key": "repository-policy",
                "disposition": "applicable",
                "reason": "repository gates pass at exact head",
                "owner": "ct-l0-007",
                "source_sha": _SHA_B,
                "environment": "disposable-development",
                "proof_digest": _SHA_C,
                "verifier": _UUID_3,
                "applicability_reason": (
                    "repository gates are in scope for the current I1 increment"
                ),
            },
            {
                "criterion_key": "cp3-d-host-loss",
                "disposition": "deferred",
                "reason": "CP3-D external failure domain acknowledgement not yet proven",
                "owner": "ct-i1-008",
                "source_sha": _SHA_B,
                "environment": "disposable-development",
                "proof_digest": _SHA_C,
                "verifier": _UUID_4,
                "applicability_reason": "CP3-D host-loss acknowledgement deferred until S11",
            },
            {
                "criterion_key": "browser-ui",
                "disposition": "deferred",
                "reason": "browser implementation deferred to CT-I2-005",
                "owner": "ct-i1-005",
                "source_sha": _SHA_B,
                "environment": "disposable-development",
                "proof_digest": _SHA_C,
                "verifier": _UUID_5,
                "applicability_reason": "browser UI not in scope for I1; deferred to I2",
            },
        ],
        "verdict_ids": [_UUID_3],
        "deferred_capabilities": _deferred_capability_rows(deferred_keys),
    }


# ---------------------------------------------------------------------------
# Acceptance 1 — every I1 criterion has exactly one typed disposition
# ---------------------------------------------------------------------------


class TestCriterionDispositions:
    def test_complete_manifest_validates(self) -> None:
        _validator().validate(_manifest())

    def test_every_criterion_has_exactly_one_disposition(self) -> None:
        manifest = _manifest()
        keys = [c["criterion_key"] for c in manifest["criteria"]]
        assert len(keys) == len(set(keys)), "criterion keys must be unique"

    @pytest.mark.parametrize(
        ("field", "bad_value"),
        [
            ("disposition", "invalid"),
            ("disposition", ""),
            ("reason", ""),
            ("owner", ""),
            ("source_sha", ""),
            ("environment", ""),
            ("proof_digest", "not-a-digest"),
            ("verifier", "not-a-uuid"),
            ("applicability_reason", ""),
        ],
    )
    def test_criterion_missing_or_invalid_field_fails(self, field: str, bad_value: object) -> None:
        candidate = _manifest()
        candidate["criteria"][0][field] = bad_value
        with pytest.raises(ValidationError):
            _validator().validate(candidate)

    def test_criterion_missing_required_field_fails(self) -> None:
        candidate = _manifest()
        del candidate["criteria"][0]["verifier"]
        with pytest.raises(ValidationError):
            _validator().validate(candidate)

    def test_duplicate_criterion_key_validates_schema_but_tests_catch_it(self) -> None:
        """The schema allows duplicate keys (it validates structure), but the
        denominator contract requires unique criterion keys — the test layer
        enforces that invariant separately."""

        candidate = _manifest()
        candidate["criteria"].append(copy.deepcopy(candidate["criteria"][0]))
        # Schema validation passes (no uniqueness constraint at schema level)
        _validator().validate(candidate)
        # But our denominator check catches the duplicate
        keys = [c["criterion_key"] for c in candidate["criteria"]]
        assert len(keys) != len(set(keys))


# ---------------------------------------------------------------------------
# Acceptance 2 — deferred capabilities are keyed rows derived from the registry
# ---------------------------------------------------------------------------


class TestDeferredCapabilitiesDerivedFromRegistry:
    def test_manifest_deferred_capabilities_match_registry_exactly(self) -> None:
        """The manifest's deferred_capability keys must be exactly the union of
        capability registry keys and deferred expected-suite IDs — no more, no less."""

        registry_keys = derive_denominator_keys(ROOT)
        manifest = _manifest()
        manifest_keys = {row["capability_key"] for row in manifest["deferred_capabilities"]}

        missing = registry_keys - manifest_keys
        extra = manifest_keys - registry_keys
        assert not missing, f"manifest omits registry entries: {sorted(missing)}"
        assert not extra, f"manifest declares unknown entries: {sorted(extra)}"

    def test_missing_registry_capability_fails_by_name(self) -> None:
        """If a capability exists in the registry but is absent from the manifest,
        the denominator check fails by naming the missing capability."""

        registry_keys = derive_denominator_keys(ROOT)
        # Remove one capability from the manifest
        first_key = min(registry_keys)
        manifest = _manifest(deferred_keys=registry_keys - {first_key})
        manifest_keys = {row["capability_key"] for row in manifest["deferred_capabilities"]}
        missing = registry_keys - manifest_keys
        assert missing, "removing one capability must produce a missing set"
        # The missing set names the exact capability that was omitted
        assert sorted(missing) == [first_key]

    def test_extra_manifest_capability_fails_by_name(self) -> None:
        """If the manifest declares a capability not in the registry, the
        denominator check fails by naming the extra capability."""

        manifest = _manifest()
        manifest["deferred_capabilities"].append(
            {
                "capability_key": "nonexistent.capability",
                "status": "not_exercised",
                "source_count": 0,
                "reason": "fabricated",
            }
        )
        registry_keys = derive_denominator_keys(ROOT)
        manifest_keys = {row["capability_key"] for row in manifest["deferred_capabilities"]}
        extra = manifest_keys - registry_keys
        assert extra == {"nonexistent.capability"}

    def test_deferred_capability_must_be_not_exercised_with_zero_sources(self) -> None:
        candidate = _manifest()
        candidate["deferred_capabilities"][0]["status"] = "exercised"
        with pytest.raises(ValidationError):
            _validator().validate(candidate)

    def test_deferred_capability_source_count_must_be_zero(self) -> None:
        candidate = _manifest()
        candidate["deferred_capabilities"][0]["source_count"] = 1
        with pytest.raises(ValidationError):
            _validator().validate(candidate)

    def test_capability_registry_has_at_least_one_deferred_capability(self) -> None:
        """The capability registry must contain deferred entries; an empty
        registry would make the denominator vacuous."""

        assert capability_registry_keys(ROOT), "capability registry is empty"

    def test_expected_suite_registry_has_at_least_one_deferred_suite(self) -> None:
        """The expected-suite registry must contain deferred suites; an empty
        deferred set would make the denominator vacuous."""

        assert deferred_suite_ids(ROOT), "expected-suite registry has no deferred suites"

    def test_no_fixed_four_name_roster_in_schema(self) -> None:
        """The schema must NOT hard-code a fixed four-name deferred list.
        The old schema required 'remote', 'images', 'effects', 'extensions'
        as fixed property names — the new schema uses a dynamic array."""

        schema_text = _SCHEMA_PATH.read_text(encoding="utf-8")
        assert '"deferred_sources"' not in schema_text, (
            "schema must not contain the old fixed deferred_sources object"
        )
        # The new schema uses a dynamic array, not fixed property names
        assert '"remote"' not in schema_text
        assert '"images"' not in schema_text
        assert '"effects"' not in schema_text
        assert '"extensions"' not in schema_text


class TestCommittedFixtureDenominator:
    """The committed I1 manifest fixture must carry a deferred disposition for
    every capability in the on-disk capability registry AND every deferred suite
    in the expected-suite registry.  This is the real mutation guard: adding a
    capability YAML to the registry or a deferred suite to expected-suites.toml
    WITHOUT updating the fixture makes this test RED by naming the missing entry.

    The verification is delegated to the repository-owned generator
    (``verify_evidence_manifest``) so the tests exercise the same code path
    that the build-time CLI uses.
    """

    def test_committed_manifest_validates_against_schema(self) -> None:
        manifest = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        _validator().validate(manifest)

    def test_committed_manifest_denominator_matches_registry(self) -> None:
        """The generator's ``verify_evidence_manifest`` returns no errors
        when the committed fixture matches the registries exactly."""
        errors = verify_evidence_manifest(ROOT, _FIXTURE_PATH)
        assert errors == (), f"fixture denominator errors: {errors}"

    def test_committed_manifest_has_unique_criterion_keys(self) -> None:
        manifest = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        keys = [c["criterion_key"] for c in manifest["criteria"]]
        assert len(keys) == len(set(keys)), "fixture has duplicate criterion keys"

    def test_committed_manifest_every_criterion_has_typed_disposition(self) -> None:
        manifest = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        for criterion in manifest["criteria"]:
            assert criterion["disposition"] in (
                "applicable",
                "satisfied_by_superseding_evidence",
                "deferred",
                "failed",
            )
            for field in (
                "reason",
                "owner",
                "source_sha",
                "environment",
                "proof_digest",
                "verifier",
                "applicability_reason",
            ):
                assert field in criterion, f"criterion {criterion['criterion_key']} missing {field}"


# ---------------------------------------------------------------------------
# Acceptance 4 — mutation proof: add a registry capability -> test goes RED
# ---------------------------------------------------------------------------


class TestMutationProof:
    def test_adding_a_registry_capability_without_manifest_disposition_fails(
        self, tmp_path: Path
    ) -> None:
        """Add a capability in a scratch copy of the registry -> the denominator
        check goes RED until the manifest carries its disposition."""

        # 1. Build a scratch registry with one extra capability
        scratch_root = tmp_path
        scratch_caps = scratch_root / _CAPABILITIES_REL
        scratch_caps.mkdir(parents=True)
        for path in sorted(_CAPABILITIES_DIR.rglob("*.yaml")):
            rel = path.relative_to(_CAPABILITIES_DIR)
            target = scratch_caps / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
        # Also copy the expected-suite registry so both registries exist.
        scratch_suites = scratch_root / _EXPECTED_SUITES_REL
        scratch_suites.parent.mkdir(parents=True, exist_ok=True)
        scratch_suites.write_bytes(_EXPECTED_SUITES_PATH.read_bytes())

        # Add a phantom capability
        phantom_dir = scratch_caps / "phantom.capability"
        phantom_dir.mkdir()
        (phantom_dir / "v1.yaml").write_text(
            json.dumps(
                {
                    "schema": "ctower.capability/v1",
                    "key": "phantom.capability",
                    "display_name": "Phantom capability for mutation test",
                    "operation": "ctower.phantom",
                    "authority": "requested_not_granted",
                }
            ),
            encoding="utf-8",
        )

        # 2. The committed fixture does NOT carry phantom.capability
        errors = verify_evidence_manifest(scratch_root, _FIXTURE_PATH)
        assert any("phantom.capability" in e for e in errors), (
            "adding a registry capability must surface the missing entry by name"
        )

        # 3. Add the disposition to a scratch manifest -> GREEN
        manifest = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        manifest["deferred_capabilities"].append(
            {
                "capability_key": "phantom.capability",
                "status": "not_exercised",
                "source_count": 0,
                "reason": "phantom capability disposition added",
            }
        )
        scratch_manifest = scratch_root / "manifest.json"
        scratch_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        errors_after = verify_evidence_manifest(scratch_root, scratch_manifest)
        assert not errors_after, "after adding the disposition the manifest must match the registry"

    def test_adding_a_deferred_suite_without_manifest_disposition_fails(
        self, tmp_path: Path
    ) -> None:
        """Add a deferred suite in a scratch copy of expected-suites.toml -> the
        denominator check goes RED until the manifest carries its disposition."""

        # 1. Build a scratch expected-suites.toml with one extra deferred suite
        scratch_root = tmp_path
        scratch_suites = scratch_root / _EXPECTED_SUITES_REL
        scratch_suites.parent.mkdir(parents=True, exist_ok=True)
        original = _EXPECTED_SUITES_PATH.read_text(encoding="utf-8")
        extra_suite = (
            "\n[[suite]]\n"
            'id = "phantom-suite"\n'
            'owner = "CT-I2-099"\n'
            'phase = "CT-I2-099"\n'
            'status = "deferred"\n'
            'path = "tests/phantom"\n'
            'patterns = ["test_*.py"]\n'
            'command = ["{python}", "-m", "pytest", "tests/phantom", "-q"]\n'
            "timeout_seconds = 300\n"
        )
        scratch_suites.write_text(original + extra_suite, encoding="utf-8")
        # Also copy the capabilities registry so both registries exist.
        scratch_caps = scratch_root / _CAPABILITIES_REL
        scratch_caps.mkdir(parents=True)
        for path in sorted(_CAPABILITIES_DIR.rglob("*.yaml")):
            rel = path.relative_to(_CAPABILITIES_DIR)
            target = scratch_caps / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())

        # 2. The committed fixture does NOT carry phantom-suite
        errors = verify_evidence_manifest(scratch_root, _FIXTURE_PATH)
        assert any("phantom-suite" in e for e in errors), (
            "adding a deferred suite must surface the missing entry by name"
        )

        # 3. Add the disposition to a scratch manifest -> GREEN
        manifest = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        manifest["deferred_capabilities"].append(
            {
                "capability_key": "phantom-suite",
                "status": "not_exercised",
                "source_count": 0,
                "reason": "phantom suite disposition added",
            }
        )
        scratch_manifest = scratch_root / "manifest.json"
        scratch_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        errors_after = verify_evidence_manifest(scratch_root, scratch_manifest)
        assert not errors_after, "after adding the disposition the manifest must match the registry"
