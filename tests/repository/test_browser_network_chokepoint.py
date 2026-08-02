"""Fail-closed discovery of the browser boundary's crossings and its honesty rules.

`docs/CODING_STANDARDS.md` (O10) forbids single-shot network requests, loopback
services included, and requires coverage to be derived from repository
structure rather than from a hand-maintained endpoint list. These tests build
the denominator by scanning every authored and generated TypeScript module for
network-capable constructs, then require each discovered site to sit in an
approved policy holder. An unclassifiable site fails the gate.

Three further discoveries run the same way, each fail-closed:

* an unreachable source must render as unreachable, never as empty, so a
  `Reading` may only be inspected inside the read layer and the one component
  that renders its non-present states;
* this surface reads other repositories' live files, so no module under `apps/`
  may call a filesystem write, and
* every interim source renders text authored elsewhere, so each one must pass it
  through the redaction list before a screen can see it.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCANNED_ROOTS = ("apps", "generated/typescript")
_SUFFIXES = (".ts", ".tsx")

# Constructs that can open a process or network boundary from TypeScript.
_NETWORK_PATTERN = re.compile(
    r"\bfetch\s*\(|\bXMLHttpRequest\b|\bWebSocket\b|\bEventSource\b|\bsendBeacon\b"
    r"|\bnavigator\.connection\b|\baxios\b|\bnode-fetch\b|\bundici\b|\bhttps?\.request\s*\("
    # A child process is a boundary crossing too, and O10 names it. The module
    # specifier is the anchor: Node cannot create a process without one of
    # these, so the denominator cannot be dodged by aliasing a call.
    r"|node:child_process|node:worker_threads|node:cluster"
    r"|\bexecFileSync\b|\bexecSync\b|\bspawnSync\b|\bchild_process\b"
)
# Filesystem writes. This app reads another repository's live state; it may not
# write, lock, truncate, rename or remove anything, anywhere.
_WRITE_PATTERN = re.compile(
    r"\bwriteFile\b|\bwriteFileSync\b|\bappendFile\b|\bappendFileSync\b|\bcreateWriteStream\b"
    r"|\bunlinkSync?\b|\brmdir\b|\brmSync\b|\bmkdirSync?\b|\brenameSync?\b|\btruncate\b|\bchmodSync?\b"
)
_READING_PATTERN = re.compile(r"\.state\s*(?:===|!==)|\breading\.(?:value|failure|source)\b")
_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

# The approved holders. Each entry is a path and the reason it may hold the site.
_NETWORK_POLICY_HOLDERS = {
    "apps/ctower-ui/src/read/bounded.ts": (
        "the boundary's single bounded-retry chokepoint: per-attempt timeout, "
        "finite attempts and deadline, jittered capped backoff, typed predicate, "
        "typed exhaustion"
    ),
    "generated/typescript/ctower-client/src/client.ts": (
        "the generated client; unreachable at runtime from this repository's "
        "applications, which is asserted separately below"
    ),
}
_READING_HOLDERS = (
    "apps/ctower-ui/src/read/",
    "apps/ctower-ui/src/frame/Declared.tsx",
)
_CHOKEPOINT = "apps/ctower-ui/src/read/bounded.ts"
_SOURCE_DIRECTORY = "apps/ctower-ui/src/read/sources/"
# Helpers in the source directory that carry no foreign text of their own.
_SOURCE_HELPERS = frozenset(
    {
        f"{_SOURCE_DIRECTORY}redact.ts",
        f"{_SOURCE_DIRECTORY}paths.ts",
        f"{_SOURCE_DIRECTORY}jsonl.ts",
        f"{_SOURCE_DIRECTORY}cadenceHealth.ts",
    }
)

# Every O10 property must remain visible in the chokepoint, by name.
_REQUIRED_BOUNDS = (
    "attemptTimeoutMs",
    "maxAttempts",
    "maxElapsedMs",
    "baseDelayMs",
    "maxDelayMs",
    "AbortSignal.timeout",
    "ReadExhausted",
    "ReadRefused",
    "failureClass",
)


def _sources() -> tuple[Path, ...]:
    found: list[Path] = []
    for root in _SCANNED_ROOTS:
        base = _ROOT / root
        if not base.is_dir():
            continue
        found.extend(
            path
            for path in base.rglob("*")
            if path.suffix in _SUFFIXES
            and path.is_file()
            and "node_modules" not in path.parts
            and ".next" not in path.parts
        )
    return tuple(sorted(found))


def _code(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", text))


def _relative(path: Path) -> str:
    return path.relative_to(_ROOT).as_posix()


def _matching(pattern: re.Pattern[str]) -> tuple[str, ...]:
    return tuple(_relative(path) for path in _sources() if pattern.search(_code(path)))


class BrowserNetworkChokepointTests(unittest.TestCase):
    """O10 coverage and honest-state coverage, both derived from the tree."""

    def test_the_scan_finds_a_non_empty_denominator(self) -> None:
        discovered = _sources()
        self.assertGreater(len(discovered), 10, "the TypeScript scan found almost nothing")
        self.assertIn(_CHOKEPOINT, {_relative(path) for path in discovered})

    def test_every_network_call_site_sits_in_an_approved_policy_holder(self) -> None:
        unclassified = sorted(set(_matching(_NETWORK_PATTERN)) - set(_NETWORK_POLICY_HOLDERS))
        self.assertEqual(
            unclassified,
            [],
            "a network-capable call site appeared outside an approved O10 policy holder; "
            "route it through apps/ctower-ui/src/read/bounded.ts or classify it here",
        )

    def test_the_chokepoint_still_declares_every_required_bound(self) -> None:
        code = _code(_ROOT / _CHOKEPOINT)
        missing = [name for name in _REQUIRED_BOUNDS if name not in code]
        self.assertEqual(missing, [], "the bounded-read policy lost a required O10 property")

    def test_the_generated_client_runtime_is_not_reachable_from_an_application(self) -> None:
        value_import = re.compile(
            r"^\s*import\s+(?!type\b)[^;]*?from\s+\"@ctower/client\"", re.MULTILINE
        )
        offenders = sorted(
            _relative(path)
            for path in _sources()
            if path.is_relative_to(_ROOT / "apps") and value_import.search(_code(path))
        )
        self.assertEqual(
            offenders,
            [],
            "an application value-imports the generated client, whose requests are single-shot; "
            "either bring that client under a bounded policy or keep the import type-only",
        )

    def test_no_module_in_apps_writes_to_the_filesystem(self) -> None:
        offenders = sorted(path for path in _matching(_WRITE_PATTERN) if path.startswith("apps/"))
        self.assertEqual(
            offenders,
            [],
            "a module under apps/ calls a filesystem write; this surface reads other "
            "repositories' live state and may never write, lock, rename or remove",
        )

    def test_every_interim_source_redacts_before_a_screen_sees_its_text(self) -> None:
        sources = sorted(
            path
            for path in (_relative(item) for item in _sources())
            if path.startswith(_SOURCE_DIRECTORY) and path not in _SOURCE_HELPERS
        )
        self.assertGreater(len(sources), 3, "the interim source scan found almost nothing")
        imports_redaction = re.compile(r"from\s+\"\./redact\"")
        missing = [
            path for path in sources if imports_redaction.search(_code(_ROOT / path)) is None
        ]
        self.assertEqual(
            missing,
            [],
            "an interim source renders text authored elsewhere without passing it through "
            "the redaction list; a credential pasted into that source would reach the screen",
        )

    def test_readings_are_only_unwrapped_inside_the_declared_boundary(self) -> None:
        offenders = sorted(
            path for path in _matching(_READING_PATTERN) if not path.startswith(_READING_HOLDERS)
        )
        self.assertEqual(
            offenders,
            [],
            "a surface inspected a Reading directly; unwrap it through frame/Declared.tsx so an "
            "unreachable source can never be rendered as an empty one",
        )


if __name__ == "__main__":
    unittest.main()
