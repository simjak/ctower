// Drivers for the two contracts the surface makes in words rather than numbers:
// what it cites for a fact it cannot show, and where a nav item promises to go.
//
// Round-3 QA found nine "not built yet" panels all reading *lands with #186* —
// an issue about the operator-channel feed, which covers none of them (#241) —
// and a nav item called *Tickets* that opened the detail page of one arbitrary
// ticket (#243). Both are honesty defects in data this app declares, so both are
// checked here rather than left to a reviewer noticing.
//
// Both modules are pure, so Node runs them directly with type stripping.

import { DECLARED_SOURCES } from "../../apps/ctower-ui/src/read/futureSources.ts";
import { NEW_TICKET_INERT, RAIL } from "../../apps/ctower-ui/src/frame/rail.ts";

process.stdout.write(
  JSON.stringify({ sources: DECLARED_SOURCES, rail: RAIL, newTicket: NEW_TICKET_INERT }, null, 2)
);
