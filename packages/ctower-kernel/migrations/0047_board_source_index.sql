CREATE INDEX board_projection_project_source
    ON board_projection_rows (tenant_id, project_key, source_kind, source_ref);
