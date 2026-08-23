"""The company read waits for admission.

`App` reads the company once, at the top, so the shell and the page cannot
disagree about which tower this is. That read crosses the development server's
admission gate: with no session token held, the server answers `/v1/...` with
its own 401 before the API is ever asked. QA found the consequence in custody
(2026-08-22, ticket t_150a1df0): the unlock screen rendered correctly, yet the
console carried two 401 errors and two company-bundle requests — StrictMode
mounts the effect twice — fired *before* anything was admitted.

The repair is one wire: `useSeed` takes an enablement and asks nothing until
it is set, and `App` hands it the same admission state that decides whether
the gate screen is drawn. Nothing else may hold an unconditional company ask,
and the wire cannot quietly detach — this suite fails when either half is
removed.

As with the mark-containment guard, the rule is asserted from repository
structure rather than from a browser: D75 keeps browser suites out of this
repository's gates, and what regresses in a diff is exactly this wiring.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_USE_SEED = "apps/ctower-web/src/wizard/useSeed.ts"
_APP = "apps/ctower-web/src/app/App.tsx"

# The hook's signature: a reload key plus the enablement that gates the ask.
# A default keeps post-admission callers (the harness panels) honest without
# repeating what they cannot observe.
_SIGNATURE = re.compile(
    r"export function useSeed\(\s*reloadKey:\s*number,\s*(?:enabled|admitted)\s*(?:=\s*true)?\s*\)",
)

# The effect must refuse to ask until the enablement is set...
_GATE = re.compile(r"if\s*\(\s*!\s*(?:enabled|admitted)\s*\)\s*(?:\{\s*return;?|return)")
# ...and must re-run when the enablement changes, so admitting after the gate
# screen actually performs the read the screen was holding back.
_DEPS = re.compile(r"\[\s*reloadKey\s*,\s*(?:enabled|admitted)\s*\]")

# The one ask, counted so a rename cannot turn this suite into a no-op.
_ASK = re.compile(r"reads\.exportCompanyBundle\s*\(")


def _is_gated(source: str) -> bool:
    """Whether a `useSeed`-shaped module asks only through a real gate."""
    return bool(_SIGNATURE.search(source) and _GATE.search(source) and _DEPS.search(source))


class CompanyReadWaitsForAdmissionTests(unittest.TestCase):
    """No `/v1` company read leaves this app before admission."""

    def setUp(self) -> None:
        self.use_seed = (_ROOT / _USE_SEED).read_text(encoding="utf-8")
        self.app = (_ROOT / _APP).read_text(encoding="utf-8")

    def test_the_company_read_is_asked_exactly_once(self) -> None:
        """The denominator, so a silent rename cannot turn this suite into a no-op."""

        self.assertEqual(
            len(_ASK.findall(self.use_seed)),
            1,
            f"{_USE_SEED} no longer asks for the company bundle exactly once; either the "
            "single company read moved elsewhere, or this suite is asserting nothing",
        )

    def test_the_read_waits_for_admission_before_it_asks(self) -> None:
        self.assertTrue(
            _is_gated(self.use_seed),
            f"the company read in {_USE_SEED} is no longer gated on admission: the hook must "
            "take an enablement, ask nothing while it is unset, and list it as an effect "
            "dependency — otherwise the unlock screen fires /v1 requests (and collects 401s) "
            "before any token exists",
        )

    def test_the_app_hands_the_hook_its_own_admission_state(self) -> None:
        self.assertRegex(
            self.app,
            r"useSeed\(\s*reloadKey\s*,\s*admitted\s*\)",
            f"{_APP} calls useSeed without passing the admission state that decides whether "
            "the gate screen is drawn; the read and the gate can then disagree, and the "
            "pre-admission 401s come back",
        )

    def test_an_unconditional_read_is_still_detectable(self) -> None:
        """The regressed shape, so the guard cannot pass by failing to see anything."""

        regressed = """
export function useSeed(reloadKey: number): Answer<Seed> {
  useEffect(() => {
    void load();
  }, [reloadKey]);
}
"""
        self.assertFalse(_is_gated(regressed))


if __name__ == "__main__":
    unittest.main()
