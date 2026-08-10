DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'console_output_reader') THEN
        CREATE ROLE console_output_reader NOLOGIN NOINHERIT;
    END IF;
END
$$;

GRANT console_output_reader TO ctower_svc;
