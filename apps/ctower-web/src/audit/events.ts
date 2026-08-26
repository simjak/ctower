import type { AuditEvent } from "@ctower/client";
import type { MarkName } from "../ui/marks";

/**
 * What a recorded event says, in the operator's words.
 *
 * The audit read answers the canonical events themselves — `work.changed`,
 * `proof.changed`, `session.started` — and those are the record's own nouns, not
 * a person's. `DESIGN.md` forbids drawing them: a row says what somebody did,
 * and the event's own spelling stays behind the disclosure with the hash and the
 * position, where it is reachable rather than rendered.
 *
 * Three rules hold across every case below:
 *
 * - Nothing is derived. A headline restates a fact the payload carries; a reason
 *   is the reason the command was given, quoted, never summarised.
 * - A mark is drawn only where the event itself is the state. Most rows carry
 *   none, because "somebody changed the priority" is not a state and borrowing
 *   `●` for it would put a proven mark on an unproven thing.
 * - A chip is a state, not a sentence — two words, D9's budget.
 */
export interface Fact {
  readonly label: string;
  /** Machine-owned text — a ref, a digest, a key — renders in the mono face. */
  readonly machine: boolean;
  readonly value: string;
}

export interface AuditRow {
  readonly id: string;
  /** The recorded instant, verbatim; the panel decides how to draw it. */
  readonly at: string;
  readonly headline: string;
  /** The reason, the comment, the title — quoted from the payload or absent. */
  readonly detail: string | null;
  readonly chip: string | null;
  readonly mark: MarkName | null;
  readonly facts: readonly Fact[];
}

export function rowOf(event: AuditEvent): AuditRow {
  const said = saidOf(event);
  return {
    id: event.event_id,
    at: event.occurred_at,
    headline: said.headline,
    detail: said.detail,
    chip: said.chip,
    mark: said.mark,
    facts: [...said.facts, ...identityOf(event)],
  };
}

interface Said {
  readonly headline: string;
  readonly detail: string | null;
  readonly chip: string | null;
  readonly mark: MarkName | null;
  readonly facts: readonly Fact[];
}

/** Every row can be traced to its own line in the record. */
function identityOf(event: AuditEvent): readonly Fact[] {
  return [
    { label: "Event", machine: true, value: event.kind },
    { label: "Actor", machine: true, value: event.actor_principal_id },
    { label: "Command", machine: true, value: event.command_id },
    { label: "Stream", machine: true, value: `${event.stream_id} @ ${String(event.sequence)}` },
    { label: "Position", machine: true, value: String(event.record_position) },
    { label: "Hash", machine: true, value: event.event_hash },
  ];
}

function saidOf(event: AuditEvent): Said {
  switch (event.kind) {
    case "ticket.created":
      return {
        headline: "Raised",
        detail: event.payload.title,
        chip: event.payload.priority,
        mark: null,
        facts: [
          { label: "Source", machine: true, value: event.payload.source_ref },
          { label: "Custodian", machine: true, value: event.payload.custodian_id },
        ],
      };
    case "ticket.custody_transferred":
      return {
        headline: "Custody moved",
        detail: event.payload.reason,
        chip: null,
        mark: null,
        facts: [
          { label: "From", machine: true, value: event.payload.from_custodian_id },
          { label: "To", machine: true, value: event.payload.to_custodian_id },
        ],
      };
    case "ticket.comment_added":
      return {
        headline: "Comment",
        detail: event.payload.body,
        chip: null,
        mark: null,
        facts: [{ label: "Comment", machine: true, value: event.payload.comment_id }],
      };
    case "work.changed":
      return workSaid(event.payload);
    case "workflow.changed":
      return workflowSaid(event.payload);
    case "proof.changed":
      return proofSaid(event.payload);
    case "session.started":
      return sessionStartedSaid(event.payload);
    case "session.transitioned":
      return {
        headline: `Session ${event.payload.to_state}`,
        detail: event.payload.reason,
        chip: null,
        mark: null,
        facts: [{ label: "From", machine: true, value: event.payload.from_state }],
      };
    case "session.closed":
      return sessionClosedSaid(event.payload);
  }
}

type WorkPayload = Extract<AuditEvent, { kind: "work.changed" }>["payload"];

/** The eight work intents, and the four of them that are themselves a state. */
function workSaid(payload: WorkPayload): Said {
  switch (payload.operation) {
    case "admitted":
      return plain(
        "Admitted",
        payload.data.reason,
        `Episode ${String(payload.data.episode_number)}`
      );
    case "priority_changed":
      return plain(
        "Priority changed",
        payload.data.reason,
        `${payload.data.from_priority} → ${payload.data.to_priority}`
      );
    case "assignment_changed":
      return {
        ...plain(
          "Assignment changed",
          payload.data.reason,
          assignmentWord(payload.data.assignment_kind)
        ),
        facts: [{ label: "To", machine: true, value: payload.data.to_principal_id }],
      };
    case "relation_added":
      return {
        ...plain("Related", payload.data.reason, relationWord(payload.data.relation_kind)),
        facts: [{ label: "Target", machine: true, value: payload.data.target_ticket_id }],
      };
    case "deferred":
      return {
        ...plain("Deferred", payload.data.reason, null),
        mark: "idle",
        facts: [{ label: "Review after", machine: true, value: payload.data.review_after }],
      };
    case "blocker_opened":
      return {
        ...plain("Blocked", payload.data.reason, payload.data.board_impact ? "On board" : null),
        mark: "parked",
      };
    case "blocker_resolved":
      return {
        ...plain("Unblocked", payload.data.reason, null),
        facts: [{ label: "Evidence", machine: true, value: payload.data.resolution_evidence_ref }],
      };
    case "reopened":
      return plain("Reopened", payload.data.reason, payload.data.priority);
  }
}

type WorkflowPayload = Extract<AuditEvent, { kind: "workflow.changed" }>["payload"];

/**
 * A stage is the workflow's own word and it renders as itself: it is the label
 * the pack authored, and inventing a prettier one here would make the console
 * and `ctowerctl workflow` disagree about what stage a ticket stands at.
 */
function workflowSaid(payload: WorkflowPayload): Said {
  const moved =
    payload.source_stage === "" ? payload.stage : `${payload.source_stage} → ${payload.stage}`;
  const facts: readonly Fact[] = [
    { label: "Workflow", machine: true, value: payload.workflow_ref },
  ];
  if (payload.operation === "start") {
    return { headline: "Work started", detail: null, chip: payload.stage, mark: null, facts };
  }
  if (payload.operation === "transition") {
    return { headline: "Stage moved", detail: null, chip: moved, mark: null, facts };
  }
  return { headline: "Closed", detail: null, chip: moved, mark: "done", facts };
}

type ProofPayload = Extract<AuditEvent, { kind: "proof.changed" }>["payload"];

const PROOF_WORD: Readonly<Record<ProofPayload["operation"], string>> = {
  freeze_criteria: "Criteria frozen",
  record_evidence: "Evidence recorded",
  record_verdict: "Verdict recorded",
  change_candidate: "Candidate changed",
};

/**
 * A verdict's own decision is not in this payload, so no row here says passed or
 * failed. `record_verdict` means a verdict was recorded, and that is all it is
 * drawn as — the proof read is where a decision lives.
 */
function proofSaid(payload: ProofPayload): Said {
  const invalidated =
    payload.invalidated_evidence_ids.length + payload.invalidated_verdict_ids.length;
  return {
    headline: PROOF_WORD[payload.operation],
    detail: null,
    chip: invalidated === 0 ? null : `${String(invalidated)} invalidated`,
    mark: null,
    facts: [{ label: "Candidate", machine: true, value: payload.candidate_digest }],
  };
}

type SessionStartedPayload = Extract<AuditEvent, { kind: "session.started" }>["payload"];

function sessionStartedSaid(payload: SessionStartedPayload): Said {
  return {
    headline: "Session opened",
    detail: null,
    chip: payload.crew_name,
    mark: null,
    facts: [
      { label: "Seat", machine: true, value: payload.seat_key },
      { label: "Model", machine: true, value: payload.model_ref },
      { label: "Harness", machine: true, value: payload.harness_ref },
      { label: "Branch", machine: true, value: payload.branch_ref },
      { label: "Worktree", machine: true, value: payload.worktree_ref },
    ],
  };
}

type SessionClosedPayload = Extract<AuditEvent, { kind: "session.closed" }>["payload"];

/** Delivered is proven, blocked is parked, and the other two are dead. */
const OUTCOME_MARK: Readonly<Record<SessionClosedPayload["outcome"], MarkName>> = {
  delivered: "done",
  blocked: "parked",
  abandoned: "dead",
  failed: "dead",
};

function sessionClosedSaid(payload: SessionClosedPayload): Said {
  const tokens = payload.input_tokens + payload.output_tokens;
  const evidence: readonly Fact[] =
    payload.evidence_ref === null
      ? []
      : [{ label: "Evidence", machine: true, value: payload.evidence_ref }];
  return {
    headline: "Session closed",
    detail: null,
    chip: payload.outcome,
    mark: OUTCOME_MARK[payload.outcome],
    facts: [
      { label: "Ran for", machine: false, value: `${String(payload.duration_seconds)}s` },
      { label: "Tokens", machine: true, value: tokens.toLocaleString("en-US") },
      ...evidence,
    ],
  };
}

function plain(headline: string, detail: string, chip: string | null): Said {
  return { headline, detail, chip, mark: null, facts: [] };
}

const ASSIGNMENT_WORD: Readonly<Record<string, string>> = {
  current_assignee: "Assignee",
  stage_owner: "Stage owner",
  reviewer_assignment: "Reviewer",
};

function assignmentWord(kind: string): string {
  return ASSIGNMENT_WORD[kind] ?? kind;
}

const RELATION_WORD: Readonly<Record<string, string>> = {
  parent_of: "Parent of",
  depends_on: "Depends on",
  blocks: "Blocks",
  duplicates: "Duplicates",
  relates_to: "Relates to",
  caused_by: "Caused by",
};

function relationWord(kind: string): string {
  return RELATION_WORD[kind] ?? kind;
}

/**
 * A recorded instant, as the record holds it: UTC, to the minute.
 *
 * Not the reader's locale. Two people looking at the same feed must be looking
 * at the same instant, and the record's own zone is the only one both of them
 * can check against the log.
 */
export function instant(iso: string): string {
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? iso : `${at.toISOString().slice(0, 16).replace("T", " ")}Z`;
}
