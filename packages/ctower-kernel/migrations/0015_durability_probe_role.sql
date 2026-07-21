DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ctower_durability_probe') THEN
        CREATE ROLE ctower_durability_probe
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT NOREPLICATION NOBYPASSRLS;
    END IF;
END
$$;

ALTER ROLE ctower_durability_probe
    NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT NOREPLICATION NOBYPASSRLS;
GRANT pg_read_all_stats TO ctower_durability_probe;
GRANT ctower_durability_probe TO ctower_admin WITH INHERIT FALSE, SET TRUE;
GRANT USAGE, CREATE ON SCHEMA public TO ctower_durability_probe;
REVOKE ctower_durability_probe FROM ctower_svc, ctower_runtime, ctower_projection;
