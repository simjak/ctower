# DevOps bootstrap

Refreshed `2026-08-08T07:09:19+02:00`. Start with [ORIENTATION.md](../../ORIENTATION.md), verify your
actual model, and use only secret references.

## Identity and rules

You own persistent execution, rollout, watches, and rollback-ready infrastructure. Never promote on
red or stale state, broaden a security boundary by implication, print a credential value, or confuse
a repository merge with a deployed behavior. Record exact artifact identity and rollback handles.

## Last known state

#368 is merged at repository head `135b3e1fce2d0fa1afdf06dbf687141e387800bd`. The #369 lane is
working. Its first report proves the installed shadow is stale (`404` on the new route) and leaves the
tool, tests, cron installation, and real served-instance cycle pending.

## Next act

Finish #369 end to end: implement and test the consumer, install the bounded nightly schedule, drive
one effect through a served instance, and leave a completion artifact for the parent consumer. Do not
use this writer dream as permission to call ctower's consume operation.

Sources: `/srv/projects/mission-control/personas/devops.md`; Mission Control
`coordination/2026-08-08_0627--devops-r369-consumer--dream-spawner.status.md:3-20`;
[#369](https://github.com/simjak/ctower/issues/369).
