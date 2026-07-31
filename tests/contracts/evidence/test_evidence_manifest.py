"""Evidence-manifest typed denominator contract vectors.

Both denominators are derived from registries of record, never from a hand-copied
roster and never from the manifest itself:

* criteria — the criteria frozen by the authored gate policies in
  ``packs/policies/gates`` plus the acceptance-criterion codes the traceability
  generator reads out of ``contracts/traceability/sources.json``.  Each row names the
  registry it came from, so the two namespaces never share a key space.
* deferred suites — the ``status = "deferred"`` suites of the expected-suite registry
  in ``tools/checks/expected-suites.toml``.  Capability components are deliberately
  not a denominator source: an exercised capability must never be forced to declare
  itself unexercised, and suite ids never share the capability key space.

``_criterion_denominator_errors`` and ``_deferred_suite_errors`` are the two
chokepoints: they are the only places that decide whether the committed manifest
agrees with its registries, and each names every missing, unknown, and duplicated
entry.  Neither reads the manifest to build the denominator, so a manifest can never
widen its own denominator.
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


def _suites(root: Path = ROOT) -> list[dict[str, Any]]:
    path = root / _EXPECTED_SUITES
    suites = tomllib.loads(path.read_text(encoding="utf-8")).get("suite")
    if not isinstance(suites, list):
        raise RegistryError(f"{path}: 'suite' must be a list")
    return cast(list[dict[str, Any]], suites)


def _suite_registry_ids(root: Path = ROOT) -> frozenset[str]:
    """Every suite id the expected-suite registry declares, deferred or not."""

    return frozenset(suite["id"] for suite in _suites(root))


def _deferred_suites(root: Path = ROOT) -> dict[str, str]:
    """Deferred suite id -> the phase the expected-suite registry defers it to."""

    deferred = {
        suite["id"]: suite["phase"] for suite in _suites(root) if suite["status"] == "deferred"
    }
    if not deferred:
        raise RegistryError(
            f"{root / _EXPECTED_SUITES}: no deferred suite; the denominator would be vacuous"
        )
    return deferred


# ---------------------------------------------------------------------------
# The committed manifest and the chokepoint that judges it
# ---------------------------------------------------------------------------


def _committed_manifest() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(_FIXTURE_PATH.read_text(encoding="utf-8")))


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


def _deferred_suite_errors(manifest: dict[str, Any], root: Path = ROOT) -> list[str]:
    """CHOKEPOINT: every disagreement between a manifest and the deferred-suite registry."""

    denominator = set(_deferred_suites(root))
    declared = [row["suite_id"] for row in manifest["deferred_suites"]]
    errors = [f"manifest repeats deferred suite {name}" for name in _duplicates(declared)]
    errors += [
        f"manifest omits deferred suite {name}" for name in sorted(denominator - set(declared))
    ]
    errors += [
        f"manifest declares unknown deferred suite {name}"
        for name in sorted(set(declared) - denominator)
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
# Acceptance 2 — deferred suites are keyed rows derived from the suite registry
# ---------------------------------------------------------------------------


class TestDeferredSuiteDenominatorIsDerived:
    """The deferred denominator is the deferred suites of the expected-suite registry."""

    def test_committed_manifest_deferred_suites_match_the_registry_exactly(self) -> None:
        assert _deferred_suite_errors(_committed_manifest()) == []

    def test_every_row_names_the_phase_the_registry_defers_it_to(self) -> None:
        deferred = _deferred_suites()
        for row in _committed_manifest()["deferred_suites"]:
            phase = deferred[row["suite_id"]]
            assert phase in row["reason"], f"{row['suite_id']}: reason omits phase {phase}"

    def test_missing_deferred_suite_is_refused_by_name(self) -> None:
        candidate = _committed_manifest()
        dropped = candidate["deferred_suites"].pop()
        expected = f"manifest omits deferred suite {dropped['suite_id']}"
        assert expected in _deferred_suite_errors(candidate)

    def test_extra_deferred_suite_is_refused_by_name(self) -> None:
        candidate = _committed_manifest()
        candidate["deferred_suites"].append(
            {
                "suite_id": "phantom-suite",
                "status": "not_exercised",
                "source_count": 0,
                "reason": "fabricated",
            }
        )
        assert "manifest declares unknown deferred suite phantom-suite" in _deferred_suite_errors(
            candidate
        )

    def test_duplicate_deferred_suite_is_refused_by_name(self) -> None:
        candidate = _committed_manifest()
        repeated = copy.deepcopy(candidate["deferred_suites"][0])
        repeated["reason"] = "a second row for the same suite"
        candidate["deferred_suites"].append(repeated)
        expected = f"manifest repeats deferred suite {repeated['suite_id']}"
        assert expected in _deferred_suite_errors(candidate)

    def test_registry_is_not_vacuous(self) -> None:
        assert _deferred_suites(), "expected-suite registry declares no deferred suite"

    def test_deferred_suite_must_be_not_exercised_with_zero_sources(self) -> None:
        candidate = _committed_manifest()
        candidate["deferred_suites"][0]["status"] = "exercised"
        with pytest.raises(ValidationError):
            _validator().validate(candidate)

    def test_deferred_suite_source_count_must_be_zero(self) -> None:
        candidate = _committed_manifest()
        candidate["deferred_suites"][0]["source_count"] = 1
        with pytest.raises(ValidationError):
            _validator().validate(candidate)


class TestNamespacesStaySeparate:
    """Suite ids, capability keys and criterion keys are three registries, never one
    key space: a capability that is exercised must never be forced to declare itself
    unexercised because something else reused its name."""

    def test_no_capability_key_is_a_deferred_suite_id(self) -> None:
        shared = _capability_registry_keys() & set(_deferred_suites())
        assert not shared, f"suite ids collide with capability keys: {sorted(shared)}"

    def test_no_capability_is_forced_to_declare_itself_unexercised(self) -> None:
        capabilities = _capability_registry_keys()
        declared = {row["suite_id"] for row in _committed_manifest()["deferred_suites"]}
        assert not capabilities & declared, (
            f"capabilities declared not_exercised: {sorted(capabilities & declared)}"
        )

    def test_every_registry_suite_id_matches_the_schema_suite_namespace(self) -> None:
        pattern = re.compile(_schema()["$defs"]["suiteId"]["pattern"])
        for suite_id in _suite_registry_ids():
            assert pattern.fullmatch(suite_id), f"{suite_id}: outside the suite-id namespace"

    def test_a_capability_key_is_refused_in_the_suite_namespace(self) -> None:
        candidate = _committed_manifest()
        candidate["deferred_suites"][0]["suite_id"] = min(_capability_registry_keys())
        with pytest.raises(ValidationError):
            _validator().validate(candidate)


class TestDeferredSuiteMutationProof:
    """A suite deferred in the registry makes the committed fixture RED by name."""

    def test_adding_a_deferred_suite_without_a_disposition_fails_by_name(
        self, tmp_path: Path
    ) -> None:
        root = _scratch_suite_registry(tmp_path, status="deferred")
        errors = _deferred_suite_errors(_committed_manifest(), root)
        assert any("phantom-suite" in error for error in errors), errors

    def test_a_suite_that_is_not_deferred_stays_out_of_the_denominator(
        self, tmp_path: Path
    ) -> None:
        root = _scratch_suite_registry(tmp_path, status="required")
        assert _deferred_suite_errors(_committed_manifest(), root) == []


def _scratch_suite_registry(tmp_path: Path, *, status: str) -> Path:
    """A disposable copy of the suite registry carrying one extra suite."""

    root = tmp_path / "repo"
    (root / _EXPECTED_SUITES).parent.mkdir(parents=True, exist_ok=True)
    extra = (
        "\n[[suite]]\n"
        'id = "phantom-suite"\n'
        'owner = "CT-I2-099"\n'
        'phase = "CT-I2-099"\n'
        f'status = "{status}"\n'
        'path = "tests/phantom"\n'
        'patterns = ["test_*.py"]\n'
        'command = ["{python}", "-m", "pytest", "tests/phantom", "-q"]\n'
        "timeout_seconds = 300\n"
    )
    (root / _EXPECTED_SUITES).write_text(
        _EXPECTED_SUITES_PATH.read_text(encoding="utf-8") + extra, encoding="utf-8"
    )
    return root
