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
 *     let me in → make a project → open my tickets → raise one → see it in the
 *     list, in the columns, and on the board
 *
 * — and refuses to call it done until the last screen shows the thing the first
 * one wrote.
 *
 * Raising one is asserted as the operator's own sentence, not as a form fill:
 * the pop-up may ask for exactly one thing (the title), the people it offers
 * must be this company's own and only the calling seat may be live, and the
 * ticket must land in the record's first lane — read back from the list, from
 * the same screen's columns, and from the Board destination.
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
 *   JOURNEY_SHOT_DIR      where screenshots and the report are written
 *   JOURNEY_TECH_TEXT     `fail` (default) or `report`
 *   JOURNEY_STEPS         comma-separated step ids; default is the whole
 *                         sentence. Authoring a project is the operator's act
 *                         and raising a ticket is the commander's, and a console
 *                         holds one credential, so each half is walked against
 *                         the console the act belongs to
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

/**
 * Which steps to attempt, when the whole sentence cannot be walked at once.
 *
 * The journey crosses two authorities on purpose. Authoring a project is a
 * company-bundle apply and is the **operator's** act; raising a ticket requires
 * Commander custody and is the **commander's**. A console holds one credential,
 * so one run cannot do both, and a walk that pretended otherwise would report a
 * credential as a defect. Naming the steps lets each half be walked against the
 * console the act actually belongs to, and the report says which half it was.
 */
const ONLY = (process.env.JOURNEY_STEPS ?? "")
  .split(",")
  .map((one) => one.trim())
  .filter((one) => one !== "");

/** How long the board is given to fold a ticket that was accepted. */
const FOLD_CAP_MS = 45_000;

/**
 * The board's columns, in the order work moves through them.
 *
 * Six, because the contract's `BoardLane` is closed at six, and these are the
 * operator's words for them rather than the record's spellings — the vocabulary
 * he froze on the ticket screens, which a board of the same tickets says too.
 * Authored here beside the heads for the same reason those are: what a screen
 * *says* is product text, and a walk that read it off the product could never
 * catch the product changing it.
 */
const LANE_WORDS = ["Waiting", "Ready to start", "Being worked on", "In review", "Stuck", "Done"];

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
// The key and the ticket prefix are derived from the name by the pop-up that
// authors one — a key is machine text and asking for it is asking a question
// with no right answer (`projects/draft.ts`). So the walk cannot choose them; it
// chooses a *name* whose derivation lands where it needs to, and holds what that
// produces so later steps can say what is and is not addressable. The name opens
// with the run's three letters precisely because the prefix is the first three
// letters of the name, and two active projects may not share one.
const PROJECT = {
  key: `${PREFIX.toLowerCase()}-journey-walk-${RUN}`,
  name: `${PREFIX} journey walk ${RUN}`,
  prefix: PREFIX,
  repository: "https://github.com/ctower/journey-walk",
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

  const walking = ONLY.length === 0 ? STEPS : STEPS.filter((step) => ONLY.includes(step.id));
  assert.ok(walking.length > 0, `JOURNEY_STEPS names no step this walk has: ${ONLY.join(", ")}`);

  const results = [];
  try {
    for (const step of walking) {
      const done = await take(journey, step);
      results.push(done);
      // A journey is ordered. Once the thing a later step needs was never made,
      // the rest would fail for a reason that is not their own, so they are
      // reported as unreached rather than run and blamed. A step that was
      // *blocked* stops the ones after it for the same reason a failed one
      // does — the act did not happen either way — and the difference between
      // the two stays on the step that earned it.
      if (step.stops && (done.status === "FAIL" || done.status === "BLOCKED-BY-RULING")) {
        for (const later of walking.slice(walking.indexOf(step) + 1)) {
          results.push({
            step: later.id,
            act: later.act,
            status: "UNREACHED",
            because: done.status,
            note: `not attempted: ${step.id} ended ${done.status}`,
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
      await page.getByRole("button", { name: /^Project: / }).click();
      const add = page.getByRole("menuitem", { name: /New project/ });
      await add.waitFor();
      await seen(journey, "02-project-menu");
      await add.click();
      await settle(page, journey.watched);
      const address = new URL(page.url()).search;
      assert.ok(address === "?at=projects", `"New project…" left the operator at "${address}"`);
      await page.getByRole("dialog").getByLabel("Project name").waitFor();
      await seen(journey, "03-project-form");
      return "the project switcher leads to the pop-up a project is authored in";
    },
  },
  {
    id: "project-authored",
    act: "a project with a dot-free key is authored into the company record",
    stops: true,
    async run(journey) {
      const { page } = journey;
      // Two things are typed and the rest is derived. A key and a ticket prefix
      // are machine text, so the pop-up mints them from the name rather than
      // asking a question with no right answer.
      const form = page.getByRole("dialog");
      await form.getByLabel("Project name").fill(PROJECT.name);
      await form.getByPlaceholder("https://github.com/org/repo").fill(PROJECT.repository);
      await form.getByRole("button", { name: "Create project" }).click();
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
      // The chooser by its own address rather than by the rail: the rail always
      // carries the project the switcher is pointed at, so a rail click opens
      // that project's screen instead of asking which one.
      await page.goto(`${TARGET}?at=tickets`, { waitUntil: "domcontentloaded" });
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

      // Third fact: its own screen opens, because the company now records a
      // document for it — and the work plane still answers with nothing,
      // because the document this console minted declares no component scoped
      // to that key. The screen says so plainly rather than drawing a project
      // that is half there.
      const head = await page.locator("main h1").innerText();
      assert.ok(
        head === PROJECT.name,
        `the authored project's own screen drew "${head}" rather than its name`
      );
      const shown = await page.locator("main").innerText();
      assert.ok(
        shown.includes("No ticket has been raised here yet."),
        `the board for ${PROJECT.key} did not say it is empty: ${shown.split("\n").slice(0, 5).join(" ")}`
      );
      throw new Blocked(
        `authored, and not yet addressable as work: the tickets chooser does not offer ` +
          `${PROJECT.key}, and the project's own screen answers with no ticket because ` +
          "the document this console authored declares no component scoped to it. " +
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
      // The chooser cannot offer a project until the company read has landed,
      // and a reload starts that read from nothing. Wait for the screen the
      // offers live on rather than for the network to go quiet around it.
      await page.getByLabel("Project key", { exact: true }).waitFor();
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
    id: "raise-pop-up-offers-the-record",
    act: "the pop-up that raises one offers the company's own people and projects",
    stops: true,
    async run(journey) {
      const { page } = journey;
      await page.getByRole("button", { name: "New ticket" }).click();
      await page.getByRole("dialog").waitFor();
      await seen(journey, "09-new-ticket");

      // The title is the only thing typed. Who takes it, what it came from and
      // where it lands are the record's own answers, so none of them is a box.
      const asked = await page.getByRole("dialog").locator("input, textarea").count();
      assert.ok(
        asked === 1,
        `the pop-up asks for ${String(asked)} things; it may only ask for one`
      );

      // Who: one live row, because omitting the custodian is what makes the
      // record hand the ticket to the calling seat. Everything else is a name
      // this company records, drawn and refused rather than left out.
      const people = await opened(journey, "Who takes it: Me", "09b-who-picker");
      assert.ok(people[0]?.startsWith("Me"), `the people picker opens on ${String(people[0])}`);
      assert.ok(
        people.slice(1).every((row) => row.includes("cannot take one yet")),
        "a name in the people picker is offered as though it could take a ticket"
      );

      // Where: the projects this company records, by name. The one the operator
      // is standing in is already chosen, so the sentence is true before it is
      // read rather than after it is answered.
      const wheres = await opened(journey, /^Which project: /, "09c-where-picker");
      assert.ok(wheres.length > 0, "the project picker offers nothing");

      // How urgent: three words, and the record's own three priorities.
      const urgency = await opened(journey, /^How urgent: /, "09d-urgency-picker");
      assert.ok(
        urgency.length === 3,
        `the urgency picker offers ${String(urgency.length)} words, not the record's three`
      );

      journey.facts.raisePopUp = {
        people: people.length,
        projects: wheres.length,
        urgencies: urgency.length,
      };
      return `the pop-up asks for one thing and offers ${String(people.length)} people, ${String(wheres.length)} projects and ${String(urgency.length)} urgencies`;
    },
  },
  {
    id: "ticket-raised",
    act: "a ticket is raised with a title and nothing else, and the console shows the receipt",
    ruling: "T-020",
    stops: true,
    async run(journey) {
      const { page } = journey;
      const dialog = page.getByRole("dialog");
      await dialog.getByLabel("Ticket title").fill(TICKET_TITLE);
      await dialog.getByRole("button", { name: "Raise it" }).click();
      await settle(page, journey.watched);
      await seen(journey, "10-raised");

      const shown = await dialog.innerText();
      // The record refuses this write for two reasons an open ruling owns, and
      // for neither of them is the console at fault: a project key the work
      // plane will not take (T-020's identifier families), and a caller who is
      // not an eligible custodian. Raising a ticket is a Commander's act —
      // `record/ticket_creation.py` requires Commander self-custody or an
      // operator naming an eligible Commander, and no declared read enumerates
      // one — so a console credentialled as the operator is refused here by
      // design. Either way the walk asserts the words the surface drew rather
      // than the act, and names what owes the answer.
      if (shown.includes("No ticket was raised.")) {
        const custody = shown.includes("Initial custody requires");
        throw new Blocked(
          `raising was refused on ${String(journey.facts.project)} and the pop-up drew the ` +
            `record's own words: ${refusal(shown)}. ` +
            (custody
              ? "This console's credential is not an eligible custodian; raising is a " +
                "Commander's act and no declared read enumerates one"
              : "T-020 owns the identifier families this refuses on")
        );
      }
      assert.ok(
        shown.includes("Raised") || shown.includes("Sent, and not confirmed yet"),
        `raising drew no receipt: ${shown.split("\n").slice(-4).join(" ")}`
      );
      journey.facts.ticket = TICKET_TITLE;
      // Back to the list, the way an operator leaves a pop-up they are done
      // with. The receipt stays until they do; a command that unmounted its own
      // answer would report nothing.
      await dialog.getByRole("button", { name: "Discard" }).click();
      await settle(page, journey.watched);
      return shown.includes("Raised")
        ? "the ticket was raised and accepted"
        : "the ticket was sent and is not yet confirmed durable";
    },
  },
  {
    id: "ticket-in-the-list",
    act: "the ticket appears in the project's own list",
    stops: true,
    async run(journey) {
      const { page } = journey;
      const row = page.getByText(TICKET_TITLE);
      const reads = await folded(journey, row, () => page.reload({ waitUntil: "networkidle" }));
      await seen(journey, "11-list");
      assert.ok(
        reads !== null,
        `the list never showed "${TICKET_TITLE}" within ${String(FOLD_CAP_MS / 1000)}s`
      );
      return `the row is in the list after ${String(reads)} ${reads === 1 ? "read" : "reads"}`;
    },
  },
  {
    id: "ticket-in-the-columns",
    act: "the toggle beside the list opens the same tickets as columns, and the rail moves with it",
    stops: false,
    async run(journey) {
      const { page } = journey;
      // Inside the screen, not in the rail. The toggle is a switch between two
      // shapes of one read, and the columns are a destination the rail carries
      // a row for — so asking for them has to move the rail and the address as
      // well as the shape, or the three would disagree about where the operator
      // is standing.
      await page.locator("main").getByRole("button", { name: "Board" }).click();
      await settle(page, journey.watched);
      await seen(journey, "12-columns");

      const asked = new URLSearchParams(new URL(page.url()).search);
      assert.ok(
        asked.get("at") === "board" && asked.get("project") === journey.facts.project,
        `the toggle left the address at "${new URL(page.url()).search}"`
      );
      const rail = await page
        .locator('nav[aria-label="Sections"] button[aria-current="page"]')
        .innerText();
      assert.ok(rail.trim() === "Board", `the rail still says the operator is on "${rail.trim()}"`);

      // The record's own answer for a new ticket is the first lane, so this
      // asserts the column rather than merely the card: a ticket that landed
      // anywhere else would mean the console and `_board_sql` disagree.
      const card = columnOf(page, "Waiting").getByText(TICKET_TITLE);
      assert.ok(
        (await card.count()) > 0,
        `"${TICKET_TITLE}" is not a card in the Waiting column of the board view`
      );
      return "the toggle moved the rail to Board, and the ticket is a card in the first column";
    },
  },
  {
    id: "board-shows-the-row",
    act: "the Board opens by its own address, on every lane the record keeps, with the seeded row on it",
    stops: false,
    async run(journey) {
      const { page } = journey;
      // By address, because a screen is a link: the Board reads whichever
      // project the address names, and this is the one the ticket was raised
      // on. Opening it fresh is the operator's own morning — nothing here
      // inherits the state the toggle left behind.
      await page.goto(`${TARGET}?at=board&project=${encodeURIComponent(journey.facts.project)}`, {
        waitUntil: "domcontentloaded",
      });
      // The columns are the screen, so the screen has arrived when they have. A
      // board that answered with nothing still draws all six.
      await columnOf(page, "Waiting").waitFor();
      await settle(page, journey.watched);

      // Every lane the record keeps has a column, in the order work moves
      // through them, at zero as readily as at ten: a lane whose column came
      // and went as work moved would be a board an operator has to re-learn
      // every morning, and a seventh would be one nothing could ever arrive in.
      const drawn = (await page.locator("main h2").allInnerTexts()).map((word) =>
        word.trim().toLowerCase()
      );
      assert.deepEqual(
        drawn,
        LANE_WORDS.map((word) => word.toLowerCase()),
        `the board drew the columns ${drawn.join(", ")}`
      );

      // The seeded row, read back off the board it should have folded into.
      // Re-read by reloading: this screen has no button that asks again, and
      // the operator's own way to ask a still screen for new facts is the one
      // the browser already gives them.
      const card = columnOf(page, "Waiting").getByText(TICKET_TITLE);
      const reads = await folded(journey, card, () => page.reload({ waitUntil: "networkidle" }));
      await seen(journey, "13-board");
      assert.ok(reads !== null, `the board never showed "${TICKET_TITLE}"`);
      return `${String(LANE_WORDS.length)} columns, and the row is on the board after ${String(reads)} ${reads === 1 ? "read" : "reads"}`;
    },
  },
];

/** One column of the board, found by the lane word at its head. */
function columnOf(page, lane) {
  return page.locator("section", { has: page.getByRole("heading", { name: lane, exact: true }) });
}

/** The step said it was blocked, and proved the surface said so honestly. */
class Blocked extends Error {}

/**
 * One picker, opened, read and shut.
 *
 * Every row it offers is returned as the operator sees it, which is what makes
 * "offers only real principals and projects" assertable rather than a claim.
 * A disabled row is a row: it is drawn on purpose, and a walk that only looked
 * at what it could click would miss the whole point of drawing it.
 */
async function opened(journey, name, shot) {
  const { page } = journey;
  await page.getByRole("dialog").getByRole("button", { name }).click();
  const menu = page.getByRole("menu");
  await menu.waitFor();
  const rows = await menu.getByRole("menuitem").allInnerTexts();
  await seen(journey, shot);
  await page.keyboard.press("Escape");
  await menu.waitFor({ state: "detached" });
  return rows;
}

/**
 * The refusal a pop-up drew, as one line: the registry's sentence and its code.
 *
 * The console renders a refusal as the registry's own words plus the code an
 * operator will meet again in the log and in the CLI, so those are what the
 * report carries — not a restatement this walk made up.
 */
function refusal(shown) {
  const lines = shown
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
  const at = lines.indexOf("No ticket was raised.");
  return at < 0 ? lines.join(" · ") : lines.slice(Math.max(0, at - 1), at + 2).join(" · ");
}

/**
 * Ask again until the projection has folded the write, or give up saying so.
 *
 * A write is not visible until the record's own projection has caught up, so a
 * screen judged on its first answer would be judged on a fact that had not
 * arrived yet. This is the only place in the walk that waits, and it waits by
 * asking rather than by sleeping.
 */
async function folded(journey, locator, again) {
  const deadline = Date.now() + FOLD_CAP_MS;
  let reads = 1;
  while ((await locator.count()) === 0) {
    if (Date.now() >= deadline) {
      return null;
    }
    await again();
    await settle(journey.page, journey.watched);
    reads += 1;
  }
  return reads;
}

async function report(results, journey) {
  const techText = journey.screens.filter((screen) => screen.techText.length > 0);
  // A step nobody reached because an open ruling stopped the one before it is
  // not a defect in this console, so it does not enter the failure count. It is
  // still reported as unreached, because the journey did not finish either.
  const failed = results.filter(
    (one) =>
      one.status === "FAIL" || (one.status === "UNREACHED" && one.because !== "BLOCKED-BY-RULING")
  );
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
