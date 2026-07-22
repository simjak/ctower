REVOKE ALL ON FUNCTION durability_primary_live_evidence() FROM PUBLIC;
REVOKE ALL ON FUNCTION durability_standby_live_evidence() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION durability_primary_live_evidence() TO ctower_svc;
GRANT EXECUTE ON FUNCTION durability_standby_live_evidence() TO ctower_svc;
