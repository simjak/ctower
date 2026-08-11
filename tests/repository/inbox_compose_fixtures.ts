import { composeInboxThread } from "../../apps/ctower-ui/src/mutate/inboxCompose.ts";
import type { InboxComposeState } from "../../apps/ctower-ui/src/mutate/types.ts";

const threadId = "018f0d5e-7b9a-7c01-8000-000000000600";

/** No answer yet, so nothing to replay: what a first compose always carries. */
const FIRST: InboxComposeState = { kind: "idle" };

/** The record's own closed world: the seats this principal may address. */
const correspondents = {
  sender: "ctower-commander",
  correspondents: [
    { project_key: "ctower", seat_key: "director" },
    { project_key: "ctower", seat_key: "engineer" },
  ],
};

const started = {
  command_id: "018f0d5e-7b9a-7c01-8000-000000000700",
  durability_state: "accepted",
  event_ids: ["018f0d5e-7b9a-7c01-8000-000000000701"],
  from: "ctower-commander",
  message_id: "018f0d5e-7b9a-7c01-8000-000000000702",
  position: 1,
  sent_at: "2026-08-09T03:05:00Z",
  thread_id: threadId,
  thread_version: 2,
  to: "director",
};

/**
 * The same authored answer, explicitly *not* accepted.
 *
 * The command committed, but the off-host durable acknowledgement it needs did
 * not, so the record answers `202` and names the state it is really in. Every
 * other byte is identical — thread identity included — so only the
 * discriminator says whether this conversation exists.
 */
const unconfirmed = { ...started, durability_state: "durability_pending" };

const unaddressable = {
  code: "inbox-sender-unaddressable",
  detail: "The authenticated principal has no addressable project seat.",
  status: 422,
  title: "Inbox command refused",
  type: "https://ctower.invalid/problems/inbox-sender-unaddressable",
};

interface Attempt {
  readonly method: string;
  readonly url: string;
  readonly body: string;
  readonly bodyKeys: readonly string[];
  readonly idempotencyKey: string | null;
  readonly authorized: boolean;
}

function attemptOf(input: RequestInfo | URL, init: RequestInit | undefined): Attempt {
  const request = init ?? {};
  const body = request.body === undefined ? "" : String(request.body);
  const headers = new Headers(request.headers);
  return {
    method: String(request.method ?? "GET"),
    url: String(input),
    body,
    bodyKeys: body === "" ? [] : Object.keys(JSON.parse(body) as Record<string, unknown>).sort(),
    idempotencyKey: headers.get("Idempotency-Key"),
    authorized: headers.get("Authorization") !== null,
  };
}

/**
 * Serve the correspondents read, then hand every command to `answer`.
 *
 * `answer` receives the attempt as well as its ordinal, because the record
 * echoes the seat it actually addressed: a stub that always named one seat
 * would make a compose to another seat look like an answer about the wrong
 * conversation, which is a thing this surface is required to refuse.
 */
function transcript(answer: (attempt: number, sent: Attempt) => Response): Attempt[] {
  const attempts: Attempt[] = [];
  let commands = 0;
  globalThis.fetch = (input, init): Promise<Response> => {
    const attempt = attemptOf(input, init);
    attempts.push(attempt);
    if (attempt.method === "GET") {
      return Promise.resolve(new Response(JSON.stringify(correspondents), { status: 200 }));
    }
    commands += 1;
    return Promise.resolve(answer(commands, attempt));
  };
  return attempts;
}

/** The seat one command attempt addressed, as the record would echo it back. */
function addressed(sent: Attempt): string {
  return String((JSON.parse(sent.body) as { readonly to: string }).to);
}

/** The key each command attempt carried, in the order they were attempted. */
function commandKeys(attempts: readonly Attempt[]): Array<string | null> {
  return attempts.filter((attempt) => attempt.method === "POST").map((a) => a.idempotencyKey);
}

async function main(): Promise<void> {
  process.env.CTOWER_UI_API_TOKEN = "test-credential";

  const accepted = transcript(() => new Response(JSON.stringify(started), { status: 201 }));
  const success = await composeInboxThread("director", "  open the conversation  ", FIRST);

  const refusedAttempts = transcript(
    () =>
      new Response(JSON.stringify(unaddressable), {
        status: 422,
        headers: { "content-type": "application/problem+json" },
      })
  );
  const refusal = await composeInboxThread("director", "who am I here?", FIRST);

  // A seat the record does not list is refused before the boundary: the picker
  // is the closed world, and a browser that names something outside it is not
  // handed to the record as an address.
  const strangerAttempts = transcript(() => new Response(null, { status: 500 }));
  const stranger = await composeInboxThread("nobody", "hello?", FIRST);

  // No seat picked, and an empty message: neither reaches the boundary.
  const unpickedAttempts = transcript(() => new Response(null, { status: 500 }));
  const unpicked = await composeInboxThread("", "who is this for?", FIRST);

  const blankAttempts = transcript(() => new Response(null, { status: 500 }));
  const blank = await composeInboxThread("director", "   \n  ", FIRST);

  // A retryable status re-enters the bounded loop under the one minted key.
  const retryAttempts = transcript((attempt) =>
    attempt === 1
      ? new Response(JSON.stringify({ status: 503 }), { status: 503 })
      : new Response(JSON.stringify(started), { status: 201 })
  );
  const retried = await composeInboxThread("director", "second attempt, same key", FIRST);

  // A terminal refusal whose body is not a problem document stays terminal.
  transcript(
    () => new Response("conflict", { status: 409, headers: { "content-type": "text/plain" } })
  );
  const opaque = await composeInboxThread("director", "no problem document here", FIRST);

  // An explicit non-accepted answer. No conversation was started, so the words
  // and the chosen seat stay with the sender and the command keeps its identity.
  const heldAttempts = transcript(() => new Response(JSON.stringify(unconfirmed), { status: 202 }));
  const held = await composeInboxThread("director", "  is this recorded?  ", FIRST);

  // The sender presses the box again. The retry carries the identity the first
  // attempt minted, so the record replays one command rather than opening a
  // second conversation.
  const replayAttempts = transcript((attempt) =>
    attempt === 1
      ? new Response(JSON.stringify(unconfirmed), { status: 202 })
      : new Response(JSON.stringify(started), { status: 201 })
  );
  const unresolved = await composeInboxThread("director", "  is this recorded?  ", FIRST);
  const resolved = await composeInboxThread("director", "  is this recorded?  ", unresolved);

  // Same words, different seat: a different request, so a different command.
  const readdressedAttempts = transcript(
    (_attempt, sent) =>
      new Response(JSON.stringify({ ...unconfirmed, to: addressed(sent) }), { status: 202 })
  );
  const first = await composeInboxThread("director", "the same words", FIRST);
  const readdressed = await composeInboxThread("engineer", "the same words", first);

  // A replay identity that is not one is refused before the boundary rather
  // than sent to the record as a key.
  const forgedAttempts = transcript(() => new Response(JSON.stringify(started), { status: 201 }));
  const forged = await composeInboxThread("director", "tampered state", {
    kind: "pending",
    message: "held",
    text: "tampered state",
    to: "director",
    commandId: "not-a-command-identity",
  });

  process.stdout.write(
    JSON.stringify({
      success,
      accepted,
      refusal,
      refusedAttempts,
      stranger,
      strangerAttempts,
      unpicked,
      unpickedAttempts,
      blank,
      blankAttempts,
      retried,
      retryKeys: commandKeys(retryAttempts),
      opaque,
      held,
      heldKeys: commandKeys(heldAttempts),
      unresolved,
      resolved,
      replayKeys: commandKeys(replayAttempts),
      first,
      readdressed,
      readdressedKeys: commandKeys(readdressedAttempts),
      forged,
      forgedAttempts,
    })
  );
}

void main();
