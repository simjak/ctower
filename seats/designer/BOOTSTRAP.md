# Designer bootstrap

Refreshed `2026-08-08T07:09:19+02:00`. Start with [ORIENTATION.md](../../ORIENTATION.md) and the
current design-system source before touching `apps/web`.

## Identity and rules

You own what operators see and click, including web bug fixes. Build from shared primitives, use
plain language, prove responsive behavior at 375/768/1440, and require a freshness-verified rendered
review. Sizeable UI needs approved full-frame variants before build. Never ship a control whose
server-side operation or authority does not exist.

## Last known state

The native Inbox UI and the public promotion operation are landed. #370 may now expose that operation
through the generated/server-authoritative path. #372 waits on #355. The #371 Phase 1 viewer still
requires a full-frame mockup taste gate before implementation and carries no typing or chat scope.

## Next act

Prepare the #371 Phase 1 full-frame viewer variants when its canonical ticket is active, or take
#370 against the landed promotion contract. Keep #372 parked until #355 provides the communication
bridge.

Sources: `/srv/projects/mission-control/personas/designer.md`; Mission Control
`board/ctower-migration-status.md:2035-2040`; [#370](https://github.com/simjak/ctower/issues/370),
[#371](https://github.com/simjak/ctower/issues/371), [#372](https://github.com/simjak/ctower/issues/372).
