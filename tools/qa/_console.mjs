/**
 * What both walks need from a live console, in one place.
 *
 * `walk-web.mjs` proves every destination renders. `journey-walk.mjs` proves an
 * operator can get a job done across several of them. They are different
 * questions and stay different files, but they meet the same console the same
 * way — the same admission gate, the same idea of when a screen has finished
 * reading, the same refusal to print a token into a report — so that part is
 * authored once here rather than twice, slightly differently.
 *
 * Nothing in this file knows what is being walked. It takes a page and a
 * target and hands back facts.
 */

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import path from "node:path";

/** How long a screen is given to finish its reads before it is judged. */
export const SETTLE_QUIET_MS = 700;
export const SETTLE_CAP_MS = 20_000;

/**
 * The two states a walk reads as a failed screen rather than as content.
 *
 * Both are authored once in `wizard/states.tsx` and every screen renders them
 * through it, so matching their words is matching the state and not a phrase
 * that happens to appear. A refusal is deliberately not here: a refusal is an
 * answer, and an operator walking a console may legitimately meet one.
 */
export const CONTRACT_ERROR = "ctower answered something this client cannot read.";
export const NO_ANSWER = "ctower did not answer.";

export const RAIL = 'nav[aria-label="Sections"]';

export function loadPlaywright() {
  const root = process.env.WALK_PLAYWRIGHT_ROOT;
  const from = root === undefined ? import.meta.filename : path.join(root, "package.json");
  try {
    return createRequire(from)("playwright");
  } catch (error) {
    const why = error instanceof Error ? error.message.split("\n", 1)[0] : String(error);
    throw new Error(
      `playwright is not resolvable (${why}). This walk is outside the repository's ` +
        "dependency set on purpose: point WALK_PLAYWRIGHT_ROOT at a directory whose " +
        "node_modules holds playwright, and set PLAYWRIGHT_BROWSERS_PATH if that " +
        "install keeps its browsers beside itself."
    );
  }
}

/**
 * Watch one page for the things a screenshot cannot show.
 *
 * Everything is collected for the whole session and read in slices, so a
 * failure names the step that provoked it. Only the console's own `/v1/...`
 * calls are judged: the module graph a dev server serves is not the product,
 * and a lost module is a lost link rather than a page defect.
 */
export function watch(page, origin) {
  const state = { crashes: [], apiFailures: [], inFlight: 0, lastActivity: Date.now() };
  const isApi = (url) => url.startsWith(`${origin}/v1/`);

  page.on("pageerror", (error) => {
    state.crashes.push(error.message.split("\n", 1)[0].slice(0, 300));
  });
  page.on("request", (request) => {
    if (isApi(request.url())) {
      state.inFlight += 1;
      state.lastActivity = Date.now();
    }
  });
  page.on("requestfinished", (request) => {
    if (isApi(request.url())) {
      state.inFlight -= 1;
      state.lastActivity = Date.now();
    }
  });
  page.on("requestfailed", (request) => {
    if (!isApi(request.url())) {
      return;
    }
    state.inFlight -= 1;
    state.lastActivity = Date.now();
    state.apiFailures.push(
      `${request.method()} ${short(request.url(), origin)} — ${request.failure()?.errorText ?? "failed"}`
    );
  });
  page.on("response", (response) => {
    if (isApi(response.url()) && response.status() >= 400) {
      state.apiFailures.push(
        `${response.request().method()} ${short(response.url(), origin)} — ${String(response.status())}`
      );
    }
  });
  return state;
}

function short(url, origin) {
  return url.startsWith(origin) ? url.slice(origin.length) : url;
}

/** Wait for whatever is on screen to finish its reads, or give up and judge it anyway. */
export async function settle(page, watched) {
  const deadline = Date.now() + SETTLE_CAP_MS;
  watched.lastActivity = Date.now();
  while (Date.now() < deadline) {
    if (watched.inFlight <= 0 && Date.now() - watched.lastActivity >= SETTLE_QUIET_MS) {
      return;
    }
    await page.waitForTimeout(100);
  }
}

/**
 * Admission, once, for the whole walk.
 *
 * The token admits the browser to the serving process and nothing else. It is
 * read from a file, typed into the gate the operator types it into, and never
 * printed — not into the report, and not into a failure note.
 */
export async function admit(page, { target, tokenFile, token }) {
  let last = null;
  for (const attempt of [1, 2]) {
    try {
      await page.goto(target, { waitUntil: "domcontentloaded" });
      const gate = page.getByRole("heading", { name: "Unlock this console" });
      await gate.waitFor();
      await page.getByLabel("Session token").fill(token);
      await page.getByRole("button", { name: "Unlock" }).click();
      // The gate proves the token before it keeps it, and says so when it is
      // not this server's. Read that answer rather than waiting out a timeout
      // and calling a refusal a hang.
      const refused = page.getByText("That token is not this server");
      const deadline = Date.now() + 20_000;
      while (Date.now() < deadline) {
        if ((await gate.count()) === 0) {
          return attempt === 1 ? "the console admitted this walk" : "admitted on a second attempt";
        }
        assert.ok(
          (await refused.count()) === 0,
          `${target} refused the token in ${tokenFile}: it is not the one that server printed at startup`
        );
        await page.waitForTimeout(200);
      }
      throw new Error(`${target} neither admitted this walk nor refused its token`);
    } catch (error) {
      last = error;
    }
  }
  throw last;
}

/** A failure, in one line, with nothing secret in it. */
export function why(error) {
  const message = error instanceof Error ? error.message : String(error);
  return message
    .replace(/\b[0-9a-f]{32,}\b/gi, "<redacted>")
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "")
    .slice(0, 3)
    .join(" ")
    .slice(0, 400);
}
