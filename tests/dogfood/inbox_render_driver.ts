/**
 * Drive the dogfood Inbox surface in a real browser and report what it did.
 *
 * Two claims live only in a running browser, and reading the sources behind
 * them proves neither.
 *
 * The first is copy. It is composed at render time from a frame component, a
 * rail constant and a screen, so a grep over those files passes while the page
 * an operator looks at still carries a retired claim. This opens the served
 * surface in headless Chromium at the three widths the design bar names and
 * reports the text back, per width and per route.
 *
 * The second is the send box's whole point: a message typed into it appears in
 * the thread *without a reload*. That is a statement about one document's
 * lifetime, and only a browser can make it. So each width stamps the document,
 * submits the box, waits for its own text, and reports whether the stamp
 * survived — a full page load would have wiped it.
 *
 * The third is that same claim's other half: a send the record answers *without
 * accepting* must not appear as a message at all. Each width therefore also
 * submits on a thread the stub answers `202`/`durability_pending` for, and
 * reports the rows, the box's own words, its button and the sentence it put on
 * screen — before and after pressing it again.
 *
 * Two texts are reported for each capture, because they answer different
 * questions. `visible` is `innerText` — what a reader actually sees, with the
 * rail collapsed into its drawer at phone width. `rendered` is every text node
 * in the document, drawer included, so an absence assertion cannot pass merely
 * because a stale claim was scrolled off or folded away. Script and style
 * contents are left out of `rendered`: the framework's serialized props repeat
 * every rendered string, and counting a sentence twice because it was also
 * shipped as hydration data would say nothing about the surface.
 *
 * The browser still holds nothing. It submits the box to this dogfood server's
 * own Server Action, which holds the bearer; it never receives a credential and
 * never addresses a running instance. The promotion form is not submitted here
 * at all — its transport is proved against the real module in
 * `tests/repository`.
 *
 * Usage:
 *   node --no-warnings inbox_render_driver.ts <base-url> <thread-id> <refused-thread-id>
 *     <unconfirmed-thread-id> <dir>
 */

import { chromium } from "@playwright/test";
import type { Page } from "@playwright/test";

const WIDTHS = [375, 768, 1440] as const;
const HEIGHT = 900;
const NAVIGATION_TIMEOUT_MS = 30_000;
const SETTLE_TIMEOUT_MS = 30_000;
const STAMP = "kept";
/** The send box, told from the promote form it shares a page and a class with. */
const SEND_BOX = "form.steer-box:has(textarea[name='text'])";

interface NewTicketAffordance {
  readonly label: string;
  readonly disabled: boolean;
  readonly verdict: string;
  readonly reason: string;
}

interface Surface {
  readonly visible: string;
  readonly rendered: string;
  readonly foot: string;
  readonly newTicket: NewTicketAffordance | null;
}

interface Capture extends Surface {
  readonly width: number;
  readonly route: string;
  readonly screenshot: string;
}

/** The thread and its send box, as one document reports them. */
interface BoxState {
  /** True when the document that submitted is the document that answered. */
  readonly sameDocument: boolean;
  /** The box's own field after the round trip. */
  readonly fieldAfter: string;
  /** What the box's own button offers next: `Send`, `Retry`, or `Sending…`. */
  readonly button: string;
  /** The thread's messages as the page lists them. */
  readonly messages: readonly string[];
  /** Those of them the projection has not folded yet, by their own marker. */
  readonly unfolded: readonly string[];
  /** The unconfirmed-send sentence on screen, or the empty string. */
  readonly notice: string;
  /** The refusal sentence on screen, or the empty string. */
  readonly refusal: string;
}

/** What one width's send box did when it was actually used. */
interface Drive extends BoxState {
  readonly width: number;
  readonly outcome: string;
  /** The text typed into the box. */
  readonly typed: string;
  /** The same page after pressing the box again, when it was not confirmed. */
  readonly retried: BoxState | null;
  /** The thread re-read in a fresh document, with none of this page's state. */
  readonly messagesReloaded: readonly string[];
  readonly unfoldedReloaded: readonly string[];
  readonly screenshot: string;
}

async function surfaceOf(page: Page): Promise<Surface> {
  return await page.evaluate(() => {
    const button = document.querySelector("button[aria-describedby='new-ticket-readonly']");
    const reason = document.getElementById("new-ticket-readonly");
    const verdict = button?.parentElement?.querySelector(".verdict");
    const foot = document.querySelector(".foot");
    const text = (node: Element | null | undefined): string => node?.textContent?.trim() ?? "";
    const skipped = new Set(["SCRIPT", "STYLE", "TEMPLATE", "NOSCRIPT"]);
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode: (node: Node): number =>
        skipped.has(node.parentElement?.tagName ?? "")
          ? NodeFilter.FILTER_REJECT
          : NodeFilter.FILTER_ACCEPT,
    });
    const spoken: string[] = [];
    while (walker.nextNode() !== null) {
      spoken.push(walker.currentNode.nodeValue ?? "");
    }
    return {
      visible: document.body.innerText,
      rendered: spoken.join("\n"),
      foot: text(foot),
      newTicket:
        button instanceof HTMLButtonElement
          ? {
              label: text(button),
              disabled: button.disabled,
              verdict: text(verdict),
              reason: text(reason),
            }
          : null,
    };
  });
}

/** The stamp is on the document, so only a document swap can remove it. */
async function stamp(page: Page): Promise<void> {
  await page.evaluate((mark: string) => {
    document.documentElement.dataset.visit = mark;
  }, STAMP);
}

async function boxState(page: Page): Promise<BoxState> {
  return await page.evaluate((mark: string) => {
    const field = document.querySelector("textarea[name='text']");
    // the send box is the form its own message field belongs to: the promote
    // control is another form in the same design-system class on the same page
    const box = field instanceof HTMLTextAreaElement ? field.form : null;
    const said = (rows: string): string[] =>
      [...document.querySelectorAll(rows)].map((node) => node.textContent ?? "");
    const text = (node: Element | null | undefined): string => node?.textContent?.trim() ?? "";
    return {
      sameDocument: document.documentElement.dataset.visit === mark,
      fieldAfter: field instanceof HTMLTextAreaElement ? field.value : "",
      button: text(box?.querySelector("button[type='submit']")),
      messages: said(".panel .msg .subj"),
      unfolded: said(".panel .msg:has(.verdict) .subj"),
      notice: text(box?.querySelector("p[role='status']")),
      refusal: text(box?.querySelector("p[role='alert']")),
    };
  }, STAMP);
}

/** Wait for the one thing this outcome puts on the screen. */
async function settle(page: Page, outcome: string, typed: string): Promise<void> {
  if (outcome === "sent") {
    await page.locator(".msg .subj", { hasText: typed }).first().waitFor({
      timeout: SETTLE_TIMEOUT_MS,
    });
    return;
  }
  const role = outcome === "refused" ? "alert" : "status";
  await page.locator(`${SEND_BOX} p[role='${role}']`).waitFor({ timeout: SETTLE_TIMEOUT_MS });
}

/**
 * Press the box again on a send the server has not confirmed.
 *
 * The screen says the same thing before and after, so the round trip is waited
 * for at the transport: the Server Action's own answer. What the retry has to
 * prove is on the record's side — one command identity, not two — and that is
 * asserted against the stub's command log.
 */
async function retry(page: Page): Promise<BoxState> {
  const answered = page.waitForResponse((response) => response.request().method() === "POST", {
    timeout: SETTLE_TIMEOUT_MS,
  });
  await page.locator(SEND_BOX).getByRole("button", { name: "Retry" }).click();
  await answered;
  await settle(page, "unconfirmed", "");
  return await boxState(page);
}

/** Type into the send box, submit it, and report what the same document did. */
async function drive(
  page: Page,
  width: number,
  outcome: string,
  typed: string,
  screenshot: string,
  route: string
): Promise<Drive> {
  await stamp(page);
  await page.locator("textarea[name='text']").fill(typed);
  await page.locator(SEND_BOX).getByRole("button", { name: "Send" }).click();
  await settle(page, outcome, typed);
  const state = await boxState(page);
  await page.screenshot({ path: screenshot, fullPage: true });
  const retried = outcome === "unconfirmed" ? await retry(page) : null;

  // a second, fresh document: what the thread projection itself now carries,
  // with nothing of the submitting page's state left to carry it
  await page.goto(route, { waitUntil: "networkidle" });
  const reloaded = await boxState(page);
  return {
    width,
    outcome,
    typed,
    retried,
    screenshot,
    ...state,
    messagesReloaded: reloaded.messages,
    unfoldedReloaded: reloaded.unfolded,
  };
}

async function main(): Promise<void> {
  const [baseUrl, threadId, refusedThreadId, unconfirmedThreadId, screenshotDirectory] =
    process.argv.slice(2);
  if (
    baseUrl === undefined ||
    threadId === undefined ||
    refusedThreadId === undefined ||
    unconfirmedThreadId === undefined ||
    screenshotDirectory === undefined ||
    baseUrl === "" ||
    threadId === "" ||
    refusedThreadId === "" ||
    unconfirmedThreadId === "" ||
    screenshotDirectory === ""
  ) {
    throw new TypeError(
      "usage: inbox_render_driver.ts <base-url> <thread-id> <refused-thread-id>" +
        " <unconfirmed-thread-id> <screenshot-dir>"
    );
  }
  const threadRoute = `/inbox?thread=${encodeURIComponent(threadId)}`;
  const routes: ReadonlyArray<readonly [string, string]> = [
    ["list", "/inbox"],
    ["thread", threadRoute],
  ];

  const browser = await chromium.launch();
  const captures: Capture[] = [];
  const drives: Drive[] = [];
  try {
    for (const width of WIDTHS) {
      const context = await browser.newContext({ viewport: { width, height: HEIGHT } });
      const page = await context.newPage();
      page.setDefaultNavigationTimeout(NAVIGATION_TIMEOUT_MS);
      for (const [name, route] of routes) {
        const response = await page.goto(`${baseUrl}${route}`, { waitUntil: "networkidle" });
        const status = response === null ? 0 : response.status();
        if (status !== 200) {
          throw new Error(`${route} answered ${status.toString()} at width ${width.toString()}`);
        }
        const screenshot = `${screenshotDirectory}/inbox-${name}-${width.toString()}.png`;
        await page.screenshot({ path: screenshot, fullPage: true });
        captures.push({ width, route: name, screenshot, ...(await surfaceOf(page)) });
      }

      // the send box, actually used: the page is already on the thread route
      drives.push(
        await drive(
          page,
          width,
          "sent",
          `Sent from the ${width.toString()}px send box.`,
          `${screenshotDirectory}/inbox-sent-${width.toString()}.png`,
          `${baseUrl}${threadRoute}`
        )
      );

      const refusedRoute = `${baseUrl}/inbox?thread=${encodeURIComponent(refusedThreadId)}`;
      await page.goto(refusedRoute, { waitUntil: "networkidle" });
      drives.push(
        await drive(
          page,
          width,
          "refused",
          `Refused at ${width.toString()}px.`,
          `${screenshotDirectory}/inbox-refused-${width.toString()}.png`,
          refusedRoute
        )
      );

      // the send the record answers without accepting: it must not appear as a
      // message, and pressing the box again must replay one command
      const unconfirmedRoute = `${baseUrl}/inbox?thread=${encodeURIComponent(unconfirmedThreadId)}`;
      await page.goto(unconfirmedRoute, { waitUntil: "networkidle" });
      drives.push(
        await drive(
          page,
          width,
          "unconfirmed",
          `Unconfirmed at ${width.toString()}px.`,
          `${screenshotDirectory}/inbox-unconfirmed-${width.toString()}.png`,
          unconfirmedRoute
        )
      );
      await context.close();
    }
  } finally {
    await browser.close();
  }

  process.stdout.write(JSON.stringify({ captures, drives }));
}

void main();
