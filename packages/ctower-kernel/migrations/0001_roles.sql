DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ctower_admin') THEN
        CREATE ROLE ctower_admin NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ctower_svc') THEN
        CREATE ROLE ctower_svc NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ctower_projection') THEN
        CREATE ROLE ctower_projection NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ctower_runtime') THEN
        CREATE ROLE ctower_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ctower_migrator') THEN
        CREATE ROLE ctower_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
END
$$;

GRANT ctower_svc TO ctower_runtime;
GRANT ctower_admin TO ctower_migrator;
REVOKE ctower_admin FROM ctower_runtime;
REVOKE ctower_projection FROM ctower_runtime;
REVOKE ctower_svc, ctower_projection FROM ctower_migrator;
GRANT USAGE, CREATE ON SCHEMA public TO ctower_admin;
