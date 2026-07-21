DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ctower_projection_runtime') THEN
        CREATE ROLE ctower_projection_runtime
            LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    ELSE
        ALTER ROLE ctower_projection_runtime
            LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
END
$$;

GRANT ctower_projection TO ctower_projection_runtime;
REVOKE ctower_svc, ctower_admin FROM ctower_projection_runtime;
