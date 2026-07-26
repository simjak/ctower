ALTER TABLE catalog_components DROP CONSTRAINT catalog_components_kind_check;
ALTER TABLE catalog_components ADD CONSTRAINT catalog_components_kind_check CHECK (kind IN (
    'workflow', 'execution_policy', 'gate_policy', 'evidence_policy',
    'goal', 'project', 'agent_profile', 'persona', 'skill', 'tool',
    'capability', 'environment', 'image', 'harness', 'supervisor',
    'target', 'workspace', 'telemetry', 'placement_policy', 'extension',
    'cadence_policy', 'notification', 'integration', 'adapter', 'checkpoint'
));

GRANT SELECT ON migration_import_runs, migration_import_run_facts,
    migration_reconciliation_facts, migration_fence_observations
    TO ctower_projection;
