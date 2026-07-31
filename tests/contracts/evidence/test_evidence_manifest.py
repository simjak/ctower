"""Evidence-manifest typed denominator contract vectors.

Both denominators are derived from registries of record, never from a hand-copied
roster and never from the manifest itself:

* criteria — the criteria frozen by the authored gate policies in
  ``packs/policies/gates`` plus every acceptance criterion ``SPEC.md`` declares.  Each
  row names the registry it came from, so the two namespaces never share a key space.
  The denominator is what this increment owes, not what it has already built:
  ``contracts/traceability/sources.json`` is a coverage map (``DECISIONS.md`` D17.8 —
  SPEC owns acceptance criteria; traceability proves coverage and drift only) and is
  deliberately not read here, so an obligation cannot leave the denominator because an
  artifact stopped citing it.
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
import inspect
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

from tools.checks import SuiteDisposition, verify_expected_suites

__all__: tuple[str, ...] = ()

_FORMAT_CHECKER = Draft202012Validator.FORMAT_CHECKER

ROOT = Path(__file__).parents[3]
GATE_POLICY_DIR = "packs/policies/gates"
SPEC = "SPEC.md"
EXPECTED_SUITES = "tools/checks/expected-suites.toml"
CAPABILITIES_DIR = "packs/components/capabilities"
_EXPECTED_SUITES_PATH = ROOT / EXPECTED_SUITES
_SCHEMA_PATH = ROOT / "contracts/evidence/evidence-manifest.schema.json"
_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "i1-complete-manifest.json"

GATE_POLICY = "gate-policy"
ACCEPTANCE = "acceptance-criterion"

# Shared verbatim with the traceability generator's `_ACCEPTANCE`, the authority that
# decides whether an AC code exists at all.  That module is private and a private import
# would breach the architecture boundary, so the copy is guarded instead: any drift
# between the two spellings is refused by name in TestCriterionDenominatorIsDerived.
_ACCEPTANCE_CODE = re.compile(r"</a>(AC-[A-Z0-9]+-[0-9]{2})\s+\|")


class RegistryError(AssertionError):
    """A registry of record cannot be read as a denominator source."""


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = YAML(typ="safe", pure=True).load(path.read_text(encoding="utf-8"))
    except (OSError, YAMLError) as error:
        raise RegistryError(f"{path}: unreadable registry entry: {error}") from error
    if not isinstance(data, dict):
        raise RegistryError(f"{path}: registry entry must be a mapping")
    return cast(dict[str, Any], data)


def gate_policy_criteria(root: Path = ROOT) -> dict[str, int]:
    """Frozen gate-policy criterion key -> the policy revision that freezes it."""

    frozen: dict[str, int] = {}
    for path in sorted((root / GATE_POLICY_DIR).glob("*.yaml")):
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


def acceptance_criteria(root: Path = ROOT) -> frozenset[str]:
    """Every acceptance criterion SPEC.md declares — what this increment owes."""

    path = root / SPEC
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as error:
        raise RegistryError(f"{path}: cannot read the acceptance table: {error}") from error
    codes = frozenset(_ACCEPTANCE_CODE.findall(source))
    if not codes:
        raise RegistryError(f"{path}: no anchored AC rows; the denominator would be vacuous")
    return codes


def criterion_denominator(root: Path = ROOT) -> frozenset[tuple[str, str]]:
    """The complete criterion denominator as (registry, key) pairs."""

    frozen = {(GATE_POLICY, key) for key in gate_policy_criteria(root)}
    if not frozen:
        raise RegistryError(f"{root / GATE_POLICY_DIR}: no gate policy freezes any criterion")
    return frozenset(frozen | {(ACCEPTANCE, code) for code in acceptance_criteria(root)})


def capability_registry_keys(root: Path = ROOT) -> frozenset[str]:
    """Capability component keys, read only so the namespace guard can prove disjointness."""

    keys: set[str] = set()
    for path in sorted((root / CAPABILITIES_DIR).rglob("*.yaml")):
        key = _load_yaml(path).get("key")
        if not isinstance(key, str):
            raise RegistryError(f"{path}: capability component has no string key")
        if key in keys:
            raise RegistryError(f"{path}: duplicate capability key {key!r}")
        keys.add(key)
    return frozenset(keys)


def _suites(root: Path = ROOT) -> list[dict[str, Any]]:
    path = root / EXPECTED_SUITES
    suites = tomllib.loads(path.read_text(encoding="utf-8")).get("suite")
    if not isinstance(suites, list):
        raise RegistryError(f"{path}: 'suite' must be a list")
    return cast(list[dict[str, Any]], suites)


def suite_registry_ids(root: Path = ROOT) -> frozenset[str]:
    """Every suite id the expected-suite registry declares, deferred or not."""

    return frozenset(suite["id"] for suite in _suites(root))


def deferred_suites(root: Path = ROOT) -> dict[str, str]:
    """Deferred suite id -> the phase the expected-suite registry defers it to."""

    deferred = {
        suite["id"]: suite["phase"] for suite in _suites(root) if suite["status"] == "deferred"
    }
    if not deferred:
        raise RegistryError(
            f"{root / EXPECTED_SUITES}: no deferred suite; the denominator would be vacuous"
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

    denominator = criterion_denominator(root)
    pairs = _criterion_pairs(manifest)
    declared = set(pairs)
    repeats = _duplicates(f"{source}/{key}" for source, key in pairs)
    omits = sorted(f"{source}/{key}" for source, key in denominator - declared)
    unknown = sorted(f"{source}/{key}" for source, key in declared - denominator)
    return (
        [f"manifest repeats criterion {name}" for name in repeats]
        + [f"manifest omits registry criterion {name}" for name in omits]
        + [f"manifest declares unknown criterion {name}" for name in unknown]
    )


def _deferred_suite_errors(manifest: dict[str, Any], root: Path = ROOT) -> list[str]:
    """CHOKEPOINT: every disagreement between a manifest and the deferred-suite registry."""

    denominator = set(deferred_suites(root))
    declared = [row["suite_id"] for row in manifest["deferred_suites"]]
    omits = sorted(denominator - set(declared))
    unknown = sorted(set(declared) - denominator)
    return (
        [f"manifest repeats deferred suite {name}" for name in _duplicates(declared)]
        + [f"manifest omits deferred suite {name}" for name in omits]
        + [f"manifest declares unknown deferred suite {name}" for name in unknown]
    )


def _schema() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")))


def _schema_nodes(schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Every subschema object, so a roster is found wherever it tries to live."""

    nodes: list[dict[str, Any]] = []
    stack: list[Any] = [schema]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            nodes.append(node)
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return nodes


def _schema_names(schema: dict[str, Any]) -> set[str]:
    """Every name the schema fixes: property names, required entries, consts and enums."""

    names: set[str] = set()
    for node in _schema_nodes(schema):
        names |= set(node.get("properties", {}))
        names |= {item for item in node.get("required", []) if isinstance(item, str)}
        names |= {item for item in node.get("enum", []) if isinstance(item, str)}
        if isinstance(node.get("const"), str):
            names.add(node["const"])
    return names


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
        revisions = set(gate_policy_criteria().values())
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
        shared = set(gate_policy_criteria()) & set(acceptance_criteria())
        assert not shared, f"criterion registries share keys: {sorted(shared)}"


class TestSchemaEnforcesTheDenominatorContract:
    """Emptiness and repetition are illegal in the contract, not only in one test."""

    @pytest.mark.parametrize("array", ["criteria", "verdict_ids", "deferred_suites"])
    def test_empty_array_is_refused_by_the_schema(self, array: str) -> None:
        candidate = _committed_manifest()
        candidate[array] = []
        with pytest.raises(ValidationError):
            _validator().validate(candidate)

    @pytest.mark.parametrize("array", ["criteria", "deferred_suites"])
    def test_identical_repeated_row_is_refused_by_the_schema(self, array: str) -> None:
        candidate = _committed_manifest()
        candidate[array].append(copy.deepcopy(candidate[array][0]))
        with pytest.raises(ValidationError):
            _validator().validate(candidate)

    def test_repeated_verdict_id_is_refused_by_the_schema(self) -> None:
        candidate = _committed_manifest()
        candidate["verdict_ids"].append(candidate["verdict_ids"][0])
        with pytest.raises(ValidationError):
            _validator().validate(candidate)

    def test_a_repeated_key_with_a_different_payload_is_refused_by_the_chokepoints(self) -> None:
        """JSON Schema 2020-12 cannot express uniqueness by key; the chokepoints do,
        and this vector proves the seam is covered rather than assumed."""

        candidate = _committed_manifest()
        criterion = copy.deepcopy(candidate["criteria"][0])
        criterion["reason"] = "a second disposition for the same criterion"
        candidate["criteria"].append(criterion)
        suite = copy.deepcopy(candidate["deferred_suites"][0])
        suite["reason"] = "a second row for the same suite"
        candidate["deferred_suites"].append(suite)

        _validator().validate(candidate)
        assert _criterion_denominator_errors(candidate) == [
            f"manifest repeats criterion {criterion['criterion_source']}/"
            f"{criterion['criterion_key']}"
        ]
        assert _deferred_suite_errors(candidate) == [
            f"manifest repeats deferred suite {suite['suite_id']}"
        ]


class TestCriterionSchemaVectors:
    @pytest.mark.parametrize(
        ("field", "bad_value"),
        [
            ("criterion_source", "invented-registry"),
            ("disposition", "invalid"),
            ("reason", ""),
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
        criterion = {"key": "phantom-gate-criterion", "description": "Phantom."}
        policy = {"schema": "ctower.gate-policy/v1", "revision": 1, "criteria": [criterion]}
        (root / GATE_POLICY_DIR / "phantom-v1.yaml").write_text(json.dumps(policy), "utf-8")
        errors = _criterion_denominator_errors(_committed_manifest(), root)
        assert any("gate-policy/phantom-gate-criterion" in error for error in errors), errors

    def test_declaring_an_acceptance_criterion_in_spec_fails_by_name(self, tmp_path: Path) -> None:
        root = _scratch_registries(tmp_path, spec_extra=_SPEC_ROW.format(code="AC-PHANTOM-01"))
        errors = _criterion_denominator_errors(_committed_manifest(), root)
        assert any("acceptance-criterion/AC-PHANTOM-01" in error for error in errors), errors


_SPEC_ROW = '\n| <a id="phantom"></a>{code} | Phantom obligation. | Phantom proof |\n'


def _scratch_registries(tmp_path: Path, *, spec_extra: str = "") -> Path:
    """A disposable copy of the criterion registries; the fixture stays untouched.

    The coverage map is deliberately never copied: nothing here may read it."""

    root = tmp_path / "repo"
    (root / GATE_POLICY_DIR).mkdir(parents=True, exist_ok=True)
    for path in sorted((ROOT / GATE_POLICY_DIR).glob("*.yaml")):
        (root / GATE_POLICY_DIR / path.name).write_bytes(path.read_bytes())
    spec = (ROOT / SPEC).read_text(encoding="utf-8")
    (root / SPEC).write_text(spec + spec_extra, encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# Acceptance 2 — deferred suites are keyed rows derived from the suite registry
# ---------------------------------------------------------------------------


class TestDeferredSuiteDenominatorIsDerived:
    """The deferred denominator is the deferred suites of the expected-suite registry."""

    def test_committed_manifest_deferred_suites_match_the_registry_exactly(self) -> None:
        assert _deferred_suite_errors(_committed_manifest()) == []

    def test_every_row_names_the_phase_the_registry_defers_it_to(self) -> None:
        deferred = deferred_suites()
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
        row = {"suite_id": "phantom-suite", "status": "not_exercised", "source_count": 0}
        candidate["deferred_suites"].append({**row, "reason": "fabricated"})
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
        assert deferred_suites(), "expected-suite registry declares no deferred suite"

    @pytest.mark.parametrize(("field", "bad_value"), [("status", "exercised"), ("source_count", 1)])
    def test_a_deferred_row_stays_not_exercised_with_zero_sources(
        self, field: str, bad_value: object
    ) -> None:
        candidate = _committed_manifest()
        candidate["deferred_suites"][0][field] = bad_value
        with pytest.raises(ValidationError):
            _validator().validate(candidate)


class TestNamespacesStaySeparate:
    """Suite ids, capability keys and criterion keys are three registries, never one
    key space: a capability that is exercised must never be forced to declare itself
    unexercised because something else reused its name."""

    def test_no_capability_key_is_a_deferred_suite_id(self) -> None:
        shared = capability_registry_keys() & set(deferred_suites())
        assert not shared, f"suite ids collide with capability keys: {sorted(shared)}"

    def test_no_capability_is_forced_to_declare_itself_unexercised(self) -> None:
        declared = {row["suite_id"] for row in _committed_manifest()["deferred_suites"]}
        forced = capability_registry_keys() & declared
        assert not forced, f"capabilities declared not_exercised: {sorted(forced)}"

    def test_every_registry_suite_id_matches_the_schema_suite_namespace(self) -> None:
        pattern = re.compile(_schema()["$defs"]["suiteId"]["pattern"])
        for suite_id in suite_registry_ids():
            assert pattern.fullmatch(suite_id), f"{suite_id}: outside the suite-id namespace"

    def test_a_capability_key_is_refused_in_the_suite_namespace(self) -> None:
        candidate = _committed_manifest()
        candidate["deferred_suites"][0]["suite_id"] = min(capability_registry_keys())
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
    (root / EXPECTED_SUITES).parent.mkdir(parents=True, exist_ok=True)
    extra = f"""
[[suite]]
id = "phantom-suite"
owner = "CT-I2-099"
phase = "CT-I2-099"
status = "{status}"
path = "tests/phantom"
patterns = ["test_*.py"]
command = ["{{python}}", "-m", "pytest", "tests/phantom", "-q"]
timeout_seconds = 300
"""
    (root / EXPECTED_SUITES).write_text(
        _EXPECTED_SUITES_PATH.read_text(encoding="utf-8") + extra, encoding="utf-8"
    )
    return root


# ---------------------------------------------------------------------------
# The chokepoints, the registries they read, and the shape of the schema
# ---------------------------------------------------------------------------

_CHOKEPOINTS: tuple[tuple[str, str], ...] = (
    ("_criterion_denominator_errors", "TestCriterionDenominatorIsDerived"),
    ("_deferred_suite_errors", "TestDeferredSuiteDenominatorIsDerived"),
)


class TestChokepointsCannotBeSilentlyRemoved:
    """Each denominator has exactly one named chokepoint and one guard over the
    committed fixture.  Deleting either makes this RED by name instead of quietly
    dropping the only assertion that proves the denominator is derived."""

    @pytest.mark.parametrize(("chokepoint", "guard"), _CHOKEPOINTS)
    def test_the_chokepoint_and_its_guard_both_survive(self, chokepoint: str, guard: str) -> None:
        assert callable(globals().get(chokepoint)), f"{chokepoint}: chokepoint is gone"
        assert guard in globals(), f"{guard}: the guard over the committed fixture is gone"
        source = inspect.getsource(cast(type, globals()[guard]))
        assert f"{chokepoint}(_committed_manifest())" in source, (
            f"{guard}: no longer judges the committed fixture through {chokepoint}"
        )

    def test_no_denominator_is_built_from_the_manifest_under_test(self) -> None:
        """The registries never read the fixture, so a manifest cannot widen its own
        denominator by declaring an extra row."""

        for registry in (criterion_denominator, deferred_suites, capability_registry_keys):
            source = inspect.getsource(registry)
            assert "_committed_manifest" not in source, f"{registry.__name__}: reads the manifest"
            assert str(_FIXTURE_PATH.name) not in source, f"{registry.__name__}: reads the fixture"


class TestDeferredRegistryIsTheOneTheRuntimeReads:
    """The deferred denominator is not a private glob: it is exactly the set of suites
    the repository's own verification gate refuses to count as passing."""

    def test_the_denominator_matches_the_runtime_suite_gate(self) -> None:
        report = verify_expected_suites(ROOT)
        assert not report.manifest_errors, report.manifest_errors
        not_yet_required = {
            suite.suite_id
            for suite in report.suites
            if suite.disposition is SuiteDisposition.NOT_YET_REQUIRED
        }
        assert set(deferred_suites()) == not_yet_required


class TestSchemaCarriesNoRoster:
    """Structural, not textual: a roster is refused wherever it tries to live."""

    def test_no_denominator_member_name_appears_in_the_schema(self) -> None:
        members = (
            {key for _, key in criterion_denominator()}
            | set(deferred_suites())
            | capability_registry_keys()
        )
        leaked = members & _schema_names(_schema())
        assert not leaked, f"the schema hard-codes denominator members: {sorted(leaked)}"

    @pytest.mark.parametrize("array", ["criteria", "deferred_suites"])
    def test_the_denominator_array_is_dynamic_and_constrained(self, array: str) -> None:
        declared = _schema()["properties"][array]
        assert "items" in declared, f"{array}: has no dynamic item schema"
        assert "prefixItems" not in declared, f"{array}: pins its rows by position"
        assert "maxItems" not in declared, f"{array}: pins the size of the denominator"
        assert declared["minItems"] == 1, f"{array}: emptiness is legal"
        assert declared["uniqueItems"] is True, f"{array}: an identical row may repeat"

    def test_the_removed_four_name_roster_cannot_return_as_an_object(self) -> None:
        roster = {"remote", "images", "effects", "extensions"}
        for node in _schema_nodes(_schema()):
            assert set(node.get("properties", {})) != roster, "the four-name roster is back"
        assert "deferred_sources" not in _schema_names(_schema())


class TestRegistryFailuresAreNamed:
    """A registry that cannot be read refuses by naming the file, never by crashing
    the whole suite with a decoder error."""

    def test_a_genuinely_yaml_capability_entry_is_read(self, tmp_path: Path) -> None:
        entry = tmp_path / CAPABILITIES_DIR / "yaml.written" / "v1.yaml"
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text("schema: ctower.capability/v1\nkey: yaml.written\n", encoding="utf-8")
        assert capability_registry_keys(tmp_path) == frozenset({"yaml.written"})

    @pytest.mark.parametrize("body", ["key: [unclosed\n", "schema: ctower.capability/v1\n"])
    def test_an_unreadable_capability_entry_fails_by_name(self, tmp_path: Path, body: str) -> None:
        entry = tmp_path / CAPABILITIES_DIR / "broken.entry" / "v1.yaml"
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(body, encoding="utf-8")
        with pytest.raises(RegistryError, match=re.escape(str(entry))):
            capability_registry_keys(tmp_path)

    def test_a_gate_policy_without_a_revision_fails_by_name(self, tmp_path: Path) -> None:
        policy = tmp_path / GATE_POLICY_DIR / "unrevisioned-v1.yaml"
        policy.parent.mkdir(parents=True, exist_ok=True)
        policy.write_text("schema: ctower.gate-policy/v1\ncriteria: []\n", encoding="utf-8")
        with pytest.raises(RegistryError, match=re.escape(str(policy))):
            gate_policy_criteria(tmp_path)
