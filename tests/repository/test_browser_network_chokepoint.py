"""Fail-closed discovery of the browser boundary's crossings and its honesty rules.

The repository coding standard forbids single-shot network requests, loopback
services included, and requires coverage to be derived from repository
structure rather than from a hand-maintained endpoint list. These tests build
the denominator by scanning every authored and generated TypeScript module for
network-capable constructs, then require each discovered site to sit in an
approved policy holder. An unclassifiable site fails the gate.

Three further discoveries run the same way, each fail-closed: the generated
client may be reached from an application only through a binder that hands it
that application's bounded fetch and no credential, no module under `apps/` may
call a filesystem write, and the generated reader's decode-failure prefix stays
recognizable to the app that renders it as a visible state.

The interim-source and `Reading` rules that used to live here went with the
phase-1 surface in #545; they named `apps/ctower-ui/src/read/**` directly and
have nothing left to assert. What remains is what the surviving app claims.
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
#
# The name must be *called* to count. The bare-word form matched `truncate`
# wherever it appeared, including a CSS utility class of that name in markup,
# which is a class attribute rather than a syscall. Requiring the call makes the
# pattern say what it means; every real write site still matches, because none
# of these names does anything except when invoked.
_WRITE_PATTERN = re.compile(
    r"\b(?:writeFile|writeFileSync|appendFile|appendFileSync|createWriteStream"
    r"|unlink|unlinkSync|rmdir|rmSync|mkdir|mkdirSync|rename|renameSync|truncate"
    r"|chmod|chmodSync)\s*\("
)
_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

# The approved holders. Each entry is a path and the reason it may hold the site.
_NETWORK_POLICY_HOLDERS = {
    "apps/ctower-web/src/api/bounded.ts": (
        "the wizard's single bounded-retry chokepoint, with the same policy; the "
        "generated client is constructed with the fetch it returns, so every "
        "generated request inherits the bound rather than the client's single shot"
    ),
    "generated/typescript/ctower-client/src/client.ts": (
        "the generated client; reachable from an application only through an "
        "approved binder that injects that application's chokepoint, which is "
        "asserted separately below"
    ),
}
_CHOKEPOINTS = ("apps/ctower-web/src/api/bounded.ts",)

# The generated JSON reader raises a bare `SyntaxError`, so the only thing that
# separates a malformed answer from a programming fault is the prefix on its
# message. The app matches that prefix to render its declared `malformed` state;
# if the generator ever stops producing it, every malformed answer silently
# becomes an unhandled rejection and a screen that never leaves `asking`. Both
# halves are asserted, so the coupling cannot rot in either file.
_DECODE_PREFIX_HOLDERS = {
    "generated/typescript/ctower-client/src/response-json.ts": "the generated reader",
    "apps/ctower-web/src/api/client.ts": "the answer classifier that renders it",
}
_DECODE_PREFIX = "Invalid ctower JSON response"

# The only application modules that may value-import the generated client, each
# mapped to the chokepoint it must hand that client as its `fetch`. An entry
# here is not a waiver: both halves are asserted below, so a binder that stops
# injecting its chokepoint fails exactly as loudly as an unlisted importer.
_CLIENT_BINDERS = {
    "apps/ctower-web/src/api/client.ts": "./bounded",
}

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
        discovered = {_relative(path) for path in _sources()}
        self.assertGreater(len(discovered), 10, "the TypeScript scan found almost nothing")
        for chokepoint in _CHOKEPOINTS:
            self.assertIn(chokepoint, discovered)

    def test_every_network_call_site_sits_in_an_approved_policy_holder(self) -> None:
        unclassified = sorted(set(_matching(_NETWORK_PATTERN)) - set(_NETWORK_POLICY_HOLDERS))
        self.assertEqual(
            unclassified,
            [],
            "a network-capable call site appeared outside an approved O10 policy holder; "
            "route it through that application's bounded chokepoint or classify it here",
        )

    def test_every_chokepoint_still_declares_every_required_bound(self) -> None:
        for chokepoint in _CHOKEPOINTS:
            with self.subTest(chokepoint=chokepoint):
                code = _code(_ROOT / chokepoint)
                missing = [name for name in _REQUIRED_BOUNDS if name not in code]
                self.assertEqual(
                    missing, [], "the bounded-read policy lost a required O10 property"
                )

    def test_the_generated_client_runtime_is_reachable_only_through_a_binder(self) -> None:
        value_import = re.compile(
            r"^\s*import\s+(?!type\b)[^;]*?from\s+\"@ctower/client\"", re.MULTILINE
        )
        importers = sorted(
            _relative(path)
            for path in _sources()
            if path.is_relative_to(_ROOT / "apps") and value_import.search(_code(path))
        )
        self.assertEqual(
            importers,
            sorted(_CLIENT_BINDERS),
            "an application value-imports the generated client, whose requests are single-shot; "
            "either keep the import type-only, or bind that client to the application's bounded "
            "chokepoint and declare the binder here",
        )

    def test_every_binder_hands_the_generated_client_its_bounded_fetch(self) -> None:
        """A declared binder that stops injecting its chokepoint is not a binder."""

        for binder, chokepoint in _CLIENT_BINDERS.items():
            with self.subTest(binder=binder):
                code = _code(_ROOT / binder)
                self.assertRegex(
                    code,
                    rf"import\s+\{{[^}}]*\bboundedFetch\b[^}}]*\}}\s+from\s+\"{re.escape(chokepoint)}\"",
                    "the binder does not import its application's bounded fetch",
                )
                self.assertRegex(
                    code,
                    r"new\s+CtowerClient\s*\((?:[^)]|\)(?!\s*;))*fetch:\s*boundedFetch\(",
                    "the binder constructs the generated client without its bounded fetch",
                )
                self.assertNotRegex(
                    code,
                    r"new\s+CtowerClient\s*\([^)]*credential:",
                    "the browser holds no API bearer; the credential is attached server-side",
                )

    def test_the_generated_decode_failure_stays_recognizable_to_the_app(self) -> None:
        for path, role in _DECODE_PREFIX_HOLDERS.items():
            with self.subTest(holder=path):
                self.assertIn(
                    _DECODE_PREFIX,
                    (_ROOT / path).read_text(encoding="utf-8"),
                    f"{role} no longer names the generated decode-failure prefix; a malformed "
                    "answer would escape the declared malformed state and strand the screen",
                )

    def test_no_module_in_apps_writes_to_the_filesystem(self) -> None:
        offenders = sorted(path for path in _matching(_WRITE_PATTERN) if path.startswith("apps/"))
        self.assertEqual(
            offenders,
            [],
            "a module under apps/ calls a filesystem write; this surface reads other "
            "repositories' live state and may never write, lock, rename or remove",
        )


if __name__ == "__main__":
    unittest.main()
