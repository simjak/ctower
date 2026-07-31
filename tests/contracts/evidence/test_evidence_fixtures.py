"""Named positive and negative evidence-manifest fixtures.

This module exercises on-disk fixture files under
``tests/contracts/evidence/fixtures/`` so that the denominator contract is
proven against committed artifacts rather than inline dictionaries.

Positive fixture (``fixtures/i1-complete-manifest.json``):
    A complete I1 manifest where every criterion has exactly one disposition
    (applicable | satisfied_by_superseding_evidence | deferred | failed) with
    reason, owner, source SHA/environment, proof digest, verifier.  The
    manifest denominator matches the capability/expected-suite registries
    exactly — the test goes GREEN.

Negative fixtures (``fixtures/negative/*.json``):
    Named cases that go RED when a registry entry lacks a manifest disposition
    or vice versa:

    * ``missing-registry.json`` — a capability registry entry (``control.api``)
      has no manifest disposition; the denominator check fails by naming the
      missing entry.
    * ``extra-registry.json`` — the manifest declares a capability
      (``phantom.capability``) not present in the registry; the denominator
      check fails by naming the extra entry.
    * ``deferred-registry.json`` — a deferred-suite-sourced entry
      (``increment-1-acceptance``) has no manifest disposition; the denominator
      check fails by naming the missing deferred entry.

Mutation proof:
    Adding a scratch registry capability makes a named test RED until the
    manifest carries its disposition; restoring the registry makes the test
    GREEN again.  The scratch capability is written into a temporary copy of
    the registry (``tmp_path``) so the real on-disk registry is never mutated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator

from tools.checks._impl.evidence_manifest import (
    check_evidence_manifest,
    derive_denominator_keys,
    verify_evidence_manifest,
    EvidenceManifestError,
)

ROOT = Path(__file__).parents[3]
_FIXTURES = ROOT / "tests/contracts/evidence/fixtures"
_POSITIVE_FIXTURE = _FIXTURES / "i1-complete-manifest.json"
_NEGATIVE_DIR = _FIXTURES / "negative"
_SCHEMA_PATH = ROOT / "contracts/evidence/evidence-manifest.schema.json"
_CAPABILITIES_REL = Path("packs/components/capabilities")
_CAPABILITIES_DIR = ROOT / _CAPABILITIES_REL
_EXPECTED_SUITES_REL = Path("tools/checks/expected-suites.toml")
_EXPECTED_SUITES_PATH = ROOT / _EXPECTED_SUITES_REL

_FORMAT_CHECKER = Draft202012Validator.FORMAT_CHECKER


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _schema() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")))


def _validator() -> Draft202012Validator:
    return Draft202012Validator(_schema(), format_checker=_FORMAT_CHECKER)


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


_VALID_DISPOSITIONS = frozenset(
    ("applicable", "satisfied_by_superseding_evidence", "deferred", "failed")
)


# ---------------------------------------------------------------------------
# Acceptance 1 — positive fixture: complete I1 manifest
# ---------------------------------------------------------------------------


class TestPositiveFixture:
    """The committed positive fixture is a complete I1 manifest where every
    criterion has exactly one typed disposition and the denominator matches
    the registries exactly.  This is the GREEN baseline."""

    def test_positive_fixture_validates_against_schema(self) -> None:
        manifest = _load(_POSITIVE_FIXTURE)
        _validator().validate(manifest)

    def test_positive_fixture_denominator_matches_registry(self) -> None:
        errors = verify_evidence_manifest(ROOT, _POSITIVE_FIXTURE)
        assert errors == (), f"positive fixture has denominator errors: {errors}"

    def test_positive_fixture_every_criterion_has_exactly_one_disposition(
        self,
    ) -> None:
        manifest = _load(_POSITIVE_FIXTURE)
        keys = [c["criterion_key"] for c in manifest["criteria"]]
        assert len(keys) == len(set(keys)), "criterion keys must be unique"
        for criterion in manifest["criteria"]:
            assert criterion["disposition"] in _VALID_DISPOSITIONS, (
                f"criterion {criterion['criterion_key']} has invalid disposition "
                f"{criterion['disposition']!r}"
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

    def test_positive_fixture_check_does_not_raise(self) -> None:
        check_evidence_manifest(ROOT, _POSITIVE_FIXTURE)

    def test_positive_fixture_deferred_capabilities_match_registry_exactly(
        self,
    ) -> None:
        manifest = _load(_POSITIVE_FIXTURE)
        manifest_keys = {row["capability_key"] for row in manifest["deferred_capabilities"]}
        registry_keys = derive_denominator_keys(ROOT)
        assert manifest_keys == registry_keys


# ---------------------------------------------------------------------------
# Acceptance 2 — negative fixtures: named cases that go RED
# ---------------------------------------------------------------------------


class TestNegativeMissingRegistry:
    """A capability registry entry (``control.api``) lacks a manifest
    disposition — the denominator check goes RED by naming the missing entry."""

    _fixture = _NEGATIVE_DIR / "missing-registry.json"
    _missing_key = "control.api"

    def test_negative_fixture_validates_against_schema(self) -> None:
        """The negative fixture is structurally valid — it fails the
        denominator contract, not the schema."""
        manifest = _load(self._fixture)
        _validator().validate(manifest)

    def test_missing_registry_fails_by_name(self) -> None:
        errors = verify_evidence_manifest(ROOT, self._fixture)
        assert errors, "missing-registry fixture must produce errors"
        assert any(self._missing_key in e for e in errors), (
            f"error must name '{self._missing_key}': {errors}"
        )

    def test_missing_registry_check_raises(self) -> None:
        with pytest.raises(EvidenceManifestError, match=self._missing_key):
            check_evidence_manifest(ROOT, self._fixture)

    def test_missing_registry_error_is_an_omission(self) -> None:
        errors = verify_evidence_manifest(ROOT, self._fixture)
        assert any("omits" in e.lower() for e in errors), f"error must be an omission: {errors}"


class TestNegativeExtraRegistry:
    """The manifest declares a capability (``phantom.capability``) not present
    in the registry — the denominator check goes RED by naming the extra
    entry."""

    _fixture = _NEGATIVE_DIR / "extra-registry.json"
    _extra_key = "phantom.capability"

    def test_negative_fixture_validates_against_schema(self) -> None:
        manifest = _load(self._fixture)
        _validator().validate(manifest)

    def test_extra_registry_fails_by_name(self) -> None:
        errors = verify_evidence_manifest(ROOT, self._fixture)
        assert errors, "extra-registry fixture must produce errors"
        assert any(self._extra_key in e for e in errors), (
            f"error must name '{self._extra_key}': {errors}"
        )

    def test_extra_registry_check_raises(self) -> None:
        with pytest.raises(EvidenceManifestError, match=self._extra_key):
            check_evidence_manifest(ROOT, self._fixture)

    def test_extra_registry_error_is_an_unknown_entry(self) -> None:
        errors = verify_evidence_manifest(ROOT, self._fixture)
        assert any("unknown" in e.lower() for e in errors), (
            f"error must be an unknown entry: {errors}"
        )


class TestNegativeDeferredRegistry:
    """A deferred-suite-sourced entry (``increment-1-acceptance``) lacks a
    manifest disposition — the denominator check goes RED by naming the missing
    deferred entry.  This is distinct from missing-registry because the entry
    is sourced from the expected-suite registry, not the capability
    registry."""

    _fixture = _NEGATIVE_DIR / "deferred-registry.json"
    _missing_key = "increment-1-acceptance"

    def test_negative_fixture_validates_against_schema(self) -> None:
        manifest = _load(self._fixture)
        _validator().validate(manifest)

    def test_deferred_registry_fails_by_name(self) -> None:
        errors = verify_evidence_manifest(ROOT, self._fixture)
        assert errors, "deferred-registry fixture must produce errors"
        assert any(self._missing_key in e for e in errors), (
            f"error must name '{self._missing_key}': {errors}"
        )

    def test_deferred_registry_check_raises(self) -> None:
        with pytest.raises(EvidenceManifestError, match=self._missing_key):
            check_evidence_manifest(ROOT, self._fixture)

    def test_deferred_registry_error_is_an_omission(self) -> None:
        errors = verify_evidence_manifest(ROOT, self._fixture)
        assert any("omits" in e.lower() for e in errors), f"error must be an omission: {errors}"


# ---------------------------------------------------------------------------
# Acceptance 3 — mutation proof: scratch registry capability
# ---------------------------------------------------------------------------


def _copy_registries(scratch_root: Path) -> None:
    """Copy the capability and expected-suite registries into a scratch root."""

    scratch_caps = scratch_root / _CAPABILITIES_REL
    scratch_caps.mkdir(parents=True, exist_ok=True)
    for path in sorted(_CAPABILITIES_DIR.rglob("*.yaml")):
        rel = path.relative_to(_CAPABILITIES_DIR)
        target = scratch_caps / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())

    scratch_suites = scratch_root / _EXPECTED_SUITES_REL
    scratch_suites.parent.mkdir(parents=True, exist_ok=True)
    scratch_suites.write_bytes(_EXPECTED_SUITES_PATH.read_bytes())


def _write_phantom_capability(scratch_root: Path, key: str) -> Path:
    """Write a scratch capability YAML under a scratch registry root."""

    cap_dir = scratch_root / _CAPABILITIES_REL / key
    cap_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = cap_dir / "v1.yaml"
    yaml_path.write_text(
        json.dumps(
            {
                "schema": "ctower.capability/v1",
                "key": key,
                "display_name": f"Scratch {key} for mutation test",
                "operation": f"ctower.{key.replace('.', '_')}",
                "authority": "requested_not_granted",
            }
        ),
        encoding="utf-8",
    )
    return yaml_path


class TestMutationProof:
    """Mutation proof: adding a scratch registry capability makes a named test
    RED until the manifest carries its disposition.  After restoring (adding
    the disposition to a scratch manifest), the test goes GREEN again.

    The scratch capability is written into a temporary copy of the registry so
    the real on-disk registry is never mutated — the restore is automatic when
    ``tmp_path`` is cleaned up.
    """

    _phantom_key = "scratch.mutation.capability"

    def test_scratch_capability_makes_named_test_red_then_green_after_restore(
        self, tmp_path: Path
    ) -> None:
        # 1. Build a scratch copy of both registries.
        scratch_root = tmp_path
        _copy_registries(scratch_root)

        # 2. Add a scratch capability to the scratch registry.
        _write_phantom_capability(scratch_root, self._phantom_key)

        # 3. The committed positive fixture does NOT carry the scratch
        #    capability -> the denominator check goes RED by naming it.
        errors = verify_evidence_manifest(scratch_root, _POSITIVE_FIXTURE)
        assert errors, "adding a scratch capability must produce denominator errors"
        assert any(self._phantom_key in e for e in errors), (
            f"error must name '{self._phantom_key}': {errors}"
        )
        # Confirm the error is an omission (registry entry lacks disposition).
        assert any("omits" in e.lower() for e in errors), f"error must be an omission: {errors}"

        # 4. Restore: add the disposition to a scratch copy of the manifest.
        manifest = _load(_POSITIVE_FIXTURE)
        manifest["deferred_capabilities"].append(
            {
                "capability_key": self._phantom_key,
                "status": "not_exercised",
                "source_count": 0,
                "reason": "scratch capability disposition added for mutation test",
            }
        )
        scratch_manifest = scratch_root / "restored-manifest.json"
        scratch_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        # 5. After restore, the denominator check goes GREEN.
        errors_after = verify_evidence_manifest(scratch_root, scratch_manifest)
        assert not errors_after, (
            f"after restore the manifest must match the registry: {errors_after}"
        )

        # 6. The restored scratch manifest also validates against the schema.
        _validator().validate(manifest)

    def test_scratch_capability_check_raises_until_restored(self, tmp_path: Path) -> None:
        """The ``check_evidence_manifest`` callable raises until the manifest
        carries the scratch capability's disposition."""

        scratch_root = tmp_path
        _copy_registries(scratch_root)
        _write_phantom_capability(scratch_root, self._phantom_key)

        # RED — check raises naming the scratch capability.
        with pytest.raises(EvidenceManifestError, match=self._phantom_key):
            check_evidence_manifest(scratch_root, _POSITIVE_FIXTURE)

        # Restore — add the disposition to a scratch manifest.
        manifest = _load(_POSITIVE_FIXTURE)
        manifest["deferred_capabilities"].append(
            {
                "capability_key": self._phantom_key,
                "status": "not_exercised",
                "source_count": 0,
                "reason": "scratch capability disposition added for mutation test",
            }
        )
        scratch_manifest = scratch_root / "restored-manifest.json"
        scratch_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        # GREEN — check does not raise after restore.
        check_evidence_manifest(scratch_root, scratch_manifest)

    def test_real_registry_is_unchanged_after_mutation(self, tmp_path: Path) -> None:
        """The mutation proof must never mutate the real on-disk registry.
        After the scratch mutation, the real registry denominator is unchanged
        and the positive fixture still verifies clean."""

        original_keys = derive_denominator_keys(ROOT)

        scratch_root = tmp_path
        _copy_registries(scratch_root)
        _write_phantom_capability(scratch_root, self._phantom_key)

        # The scratch registry has one extra key...
        scratch_keys = derive_denominator_keys(scratch_root)
        assert self._phantom_key in scratch_keys

        # ...but the real registry is unchanged.
        assert derive_denominator_keys(ROOT) == original_keys
        assert self._phantom_key not in original_keys

        # The positive fixture still verifies clean against the real registry.
        assert verify_evidence_manifest(ROOT, _POSITIVE_FIXTURE) == ()
