# Ticket movement

Ticket movement is the accepted workflow transition history for a Project. It
answers where work moved without creating a second Ticket status ledger.

## Movement facts

Each accepted stage transition contributes one `workflow.changed` fact to the
canonical event stream. A transition fact names:

- the stable Ticket identity;
- the exact source and destination stages;
- the authenticated Actor envelope;
- the server occurrence time and record position; and
- a stable pointer to the transition evaluation and evidence manifest.

A replay returns the original result and does not append another movement fact.
A refused or pending transition does not create movement. Movement facts link to
the Ticket; they do not copy the Ticket title, description, comments, or an
exhaustive Ticket snapshot.

## Project movement read

The read surface is one cursor over the accepted Project event stream:

- `GET /v1/projects/{project_key}/movement` returns strict JSON movement facts.
- `ctowerctl project movement <project-key>` returns the same generated read.
- `GET /v1/projects/{project_key}/movement.atom` renders the same page as Atom
  1.0 for feed readers.

Pages are ordered by record position. Use `cursor` from the preceding page and
choose a bounded `limit`; Atom exposes the same cursor as its `next` link. Each
Atom entry has a stable event ID, server timestamp, and an authorized link to
the Ticket timeline.

All three reads use the existing direct-API Bearer authentication and Project
scope checks. Anonymous requests, credentials in query strings, special feed
tokens, and new principals are not supported. The read is online-only and does
not enter the protected mutation spool.

## Morning digest movement

The morning digest counts accepted movement during the prior Europe/Vilnius
civil day. Counts are grouped by Project and exact source/destination stage.
The digest carries the movement view pointer, source watermark, and completeness
state, but no movement rows, Ticket identity, or Ticket text. A complete empty
source is a measured zero; an unavailable or partial source remains unknown and
names its unreached scope.

## Planned follow-on views

### Stall clocks — planned

Typed wait episodes, thresholds, rechecks, and uncertainty will be derived from
the same durable movement stream. This section is intentionally planned and is
not a current command, API operation, schedule, or notification.

### Commander beat worklist — planned

A future worklist will re-derive owned nonterminal Tickets in full and use a
movement cursor only for the change delta. This section is intentionally planned
and is not a current command, API operation, model prompt, or runner behavior.

## Boundaries

Movement is a read of canonical Record events. It does not create a projection
ledger, schedule, notification route, product UI route, anonymous feed, or
transport for Ticket text. See [Secret handling](../security/secret-handling.md)
for the credential boundary and [the HTTP reference](../reference/http-api.md)
for the generated operation details.
