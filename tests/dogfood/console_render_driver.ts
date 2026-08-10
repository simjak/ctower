/**
 * Walk the console typing ceremony in a real browser and report what it did.
 *
 * Four of this control's claims are true only in a running document, and
 * reading the sources behind them proves none of them.
 *
 * The first is the walk itself. Read-only, ceremony, granted, expired and
 * revoked are one control's states, not five components, and only a browser
 * that presses through them shows that the transitions are the ones the
 * approved board draws — including that the confirmed text survives into the
 * granted field and survives expiry.
 *
 * The second is the countdown. A number rendered once is not a countdown, and a
 * server-side clock cannot be proved from markup. This reads the same chip
 * twice, seconds apart, and reports both values.
 *
 * The third is expiry. The grant ends on the server's clock, so this mints one
 * that ends in seconds, waits past it, and reports what the control became
 * without touching it — the field, its words, and whether anything on screen
 * claims something was injected.
 *
 * The fourth is refusal copy. What an operator reads when the server says no is
 * composed at render time from the answer's own sentence, so a grep over the
 * sources cannot see it. Each width drives a session the record refuses and
 * reports the sentence that reached the screen.
 *
 * The browser holds nothing. It presses this dogfood server's own Server
 * Actions, which hold the bearer; it never receives a credential and never
 * addresses a running instance.
 *
 * Usage:
 *   node --no-warnings console_render_driver.ts <base-url> <dir>
 */

import { chromium } from "@playwright/test";
import type { Locator, Page } from "@playwright/test";

const WIDTHS = [375, 768, 1440] as const;
const HEIGHT = 900;
const NAVIGATION_TIMEOUT_MS = 30_000;
const SETTLE_TIMEOUT_MS = 30_000;
/** Long enough for a second whole second to tick over, short enough to run. */
const TICK_WAIT_MS = 1_400;
/** The stub's short grant, plus the margin its own expiry needs to land. */
const EXPIRY_WAIT_MS = 4_000;

const FORM = "form[data-console-phase]";
const FIELD = `${FORM} textarea`;

interface Shot {
  readonly phase: string;
  /** The composer's own field, so a lost draft is visible rather than inferred. */
  readonly field: string;
  readonly fieldDisabled: boolean;
  /** Every button the control offers, with whether it is pressable. */
  readonly buttons: readonly { readonly label: string; readonly disabled: boolean }[];
  /** The countdown chip, the expiry chip or the revocation chip — whichever is up. */
  readonly counter: string;
  /** The audit chain of the command before this one, as one line. */
  readonly chain: string;
  /** The refusal or held note on screen, or the empty string. */
  readonly note: string;
  /** The whole control's text, so an absent claim can be asserted absent. */
  readonly text: string;
  /** The page, so the state is judged where an operator meets it. */
  readonly screenshot: string;
  /**
   * The control alone, at the same width.
   *
   * The design gate compares this build against the approved board frame by
   * frame, and a full page at 1440 puts the composer in a strip a tenth of its
   * height. Both are captured because they answer different questions: whether
   * the state is right, and whether it sits right on the page.
   */
  readonly control: string;
}

interface Walk {
  readonly width: number;
  readonly readOnly: Shot;
  readonly composing: Shot;
  readonly confirmed: Shot;
  readonly granted: Shot;
  /** The same countdown chip a moment later: a number that moved is a clock. */
  readonly tickedTo: string;
  readonly dispatched: Shot;
  readonly expired: Shot;
  readonly revoked: Shot;
  readonly refused: Shot;
  /** Whether any width overflowed its viewport horizontally. */
  readonly overflowed: boolean;
}

async function shotOf(page: Page, screenshot: string): Promise<Shot> {
  const state = await page.evaluate((selector: string) => {
    const form = document.querySelector(selector);
    const field = form?.querySelector("textarea");
    const text = (node: Element | null | undefined): string => node?.textContent?.trim() ?? "";
    return {
      phase: form?.getAttribute("data-console-phase") ?? "",
      field: field instanceof HTMLTextAreaElement ? field.value : "",
      fieldDisabled: field instanceof HTMLTextAreaElement ? field.disabled : true,
      buttons: [...(form?.querySelectorAll("button") ?? [])].map((node) => ({
        label: text(node),
        disabled: node instanceof HTMLButtonElement ? node.disabled : false,
      })),
      counter: text(form?.querySelector(".ctr") ?? form?.querySelector(".verdict")),
      chain: text(form?.querySelector(".cc-chain")),
      note: text(form?.querySelector(".card-note")),
      text: text(form),
    };
  }, FORM);
  await page.screenshot({ path: screenshot, fullPage: true });
  const control = screenshot.replace(/\.png$/u, "-control.png");
  // the ceremony's modal placement lifts the body out of the panel's flow, so
  // the control is captured from the panel it belongs to rather than the form
  await page.locator("section.panel:has(form[data-console-phase])").screenshot({ path: control });
  return { ...state, screenshot, control };
}

/** The one button this step presses, waited for rather than assumed present. */
function button(page: Page, label: string): Locator {
  return page.locator(FORM).getByRole("button", { name: label, exact: true });
}

async function press(page: Page, label: string, becomes: string): Promise<void> {
  await button(page, label).click();
  await page.locator(`form[data-console-phase='${becomes}']`).waitFor({
    timeout: SETTLE_TIMEOUT_MS,
  });
}

async function open(page: Page, baseUrl: string, crew: string): Promise<void> {
  const response = await page.goto(`${baseUrl}/crew/${crew}`, { waitUntil: "networkidle" });
  const status = response === null ? 0 : response.status();
  if (status !== 200) {
    throw new Error(`/crew/${crew} answered ${status.toString()}`);
  }
  await page.locator(FORM).waitFor({ timeout: SETTLE_TIMEOUT_MS });
}

async function overflows(page: Page): Promise<boolean> {
  return await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth
  );
}

async function walk(page: Page, baseUrl: string, width: number, into: string): Promise<Walk> {
  const at = (name: string): string => `${into}/console-${name}-${width.toString()}.png`;
  let overflowed = false;
  const note = async (): Promise<void> => {
    overflowed = overflowed || (await overflows(page));
  };

  // ── the whole ceremony, on the crew whose grant lasts its full minute ──
  await open(page, baseUrl, "engineer-371-console");
  const readOnly = await shotOf(page, at("readonly"));
  await note();

  await press(page, "Request type grant", "ceremony");
  const composing = await shotOf(page, at("composing"));
  await note();

  // the confirmed half of the ceremony is still the ceremony phase, so this
  // waits for the thing the server's answer put on screen — the exact bytes it
  // canonicalized — rather than for a phase that never changed
  await page.locator(FIELD).fill("just verify");
  await button(page, "Confirm this command").click();
  await page.locator(`${FORM} .cc-bytes`).waitFor({ timeout: SETTLE_TIMEOUT_MS });
  const confirmed = await shotOf(page, at("ceremony"));
  await note();

  await press(page, "Mint 60-second grant", "granted");
  const granted = await shotOf(page, at("granted"));
  await note();
  await page.waitForTimeout(TICK_WAIT_MS);
  const tickedTo = await page.locator(`${FORM} .ctr`).innerText();

  await press(page, "Paste text", "read-only");
  const dispatched = await shotOf(page, at("dispatched"));
  await note();

  // ── expiry, on a grant the record ends in seconds, waited out untouched ──
  await open(page, baseUrl, "qa-m1-rerun2");
  await press(page, "Request type grant", "ceremony");
  await page.locator(FIELD).fill("just verify");
  await button(page, "Confirm this command").click();
  await page.locator(`${FORM} .cc-bytes`).waitFor({ timeout: SETTLE_TIMEOUT_MS });
  // this grant is minted with seconds on it, so the granted phase may be gone
  // before a wait for it could resolve; the state under test is what the
  // control became on its own, so that is the only thing waited for
  await button(page, "Mint 60-second grant").click();
  await page.locator("form[data-console-phase='expired']").waitFor({ timeout: EXPIRY_WAIT_MS });
  const expired = await shotOf(page, at("expired"));
  await note();

  // ── revocation, which the record reports before anything is pressed ──
  await open(page, baseUrl, "designer-3388-callcard");
  const revoked = await shotOf(page, at("revoked"));
  await note();

  // ── refusal, in the server's own sentence ──
  await open(page, baseUrl, "review-390-verdict");
  await press(page, "Request type grant", "ceremony");
  await page.locator(FIELD).fill("just verify");
  await button(page, "Confirm this command").click();
  await page.locator(`${FORM} .cc-bytes`).waitFor({ timeout: SETTLE_TIMEOUT_MS });
  await button(page, "Mint 60-second grant").click();
  await page.locator(`${FORM} p[role='alert']`).waitFor({ timeout: SETTLE_TIMEOUT_MS });
  const refused = await shotOf(page, at("refused"));
  await note();

  return {
    width,
    readOnly,
    composing,
    confirmed,
    granted,
    tickedTo,
    dispatched,
    expired,
    revoked,
    refused,
    overflowed,
  };
}

async function main(): Promise<void> {
  const [baseUrl, into] = process.argv.slice(2);
  if (baseUrl === undefined || into === undefined || baseUrl === "" || into === "") {
    throw new TypeError("usage: console_render_driver.ts <base-url> <screenshot-dir>");
  }

  const browser = await chromium.launch();
  const walks: Walk[] = [];
  try {
    for (const width of WIDTHS) {
      const context = await browser.newContext({ viewport: { width, height: HEIGHT } });
      const page = await context.newPage();
      page.setDefaultNavigationTimeout(NAVIGATION_TIMEOUT_MS);
      walks.push(await walk(page, baseUrl, width, into));
      await context.close();
    }
  } finally {
    await browser.close();
  }

  process.stdout.write(JSON.stringify({ walks }));
}

void main();
