"""The child-process boundary's grammar, driven rather than inspected.

`apps/ctower-ui/src/read/commands.ts` is the whole read-only guarantee at the
process boundary: callers name an inspection, the module builds the argv, and a
mutating verb is not expressible in the type. Round-2 review of PR #215 found
the module's docblock citing this test before it existed, which left the value
slots — the only part a reader's URL can reach — proven by reading alone.

These tests execute the real `invocationFor` and assert on what it returns:

* every member of the union builds an argv whose verb is an inspection verb,
  with the denominator taken from the union declaration itself rather than from
  a list kept here, so a new operation cannot be added without being covered;
* every value slot refuses the option, traversal, range, control-character and
  unbounded-count shapes it exists to refuse, as `InspectionRefused`; and
* the tools resolve to absolute paths, and no environment override can demote
  one to a `PATH` lookup.

The module is pure and dependency-free at runtime, so Node runs it directly with
type stripping. No command is executed by any of this: the fixture asks what
would be run and prints it.
"""

from __future__ import annotations

import json
import re
import shutil
import unittest
from functools import cache
from pathlib import Path

import tools.process_execution as process_execution  # noqa: PLR0402

_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = Path(__file__).with_name("inspection_fixtures.ts")
_GRAMMAR = _ROOT / "apps/ctower-ui/src/read/commands.ts"
_TIMEOUT_SECONDS = 120

# Declared operations, read out of the union itself: the denominator this suite
# must cover is the source of truth, not a copy of it.
_DECLARED_OP = re.compile(r'readonly op:\s*"([^"]+)"')

# Verbs that read. A tool's first argument must be one of these; anything else
# is a state change wearing an inspection's name.
_INSPECTION_VERBS = frozenset(
    {
        "rev-parse",
        "symbolic-ref",
        "log",
        "ls-tree",
        "show",
        "diff",
        "worktree",
        "list-timers",
        "list-sessions",
        "list-panes",
        "capture-pane",
    }
)
# Subcommands that change something. None may appear as an argument, matched
# whole: a substring test would trip over `--format`, which contains `rm`.
_MUTATING_TOKENS = frozenset(
    {
        "reset",
        "checkout",
        "switch",
        "commit",
        "push",
        "fetch",
        "pull",
        "clean",
        "gc",
        "prune",
        "add",
        "rm",
        "restore",
        "stash",
        "apply",
        "remove",
        "start",
        "stop",
        "restart",
        "enable",
        "disable",
        "kill-session",
        "kill-server",
        "new-session",
        "send-keys",
        "respawn-pane",
    }
)
# Options that hand a tool a program to run or a file to write, in either the
# `--flag value` or the `--flag=value` form. Scoped by tool because the same
# spelling differs: `git --output` redirects into a file, while
# `systemctl --output` only names a display format.
_FORBIDDEN_OPTIONS = ("--exec-path", "--upload-pack", "--receive-pack", "-e", "--edit")
_FORBIDDEN_GIT_OPTIONS = ("--output", "-o")


@cache
def _outcome() -> dict[str, object]:
    node = shutil.which("node")
    if node is None:
        # not a skip: this is a required suite, and a verification host without
        # the toolchain it declares is a failure, not a reason to pass quietly
        raise RuntimeError("node is not on PATH; the inspection fixtures cannot run")
    # the repository's single bounded process boundary, not a raw subprocess
    completed = process_execution.run(
        (node, "--no-warnings", str(_FIXTURES)),
        timeout_seconds=_TIMEOUT_SECONDS,
        check=True,
        capture_output=True,
    )
    parsed = json.loads(completed.stdout)
    if not isinstance(parsed, dict):
        raise TypeError("the inspection fixture did not emit an object")
    return parsed


def _accepted() -> dict[str, dict[str, object]]:
    accepted = _outcome()["accepted"]
    if not isinstance(accepted, dict):
        raise TypeError("the accepted inspections are not an object")
    return accepted


def _rejected() -> list[dict[str, object]]:
    rejected = _outcome()["rejected"]
    if not isinstance(rejected, list):
        raise TypeError("the refusals are not a list")
    return rejected


def _resolution() -> dict[str, object]:
    resolution = _outcome()["resolution"]
    if not isinstance(resolution, dict):
        raise TypeError("the resolution outcomes are not an object")
    return resolution


def _argv(invocation: dict[str, object]) -> list[str]:
    args = invocation["args"]
    if not isinstance(args, list):
        raise TypeError("an invocation carries no argument list")
    return [str(item) for item in args]


class InspectionGrammarCoverageTests(unittest.TestCase):
    """Every declared operation is driven, and every one builds a read."""

    def test_the_fixture_drives_every_operation_the_union_declares(self) -> None:
        declared = set(_DECLARED_OP.findall(_GRAMMAR.read_text(encoding="utf-8")))
        self.assertGreater(len(declared), 10, "the union scan found almost nothing")
        self.assertEqual(
            sorted(declared - set(_accepted())),
            [],
            "an inspection was added to the grammar without a driver here; the value slots "
            "of a process boundary may not ship unexercised",
        )

    def test_every_built_command_runs_an_inspection_verb(self) -> None:
        for op, invocation in sorted(_accepted().items()):
            with self.subTest(op=op):
                argv = _argv(invocation)
                # a git invocation is pinned to its repository first
                verb = argv[2] if invocation["tool"] == "git" else argv[0]
                if invocation["tool"] == "git":
                    self.assertEqual(argv[:2], ["-C", "/srv/projects/ctower"])
                self.assertIn(
                    verb,
                    _INSPECTION_VERBS | {"-l", "--user"},
                    f"{op} builds a command whose verb is not an inspection",
                )

    def test_no_built_command_carries_a_mutating_token(self) -> None:
        for op, invocation in sorted(_accepted().items()):
            with self.subTest(op=op):
                argv = _argv(invocation)
                forbidden = _FORBIDDEN_OPTIONS + (
                    _FORBIDDEN_GIT_OPTIONS if invocation["tool"] == "git" else ()
                )
                offenders = sorted(_MUTATING_TOKENS.intersection(argv)) + [
                    item
                    for item in argv
                    for option in forbidden
                    if item == option or item.startswith(f"{option}=")
                ]
                self.assertEqual(offenders, [], f"{op} builds a command that changes state")

    def test_crontab_is_only_ever_listed(self) -> None:
        # `crontab <file>` installs a new crontab; the list flag is the only
        # argument this tool may ever receive.
        self.assertEqual(_argv(_accepted()["crontab.list"]), ["-l"])

    def test_systemd_is_only_ever_queried(self) -> None:
        argv = _argv(_accepted()["systemd.timers"])
        self.assertEqual(argv[0], "--user")
        self.assertIn("list-timers", argv)

    def test_tmux_capture_is_bounded_and_never_writes_to_a_pane(self) -> None:
        argv = _argv(_accepted()["tmux.capture"])
        self.assertEqual(argv[0], "capture-pane")
        self.assertIn("-p", argv, "the capture must print, never redirect into a file")
        self.assertIn("-120", argv, "the scrollback bound reached the argv")

    def test_every_invocation_declares_a_byte_ceiling(self) -> None:
        for op, invocation in sorted(_accepted().items()):
            with self.subTest(op=op):
                ceiling = invocation["maxBytes"]
                self.assertIsInstance(ceiling, int)
                assert isinstance(ceiling, int)
                self.assertGreater(ceiling, 0, f"{op} reads without a size bound")


class InspectionRefusalTests(unittest.TestCase):
    """Every value slot refuses the shapes it exists to refuse."""

    def _refusal(self, slot: str) -> dict[str, object]:
        for case in _rejected():
            if case["slot"] == slot:
                return case
        raise AssertionError(f"the fixture drove no case for {slot}")

    def test_the_fixture_drives_every_validator(self) -> None:
        slots = {str(case["slot"]).split("/")[0] for case in _rejected()}
        self.assertEqual(slots, {"value", "ref", "repoPath", "count"})

    def test_every_rejected_value_is_refused_as_a_typed_refusal(self) -> None:
        for case in _rejected():
            with self.subTest(slot=case["slot"]):
                self.assertTrue(
                    case["refused"],
                    f"{case['slot']} was accepted: the boundary would run {case['argv']}",
                )
                self.assertEqual(
                    case["kind"],
                    "InspectionRefused",
                    "the refusal was not the boundary's typed refusal, so a caller cannot "
                    "distinguish a rejected value from an unrelated crash",
                )

    def test_an_option_shaped_value_never_becomes_an_option(self) -> None:
        for slot in (
            "value/leading-dash",
            "value/session-leading-dash",
            "ref/leading-dash",
            "repoPath/leading-dash",
        ):
            with self.subTest(slot=slot):
                self.assertIn("option", str(self._refusal(slot)["message"]))

    def test_a_traversal_never_leaves_the_tree(self) -> None:
        for slot in ("repoPath/absolute", "repoPath/traversal", "repoPath/interior-traversal"):
            with self.subTest(slot=slot):
                self.assertIn("inside the tree", str(self._refusal(slot)["message"]))

    def test_a_ref_may_not_carry_a_range_or_shell_punctuation(self) -> None:
        for slot in ("ref/shell-punctuation", "ref/space", "ref/double-dot", "ref/traversal"):
            with self.subTest(slot=slot):
                self.assertIn("not a plain ref", str(self._refusal(slot)["message"]))

    def test_a_control_character_never_reaches_an_argument(self) -> None:
        for slot in ("value/newline", "value/nul"):
            with self.subTest(slot=slot):
                self.assertIn("control character", str(self._refusal(slot)["message"]))

    def test_a_count_stays_a_bounded_positive_integer(self) -> None:
        for slot in (
            "count/zero",
            "count/negative",
            "count/fractional",
            "count/over-ceiling",
            "count/days-over-ceiling",
        ):
            with self.subTest(slot=slot):
                self.assertIn("bounded positive integer", str(self._refusal(slot)["message"]))


class ExecutableResolutionTests(unittest.TestCase):
    """A tool is a path from a fixed table, never a name resolved on PATH."""

    def test_every_tool_resolves_to_an_absolute_path(self) -> None:
        defaults = _resolution()["defaults"]
        assert isinstance(defaults, dict)
        self.assertEqual(sorted(defaults), ["crontab", "git", "systemctl", "tmux"])
        for tool, executable in sorted(defaults.items()):
            with self.subTest(tool=tool):
                self.assertTrue(
                    str(executable).startswith("/"),
                    f"{tool} resolves to {executable!r}, which PATH decides",
                )

    def test_an_absolute_override_is_honoured(self) -> None:
        self.assertEqual(
            _resolution()["absoluteOverrideHonoured"],
            "/opt/planted/bin/tmux",
            "the deployment override stopped working; the app could no longer name its tools",
        )

    def test_an_empty_override_falls_back_to_the_table(self) -> None:
        self.assertEqual(_resolution()["emptyOverrideFallsBackToTable"], "/usr/bin/tmux")

    def test_an_override_that_is_not_absolute_is_refused(self) -> None:
        for key in ("bareNameOverride", "relativeOverride"):
            with self.subTest(override=key):
                case = _resolution()[key]
                assert isinstance(case, dict)
                self.assertTrue(
                    case["refused"],
                    "an environment variable turned a tool into a PATH lookup, so a planted "
                    f"directory could substitute the binary: {case['argv']}",
                )
                self.assertIn("absolute path", str(case["message"]))


if __name__ == "__main__":
    unittest.main()
