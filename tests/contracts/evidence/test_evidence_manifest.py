"""Evidence-manifest typed denominator contract vectors.

Both denominators are derived from registries of record, never from a hand-copied
roster and never from the manifest itself:

* criteria — the criteria frozen by the authored gate policies in
  ``packs/policies/gates`` plus the acceptance-criterion codes the traceability
  generator reads out of ``contracts/traceability/sources.json``.  Each row names the
  registry it came from, so the two namespaces never share a key space.
* deferred capabilities — the capability registry plus the deferred expected suites.

``_criterion_denominator_errors`` is the criterion chokepoint: it is the only place
that decides whether the committed manifest agrees with the registries, and it names
every missing, unknown, and duplicated criterion.
"""

from __future__ import annotations

import copy
import json
import re
import tomllib
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

__all__: tuple[str, ...] = ()

_FORMAT_CHECKER = Draft202012Validator.FORMAT_CHECKER

ROOT = Path(__file__).parents[3]
_GATE_POLICY_DIR = "packs/policies/gates"
_TRACEABILITY_SOURCES = "contracts/traceability/sources.json"
_EXPECTED_SUITES = "tools/checks/expected-suites.toml"
_CAPABILITIES_DIR = ROOT / "packs/components/capabilities"
_EXPECTED_SUITES_PATH = ROOT / _EXPECTED_SUITES
_SCHEMA_PATH = ROOT / "contracts/evidence/evidence-manifest.schema.json"
_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "i1-complete-manifest.json"

GATE_POLICY = "gate-policy"
ACCEPTANCE = "acceptance-criterion"
_ACCEPTANCE_CODE = re.compile(r"^AC-[A-Z]{2,8}-[0-9]{2}$")


class RegistryError(AssertionError):
    """A registry of record cannot be read as a denominator source."""


# ---------------------------------------------------------------------------
# Registries of record
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = YAML(typ="safe", pure=True).load(path.read_text(encoding="utf-8"))
    except (OSError, YAMLError) as error:
        raise RegistryError(f"{path}: unreadable registry entry: {error}") from error
    if not isinstance(data, dict):
        raise RegistryError(f"{path}: registry entry must be a mapping")
    return cast(dict[str, Any], data)


def _gate_policy_criteria(root: Path = ROOT) -> dict[str, int]:
    """Frozen gate-policy criterion key -> the policy revision that freezes it."""

    frozen: dict[str, int] = {}
    for path in sorted((root / _GATE_POLICY_DIR).glob("*.yaml")):
        policy = _load_yaml(path)
        revision = policy.get("revision")
        if not isinstance(revision, int):
            raise RegistryError(f"{path}: gate policy has no integer revision")
        for entry in policy.get("criteria", []):
            key = entry.get("key") if isinstance(entry, dict) else None
            if not isinstance(key, str):
                raise RegistryError(f"{path}: gate-policy criterion has no string key")
            if key in frozen:
                raise RegistryError(f"{path}: duplicate frozen criterion key {key!r}")
            frozen[key] = revision
    return frozen


def _acceptance_criteria(root: Path = ROOT) -> frozenset[str]:
    """Acceptance-criterion codes the traceability registry binds to authored artifacts."""

    path = root / _TRACEABILITY_SOURCES
    artifacts = json.loads(path.read_text(encoding="utf-8")).get("artifacts")
    if not isinstance(artifacts, list):
        raise RegistryError(f"{path}: 'artifacts' must be a list")
    codes = {
        reference
        for artifact in artifacts
        for reference in artifact.get("references", [])
        if isinstance(reference, str) and _ACCEPTANCE_CODE.fullmatch(reference)
    }
    if not codes:
        raise RegistryError(f"{path}: no AC-* codes; the criterion denominator would be vacuous")
    return frozenset(codes)


def _criterion_denominator(root: Path = ROOT) -> frozenset[tuple[str, str]]:
    """The complete criterion denominator as (registry, key) pairs."""

    frozen = {(GATE_POLICY, key) for key in _gate_policy_criteria(root)}
    if not frozen:
        raise RegistryError(f"{root / _GATE_POLICY_DIR}: no gate policy freezes any criterion")
    return frozenset(frozen | {(ACCEPTANCE, code) for code in _acceptance_criteria(root)})


def _capability_registry_keys() -> frozenset[str]:
    """Derive the set of capability keys from the capability registry on disk."""

    keys: set[str] = set()
    for path in sorted(_CAPABILITIES_DIR.rglob("*.yaml")):
        data = json.loads(path.read_text(encoding="utf-8"))
        key = data["key"]
        if key in keys:
            raise AssertionError(f"duplicate capability key in registry: {key}")
        keys.add(key)
    return frozenset(keys)


def _deferred_suite_ids(root: Path | None = None) -> frozenset[str]:
    """Derive the set of deferred suite IDs from the expected-suite registry."""

    manifest_path = (root or ROOT) / _EXPECTED_SUITES
    data = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    return frozenset(suite["id"] for suite in data["suite"] if suite["status"] == "deferred")


def _all_deferred_keys() -> frozenset[str]:
    """Union of capability registry keys and deferred expected-suite IDs."""

    return _capability_registry_keys() | _deferred_suite_ids()


# ---------------------------------------------------------------------------
# The committed manifest and the chokepoint that judges it
# ---------------------------------------------------------------------------


def _committed_manifest() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(_FIXTURE_PATH.read_text(encoding="utf-8")))


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


def _manifest(*, deferred_keys: frozenset[str] | None = None) -> dict[str, Any]:
    """A candidate manifest: the committed fixture, optionally with a swapped roster."""

    candidate = _committed_manifest()
    if deferred_keys is not None:
        candidate["deferred_capabilities"] = _deferred_capability_rows(deferred_keys)
    return candidate


def _criterion_pairs(manifest: dict[str, Any]) -> list[tuple[str, str]]:
    return [(row["criterion_source"], row["criterion_key"]) for row in manifest["criteria"]]


def _duplicates(values: Iterable[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


def _criterion_denominator_errors(manifest: dict[str, Any], root: Path = ROOT) -> list[str]:
    """CHOKEPOINT: every disagreement between a manifest and the criterion registries."""

    denominator = _criterion_denominator(root)
    pairs = _criterion_pairs(manifest)
    declared = set(pairs)
    errors = [
        f"manifest repeats criterion {name}"
        for name in _duplicates(f"{source}/{key}" for source, key in pairs)
    ]
    errors += [
        f"manifest omits registry criterion {source}/{key}"
        for source, key in sorted(denominator - declared)
    ]
    errors += [
        f"manifest declares unknown criterion {source}/{key}"
        for source, key in sorted(declared - denominator)
    ]
    return errors


def _schema() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")))


def _validator() -> Draft202012Validator:
    return Draft202012Validator(_schema(), format_checker=_FORMAT_CHECKER)


def _criterion_row(manifest: dict[str, Any], source: str) -> dict[str, Any]:
    return next(row for row in manifest["criteria"] if row["criterion_source"] == source)


# ---------------------------------------------------------------------------
# Acceptance 1 — every derived criterion has exactly one typed disposition
# ---------------------------------------------------------------------------


class TestCriterionDenominatorIsDerived:
    """The committed fixture carries the real derived criterion set, not a sample."""

    def test_committed_manifest_criteria_match_the_registries_exactly(self) -> None:
        assert _criterion_denominator_errors(_committed_manifest()) == []

    def test_committed_manifest_validates_against_schema(self) -> None:
        _validator().validate(_committed_manifest())

    def test_criteria_revision_matches_the_frozen_gate_policy_revision(self) -> None:
        revisions = set(_gate_policy_criteria().values())
        assert len(revisions) == 1, f"gate policies disagree on revision: {sorted(revisions)}"
        assert _committed_manifest()["criteria_revision"] == revisions.pop()

    def test_every_criterion_carries_exactly_one_typed_disposition(self) -> None:
        allowed = set(_schema()["$defs"]["disposition"]["enum"])
        for row in _committed_manifest()["criteria"]:
            assert row["disposition"] in allowed, f"{row['criterion_key']}: untyped disposition"

    def test_missing_criterion_is_refused_by_name(self) -> None:
        candidate = _committed_manifest()
        dropped = candidate["criteria"].pop()
        expected = (
            f"manifest omits registry criterion "
            f"{dropped['criterion_source']}/{dropped['criterion_key']}"
        )
        assert expected in _criterion_denominator_errors(candidate)

    def test_extra_criterion_is_refused_by_name(self) -> None:
        candidate = _committed_manifest()
        invented = copy.deepcopy(candidate["criteria"][0])
        invented["criterion_key"] = "AC-PHANTOM-99"
        invented["criterion_source"] = ACCEPTANCE
        candidate["criteria"].append(invented)
        assert (
            "manifest declares unknown criterion acceptance-criterion/AC-PHANTOM-99"
            in _criterion_denominator_errors(candidate)
        )

    def test_duplicate_criterion_is_refused_by_name(self) -> None:
        candidate = _committed_manifest()
        repeated = copy.deepcopy(candidate["criteria"][0])
        repeated["reason"] = "a second disposition for the same criterion"
        candidate["criteria"].append(repeated)
        expected = (
            f"manifest repeats criterion {repeated['criterion_source']}/{repeated['criterion_key']}"
        )
        assert expected in _criterion_denominator_errors(candidate)

    def test_the_two_criterion_registries_never_share_a_key(self) -> None:
        shared = set(_gate_policy_criteria()) & set(_acceptance_criteria())
        assert not shared, f"criterion registries share keys: {sorted(shared)}"


class TestCriterionSchemaVectors:
    @pytest.mark.parametrize(
        ("field", "bad_value"),
        [
            ("criterion_source", "invented-registry"),
            ("disposition", "invalid"),
            ("disposition", ""),
            ("reason", ""),
            ("owner", ""),
            ("owner", "not-a-ticket"),
            ("source_sha", ""),
            ("environment", ""),
            ("proof_digest", "not-a-digest"),
            ("verifier", "not-a-uuid"),
        ],
    )
    def test_criterion_invalid_field_fails(self, field: str, bad_value: object) -> None:
        candidate = _committed_manifest()
        candidate["criteria"][0][field] = bad_value
        with pytest.raises(ValidationError):
            _validator().validate(candidate)

    def test_criterion_missing_required_field_fails(self) -> None:
        candidate = _committed_manifest()
        del candidate["criteria"][0]["verifier"]
        with pytest.raises(ValidationError):
            _validator().validate(candidate)

    def test_acceptance_code_under_the_gate_policy_source_fails(self) -> None:
        candidate = _committed_manifest()
        _criterion_row(candidate, GATE_POLICY)["criterion_key"] = "AC-ADM-01"
        with pytest.raises(ValidationError):
            _validator().validate(candidate)

    def test_gate_policy_key_under_the_acceptance_source_fails(self) -> None:
        candidate = _committed_manifest()
        _criterion_row(candidate, ACCEPTANCE)["criterion_key"] = "artifact-current"
        with pytest.raises(ValidationError):
            _validator().validate(candidate)


class TestCriterionMutationProof:
    """A criterion added to either registry makes the committed fixture RED by name."""

    def test_adding_a_frozen_gate_criterion_fails_by_name(self, tmp_path: Path) -> None:
        root = _scratch_registries(tmp_path)
        policy_path = root / _GATE_POLICY_DIR / "phantom-gate-v1.yaml"
        policy_path.write_text(
            json.dumps(
                {
                    "schema": "ctower.gate-policy/v1",
                    "key": "ctower.phantom.gates",
                    "revision": 1,
                    "criteria": [{"key": "phantom-gate-criterion", "description": "Phantom."}],
                }
            ),
            encoding="utf-8",
        )
        errors = _criterion_denominator_errors(_committed_manifest(), root)
        assert any("gate-policy/phantom-gate-criterion" in error for error in errors), errors

    def test_adding_an_acceptance_criterion_fails_by_name(self, tmp_path: Path) -> None:
        root = _scratch_registries(tmp_path)
        sources_path = root / _TRACEABILITY_SOURCES
        sources = json.loads(sources_path.read_text(encoding="utf-8"))
        sources["artifacts"].append(
            {"path": "contracts/phantom/phantom.schema.json", "references": ["AC-PHANTOM-01"]}
        )
        sources_path.write_text(json.dumps(sources), encoding="utf-8")
        errors = _criterion_denominator_errors(_committed_manifest(), root)
        assert any("acceptance-criterion/AC-PHANTOM-01" in error for error in errors), errors


def _scratch_registries(tmp_path: Path) -> Path:
    """A disposable copy of the criterion registries; the fixture stays untouched."""

    root = tmp_path / "repo"
    (root / _GATE_POLICY_DIR).mkdir(parents=True, exist_ok=True)
    for path in sorted((ROOT / _GATE_POLICY_DIR).glob("*.yaml")):
        (root / _GATE_POLICY_DIR / path.name).write_bytes(path.read_bytes())
    sources = root / _TRACEABILITY_SOURCES
    sources.parent.mkdir(parents=True, exist_ok=True)
    sources.write_bytes((ROOT / _TRACEABILITY_SOURCES).read_bytes())
    return root


# ---------------------------------------------------------------------------
# Acceptance 2 — deferred capabilities are keyed rows derived from the registry
# ---------------------------------------------------------------------------


class TestDeferredCapabilitiesDerivedFromRegistry:
    def test_manifest_deferred_capabilities_match_registry_exactly(self) -> None:
        """The manifest's deferred_capability keys must be exactly the union of
        capability registry keys and deferred expected-suite IDs — no more, no less."""

        registry_keys = _all_deferred_keys()
        manifest = _manifest()
        manifest_keys = {row["capability_key"] for row in manifest["deferred_capabilities"]}

        missing = registry_keys - manifest_keys
        extra = manifest_keys - registry_keys
        assert not missing, f"manifest omits registry entries: {sorted(missing)}"
        assert not extra, f"manifest declares unknown entries: {sorted(extra)}"

    def test_missing_registry_capability_fails_by_name(self) -> None:
        """If a capability exists in the registry but is absent from the manifest,
        the denominator check fails by naming the missing capability."""

        registry_keys = _all_deferred_keys()
        first_key = min(registry_keys)
        manifest = _manifest(deferred_keys=registry_keys - {first_key})
        manifest_keys = {row["capability_key"] for row in manifest["deferred_capabilities"]}
        missing = registry_keys - manifest_keys
        assert missing, "removing one capability must produce a missing set"
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
        registry_keys = _all_deferred_keys()
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
        assert _capability_registry_keys(), "capability registry is empty"

    def test_expected_suite_registry_has_at_least_one_deferred_suite(self) -> None:
        assert _deferred_suite_ids(), "expected-suite registry has no deferred suites"

    def test_no_fixed_four_name_roster_in_schema(self) -> None:
        """The schema must NOT hard-code a fixed four-name deferred list."""

        schema_text = _SCHEMA_PATH.read_text(encoding="utf-8")
        assert '"deferred_sources"' not in schema_text, (
            "schema must not contain the old fixed deferred_sources object"
        )
        assert '"remote"' not in schema_text
        assert '"images"' not in schema_text
        assert '"effects"' not in schema_text
        assert '"extensions"' not in schema_text


class TestCommittedFixtureDenominator:
    """Adding a capability YAML or a deferred suite WITHOUT updating the fixture makes
    this test RED by naming the missing entry."""

    def test_committed_manifest_deferred_capabilities_match_registry(self) -> None:
        registry_keys = _all_deferred_keys()
        manifest = _committed_manifest()
        manifest_keys = {row["capability_key"] for row in manifest["deferred_capabilities"]}

        missing = registry_keys - manifest_keys
        extra = manifest_keys - registry_keys
        assert not missing, f"fixture omits registry entries: {sorted(missing)}"
        assert not extra, f"fixture declares unknown entries: {sorted(extra)}"


class TestDeferredMutationProof:
    def test_adding_a_registry_capability_without_manifest_disposition_fails(
        self, tmp_path: Path
    ) -> None:
        """Add a capability in a scratch copy of the registry -> the denominator
        check goes RED until the manifest carries its disposition."""

        scratch_registry = tmp_path / "capabilities"
        scratch_registry.mkdir(exist_ok=True)
        for path in sorted(_CAPABILITIES_DIR.rglob("*.yaml")):
            target = scratch_registry / path.relative_to(_CAPABILITIES_DIR)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
        phantom_dir = scratch_registry / "phantom.capability"
        phantom_dir.mkdir(exist_ok=True)
        (phantom_dir / "v1.yaml").write_text(
            json.dumps({"schema": "ctower.capability/v1", "key": "phantom.capability"}),
            encoding="utf-8",
        )

        scratch_keys = {
            json.loads(path.read_text(encoding="utf-8"))["key"]
            for path in sorted(scratch_registry.rglob("*.yaml"))
        } | set(_deferred_suite_ids())
        manifest_keys = {
            row["capability_key"] for row in _committed_manifest()["deferred_capabilities"]
        }
        assert sorted(scratch_keys - manifest_keys) == ["phantom.capability"]

    def test_adding_a_deferred_suite_without_manifest_disposition_fails(
        self, tmp_path: Path
    ) -> None:
        """Add a deferred suite in a scratch copy of expected-suites.toml -> the
        denominator check goes RED until the manifest carries its disposition."""

        scratch_root = tmp_path / "repo"
        (scratch_root / "tools/checks").mkdir(parents=True, exist_ok=True)
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
        (scratch_root / _EXPECTED_SUITES).write_text(
            _EXPECTED_SUITES_PATH.read_text(encoding="utf-8") + extra_suite, encoding="utf-8"
        )

        scratch_keys = set(_capability_registry_keys()) | set(_deferred_suite_ids(scratch_root))
        manifest_keys = {
            row["capability_key"] for row in _committed_manifest()["deferred_capabilities"]
        }
        assert sorted(scratch_keys - manifest_keys) == ["phantom-suite"]
