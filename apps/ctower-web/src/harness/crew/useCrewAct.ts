import { useCallback, useRef, useState } from "react";
import type {
  CompanyBundleCommandResult,
  CompanyBundleDocument,
  CompanyBundlePlan,
  DurabilityState,
  SeatCredentialIssueRequest,
  SeatCredentialReceipt,
} from "@ctower/client";
import { ask, ASKING, commands, computations, resendable } from "../../api/client";
import type { Answer } from "../../api/client";
import { canonicalDigest } from "../../mint/digest";
import { commandKeyFor } from "../../api/commandKey";
import { bindingFor, boundAlready, withBinding } from "./binding";
import type { ProfileOption } from "./binding";
import { blankDraft, issueBody, referenceFor } from "./draft";
import type { CrewDraft } from "./draft";
import type { Minted } from "./roster";

/**
 * Defining a crew: one act, two commands, in the order the record needs them.
 *
 * A crew is a profile and a working address, and ctower keeps those in two
 * different places — the company bundle carries the binding, `issueSeatCredential`
 * mints the address. That is the shape of the record, not of the job, so the job
 * is one form, one review and one confirmation, and the two commands are what
 * runs underneath.
 *
 * The binding goes first. An address is issued *for* a crew, and minting one for
 * a profile the company does not record would put a live credential in front of
 * an identity nothing knows about — so if the bundle refuses, nothing is minted
 * and the screen says exactly that.
 *
 * Both commands are keyed, and both keys are derived from what is being sent, so
 * a retry of either is the same command rather than a second one.
 */
export interface Proposal {
  readonly document: CompanyBundleDocument;
  readonly plan: CompanyBundlePlan;
  readonly valid: boolean;
}

interface Sending {
  readonly subject: string;
  /** Frozen at review, so what is sent is what the operator was shown. */
  readonly body: SeatCredentialIssueRequest;
  /** Null when the company already binds this profile; then only the address moves. */
  readonly binding: Answer<Proposal> | null;
}

export type Stage = "define" | "review" | "sent";

export interface CrewAct {
  readonly draft: CrewDraft;
  readonly setDraft: (draft: CrewDraft) => void;
  readonly stage: Stage;
  readonly sending: Sending | null;
  readonly armed: boolean;
  readonly setArmed: (armed: boolean) => void;
  readonly openReview: (
    document: CompanyBundleDocument,
    profile: ProfileOption,
    subject: string
  ) => void;
  readonly back: () => void;
  readonly run: () => void;
  readonly bound: Answer<CompanyBundleCommandResult> | null;
  readonly address: Answer<SeatCredentialReceipt> | null;
  readonly retry: (() => void) | null;
}

export function useCrewAct(
  record: (minted: Minted) => void,
  onApplied: (() => void) | undefined,
  start: CrewDraft = blankDraft("", "")
): CrewAct {
  const [draft, setDraftState] = useState<CrewDraft>(start);
  const [sending, setSending] = useState<Sending | null>(null);
  const [armed, setArmed] = useState(false);
  const [bound, setBound] = useState<Answer<CompanyBundleCommandResult> | null>(null);
  const [address, setAddress] = useState<Answer<SeatCredentialReceipt> | null>(null);
  const generation = useRef(0);

  const supersede = useCallback((): number => {
    generation.current += 1;
    return generation.current;
  }, []);

  /**
   * Leaving the receipt. An address that was minted is now the record's, so the
   * next crew starts from an empty identity rather than from one that would only
   * ever be refused as already taken; a crew that got nowhere keeps its draft so
   * the operator can fix the one field that was wrong.
   */
  const back = useCallback((): void => {
    supersede();
    if (address?.kind === "answered") {
      setDraftState((held) => ({
        ...held,
        name: "",
        seatKey: "",
        refLocator: "",
        fingerprint: "",
      }));
    }
    setSending(null);
    setArmed(false);
    setBound(null);
    setAddress(null);
  }, [address, supersede]);

  const setDraft = useCallback(
    (next: CrewDraft): void => {
      supersede();
      setDraftState(next);
    },
    [supersede]
  );

  const openReview = useCallback(
    (document: CompanyBundleDocument, profile: ProfileOption, subject: string): void => {
      const mine = supersede();
      // No reference, no command: the review is where the address request is
      // frozen, and there is nothing honest to freeze for a place ctower would
      // be told is a credential.
      const reference = referenceFor(draft);
      if (reference === null) {
        return;
      }
      const body = issueBody(draft, subject, reference);
      const binding = bindingFor(profile, subject);
      setArmed(false);
      setBound(null);
      setAddress(null);
      if (boundAlready(document, binding)) {
        setSending({ subject, body, binding: null });
        return;
      }
      setSending({ subject, body, binding: ASKING });
      void (async (): Promise<void> => {
        const answer = await proposalOf(withBinding(document, binding));
        if (generation.current === mine) {
          setSending({ subject, body, binding: answer });
        }
      })();
    },
    [draft, supersede]
  );

  const sendAddress = useCallback(
    async (open: Sending, from?: number): Promise<void> => {
      // A retry starts its own generation; `run` hands over the one it captured
      // before the bundle command, so leaving the screen mid-flight still drops
      // the answer instead of landing it on a screen nobody is looking at.
      const mine = from ?? generation.current;
      setAddress(ASKING);
      const answer = await ask(() =>
        commands.issueSeatCredential({
          IdempotencyKey: commandKeyFor(canonicalDigest(open.body)),
          body: open.body,
        })
      );
      if (generation.current !== mine) {
        return;
      }
      setAddress(answer);
      if (answer.kind === "answered") {
        record({ subject: open.subject, receipt: answer.value });
      }
    },
    [record]
  );

  const run = useCallback((): void => {
    if (sending === null) {
      return;
    }
    const mine = generation.current;
    const open = sending;
    void (async (): Promise<void> => {
      if (open.binding !== null) {
        if (open.binding.kind !== "answered") {
          return;
        }
        const written = await applyBinding(open.binding.value, setBound);
        if (generation.current !== mine || !accepted(written)) {
          return;
        }
        onApplied?.();
      }
      await sendAddress(open, mine);
    })();
  }, [onApplied, sendAddress, sending]);

  return {
    draft,
    setDraft,
    stage: stageOf(sending, bound, address),
    sending,
    armed,
    setArmed,
    openReview,
    back,
    run,
    bound,
    address,
    retry: retryFor(sending, bound, address, run, sendAddress),
  };
}

function stageOf(
  sending: Sending | null,
  bound: Answer<CompanyBundleCommandResult> | null,
  address: Answer<SeatCredentialReceipt> | null
): Stage {
  if (sending === null) {
    return "define";
  }
  return bound === null && address === null ? "review" : "sent";
}

/**
 * Nothing sent is not something to resend. Everything else is the shared rule:
 * the API was not reached, its answer could not be read, or it took the command
 * and has not confirmed it is durable. A refusal is none of those.
 */
function resendableAnswer(
  answer: Answer<{ readonly durability_state: DurabilityState }> | null
): boolean {
  return answer !== null && resendable(answer);
}

/**
 * The retry resumes where the act stopped rather than starting it again. A
 * bundle that was already accepted must not be re-sent to reach the address it
 * never got to.
 */
function retryFor(
  sending: Sending | null,
  bound: Answer<CompanyBundleCommandResult> | null,
  address: Answer<SeatCredentialReceipt> | null,
  run: () => void,
  sendAddress: (open: Sending) => Promise<void>
): (() => void) | null {
  if (sending === null) {
    return null;
  }
  if (address !== null) {
    return resendableAnswer(address)
      ? (): void => {
          void sendAddress(sending);
        }
      : null;
  }
  return resendableAnswer(bound) ? run : null;
}

function accepted(written: Answer<CompanyBundleCommandResult>): boolean {
  return written.kind === "answered" && written.value.durability_state === "accepted";
}

async function applyBinding(
  proposal: Proposal,
  onOutcome: (answer: Answer<CompanyBundleCommandResult>) => void
): Promise<Answer<CompanyBundleCommandResult>> {
  onOutcome(ASKING);
  const answer = await ask(() =>
    commands.applyCompanyBundle({
      IdempotencyKey: commandKeyFor(proposal.plan.plan_digest),
      body: {
        bundle: proposal.document,
        expected_active_version: proposal.plan.base_version,
        plan_digest: proposal.plan.plan_digest,
      },
    })
  );
  onOutcome(answer);
  return answer;
}

/** Check and plan one document, and stop at the first thing that is not an answer. */
async function proposalOf(bundle: CompanyBundleDocument): Promise<Answer<Proposal>> {
  const validation = await ask(() => computations.validateCompanyBundle({ body: { bundle } }));
  if (validation.kind !== "answered") {
    return validation;
  }
  const plan = await ask(() => computations.planCompanyBundle({ body: { bundle } }));
  if (plan.kind !== "answered") {
    return plan;
  }
  return {
    kind: "answered",
    value: { document: bundle, plan: plan.value, valid: validation.value.valid },
  };
}
