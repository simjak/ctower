# CP3-C rollback

CP3-C is expand-only. Migrations, immutable receipts, tombstones, anchors, inventories, restore reports,
and enablement evidence are never deleted or rewritten during rollback.

Before switching any writer, capture a verified database backup plus proof-object counts/digests and the
complete role/grant graph. If the new object path fails before activation:

1. stop the CP3-C backup, anchor, and restore operations;
2. keep durability policy `pending_only` and object-only switching disabled;
3. return to the preceding object-aware build, which continues safe inline/external dual reads;
4. retain all upload/backfill/erasure and recovery evidence for diagnosis;
5. append a reviewed forward compensation for schema or metadata defects.

After any object has moved external or an erasure tombstone exists, do not roll back to a build that
understands inline objects only. Never delete a receipt, resurrect bytes from backup, revoke a tombstone,
drop an additive table, or weaken a role as a rollback shortcut.

CP3-D topology activation has its own rollback and incident procedure. These local templates do not
authorize standby promotion, host destruction, external bucket deletion, key deletion beyond an
approved exact erasure, or production deployment.

## ctower-project authority rollback and gate state

Current I1.7A has no writer epoch to roll back: its migration commands refuse and its Project Delivery data
is a rebuildable read model. Remove/rebuild projection rows if needed, but preserve append-only authority
facts. It has not established fresh-database authority, completed carry-forward, issued a CT-I1-008
development verdict, or proved CP3-D; Mission Control remains writable today.

The approved development path starts the Company / Project / checkpoint hierarchy and Project Delivery
projection on a fresh database. The complete legacy corpus is hashed, signed, and retained read-only. Only
an exact reviewed still-actionable set is recreated through ordinary generated API/CLI commands with
stable legacy aliases. Bulk import is dormant behind a separate future decision.

Before the development writer epoch, discard the incomplete fresh database if needed and leave Mission
Control authoritative. After the epoch, rollback to a compatible ctower build/restore or explicit
read-only/spool mode. Never re-enable legacy mutation or dual write. Repair an omitted carry-forward item
with a provenance-bearing ordinary command; never import it or edit the legacy archive.

CT-I1-008 may record development `GO_WITH_LIMITS` while CP3-D is red and complete only the development
Project Delivery pilot/I1.7 checkpoint. Full normative I1 exit remains `NO-GO` until CP3-D proves
external-failure-domain acknowledgement, key recovery, isolated destructive restore, and measured RPO/RTO.
The CT-I2-001 dependency means this full exit, so development success does not authorize I2.
