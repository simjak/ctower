"""The credential-limits surface, and the one field family it may never carry.

The pools read is the only record read on this surface whose *source* sits next
to credential material. A harness sweep is taken from a credential store, so the
authored contract answers it through a closed projection: `PoolObservedEntry`
may carry a fingerprint, and `PoolEntryState` — the read the browser asks for —
has no field a token, key or adjacent secret value can occupy at all.

That allowlist is the whole security argument for putting this on a screen, so
it is asserted against the authored contract rather than against a list typed
out here: the parser reads the record's fields by name, the set of names it
reads is exactly the contract's read projection, and no module behind the screen
names an observation-only or credential-shaped field.

The rest is the house read-surface contract the Requests slice established — a
dynamic route, the adapter seam, one rail entry — plus the one claim this
particular read may not make: the record deliberately answers per entry with
each account's own clock, so no aggregate pool verdict may be composed here.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any, cast

_ROOT = Path(__file__).resolve().parents[2]
_SURFACE = _ROOT / "apps/ctower-ui/src"
_CONTRACT = _ROOT / "contracts/http/openapi.yaml"
_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
# the breadcrumb every strict reader passes, which is also the field it read
#: the rail entry the frame says this screen's name lights
_LIT_RAIL = re.compile(r'Credentials: "([^"]+)"')
_ENTRY_FIELD = re.compile(r"pools\.profiles\[\]\.entries\[\]\.(\w+)")
_DRIFT_FIELD = re.compile(r"pools\.profiles\[\]\.drift\[\]\.(\w+)")
_WEIGHT_FIELD = re.compile(r"pools\.weights\[\]\.(\w+)")
# names that only exist where credential material does; none of them is a field
# of the read projection, and none may appear behind this screen
_CREDENTIAL_SHAPED = (
    "secret_fingerprint",
    "secretFingerprint",
    "access_token",
    "accessToken",
    "refresh_token",
    "refreshToken",
    "api_key",
    "apiKey",
    "Authorization",
    "Bearer",
)


def _code(path: Path) -> str:
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", path.read_text(encoding="utf-8")))


def _schema(name: str) -> dict[str, Any]:
    document = cast("dict[str, Any]", json.loads(_CONTRACT.read_text(encoding="utf-8")))
    schemas = cast("dict[str, Any]", document["components"]["schemas"])
    return cast("dict[str, Any]", schemas[name])


def _properties(name: str) -> set[str]:
    return set(cast("dict[str, Any]", _schema(name)["properties"]))


def _limits_modules() -> tuple[Path, ...]:
    """Every module behind this screen, taken from the tree rather than listed."""
    found = (
        *sorted((_SURFACE / "app/limits").rglob("*.tsx")),
        *sorted((_SURFACE / "surfaces/limits").rglob("*.tsx")),
        *sorted(_SURFACE.glob("read/poolLimits*.ts")),
    )
    return found


class LimitsRouteTests(unittest.TestCase):
    """The house read-surface shape: a dynamic route over the adapter seam."""

    def test_the_limits_route_is_dynamic_and_reads_the_adapter(self) -> None:
        page = _SURFACE / "app/limits/page.tsx"
        self.assertTrue(page.is_file(), "the credential-limits route is missing")
        source = page.read_text(encoding="utf-8")
        self.assertIn('dynamic = "force-dynamic"', source)
        self.assertIn("recordAdapter.poolLimits", source)
        self.assertIn("<Resolved", source)

    def test_the_read_contract_and_adapter_bind_the_shipped_pools_endpoint(self) -> None:
        interface = (_SURFACE / "read/interface.ts").read_text(encoding="utf-8")
        adapter = (_SURFACE / "read/adapter.ts").read_text(encoding="utf-8")
        pools = (_SURFACE / "read/poolLimits.ts").read_text(encoding="utf-8")
        self.assertIn("poolLimits:", interface)
        self.assertIn("poolLimits: readPoolLimits", adapter)
        self.assertIn('"/v1/pools"', pools)
        self.assertIn("/v1/pools", adapter)

    def test_the_rail_offers_the_surface_once_and_the_frame_lights_it(self) -> None:
        """One destination, one icon, and one rail entry the screen's name lights.

        The screen is named `Credentials` — what it holds — while the rail entry
        is still named for the read that serves it. That is the case
        ``Chrome.RAIL_OF`` exists for, and it is asserted rather than tolerated:
        a page whose name lights no rail entry leaves a reader unable to see
        where they are.
        """
        rail = (_SURFACE / "frame/rail.ts").read_text(encoding="utf-8")
        self.assertEqual(rail.count('href: "/limits"'), 1)
        self.assertIn('"/limits": icon(', (_SURFACE / "frame/Sidebar.tsx").read_text("utf-8"))
        chrome = (_SURFACE / "frame/Chrome.tsx").read_text("utf-8")
        lit = _LIT_RAIL.search(chrome)
        if lit is None:
            self.fail("the frame does not say which rail entry the Credentials screen lights")
        self.assertIn(f'label: "{lit.group(1)}"', rail)

    def test_the_scan_behind_this_screen_finds_a_non_empty_denominator(self) -> None:
        self.assertGreater(len(_limits_modules()), 2, "the limits module scan found almost nothing")


class ProjectionAllowlistTests(unittest.TestCase):
    """The contract's own closed projection, asserted as this screen's field set."""

    def test_the_contract_keeps_the_fingerprint_out_of_the_read_projection(self) -> None:
        """The premise: the observation may carry one, the read has nowhere to put it."""
        self.assertIn("secret_fingerprint", _properties("PoolObservedEntry"))
        self.assertNotIn(
            "secret_fingerprint",
            _properties("PoolEntryState"),
            "the read projection grew a fingerprint field; this screen's whole security "
            "argument is that it cannot have one",
        )
        self.assertFalse(
            _schema("PoolEntryState")["additionalProperties"],
            "the read projection stopped being a closed object, so an unreviewed field "
            "can now ride along with it",
        )

    def test_the_parser_reads_exactly_the_contract_s_read_projection(self) -> None:
        pools = (_SURFACE / "read/poolLimits.ts").read_text(encoding="utf-8")
        for pattern, schema in (
            (_ENTRY_FIELD, "PoolEntryState"),
            (_DRIFT_FIELD, "PoolDriftFinding"),
            (_WEIGHT_FIELD, "PoolModelWeight"),
        ):
            with self.subTest(schema=schema):
                self.assertEqual(
                    set(pattern.findall(pools)),
                    _properties(schema),
                    f"the fields this surface reads are not {schema}'s; a field-by-field "
                    "named projection is what keeps an unreviewed field off the screen",
                )

    def test_no_module_behind_this_screen_names_a_credential_shaped_field(self) -> None:
        offenders = sorted(
            f"{path.relative_to(_ROOT).as_posix()}: {name}"
            for path in _limits_modules()
            for name in _CREDENTIAL_SHAPED
            if name in _code(path)
        )
        self.assertEqual(
            offenders,
            [],
            "a module behind the limits screen names a credential-bearing field; the read "
            "projection has no such field, so naming one can only mean reaching past it",
        )


class NoAggregateVerdictTests(unittest.TestCase):
    """A pool is not one word, and this screen may not make it one."""

    def test_the_screen_states_the_per_entry_rule_within_the_copy_budget(self) -> None:
        """The rule stays on screen; the argument for it does not.

        The record answers per entry with each account's own clock, and a reader
        who does not know that reads the first row as the pool. So the screen
        still says what it is showing — in one hint line. What it no longer
        carries is the three-line case for the layout, which was reviewer-facing
        prose shipped inside an operator-facing screen and is exactly what the
        copy budget was written against.
        """
        page = _code(_SURFACE / "app/limits/page.tsx")
        self.assertIn("one row per account", page)
        for retired in ("no single pool verdict", "three clocks, not one state"):
            with self.subTest(retired=retired):
                self.assertNotIn(retired, page, "the screen is rendering its own rationale again")

    def test_the_row_s_mark_is_the_record_s_verdict_and_not_a_composed_one(self) -> None:
        """The one mark on the row comes from the record's own field.

        A mark derived from whichever axis is blocking would read better and
        would sometimes contradict the record: this pool answers `selectable`
        for an entry whose quota it never observed. `capped` and `dead · auth`
        are told apart by their axis chips, which is where the accepted design
        puts that difference.
        """
        row = _code(_SURFACE / "surfaces/limits/PoolEntryRow.tsx")
        self.assertIn('StateGlyph name={entry.selectable ? "done" : "held"}', row)

    def test_the_surface_neither_sorts_nor_counts_the_rows_it_was_given(self) -> None:
        for path in _limits_modules():
            with self.subTest(module=path.relative_to(_ROOT).as_posix()):
                source = _code(path)
                self.assertNotIn(".sort(", source, "the browser must not invent a ranking")
                self.assertNotIn(
                    "entries.length.toString()",
                    source,
                    "the record states how many entries are selectable; a length counted "
                    "here would be a second, unsourced number beside it",
                )
                self.assertNotIn("Count value={", source)

    def test_the_selectable_count_comes_from_the_record(self) -> None:
        rendered = "".join(_code(path) for path in _limits_modules())
        self.assertIn(
            "selectableEntryCount",
            rendered,
            "the server states how many entries of this profile are selectable, and that "
            "is the only number on this screen entitled to say so",
        )


if __name__ == "__main__":
    unittest.main()
