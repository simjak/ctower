## Outcome

Describe the user-visible or system outcome and why it is needed.

Author-model: <family/model>

## Delivery item

`Refs #<issue>`

**Do not use `Closes`, `Fixes` or `Resolves`.** A merge is not a delivery. The issue stays open
through staging QA, production deploy and production QA, and is closed by whoever verifies it in
production — not by this merge.

## Scope

- In scope:
- Explicitly out of scope:

## Evidence

List exact commands, test results, artifacts, and failure injection performed. Do not paste secrets,
personal data, customer data, or private infrastructure details.

## Risk and recovery

Describe authorization, durability, restart, idempotency, migration, rollback, and compatibility impact as
applicable.

## Checklist

- [ ] The change has one cohesive purpose and follows the current implementation increment.
- [ ] I updated tests and exact contracts with changed behavior.
- [ ] I updated public docs and release notes where surfaces changed.
- [ ] I did not hand-edit generated files or introduce a competing source of truth.
- [ ] Repository policy, formatting, typing, tests, and generated-drift checks pass.
- [ ] The diff contains no secrets, PII, customer data, private URLs, or local machine paths.
- [ ] New or changed behavior is observable and every visible control is wired.
- [ ] An independent reviewer other than the author will approve the candidate.
- [ ] Every network request added or changed carries bounded retry with exponential backoff and jitter.
- [ ] This PR references its delivery item with `Refs`, not a closing keyword.
