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
 *   node --no-warnings inbox_render_driver.ts <base-url> <thread-id> <refused-thread-id> <dir>
 */

import { chromium } from "@playwright/test";
import type { Page } from "@playwright/test";

const WIDTHS = [375, 768, 1440] as const;
const HEIGHT = 900;
const NAVIGATION_TIMEOUT_MS = 30_000;
const SETTLE_TIMEOUT_MS = 30_000;
const STAMP = "kept";

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

/** What one width's send box did when it was actually used. */
interface Drive {
  readonly width: number;
  readonly outcome: string;
  /** The text typed into the box. */
  readonly typed: string;
  /** True when the document that submitted is the document that answered. */
  readonly sameDocument: boolean;
  /** The box's own field after the round trip. */
  readonly fieldAfter: string;
  /** The thread's messages as the page lists them, after the round trip. */
  readonly messages: readonly string[];
  /** Those of them the projection has not folded yet, by their own marker. */
  readonly pending: readonly string[];
  /** The same two, re-read in a fresh document once the projection caught up. */
  readonly messagesReloaded: readonly string[];
  readonly pendingReloaded: readonly string[];
  /** The refusal sentence the box put on screen, when it refused. */
  readonly refusal: string | null;
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

async function threadState(page: Page): Promise<{
  readonly sameDocument: boolean;
  readonly fieldAfter: string;
  readonly messages: string[];
  readonly pending: string[];
}> {
  return await page.evaluate((mark: string) => {
    const field = document.querySelector("textarea[name='text']");
    const said = (rows: string): string[] =>
      [...document.querySelectorAll(rows)].map((node) => node.textContent ?? "");
    return {
      sameDocument: document.documentElement.dataset.visit === mark,
      fieldAfter: field instanceof HTMLTextAreaElement ? field.value : "",
      messages: said(".panel .msg .subj"),
      pending: said(".panel .msg:has(.verdict) .subj"),
    };
  }, STAMP);
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
  await page.getByRole("button", { name: "Send" }).click();
  const settled =
    outcome === "sent"
      ? page.locator(".msg .subj", { hasText: typed }).first()
      : page.locator("form.steer-box p[role='alert']");
  await settled.waitFor({ timeout: SETTLE_TIMEOUT_MS });
  const refusal = outcome === "sent" ? null : ((await settled.textContent()) ?? "");
  const state = await threadState(page);
  await page.screenshot({ path: screenshot, fullPage: true });

  // a second, fresh document: what the thread projection itself now carries,
  // with nothing of the submitting page's state left to carry it
  await page.goto(route, { waitUntil: "networkidle" });
  const reloaded = await threadState(page);
  return {
    width,
    outcome,
    typed,
    refusal,
    screenshot,
    ...state,
    messagesReloaded: reloaded.messages,
    pendingReloaded: reloaded.pending,
  };
}

async function main(): Promise<void> {
  const [baseUrl, threadId, refusedThreadId, screenshotDirectory] = process.argv.slice(2);
  if (
    baseUrl === undefined ||
    threadId === undefined ||
    refusedThreadId === undefined ||
    screenshotDirectory === undefined ||
    baseUrl === "" ||
    threadId === "" ||
    refusedThreadId === "" ||
    screenshotDirectory === ""
  ) {
    throw new TypeError(
      "usage: inbox_render_driver.ts <base-url> <thread-id> <refused-thread-id> <screenshot-dir>"
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
      await context.close();
    }
  } finally {
    await browser.close();
  }

  process.stdout.write(JSON.stringify({ captures, drives }));
}

void main();
