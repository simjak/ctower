DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'console_output_reader') THEN
        CREATE ROLE console_output_reader NOLOGIN NOINHERIT;
    END IF;
END
$$;

GRANT console_output_reader TO ctower_admin;
GRANT USAGE, CREATE ON SCHEMA public TO console_output_reader;
REVOKE console_output_reader FROM ctower_svc, ctower_runtime;
