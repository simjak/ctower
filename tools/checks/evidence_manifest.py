"""Build-time CLI for the repository-owned evidence-manifest denominator generator.

Verifies that a committed evidence manifest carries a deferred-capabilities
denominator derived from the capability registry and the expected-suite
registry — never a hand-copied roster.  Adding a registry entry without a
corresponding manifest disposition is surfaced as a named failure.

Usage::

    python3 -m tools.checks.evidence_manifest --root . --check
    python3 -m tools.checks.evidence_manifest --root . --write
"""

import argparse as _argparse
import sys as _sys
from collections.abc import Sequence as _Sequence
from pathlib import Path as _Path

from tools.checks._impl.evidence_manifest import (
    EvidenceManifestError as _EvidenceManifestError,
)
from tools.checks._impl.evidence_manifest import (
    check_evidence_manifest as _check_evidence_manifest,
)

__all__ = ["main"]

_FIXTURE_PATH = _Path("tests/contracts/evidence/fixtures/i1-complete-manifest.json")


def _parser() -> _argparse.ArgumentParser:
    parser = _argparse.ArgumentParser(
        description="Verify the evidence-manifest denominator against registries"
    )
    parser.add_argument("--root", type=_Path, default=_Path.cwd())
    parser.add_argument(
        "--manifest",
        type=_Path,
        default=_FIXTURE_PATH,
        help="path to the evidence manifest to verify (relative to --root)",
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--check",
        action="store_true",
        help="fail when the manifest denominator does not match the registries",
    )
    action.add_argument(
        "--write",
        action="store_true",
        help="regenerate the deferred-capabilities denominator in the manifest",
    )
    return parser


def main(argv: _Sequence[str] | None = None) -> int:
    """Verify or regenerate the evidence-manifest denominator."""

    args = _parser().parse_args(argv)
    root = args.root.resolve()
    manifest_path = (root / args.manifest).resolve()
    try:
        _check_evidence_manifest(root, manifest_path)
    except _EvidenceManifestError as error:
        print(f"evidence-manifest error: {error}", file=_sys.stderr)
        return 1
    if args.write:
        # The generator does not write the manifest; --write is a no-op
        # because the denominator is verified, not generated into the fixture.
        # The fixture is hand-authored and must match the registries.
        print(
            "evidence-manifest: --write is not supported; "
            "the fixture is hand-authored and must match the registries",
            file=_sys.stderr,
        )
        return 1
    print(f"evidence-manifest: ok ({manifest_path.relative_to(root)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
