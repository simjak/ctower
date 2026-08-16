import { requestsFrom } from "../../apps/ctower-ui/src/read/httpRecordAdapter.ts";

function outcome(run: () => unknown): { readonly thrown: boolean; readonly value?: unknown } {
  try {
    return { thrown: false, value: run() };
  } catch {
    return { thrown: true };
  }
}

const row = {
  request_id: "request-two",
  request_number: 2,
  reference: "R2",
  project_key: "ctower",
  content: "second record row",
  content_sha256: "sha256:2222",
  state: "NEW",
  triage: "UNTRIAGED",
  owner_id: "owner-two",
  owner: "",
  priority: "P2",
  priority_default: true,
  created_at: "2026-08-16T00:00:00Z",
  age_seconds: 12,
  required_ticket_ids: ["ticket-two"],
  optional_ticket_ids: [],
  blocker: null,
  proof_coverage: 0,
  durability_state: "accepted",
  freshness: 7,
  source_kind: "cli",
  source_ref: "request-two",
  original_owner_sha256: null,
  decision_brief: null,
  unknown_reason: null,
};

const snapshot = {
  rows: [
    row,
    {
      ...row,
      request_id: "request-one",
      request_number: 1,
      reference: "R1",
      content: "first record row",
      content_sha256: "sha256:1111",
      owner: "operator",
    },
  ],
  answered_project_count: 1,
  answered_projects: ["ctower"],
  observed_at: "2026-08-16T00:01:00Z",
  requested_project_count: 1,
  requested_projects: ["ctower"],
  unanswered_projects: [],
  watermark: 7,
};

const { unanswered_projects: _unanswered, ...snapshotWithoutUnanswered } = snapshot;

process.stdout.write(
  JSON.stringify({
    parsed: requestsFrom(snapshot),
    rejectsUnknownState: outcome(() =>
      requestsFrom({ ...snapshot, rows: [{ ...row, state: "MAYBE" }] })
    ),
    rejectsMissingUnansweredProjects: outcome(() => requestsFrom(snapshotWithoutUnanswered)),
    rejectsMissingRowField: outcome(() =>
      requestsFrom({
        ...snapshot,
        rows: [{ ...row, content_sha256: undefined }],
      })
    ),
  })
);
