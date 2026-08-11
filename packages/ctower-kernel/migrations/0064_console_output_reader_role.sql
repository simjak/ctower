-- Console Phase 1 follows the fleet-beat migrations accepted on current main.
DO $$
DECLARE
    reader_role oid;
    recovery_function oid;
    actual_schema_acl jsonb;
    actual_table_acl jsonb;
    expected_schema_acl constant jsonb :=
        '[["public", "USAGE", false]]'::jsonb;
    expected_table_acl jsonb;
BEGIN
    SELECT oid INTO reader_role
    FROM pg_catalog.pg_roles
    WHERE rolname = 'console_output_reader';

    IF reader_role IS NULL THEN
        CREATE ROLE console_output_reader
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT -1;
        RETURN;
    END IF;

    SELECT to_regprocedure(
        'recover_console_output_object(uuid,timestamp with time zone)'
    ) INTO recovery_function;
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_array(namespace.nspname, acl.privilege_type, acl.is_grantable)
            ORDER BY namespace.nspname, acl.privilege_type, acl.is_grantable
        ),
        '[]'::jsonb
    ) INTO actual_schema_acl
    FROM pg_catalog.pg_namespace AS namespace
    CROSS JOIN LATERAL pg_catalog.aclexplode(namespace.nspacl) AS acl
    WHERE acl.grantee = reader_role;
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_array(
                namespace.nspname,
                relation.relname,
                acl.privilege_type,
                acl.is_grantable
            ) ORDER BY
                namespace.nspname,
                relation.relname,
                acl.privilege_type,
                acl.is_grantable
        ),
        '[]'::jsonb
    ) INTO actual_table_acl
    FROM pg_catalog.pg_class AS relation
    JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    CROSS JOIN LATERAL pg_catalog.aclexplode(relation.relacl) AS acl
    WHERE acl.grantee = reader_role;
    expected_table_acl := CASE
        WHEN recovery_function IS NULL THEN '[]'::jsonb
        ELSE '[
            ["public", "console_output_access_facts", "SELECT", false],
            ["public", "console_output_objects", "SELECT", false],
            ["public", "console_output_recovery_facts", "INSERT", false]
        ]'::jsonb
    END;

    IF EXISTS (
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
    ) OR NOT (
        actual_schema_acl = expected_schema_acl
        OR (recovery_function IS NULL AND actual_schema_acl = '[]'::jsonb)
    ) OR actual_table_acl <> expected_table_acl OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_attribute AS attribute
        CROSS JOIN LATERAL pg_catalog.aclexplode(attribute.attacl) AS acl
        WHERE acl.grantee = reader_role
    ) OR pg_catalog.has_schema_privilege(reader_role, 'public', 'CREATE') OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_shdepend AS dependency
        WHERE dependency.refclassid = 'pg_catalog.pg_authid'::regclass
          AND dependency.refobjid = reader_role
          AND dependency.dbid IN (
              0,
              (SELECT database.oid FROM pg_catalog.pg_database AS database
               WHERE database.datname = current_database())
          )
          AND dependency.deptype IN ('o', 'a')
          AND NOT (
              dependency.dbid = (
                  SELECT database.oid
                  FROM pg_catalog.pg_database AS database
                  WHERE database.datname = current_database()
              )
              AND
              (
                  dependency.deptype = 'o'
                  AND dependency.classid = 'pg_catalog.pg_proc'::regclass
                  AND dependency.objid = recovery_function
              )
              OR (
                  dependency.deptype = 'a'
                  AND (
                      (
                          dependency.classid = 'pg_catalog.pg_namespace'::regclass
                          AND dependency.objid = 'public'::regnamespace
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
              )
          )
    ) THEN
        RAISE EXCEPTION 'unsafe pre-existing console_output_reader role';
    END IF;
END
$$;

GRANT console_output_reader TO ctower_admin;
GRANT CREATE ON SCHEMA public TO ctower_admin WITH GRANT OPTION;
GRANT USAGE ON SCHEMA public TO console_output_reader;
REVOKE console_output_reader FROM ctower_svc, ctower_runtime;
