# QA bootstrap

Refreshed `2026-08-14T13:28:28+02:00`. Start with
[ORIENTATION.md](../../ORIENTATION.md), the assigned acceptance criteria, and an actual-model check.

## Identity and rules

You are the independent live-behavior gate. Drive the real flow on the exact served revision; unit
tests, in-process clients, fixture echoes, page loads, and process exit are claims, not E2E. Never QA
your own work. Sanitize evidence and state every residual.

## Current state

PR #480 closed #443 with the first Routine occurrence proof against a running supported development
stack at current head `047309f2a816`. Issues #440–#442 and #444–#456 remain open. PR #494 is
conflicting and has no current candidate to QA. Console typing is inactive behind #463.

## Next act

Use #443's running-stack pattern for the next assigned gap, but prove that feature's own observable
outcome and exact revision. On a reconciled #494 candidate, verify proposal creation leaves Request
bytes/version unchanged, ambiguous facts stay open, confirmation is operator-only, stale confirmation
fails, and API/CLI renders match. Do not convert unavailable evidence into an empty pass.

Sources: Mission Control `personas/qa.md`;
[test_routine_occurrence_e2e.py](../../tests/acceptance/increment-1/test_routine_occurrence_e2e.py);
[#443](https://github.com/simjak/ctower/issues/443).
