import { boundedMutation, ReadExhausted } from "../../apps/ctower-ui/src/read/bounded.ts";
import { promoteInboxThread } from "../../apps/ctower-ui/src/mutate/inboxPromotion.ts";

const threadId = "018f0d5e-7b9a-7c01-8000-000000000600";
const ticketId = "018f0d5e-7b9a-7c01-8000-000000000010";

const promoted = {
  command_id: "018f0d5e-7b9a-7c01-8000-000000000700",
  durability_state: "accepted",
  event_ids: ["018f0d5e-7b9a-7c01-8000-000000000701"],
  outcome: "ticket_linked",
  thread_id: threadId,
  thread_version: 3,
  ticket_id: ticketId,
};

const alreadyPromoted = {
  code: "inbox-already-promoted",
  detail: "The inbox thread is already linked to a ticket.",
  status: 409,
  title: "Inbox promotion refused",
  type: "https://ctower.invalid/problems/inbox-already-promoted",
};

async function main(): Promise<void> {
  process.env.CTOWER_UI_API_TOKEN = "test-credential";
  const requests: Array<{
    readonly url: string;
    readonly method: string;
    readonly body: string;
    readonly idempotencyKey: string | null;
  }> = [];
  globalThis.fetch = async (input, init): Promise<Response> => {
    const request = init ?? {};
    requests.push({
      url: String(input),
      method: String(request.method),
      body: String(request.body),
      idempotencyKey: new Headers(request.headers).get("Idempotency-Key"),
    });
    return new Response(JSON.stringify(promoted), { status: 200 });
  };
  const success = await promoteInboxThread(threadId, ticketId);

  globalThis.fetch = async (): Promise<Response> =>
    new Response(JSON.stringify(alreadyPromoted), {
      status: 409,
      headers: { "content-type": "application/problem+json" },
    });
  const refusal = await promoteInboxThread(threadId, null);

  const retryKeys: string[] = [];
  let retryResponses = 0;
  globalThis.fetch = async (_input, init): Promise<Response> => {
    retryResponses += 1;
    retryKeys.push(new Headers(init?.headers).get("Idempotency-Key") ?? "");
    if (retryResponses === 1) {
      return new Response(JSON.stringify({ status: 503 }), { status: 503 });
    }
    return new Response(JSON.stringify(promoted), { status: 200 });
  };
  const retryThenSuccess = await boundedMutation(
    "http://127.0.0.1:8091/v1/inbox/threads/retry/promotion",
    { "Idempotency-Key": "promotion-retry-key" },
    "{}",
    { attemptTimeoutMs: 50, maxAttempts: 3, maxElapsedMs: 1_000, baseDelayMs: 0, maxDelayMs: 0 }
  );

  const retryableStatuses = [408, 425, 429, 500, 502, 503, 504];
  const retryableStatusKeys: Array<{ readonly status: number; readonly keys: readonly string[] }> =
    [];
  for (const status of retryableStatuses) {
    const keys: string[] = [];
    let responses = 0;
    globalThis.fetch = async (_input, init): Promise<Response> => {
      responses += 1;
      keys.push(new Headers(init?.headers).get("Idempotency-Key") ?? "");
      if (responses === 1) {
        return new Response(JSON.stringify({ status }), { status });
      }
      return new Response(JSON.stringify(promoted), { status: 200 });
    };
    await boundedMutation(
      `http://127.0.0.1:8091/v1/inbox/threads/retry-${status.toString()}/promotion`,
      { "Idempotency-Key": `promotion-retry-${status.toString()}-key` },
      "{}",
      { attemptTimeoutMs: 50, maxAttempts: 3, maxElapsedMs: 1_000, baseDelayMs: 0, maxDelayMs: 0 }
    );
    retryableStatusKeys.push({ status, keys });
  }

  const exhaustionKeys: string[] = [];
  globalThis.fetch = async (_input, init): Promise<Response> => {
    exhaustionKeys.push(new Headers(init?.headers).get("Idempotency-Key") ?? "");
    return new Response(JSON.stringify({ status: 503 }), { status: 503 });
  };
  let exhaustion: ReadExhausted | null = null;
  try {
    await boundedMutation(
      "http://127.0.0.1:8091/v1/inbox/threads/exhaust/promotion",
      { "Idempotency-Key": "promotion-exhaustion-key" },
      "{}",
      { attemptTimeoutMs: 50, maxAttempts: 3, maxElapsedMs: 1_000, baseDelayMs: 0, maxDelayMs: 0 }
    );
  } catch (error: unknown) {
    if (!(error instanceof ReadExhausted)) {
      throw error;
    }
    exhaustion = error;
  }

  process.stdout.write(
    JSON.stringify({
      success,
      refusal,
      request: requests[0],
      retryThenSuccess: { result: retryThenSuccess, keys: retryKeys },
      retryableStatusKeys,
      exhaustion: exhaustion === null ? null : exhaustion.failure,
      exhaustionKeys,
    })
  );
}

void main();
