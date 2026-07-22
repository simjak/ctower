SET ROLE ctower_durability_probe;
ALTER FUNCTION public.durability_primary_live_evidence()
    SET search_path = pg_catalog, pg_temp;
ALTER FUNCTION public.durability_standby_live_evidence()
    SET search_path = pg_catalog, pg_temp;
SET ROLE ctower_admin;
