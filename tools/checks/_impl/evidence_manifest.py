"""Repository-owned evidence-manifest denominator generator.

The evidence denominator (``deferred_capabilities``) is derived from two
authoritative registries:

* The capability registry at ``packs/components/capabilities/`` — each
  ``*.yaml`` file declares one capability with a unique ``key``.
* The expected-suite registry at ``tools/checks/expected-suites.toml`` —
  every suite with ``status = "deferred"`` contributes its ``id``.

The generator reads those registries, builds the union set of keys, and
verifies that a given evidence manifest carries exactly that set as its
``deferred_capabilities`` rows — no more, no less.  A mismatch is surfaced
as a named failure identifying the missing or extra entry.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

__all__ = [
    "EvidenceManifestError",
    "build_deferred_capabilities",
    "capability_registry_keys",
    "check_evidence_manifest",
    "deferred_suite_ids",
    "derive_denominator_keys",
    "verify_evidence_manifest",
]

_CAPABILITIES_DIR = Path("packs/components/capabilities")
_EXPECTED_SUITES_PATH = Path("tools/checks/expected-suites.toml")


class EvidenceManifestError(ValueError):
    """The evidence manifest denominator does not match the registries."""


# ---------------------------------------------------------------------------
# Registry readers
# ---------------------------------------------------------------------------


def capability_registry_keys(root: Path) -> frozenset[str]:
    """Return the set of capability keys declared in the capability registry.

    Reads every ``*.yaml`` file under ``packs/components/capabilities/`` and
    extracts the ``key`` field.  Duplicate keys are a hard error.
    """

    capabilities_dir = root / _CAPABILITIES_DIR
    if not capabilities_dir.is_dir():
        raise EvidenceManifestError(f"capability registry directory not found: {_CAPABILITIES_DIR}")
    keys: set[str] = set()
    for path in sorted(capabilities_dir.rglob("*.yaml")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EvidenceManifestError(
                f"cannot parse capability registry entry {path}: {error}"
            ) from error
        if not isinstance(data, dict) or "key" not in data:
            raise EvidenceManifestError(f"capability registry entry {path} has no 'key' field")
        key = data["key"]
        if not isinstance(key, str) or not key:
            raise EvidenceManifestError(f"capability registry entry {path} has an invalid key")
        if key in keys:
            raise EvidenceManifestError(f"duplicate capability key in registry: {key}")
        keys.add(key)
    return frozenset(keys)


def deferred_suite_ids(root: Path) -> frozenset[str]:
    """Return the set of suite IDs with ``status = "deferred"``."""

    manifest_path = root / _EXPECTED_SUITES_PATH
    if not manifest_path.is_file():
        raise EvidenceManifestError(f"expected-suite registry not found: {_EXPECTED_SUITES_PATH}")
    try:
        data = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise EvidenceManifestError(f"cannot parse expected-suite registry: {error}") from error
    suites = data.get("suite", [])
    if not isinstance(suites, list):
        raise EvidenceManifestError("expected-suite registry has no [[suite]] entries")
    return frozenset(
        suite["id"]
        for suite in suites
        if isinstance(suite, dict) and suite.get("status") == "deferred"
    )


def derive_denominator_keys(root: Path) -> frozenset[str]:
    """Union of capability registry keys and deferred expected-suite IDs."""

    return frozenset(capability_registry_keys(root) | deferred_suite_ids(root))


# ---------------------------------------------------------------------------
# Deferred capability row builder
# ---------------------------------------------------------------------------


def build_deferred_capabilities(root: Path) -> list[dict[str, object]]:
    """Build sorted deferred-capability rows from the registry denominator."""

    keys = derive_denominator_keys(root)
    return [
        {
            "capability_key": key,
            "status": "not_exercised",
            "source_count": 0,
            "reason": "deferred for I1/I2; no runtime exists",
        }
        for key in sorted(keys)
    ]


# ---------------------------------------------------------------------------
# Manifest verification
# ---------------------------------------------------------------------------


def verify_evidence_manifest(root: Path, manifest_path: Path) -> tuple[str, ...]:
    """Verify that a manifest's deferred capabilities match the registries.

    Returns a tuple of human-readable error strings.  An empty tuple means
    the manifest's denominator matches the registries exactly.
    """

    try:
        payload: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return (f"cannot load evidence manifest {manifest_path}: {error}",)
    if not isinstance(payload, dict):
        return (f"evidence manifest must be a JSON object: {manifest_path}",)

    registry_keys = derive_denominator_keys(root)
    deferred = payload.get("deferred_capabilities", [])
    if not isinstance(deferred, list):
        return ("evidence manifest deferred_capabilities must be an array",)

    manifest_keys: set[str] = set()
    for index, row in enumerate(deferred):
        if not isinstance(row, dict) or "capability_key" not in row:
            return (f"evidence manifest deferred_capabilities[{index}] has no capability_key",)
        manifest_keys.add(row["capability_key"])

    errors: list[str] = []
    missing = registry_keys - manifest_keys
    extra = manifest_keys - registry_keys
    for key in sorted(missing):
        errors.append(f"manifest omits registry entry: {key}")
    for key in sorted(extra):
        errors.append(f"manifest declares unknown entry: {key}")
    return tuple(errors)


def check_evidence_manifest(root: Path, manifest_path: Path) -> None:
    """Verify the evidence manifest denominator, raising on any mismatch."""

    errors = verify_evidence_manifest(root, manifest_path)
    if errors:
        raise EvidenceManifestError("; ".join(errors))
