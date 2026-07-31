"""Tests for the repository-owned evidence-manifest generator.

The generator derives the evidence denominator (deferred capabilities) from the
capability registry (packs/components/capabilities/) and the expected-suite
registry (tools/checks/expected-suites.toml deferred suites).  It validates the
committed fixture and surfaces missing or extra entries BY NAME.  Adding a
registry entry without a corresponding manifest disposition is a named failure.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from tools.checks._impl.evidence_manifest import (
    EvidenceManifestError,
    build_deferred_capabilities,
    check_evidence_manifest,
    deferred_suite_ids,
    capability_registry_keys,
    derive_denominator_keys,
    verify_evidence_manifest,
)

ROOT = Path(__file__).parents[3]
_CAPABILITIES_REL = Path("packs/components/capabilities")
_EXPECTED_SUITES_REL = Path("tools/checks/expected-suites.toml")
_CAPABILITIES_DIR = ROOT / _CAPABILITIES_REL
_EXPECTED_SUITES_PATH = ROOT / _EXPECTED_SUITES_REL
_SCHEMA_PATH = ROOT / "contracts/evidence/evidence-manifest.schema.json"
_FIXTURE_PATH = ROOT / "tests/contracts/evidence/fixtures/i1-complete-manifest.json"


# ---------------------------------------------------------------------------
# Registry derivation
# ---------------------------------------------------------------------------


class TestCapabilityRegistryDerivation:
    def test_capability_registry_keys_non_empty(self) -> None:
        keys = capability_registry_keys(ROOT)
        assert keys, "capability registry is empty"

    def test_capability_registry_keys_match_on_disk_yaml(self) -> None:
        keys = capability_registry_keys(ROOT)
        disk_keys: set[str] = set()
        for path in sorted(_CAPABILITIES_DIR.rglob("*.yaml")):
            data = json.loads(path.read_text(encoding="utf-8"))
            disk_keys.add(data["key"])
        assert keys == frozenset(disk_keys)

    def test_duplicate_capability_key_raises(self, tmp_path: Path) -> None:
        scratch_caps = tmp_path / _CAPABILITIES_REL
        scratch_caps.mkdir(parents=True)
        for path in sorted(_CAPABILITIES_DIR.rglob("*.yaml")):
            rel = path.relative_to(_CAPABILITIES_DIR)
            target = scratch_caps / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
        dup_dir = scratch_caps / "dup.capability"
        dup_dir.mkdir()
        (dup_dir / "v1.yaml").write_text(
            json.dumps(
                {
                    "schema": "ctower.capability/v1",
                    "key": "control.api",
                    "display_name": "Duplicate",
                    "operation": "ctower.duplicate",
                    "authority": "requested_not_granted",
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(EvidenceManifestError, match="duplicate capability key"):
            capability_registry_keys(tmp_path)


class TestDeferredSuiteDerivation:
    def test_deferred_suite_ids_non_empty(self) -> None:
        ids = deferred_suite_ids(ROOT)
        assert ids, "expected-suite registry has no deferred suites"

    def test_deferred_suite_ids_match_toml(self) -> None:
        ids = deferred_suite_ids(ROOT)
        data = tomllib.loads(_EXPECTED_SUITES_PATH.read_text(encoding="utf-8"))
        toml_ids = frozenset(
            suite["id"] for suite in data["suite"] if suite["status"] == "deferred"
        )
        assert ids == toml_ids


class TestDenominatorDerivation:
    def test_denominator_is_union_of_registries(self) -> None:
        keys = derive_denominator_keys(ROOT)
        cap_keys = capability_registry_keys(ROOT)
        suite_ids = deferred_suite_ids(ROOT)
        assert keys == frozenset(cap_keys | suite_ids)

    def test_denominator_is_frozenset(self) -> None:
        assert isinstance(derive_denominator_keys(ROOT), frozenset)


# ---------------------------------------------------------------------------
# build_deferred_capabilities
# ---------------------------------------------------------------------------


class TestBuildDeferredCapabilities:
    def test_returns_sorted_rows(self) -> None:
        rows = build_deferred_capabilities(ROOT)
        keys = [row["capability_key"] for row in rows]
        assert keys == sorted(keys)

    def test_every_row_has_required_fields(self) -> None:
        rows = build_deferred_capabilities(ROOT)
        for row in rows:
            assert row["status"] == "not_exercised"
            assert row["source_count"] == 0
            assert "reason" in row
            assert row["reason"]

    def test_rows_match_denominator_exactly(self) -> None:
        rows = build_deferred_capabilities(ROOT)
        row_keys = {row["capability_key"] for row in rows}
        denominator = derive_denominator_keys(ROOT)
        assert row_keys == denominator


# ---------------------------------------------------------------------------
# verify_evidence_manifest — committed fixture validation
# ---------------------------------------------------------------------------


class TestVerifyEvidenceManifest:
    def test_committed_fixture_verifies_clean(self) -> None:
        errors = verify_evidence_manifest(ROOT, _FIXTURE_PATH)
        assert errors == (), f"committed fixture has denominator errors: {errors}"

    def test_missing_capability_surfaces_by_name(self, tmp_path: Path) -> None:
        manifest = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        # Remove one capability from the manifest
        original = manifest["deferred_capabilities"]
        removed_key = original[0]["capability_key"]
        manifest["deferred_capabilities"] = [
            row for row in original if row["capability_key"] != removed_key
        ]
        scratch = tmp_path / "manifest.json"
        scratch.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        errors = verify_evidence_manifest(ROOT, scratch)
        missing_msgs = [e for e in errors if "omits" in e.lower()]
        assert missing_msgs, f"expected a missing-entry error, got: {errors}"
        assert any(removed_key in e for e in errors), (
            f"missing error must name '{removed_key}': {errors}"
        )

    def test_extra_capability_surfaces_by_name(self, tmp_path: Path) -> None:
        manifest = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        manifest["deferred_capabilities"].append(
            {
                "capability_key": "nonexistent.capability",
                "status": "not_exercised",
                "source_count": 0,
                "reason": "fabricated",
            }
        )
        scratch = tmp_path / "manifest.json"
        scratch.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        errors = verify_evidence_manifest(ROOT, scratch)
        extra_msgs = [e for e in errors if "unknown" in e.lower() or "extra" in e.lower()]
        assert extra_msgs, f"expected an extra-entry error, got: {errors}"
        assert any("nonexistent.capability" in e for e in errors), (
            f"extra error must name 'nonexistent.capability': {errors}"
        )

    def test_missing_and_extra_both_surface(self, tmp_path: Path) -> None:
        manifest = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        original = manifest["deferred_capabilities"]
        removed_key = original[0]["capability_key"]
        manifest["deferred_capabilities"] = [
            row for row in original if row["capability_key"] != removed_key
        ]
        manifest["deferred_capabilities"].append(
            {
                "capability_key": "phantom.extra",
                "status": "not_exercised",
                "source_count": 0,
                "reason": "fabricated",
            }
        )
        scratch = tmp_path / "manifest.json"
        scratch.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        errors = verify_evidence_manifest(ROOT, scratch)
        assert any(removed_key in e for e in errors)
        assert any("phantom.extra" in e for e in errors)


# ---------------------------------------------------------------------------
# check_evidence_manifest — raises on mismatch
# ---------------------------------------------------------------------------


class TestCheckEvidenceManifest:
    def test_check_passes_on_valid_fixture(self) -> None:
        # Should not raise
        check_evidence_manifest(ROOT, _FIXTURE_PATH)

    def test_check_raises_on_missing_entry(self, tmp_path: Path) -> None:
        manifest = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        original = manifest["deferred_capabilities"]
        removed_key = original[0]["capability_key"]
        manifest["deferred_capabilities"] = [
            row for row in original if row["capability_key"] != removed_key
        ]
        scratch = tmp_path / "manifest.json"
        scratch.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        with pytest.raises(EvidenceManifestError, match=removed_key):
            check_evidence_manifest(ROOT, scratch)


# ---------------------------------------------------------------------------
# Mutation proof: adding a registry entry -> named failure
# ---------------------------------------------------------------------------


class TestMutationProofViaGenerator:
    def test_adding_capability_to_registry_surfaces_missing_in_fixture(
        self, tmp_path: Path
    ) -> None:
        """Add a capability in a scratch registry -> verify against the
        committed fixture surfaces the missing entry by name."""

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
        phantom_dir = scratch_caps / "phantom.capability"
        phantom_dir.mkdir()
        (phantom_dir / "v1.yaml").write_text(
            json.dumps(
                {
                    "schema": "ctower.capability/v1",
                    "key": "phantom.capability",
                    "display_name": "Phantom",
                    "operation": "ctower.phantom",
                    "authority": "requested_not_granted",
                }
            ),
            encoding="utf-8",
        )
        errors = verify_evidence_manifest(tmp_path, _FIXTURE_PATH)
        assert any("phantom.capability" in e for e in errors), (
            f"phantom.capability must be surfaced as missing: {errors}"
        )

    def test_adding_deferred_suite_surfaces_missing_in_fixture(
        self, tmp_path: Path
    ) -> None:
        """Add a deferred suite in a scratch expected-suites.toml -> verify
        against the committed fixture surfaces the missing entry by name."""

        scratch_root = tmp_path
        (scratch_root / "tools/checks").mkdir(parents=True)
        original = _EXPECTED_SUITES_PATH.read_text(encoding="utf-8")
        extra = (
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
        (scratch_root / "tools/checks/expected-suites.toml").write_text(
            original + extra, encoding="utf-8"
        )
        # The capabilities directory must also exist in the scratch root;
        # copy it so the denominator includes both registries.
        scratch_caps = scratch_root / _CAPABILITIES_REL
        scratch_caps.mkdir(parents=True)
        for path in sorted(_CAPABILITIES_DIR.rglob("*.yaml")):
            rel = path.relative_to(_CAPABILITIES_DIR)
            target = scratch_caps / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
        errors = verify_evidence_manifest(scratch_root, _FIXTURE_PATH)
        assert any("phantom-suite" in e for e in errors), (
            f"phantom-suite must be surfaced as missing: {errors}"
        )
