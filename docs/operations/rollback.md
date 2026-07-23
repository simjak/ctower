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
