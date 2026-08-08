-- gh#387: preserve the protected #377 read traces after the provider-neutral
-- 0055 transition without restoring a provider-shaped write path.
CREATE VIEW integration_gitlab_sync_progress AS
SELECT tenant_id,
    connector_registration_key AS integration_key,
    registration_revision_id AS component_revision_id,
    revision_digest,
    (cursor_token::jsonb->>'updated_after')::timestamptz AS updated_after,
    (cursor_token::jsonb->>'page')::integer AS page,
    project_event_cursor,
    next_poll_at,
    consecutive_failures,
    claim_owner,
    claim_fence,
    claim_expires_at,
    claimed_at,
    completed_at
FROM connector_sync_progress
WHERE cursor_token::jsonb->>'schema' = 'ctower.gitlab-cursor/v1';

CREATE VIEW integration_gitlab_issue_links AS
SELECT tenant_id,
    connector_registration_key AS integration_key,
    source_registration_revision_id AS source_component_revision_id,
    source_revision_digest,
    split_part(external_ref, ':', 2)::bigint AS gitlab_project_id,
    split_part(external_ref, ':', 3)::bigint AS issue_iid,
    ticket_id,
    thread_id,
    display_url AS web_url,
    linked_at
FROM connector_issue_links
WHERE connector_kind = 'gitlab-issue';

CREATE VIEW integration_gitlab_issue_observations AS
SELECT tenant_id,
    connector_registration_key AS integration_key,
    registration_revision_id AS component_revision_id,
    split_part(external_ref, ':', 2)::bigint AS gitlab_project_id,
    split_part(external_ref, ':', 3)::bigint AS issue_iid,
    payload_digest,
    title,
    description AS body,
    source_labels AS labels,
    ltrim(reporter_reference, '@') AS reporter_username,
    reporter_display_name AS reporter_name,
    external_state AS issue_state,
    display_url AS web_url,
    source_updated_at,
    observed_at
FROM connector_issue_observations
WHERE connector_kind = 'gitlab-issue';

CREATE VIEW integration_gitlab_close_deliveries AS
SELECT tenant_id,
    connector_registration_key AS integration_key,
    registration_revision_id AS component_revision_id,
    split_part(external_ref, ':', 2)::bigint AS gitlab_project_id,
    split_part(external_ref, ':', 3)::bigint AS issue_iid,
    ticket_id,
    command_id AS event_id,
    comment_created,
    issue_closed,
    delivered_at
FROM connector_close_deliveries
WHERE connector_kind = 'gitlab-issue';

REVOKE ALL ON integration_gitlab_sync_progress,
    integration_gitlab_issue_links, integration_gitlab_issue_observations,
    integration_gitlab_close_deliveries
    FROM PUBLIC, ctower_svc, ctower_projection;
GRANT SELECT ON integration_gitlab_sync_progress,
    integration_gitlab_issue_links, integration_gitlab_issue_observations,
    integration_gitlab_close_deliveries
    TO ctower_svc, ctower_projection;
