-- Console Phase 1 follows the fleet-beat migrations accepted on current main.
DO $$
DECLARE
    reader_role oid;
BEGIN
    SELECT oid INTO reader_role
    FROM pg_catalog.pg_roles
    WHERE rolname = 'console_output_reader';

    IF reader_role IS NULL THEN
        CREATE ROLE console_output_reader
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT -1;
    ELSIF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_authid AS role
        WHERE role.oid = reader_role
          AND (
              role.rolcanlogin OR role.rolsuper OR role.rolcreatedb
              OR role.rolcreaterole OR role.rolinherit OR role.rolreplication
              OR role.rolbypassrls OR role.rolconnlimit <> -1
              OR role.rolpassword IS NOT NULL OR role.rolvaliduntil IS NOT NULL
          )
    ) OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_auth_members AS membership
        LEFT JOIN pg_catalog.pg_roles AS member_role ON member_role.oid = membership.member
        WHERE (membership.roleid = reader_role OR membership.member = reader_role)
          AND NOT (
              membership.roleid = reader_role
              AND member_role.rolname = 'ctower_admin'
              AND NOT membership.admin_option
          )
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_db_role_setting AS setting
        WHERE setting.setrole = reader_role
    ) OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_shdepend AS dependency
        WHERE dependency.refclassid = 'pg_catalog.pg_authid'::regclass
          AND dependency.refobjid = reader_role
          AND dependency.dbid = (
              SELECT database.oid
              FROM pg_catalog.pg_database AS database
              WHERE database.datname = current_database()
          )
          AND dependency.deptype IN ('o', 'a')
          AND NOT (
              (
                  dependency.classid = 'pg_catalog.pg_namespace'::regclass
                  AND dependency.objid = 'public'::regnamespace
              )
              OR (
                  dependency.classid = 'pg_catalog.pg_proc'::regclass
                  AND dependency.objid = to_regprocedure(
                      'recover_console_output_object(uuid,timestamp with time zone)'
                  )
              )
              OR (
                  dependency.classid = 'pg_catalog.pg_class'::regclass
                  AND dependency.objid = ANY(ARRAY[
                      to_regclass('public.console_output_objects'),
                      to_regclass('public.console_output_access_facts'),
                      to_regclass('public.console_output_recovery_facts')
                  ]::oid[])
              )
          )
    ) THEN
        RAISE EXCEPTION 'unsafe pre-existing console_output_reader role';
    END IF;
END
$$;

GRANT console_output_reader TO ctower_admin;
GRANT USAGE, CREATE ON SCHEMA public TO console_output_reader;
DO $$
BEGIN
    IF to_regprocedure(
        'public.recover_console_output_object(uuid,timestamp with time zone)'
    ) IS NOT NULL THEN
        REVOKE CREATE ON SCHEMA public FROM console_output_reader;
    END IF;
END
$$;
REVOKE console_output_reader FROM ctower_svc, ctower_runtime;
