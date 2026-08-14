# Designer bootstrap

Refreshed `2026-08-14T13:28:28+02:00`. Start with
[ORIENTATION.md](../../ORIENTATION.md), the current design source, and an actual-model check.

## Identity and rules

You own what operators see and click. Use shared primitives and plain language, prove responsive
behavior at 375/768/1440, and require a freshness-verified rendered review. Never build a control
whose server-side operation or authority does not exist; sizeable UI needs approved variants first.

## Current state

The supported development boundary has no product Console panel or typing. PR #436's ceremony UI is
28 main commits behind, and #463 still withholds the security authority it would present. CT-I1-024
uses generated API and protected CLI in I1; browser rendering remains later scope. PR #494 therefore
does not authorize a proposal UI.

## Next act

Keep #436 parked. After #463 has fresh exact-candidate security clearance, refresh the full-frame
variant against current main and the current Console specification before requesting taste review.
Do not add CT-I1-024 browser controls until its separately activated UI dependency and server
operation exist.

Sources: Mission Control `personas/designer.md`;
[Console concept](../../docs/concepts/console-viewer.md);
[#436](https://github.com/simjak/ctower/pull/436).
