DO $$
DECLARE
    recovery_role text;
BEGIN
    FOREACH recovery_role IN ARRAY ARRAY[
        'ctower_object', 'ctower_backup', 'ctower_anchor', 'ctower_restore'
    ]
    LOOP
        IF EXISTS (
            SELECT 1
            FROM pg_catalog.pg_authid AS role
            WHERE role.rolname = recovery_role
              AND (
                  role.rolcanlogin OR role.rolsuper OR role.rolcreatedb
                  OR role.rolcreaterole OR role.rolinherit OR role.rolreplication
                  OR role.rolbypassrls OR role.rolconnlimit <> -1
                  OR role.rolpassword IS NOT NULL OR role.rolvaliduntil IS NOT NULL
                  OR EXISTS (
                      SELECT 1 FROM pg_catalog.pg_auth_members AS membership
                      WHERE membership.roleid = role.oid OR membership.member = role.oid
                  )
                  OR EXISTS (
                      SELECT 1 FROM pg_catalog.pg_db_role_setting AS setting
                      WHERE setting.setrole = role.oid
                  )
              )
        ) THEN
            RAISE EXCEPTION
                'recovery role configuration does not match the declared catalog shape';
        END IF;
    END LOOP;
END
$$;

-- ctower_admin owns recovery tables but not the PostgreSQL 17 public schema. Give
-- only the migration role the grant option needed for 0023's declared USAGE grants.
GRANT USAGE ON SCHEMA public TO ctower_admin WITH GRANT OPTION;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ctower_object') THEN
        CREATE ROLE ctower_object NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
            NOREPLICATION NOBYPASSRLS CONNECTION LIMIT -1;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ctower_backup') THEN
        CREATE ROLE ctower_backup NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
            NOREPLICATION NOBYPASSRLS CONNECTION LIMIT -1;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ctower_anchor') THEN
        CREATE ROLE ctower_anchor NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
            NOREPLICATION NOBYPASSRLS CONNECTION LIMIT -1;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ctower_restore') THEN
        CREATE ROLE ctower_restore NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
            NOREPLICATION NOBYPASSRLS CONNECTION LIMIT -1;
    END IF;
END
$$;
