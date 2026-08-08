/**
 * Drive the dogfood Inbox surface in a real browser and report what it rendered.
 *
 * The copy this suite guards is only true on the rendered page: it is composed
 * from a frame component, a rail constant and a screen, and reading any one of
 * those files proves nothing about the sentence an operator ends up looking at.
 * So this opens the served surface in headless Chromium at the three widths the
 * design bar names and reports the text back, per width and per route.
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
 * Everything here is a read. The driver never submits the promotion form: the
 * transport is proved against the real module in `tests/repository`, and a
 * browser that posted a command would be exactly the product browser authority
 * D40 withholds.
 *
 * Usage: `node --no-warnings inbox_render_driver.ts <base-url> <thread-id> <screenshot-dir>`
 */

import { chromium } from "@playwright/test";
import type { Page } from "@playwright/test";

const WIDTHS = [375, 768, 1440] as const;
const HEIGHT = 900;
const NAVIGATION_TIMEOUT_MS = 30_000;

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

async function main(): Promise<void> {
  const [baseUrl, threadId, screenshotDirectory] = process.argv.slice(2);
  if (
    baseUrl === undefined ||
    threadId === undefined ||
    screenshotDirectory === undefined ||
    baseUrl === "" ||
    threadId === "" ||
    screenshotDirectory === ""
  ) {
    throw new TypeError("usage: inbox_render_driver.ts <base-url> <thread-id> <screenshot-dir>");
  }
  const routes: ReadonlyArray<readonly [string, string]> = [
    ["list", "/inbox"],
    ["thread", `/inbox?thread=${encodeURIComponent(threadId)}`],
  ];

  const browser = await chromium.launch();
  const captures: Capture[] = [];
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
      await context.close();
    }
  } finally {
    await browser.close();
  }

  process.stdout.write(JSON.stringify({ captures }));
}

void main();
