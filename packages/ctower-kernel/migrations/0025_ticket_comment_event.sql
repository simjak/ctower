ALTER TABLE events DROP CONSTRAINT events_kind_check;
ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN (
    'bootstrap.first_tenant_created',
    'ticket.created',
    'ticket.custody_transferred',
    'ticket.comment_added',
    'proof.changed',
    'workflow.changed',
    'work.changed',
    'routine.occurrence_recorded',
    'attention.poison_disposition_recorded',
    'catalog.component_published',
    'catalog.bundle_activated'
));
