REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ctower_svc, ctower_projection;

GRANT USAGE ON SCHEMA public TO ctower_svc, ctower_projection;
GRANT SELECT, INSERT, UPDATE ON tenants, principals, principal_credentials,
    bootstrap_capability, tickets, lifecycle_episodes, assignment_intervals, priority_facts
    TO ctower_svc;
GRANT INSERT, SELECT ON events, command_results, outbox TO ctower_svc;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ctower_projection;

ALTER DEFAULT PRIVILEGES FOR ROLE ctower_admin IN SCHEMA public
    GRANT SELECT ON TABLES TO ctower_projection;
