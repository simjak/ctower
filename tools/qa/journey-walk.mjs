#!/usr/bin/env node
/**
 * The journey: one job an operator actually has, carried across the console
 * from end to end, on a live tower, in a headless browser.
 *
 * `walk-web.mjs` asks whether every destination renders. That is a real
 * question and it is not this one. A console can draw ten clean screens and
 * still make a job impossible, because a job crosses them: what one screen
 * writes, the next has to be able to address. This walk takes the operator's
 * own sentence —
 *
 *     let me in → make a project → open my tickets → raise one → see it on the board
 *
 * — and refuses to call it done until the last screen shows the thing the first
 * one wrote.
 *
 * **This walk writes.** That is the difference from `walk-web.mjs`, which never
 * touches a control that writes, and it is why the two are separate files
 * rather than one flag. It authors a project into the company record and raises
 * a ticket, both under keys that name this walk and the run that made them, so
 * a tower that has been walked says so plainly. Point it at a disposable tower.
 *
 * Every step ends one of three ways, and the difference matters more than the
 * count:
 *
 *   PASS               the act completed.
 *   BLOCKED-BY-RULING  the act is not available today, the surface says so
 *                      honestly, and an open ruling is named. The walk asserts
 *                      the refusal's own words instead of the act, and does not
 *                      call that a failure — a console that refuses honestly for
 *                      a reason the record has not settled is behaving correctly.
 *   FAIL               anything else: the act was refused with words nobody
 *                      authored, or the screen pretended.
 *
 * A step that is blocked names its ruling in the report. `T-020` is the open
 * one this journey meets: a project may be authored under an identifier the
 * work plane will not take, and nothing in the contract converts one family
 * into the other, so a project made in this console cannot yet be opened as a
 * board. That is asserted, not worked around — the walk authors a dot-free key
 * precisely so the identifier is not the thing under suspicion.
 *
 * **Every screen is also read for technical text**, shell chrome included, per
 * the operator's rule of 2026-08-24. See `_tech-text.mjs` for the families and
 * for what is deliberately not one. Findings are their own section of the
 * report: a flow can work perfectly while every screen it crosses prints keys
 * and digests at the operator, and a walk that folded the two together would
 * hide one behind the other.
 *
 *   WALK_PLAYWRIGHT_ROOT=<dir holding node_modules/playwright> \
 *     PLAYWRIGHT_BROWSERS_PATH=0 node tools/qa/journey-walk.mjs
 *
 * Environment:
 *   WALK_PLAYWRIGHT_ROOT  where playwright is installed (required)
 *   JOURNEY_TARGET        the console's origin (default http://127.0.0.1:3197/)
 *   JOURNEY_TOKEN_FILE    the file holding that server's session token
 *   JOURNEY_PROJECT       the work-plane project to raise a ticket in; default
 *                         is the first the console offers. No operation
 *                         enumerates the projects a credential may write to, so
 *                         this is an input rather than something a walk can find
 *   JOURNEY_CUSTODIAN     the commander who takes the ticket; default is the
 *                         first the screen itself suggests. Same reason
 *   JOURNEY_SHOT_DIR      where screenshots and the report are written
 *   JOURNEY_TECH_TEXT     `fail` (default) or `report`
 */

import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { admit, loadPlaywright, settle, watch, why } from "./_console.mjs";
import { techTextIn, techTextLine } from "./_tech-text.mjs";

const TARGET = process.env.JOURNEY_TARGET ?? "http://127.0.0.1:3197/";
const TOKEN_FILE = process.env.JOURNEY_TOKEN_FILE ?? "/tmp/journey-session-token";
const SHOT_DIR = process.env.JOURNEY_SHOT_DIR ?? "/tmp/journey-shots";
const REPORT = path.join(SHOT_DIR, "journey-walk-report.json");
const TECH_TEXT_FAILS = (process.env.JOURNEY_TECH_TEXT ?? "fail") === "fail";

/** How long the board is given to fold a ticket that was accepted. */
const FOLD_CAP_MS = 45_000;

/**
 * The one sentence the Tickets screen offers about a key the work plane does
 * not know. It is the authored wording this walk asserts in place of the act
 * that T-020 blocks, so if the sentence is ever reworded this walk says so
 * rather than quietly passing on a screen that no longer explains itself.
 */
const UNKNOWN_KEY_IS_AN_EMPTY_BOARD =
  "A work-plane project key, as the record spells it. " +
  "A key the work plane does not know answers exactly as an empty project does.";

/**
 * What this run authored, so a walked tower says which walk walked it.
 *
 * The ticket prefix is drawn fresh every run, and that is not decoration: a
 * display prefix may occur only once in an active bundle, so a fixed one would
 * make the second journey against the same tower refuse — correctly, and for a
 * reason that has nothing to do with the flow being walked.
 */
const PREFIX = Array.from(
  { length: 3 },
  () => "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[Math.floor(Math.random() * 26)]
).join("");
const RUN = `${PREFIX.toLowerCase()}${Date.now().toString(36).slice(-4)}`;
const PROJECT = {
  key: `journey-walk-${RUN}`,
  name: `Journey walk ${RUN}`,
  prefix: PREFIX,
  repository: "repository:github/ctower/journey-walk",
};
const TICKET_TITLE = `Journey walk ${RUN} raised this`;

async function main() {
  const { chromium } = loadPlaywright();
  const token = (await readFile(TOKEN_FILE, "utf8")).trim();
  assert.ok(token !== "", `${TOKEN_FILE} holds no session token`);
  await mkdir(SHOT_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  page.setDefaultTimeout(30_000);
  const watched = watch(page, new URL(TARGET).origin);
  const journey = { page, watched, token, screens: [], facts: {} };

  const results = [];
  try {
    for (const step of STEPS) {
      const done = await take(journey, step);
      results.push(done);
      if (done.status === "FAIL" && step.stops) {
        // A journey is ordered. Once the thing a later step needs was never
        // made, the rest would fail for a reason that is not their own, so they
        // are reported as unreached rather than run and blamed.
        for (const later of STEPS.slice(STEPS.indexOf(step) + 1)) {
          results.push({
            step: later.id,
            act: later.act,
            status: "UNREACHED",
            note: `not attempted: ${step.id} did not complete`,
          });
        }
        break;
      }
    }
  } finally {
    await browser.close();
  }

  await report(results, journey);
}

/**
 * One step, attempted, and classified by what actually happened.
 *
 * A step declares itself blocked only after it has asserted the surface's own
 * refusal, so `Blocked` reaching here means those assertions all held. Anything
 * else thrown is a failure, including from a step that expected to be blocked:
 * that one was refused in words nobody authored, which is a different and worse
 * fact than being refused.
 */
async function take(journey, step) {
  const seat = { step: step.id, act: step.act, ruling: step.ruling ?? null };
  try {
    return { ...seat, status: "PASS", note: await step.run(journey) };
  } catch (error) {
    if (error instanceof Blocked) {
      return { ...seat, status: "BLOCKED-BY-RULING", note: error.message };
    }
    if (step.ruling === undefined) {
      return { ...seat, status: "FAIL", note: why(error) };
    }
    return {
      ...seat,
      status: "FAIL",
      note: `${step.ruling} blocks this step and the surface did not refuse it in the words it authored: ${why(error)}`,
    };
  }
}

/**
 * A screen, as a person sees it: a full-page shot and every word rendered,
 * shell chrome included. This is the one place technical text is looked for,
 * so a screen the journey crosses cannot escape the rule by not being a
 * destination.
 */
async function seen(journey, name) {
  const { page } = journey;
  await settle(page, journey.watched);
  const shot = path.join(SHOT_DIR, `journey-${name}.png`);
  await page.screenshot({ path: shot, fullPage: true });
  const rendered = await page.locator("body").innerText();
  const found = techTextIn(rendered);
  journey.screens.push({ screen: name, shot, techText: found });
  return found;
}

const STEPS = [
  {
    id: "admission",
    act: "the console lets the operator in",
    stops: true,
    async run(journey) {
      const how = await admit(journey.page, {
        target: TARGET,
        tokenFile: TOKEN_FILE,
        token: journey.token,
      });
      await journey.page.locator('nav[aria-label="Sections"]').waitFor();
      await seen(journey, "01-admitted");
      return how;
    },
  },
  {
    id: "create-project-opened",
    act: "the shell offers a way to make a project, and it leads somewhere",
    stops: true,
    async run(journey) {
      const { page } = journey;
      await page.locator('button:has(span:text-is("PROJECT"))').click();
      const add = page.getByRole("menuitem", { name: /Add a project/ });
      await add.waitFor();
      await seen(journey, "02-project-menu");
      await add.click();
      await settle(page, journey.watched);
      const address = new URL(page.url()).search;
      assert.ok(address === "?at=harnesses", `"Add a project…" left the operator at "${address}"`);
      const tab = page.getByRole("tab", { name: "Projects" });
      assert.ok(
        (await tab.getAttribute("aria-selected")) === "true",
        "the screen a project is made on did not open on its Projects tab"
      );
      await seen(journey, "03-project-form");
      return "the project switcher leads to the form a project is authored in";
    },
  },
  {
    id: "project-authored",
    act: "a project with a dot-free key is authored into the company record",
    stops: true,
    async run(journey) {
      const { page } = journey;
      // The fields on this panel carry no accessible name, so they are found by
      // the placeholder each one authors. Reported as its own finding.
      await page.getByPlaceholder("Acme widgets").fill(PROJECT.name);
      await page.getByPlaceholder("acme-widgets").fill(PROJECT.key);
      await page.getByPlaceholder("ACW").fill(PROJECT.prefix);
      await page.getByPlaceholder("repository:github/acme/widgets").fill(PROJECT.repository);
      // The goal is chosen, never typed: a project must name one, and the ones
      // this company has are the only ones it may name.
      await page.locator("button[aria-pressed]").first().click();

      await page.getByRole("button", { name: /Review changes/ }).click();
      await settle(page, journey.watched);
      await seen(journey, "04-review-changes");
      const head = await page.locator("main h1").innerText();
      assert.ok(head === "Review changes", `the review screen drew "${head}"`);

      await page.getByLabel("Confirm this runs with operator authority").click();
      await page.getByRole("button", { name: "Apply as operator" }).click();
      await settle(page, journey.watched);
      await seen(journey, "05-applied");

      let shown = await page.locator("main").innerText();
      assert.ok(
        shown.includes("Receipt") || shown.includes("Sent, and not yet accepted"),
        `applying drew no receipt: ${shown.split("\n").slice(0, 3).join(" ")}`
      );
      journey.facts.authoredProject = PROJECT.key;

      // A pending write is not a written one, and this console says so rather
      // than drawing acceptance. The command is idempotent — that is the whole
      // reason the screen offers to send it again — so the walk sends it once
      // more and reports which of the two answers it ended on.
      if (!shown.includes("Receipt")) {
        await page.getByRole("button", { name: /Send the same command again/ }).click();
        await settle(page, journey.watched);
        await seen(journey, "05b-applied-again");
        shown = await page.locator("main").innerText();
      }
      return shown.includes("Receipt")
        ? `${PROJECT.key} is in the company record`
        : `${PROJECT.key} was sent twice and the record still calls it not yet durable`;
    },
  },
  {
    id: "authored-project-is-a-board",
    act: "the project just authored can be opened as work",
    ruling: "T-020",
    stops: false,
    async run(journey) {
      const { page } = journey;
      await rail(page, "Tickets");
      await settle(page, journey.watched);
      await seen(journey, "06-tickets-project-choice");

      // First fact: the console does not offer it. The chooser lists the
      // project scopes components declare; a project authored here declares
      // none, so the thing just written is not among the things offerable.
      const offered = await page.locator("main button.mono").allInnerTexts();
      assert.ok(
        !offered.includes(PROJECT.key),
        `the chooser offers ${PROJECT.key}, so this walk's blocked step is stale and should be a PASS`
      );

      // Second fact: naming it anyway is allowed, and the screen says exactly
      // what that will get you before you do it.
      const hint = page.getByLabel(UNKNOWN_KEY_IS_AN_EMPTY_BOARD);
      assert.ok(
        (await hint.count()) === 1,
        "the Tickets chooser no longer explains what naming an unknown key answers"
      );
      // Exactly, not loosely: the hint beside this field carries the sentence
      // above as its own accessible name, and it contains these two words.
      await page.getByLabel("Project key", { exact: true }).fill(PROJECT.key);
      await page.getByRole("button", { name: "Open it" }).click();
      await settle(page, journey.watched);
      await seen(journey, "07-authored-project-opened");

      // Third fact: the board answers, the screen says in its own words why
      // there is nothing here, and the console still refuses to offer the
      // write — because nothing it can read says this project exists.
      const shown = await page.locator("main").innerText();
      assert.ok(shown.includes("0 tickets"), `the board did not answer for ${PROJECT.key}`);
      assert.ok(
        shown.includes(
          `This board answered with no ticket, and nothing in this company is scoped to ${PROJECT.key}.`
        ),
        `the board for ${PROJECT.key} did not say why it is empty: ${shown.split("\n").slice(0, 4).join(" ")}`
      );
      const raise = page.getByRole("button", { name: "New ticket" });
      assert.ok(
        (await raise.count()) === 0,
        `the console offered New ticket on ${PROJECT.key}, which it cannot show exists`
      );
      throw new Blocked(
        `authored, and not addressable as work: the chooser does not offer ${PROJECT.key}, ` +
          "the board it opens says nothing in this company is scoped to it, " +
          "and it carries no way to raise a ticket. " +
          "A project document key and a work-plane project key are different families and " +
          "nothing in the contract converts one into the other"
      );
    },
  },
  {
    id: "tickets-opened",
    act: "the operator opens the tickets of a project the record does address",
    stops: true,
    async run(journey) {
      const { page } = journey;
      // Back to the chooser by its own address rather than by the rail: the
      // screen is already Tickets, and a rail click on the destination the
      // operator is already at moves the address without remounting the page.
      await page.goto(`${TARGET}?at=tickets`, { waitUntil: "domcontentloaded" });
      await settle(page, journey.watched);
      const offered = await page.locator("main button.mono").allInnerTexts();
      assert.ok(offered.length > 0, "this company offers no project to open tickets on");
      const wanted = process.env.JOURNEY_PROJECT ?? offered[0];
      assert.ok(
        offered.includes(wanted),
        `${wanted} is not offered; this console offers ${offered.join(", ")}`
      );
      journey.facts.project = wanted;
      await page.locator("main button.mono", { hasText: wanted }).first().click();
      await settle(page, journey.watched);
      await seen(journey, "08-tickets-open");
      const raise = page.getByRole("button", { name: "New ticket" });
      assert.ok(
        (await raise.count()) === 1,
        `${wanted} answered, and the console offers no way to raise a ticket on it`
      );
      return `tickets open on ${wanted}`;
    },
  },
  {
    id: "ticket-raised",
    act: "a ticket is raised and the console shows the receipt",
    stops: true,
    async run(journey) {
      const { page } = journey;
      await page.getByRole("button", { name: "New ticket" }).click();
      await settle(page, journey.watched);
      await seen(journey, "09-new-ticket");

      const custodian = process.env.JOURNEY_CUSTODIAN ?? (await suggested(page));
      assert.ok(
        custodian !== null,
        "no custodian: the screen suggested none and none was given. No operation in the " +
          "authored contract enumerates principals, so a walk cannot find one on the surface"
      );
      await page.getByLabel("Title").fill(TICKET_TITLE);
      await page.getByLabel("Reference").fill(`journey-walk-${RUN}`);
      await page.getByLabel("Custodian").fill(custodian);
      await page.getByRole("button", { name: "Raise it" }).click();
      await settle(page, journey.watched);
      await seen(journey, "10-raised");

      const shown = await page.locator("main").innerText();
      assert.ok(
        shown.includes("raised") || shown.includes("not yet durable"),
        `raising drew no receipt: ${shown.split("\n").slice(-4).join(" ")}`
      );
      journey.facts.ticket = TICKET_TITLE;
      return shown.includes("raised")
        ? "the ticket was raised and accepted"
        : "the ticket was sent and is not yet durable";
    },
  },
  {
    id: "board-shows-the-row",
    act: "the board shows the row the ticket made",
    stops: false,
    async run(journey) {
      const { page } = journey;
      await rail(page, "Board");
      await settle(page, journey.watched);
      await page.getByLabel("Project").fill(journey.facts.project);
      await page.keyboard.press("Enter");
      await settle(page, journey.watched);

      // A write is not visible until the projection has folded it, so the board
      // is asked again rather than judged on its first answer.
      const row = page.getByText(TICKET_TITLE);
      const deadline = Date.now() + FOLD_CAP_MS;
      let reads = 1;
      while ((await row.count()) === 0 && Date.now() < deadline) {
        await page.getByRole("button", { name: "Read again" }).click();
        await settle(page, journey.watched);
        reads += 1;
      }
      await seen(journey, "11-board");
      assert.ok(
        (await row.count()) > 0,
        `the board never showed "${TICKET_TITLE}" after ${String(reads)} reads`
      );
      return `the row is on the board after ${String(reads)} ${reads === 1 ? "read" : "reads"}`;
    },
  },
];

/** The step said it was blocked, and proved the surface said so honestly. */
class Blocked extends Error {}

function rail(page, label) {
  return page
    .locator(`nav[aria-label="Sections"] button:has(span.truncate:text-is("${label}"))`)
    .click();
}

/** The custodians this board already has, which the screen offers as suggestions. */
async function suggested(page) {
  const options = await page
    .locator("#ctower-custodians option")
    .evaluateAll((all) => all.map((option) => option.getAttribute("value") ?? ""));
  return options.find((option) => option !== "") ?? null;
}

async function report(results, journey) {
  const techText = journey.screens.filter((screen) => screen.techText.length > 0);
  const failed = results.filter((one) => one.status === "FAIL" || one.status === "UNREACHED");
  const blocked = results.filter((one) => one.status === "BLOCKED-BY-RULING");
  const written = {
    target: TARGET,
    when: new Date().toISOString(),
    run: RUN,
    authored: journey.facts,
    steps: results,
    screens: journey.screens,
    techTextScreens: techText.length,
  };
  await writeFile(REPORT, `${JSON.stringify(written, null, 2)}\n`, "utf8");

  for (const one of results) {
    console.log(`${one.status.padEnd(18)} ${one.step.padEnd(28)} ${one.note}`);
  }
  console.log("");
  for (const screen of journey.screens) {
    const line = screen.techText.length === 0 ? "clean" : techTextLine(screen.techText);
    console.log(
      `${screen.techText.length === 0 ? "CLEAN" : "TECH "} ${screen.screen.padEnd(28)} ${line}`
    );
  }
  console.log(
    `\n${String(results.filter((one) => one.status === "PASS").length)}/${String(results.length)} ` +
      `steps completed, ${String(blocked.length)} blocked by an open ruling, ` +
      `${String(failed.length)} failed`
  );
  console.log(
    `${String(techText.length)}/${String(journey.screens.length)} screens carried technical text`
  );
  console.log(`screenshots: ${SHOT_DIR}/journey-*.png\nreport: ${REPORT}`);
  if (failed.length > 0 || (TECH_TEXT_FAILS && techText.length > 0)) {
    process.exitCode = 1;
  }
}

await main();
