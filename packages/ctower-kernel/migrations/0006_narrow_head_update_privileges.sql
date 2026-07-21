REVOKE UPDATE ON proof_bundles, workflow_runs FROM ctower_svc;
GRANT UPDATE (candidate_digest, version) ON proof_bundles TO ctower_svc;
GRANT UPDATE (current_stage, activity_class, version) ON workflow_runs TO ctower_svc;
