DO $$
DECLARE
    ledger_role oid;
BEGIN
    SELECT oid INTO ledger_role
    FROM pg_roles
    WHERE rolname = 'ctower_migration_ledger';

    IF ledger_role IS NULL THEN
        CREATE ROLE ctower_migration_ledger
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOINHERIT NOREPLICATION NOBYPASSRLS;
    ELSIF EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE oid = ledger_role
          AND (
              rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole
              OR rolinherit OR rolreplication OR rolbypassrls
          )
    ) OR EXISTS (
        SELECT 1
        FROM pg_auth_members
        WHERE roleid = ledger_role OR member = ledger_role
    ) OR EXISTS (
        SELECT 1
        FROM pg_db_role_setting
        WHERE setrole = ledger_role
    ) THEN
        RAISE EXCEPTION 'unsafe pre-existing ctower_migration_ledger role';
    END IF;
END
$$;

ALTER ROLE ctower_migration_ledger
    NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOINHERIT NOREPLICATION NOBYPASSRLS;
REVOKE ctower_migration_ledger
    FROM ctower_admin, ctower_migrator, ctower_svc, ctower_runtime,
         ctower_projection, ctower_projection_runtime;
GRANT USAGE, CREATE ON SCHEMA public TO ctower_migration_ledger;
