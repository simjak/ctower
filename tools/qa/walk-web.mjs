#!/usr/bin/env node
/**
 * The walk: every built destination of `apps/ctower-web`, on a live console, in
 * a headless browser.
 *
 * This is the apparatus an approval walk replays. It is deliberately not a repo
 * suite: D75 retired the browser suites, so nothing here is registered in
 * `tools/checks/expected-suites.toml`, nothing is wired into a gate, and the
 * repository does not depend on a browser driver. It is a tool the operator
 * runs against a console that is already serving, and it is read-only — it
 * admits itself, moves through the rail, and reads pages. It never touches a
 * control that writes.
 *
 * The map is not copied here. `apps/ctower-web/src/shell/destinations.ts` is the
 * product's only map, this reads it, and it walks exactly the destinations that
 * file marks `built`. A destination that becomes built is walked the moment it
 * is declared built; a destination this file has no expectation for fails rather
 * than being skipped, which is the same discipline `App.tsx` keeps by naming
 * every key in one `switch`.
 *
 * The walk moves the way an operator does — by clicking the rail — and not by
 * reloading the page at each address. That is the honest surface (the rail is
 * how a destination is reached), and it is also the robust one: a dev server
 * hands the browser 186 modules on every full load, and over a link that flaps
 * one lost module is a blank screen that has nothing to do with the page being
 * judged. A screen is still a link, so one authored step proves that separately.
 *
 * What each destination has to prove:
 *
 * 1. **The address followed the rail.** Clicking a destination puts `?at=<key>`
 *    in the address bar and the rail marks that destination as the place being
 *    looked at, so the address and the shell cannot disagree.
 * 2. **Its own head.** Exactly one `h1` inside the page's main region, and its
 *    text is the one authored for that destination — not the shell's, and not
 *    the destination next door's.
 * 3. **Its own body.** Something rendered below that head. A page that draws its
 *    title and nothing else has not rendered.
 * 4. **No contract error.** Not the state that says ctower answered something
 *    this client cannot read, not the one that says ctower did not answer, no
 *    uncaught exception in the page, and no API answer of 400 or worse.
 *
 * Every visit is screenshotted, whether it passed or failed, and the run writes
 * one JSON report. Any failure exits non-zero.
 *
 *   WALK_PLAYWRIGHT_ROOT=<dir holding node_modules/playwright> \
 *     PLAYWRIGHT_BROWSERS_PATH=0 node tools/qa/walk-web.mjs
 *
 * Playwright is supplied from outside the repository on purpose — it is the one
 * thing this tool needs that D75 says the repository does not carry.
 *
 * A console does not always serve the tree this tool was checked out from. The
 * seeded board surface pins an older merge on which two destinations are still
 * honestly unbuilt, so its map is a different file — `WALK_MAP` points at it,
 * and the rail check then holds the surface to its own map rather than to one
 * it never claimed.
 *
 * Environment, all optional but the first:
 *   WALK_PLAYWRIGHT_ROOT  where playwright is installed
 *   WALK_TARGET           the console's origin (default this host's :3150 walk surface)
 *   WALK_TOKEN_FILE       the file holding that server's session token
 *   WALK_MAP              the `destinations.ts` the target serves (default this checkout's)
 *   WALK_SHOT_DIR         where screenshots and the report are written
 */

import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import {
  admit,
  CONTRACT_ERROR,
  loadPlaywright,
  NO_ANSWER,
  RAIL,
  settle,
  watch,
  why,
} from "./_console.mjs";

const REPO = path.resolve(import.meta.dirname, "..", "..");
const DESTINATION_MAP =
  process.env.WALK_MAP ?? path.join(REPO, "apps", "ctower-web", "src", "shell", "destinations.ts");

const TARGET = process.env.WALK_TARGET ?? "http://100.84.252.114:3150/";
const TOKEN_FILE = process.env.WALK_TOKEN_FILE ?? "/tmp/walk-session-token";
const SHOT_DIR = process.env.WALK_SHOT_DIR ?? "/tmp/walk-shots";
const REPORT = path.join(SHOT_DIR, "walk-web-report.json");

/**
 * The head each built destination draws, authored once, here.
 *
 * One of them is not a constant: the company screen says which of its two jobs
 * it is doing, and saying "Create a company" to an operator who has one is the
 * fastest way to make him distrust the rest of the screen — so both truths are
 * accepted and nothing else is.
 */
const HEADING = {
  inbox: /^Inbox$/,
  tickets: /^Tickets$/,
  board: /^Board$/,
  workflows: /^Workflows$/,
  requests: /^Requests$/,
  crews: /^Crews$/,
  agents: /^Agents$/,
  company: /^(Create a company|Edit company definition)$/,
  harnesses: /^Harnesses$/,
  projects: /^Projects$/,
  admin: /^Admin$/,
};

/**
 * The product's map, read from the product.
 *
 * The union of keys is parsed alongside the list and the two are required to
 * agree. A reformat that made the list pattern miss an entry would otherwise
 * walk fewer destinations and still report a clean run.
 */
async function readDestinations() {
  const source = await readFile(DESTINATION_MAP, "utf8");

  const union = source.match(/export type DestinationKey =([^;]+);/);
  assert.ok(union, `${DESTINATION_MAP} declares no DestinationKey union`);
  const declared = [...union[1].matchAll(/"([a-z-]+)"/g)].map((match) => match[1]);

  const listed = [
    ...source.matchAll(
      /\{\s*key:\s*"([a-z-]+)",\s*label:\s*"([^"]+)",\s*group:\s*"([A-Z]+)",\s*built:\s*(true|false)\s*\}/g
    ),
  ].map(([, key, label, group, built]) => ({ key, label, group, built: built === "true" }));

  const found = listed.map((one) => one.key).sort();
  assert.ok(
    found.join(",") === [...declared].sort().join(","),
    "the destination list and the DestinationKey union disagree, so this file could not be read: " +
      `union ${declared.join(", ")} against list ${found.join(", ")}`
  );
  assert.ok(
    listed.some((one) => one.built),
    "no destination is marked built; there is nothing to walk"
  );
  return listed;
}

/**
 * The rail offers exactly the map, and offers it honestly.
 *
 * This is also the walk's guard against a stale surface: if the console being
 * walked serves an older tree than the checkout this script reads its map from,
 * the two disagree here, at one clearly-named step, instead of as a confusing
 * failure four destinations later.
 */
async function checkRail(page, watched, destinations) {
  const rail = page.locator(RAIL);
  await rail.waitFor();
  await settle(page, watched);

  const offered = await rail.locator("button").evaluateAll((buttons) =>
    buttons.map((button) => ({
      label: button.querySelector("span.truncate")?.textContent ?? "",
      disabled: button.getAttribute("aria-disabled") === "true",
    }))
  );
  // Locked is a different fact from unbuilt, and the rail draws both the same
  // way. Say which one this is rather than blaming the first destination.
  assert.ok(
    offered.some((one) => !one.disabled),
    "the shell is locked: nothing in the rail is reachable, so the company read has not answered"
  );
  const railed = offered.map((one) => one.label).join(", ");
  const mapped = destinations.map((one) => one.label).join(", ");
  assert.ok(
    railed === mapped,
    `the rail this console serves is not the map this checkout declares: rail ${railed} against map ${mapped}`
  );
  for (const [index, destination] of destinations.entries()) {
    assert.ok(
      offered[index].disabled === !destination.built,
      `the rail offers ${destination.label} as ${offered[index].disabled ? "unbuilt" : "built"}, ` +
        `and the map declares it ${destination.built ? "built" : "unbuilt"}`
    );
  }
  return (
    `${String(destinations.length)} destinations offered, ` +
    `${String(destinations.filter((one) => one.built).length)} of them reachable`
  );
}

/**
 * Judge whatever the shell is currently showing for one destination.
 *
 * `since` is where this arrival's traffic starts in the session's record, so a
 * page is judged on its own reads. The cause is asserted before the symptom: a
 * screen that drew a contract error because a read came back 404 reports the
 * 404, because that is the sentence that says what to go and fix.
 */
async function judge(page, watched, destination, from, since) {
  const { key, label } = destination;
  const notes = [];

  await page.locator("main").waitFor();
  await settle(page, watched);
  await page.screenshot({ path: shotFor(key), fullPage: true });

  const address = new URL(page.url()).search;
  assert.ok(
    address === `?at=${key}`,
    `${label} was opened ${from} and the address says "${address}" instead of "?at=${key}"`
  );
  const current = page.locator(`${RAIL} button[aria-current="page"]`);
  const marked = await current.count();
  assert.ok(marked === 1, `the rail marks ${String(marked)} places as here, not one`);
  const railSays = (await current.innerText()).trim();
  assert.ok(
    railSays === label,
    `the address says ${label} and the rail says the operator is on ${railSays}`
  );

  const expected = HEADING[key];
  assert.ok(expected, `${key} is built and this walk has no head authored for it`);
  const heads = await page.locator("main h1").allInnerTexts();
  assert.ok(heads.length === 1, `${label} drew ${String(heads.length)} page heads, not one`);
  assert.ok(
    expected.test(heads[0]),
    `${label} drew the head "${heads[0]}", which is not ${String(expected)}`
  );
  notes.push(`head "${heads[0]}"`);

  // The shell's content column holds the page's head and then the page. One
  // child is a title with nothing under it, which is not a rendered screen.
  const blocks = await page.locator("main > div > *").count();
  assert.ok(blocks >= 2, `${label} drew its head and nothing else`);
  notes.push(`${String(blocks)} blocks`);

  const crashes = watched.crashes.slice(since.crashes);
  assert.ok(crashes.length === 0, `${label} raised an uncaught error: ${crashes.join(" | ")}`);
  const failures = watched.apiFailures.slice(since.apiFailures);
  assert.ok(failures.length === 0, `${label} read the API and it failed: ${failures.join(" | ")}`);

  const shown = await page.locator("main").innerText();
  assert.ok(
    !shown.includes(CONTRACT_ERROR),
    `${label} rendered a contract error: ${CONTRACT_ERROR}`
  );
  assert.ok(!shown.includes(NO_ANSWER), `${label} rendered an unanswered read: ${NO_ANSWER}`);
  return notes.join("; ");
}

/**
 * One destination, opened the way an operator opens it, and then judged.
 *
 * `reload` is the second attempt's arrival: a full load of the destination's own
 * address. Moving through the rail costs no module traffic, so the first attempt
 * is the cheap and faithful one; a page that lost modules to a flapping link is
 * recovered by fetching them again rather than by being called a failure.
 */
async function visit(page, watched, destination, reload) {
  const since = { crashes: watched.crashes.length, apiFailures: watched.apiFailures.length };
  if (reload) {
    await page.goto(`${TARGET}?at=${destination.key}`, { waitUntil: "domcontentloaded" });
    return judge(page, watched, destination, "by its own address", since);
  }
  const link = railLink(page, destination.label);
  // The rail is inert rather than disabled for a destination it will not move
  // to, so a click on one is silently nothing. Say that, rather than reporting
  // it later as the shell disagreeing with an address that never changed.
  assert.ok(
    (await link.getAttribute("aria-disabled")) === null,
    `the rail refuses to move to ${destination.label}: it does not offer it as reachable`
  );
  await link.click();
  return judge(page, watched, destination, "from the rail", since);
}

function shotFor(key) {
  return path.join(SHOT_DIR, `walk-${key}.png`);
}

/**
 * A destination in the rail, found by the label the operator reads.
 *
 * Not by accessible name: an unreachable destination carries its reason in that
 * name, so asking for one by name finds nothing and the walk would time out
 * instead of saying the rail declined to move.
 */
function railLink(page, label) {
  return page.locator(`${RAIL} button:has(span.truncate:text-is("${label}"))`);
}

/**
 * A destination, walked, with one retry.
 *
 * Opening a destination and reading what it drew is a safe read, so repeating it
 * is the same act — the rule the app's own chokepoint retries under. A second
 * attempt is recorded rather than hidden: a destination that only renders the
 * second time is a fact an operator should see.
 */
async function walkDestination(page, watched, destination) {
  const refused = [];
  for (const attempt of [1, 2]) {
    try {
      const drew = await visit(page, watched, destination, attempt === 2);
      return {
        destination: destination.key,
        pass: true,
        attempts: attempt,
        note: attempt === 1 ? drew : `${drew}; drew on a second attempt`,
        shot: shotFor(destination.key),
      };
    } catch (error) {
      refused.push(why(error));
    }
  }
  await page.screenshot({ path: shotFor(destination.key), fullPage: true }).catch(() => undefined);
  // Two attempts arrive two different ways, so they can fail for two different
  // reasons. Both are reported: the one that is kept quiet is always the one
  // that said what was actually wrong.
  return {
    destination: destination.key,
    pass: false,
    attempts: 2,
    note:
      refused[0] === refused[1] ? refused[0] : `${refused[0]}; by its own address, ${refused[1]}`,
    shot: shotFor(destination.key),
  };
}

/**
 * A screen is a link.
 *
 * `destinations.ts` promises that `?at=<key>` reopens exactly what was being
 * looked at, so a reload has to come back to the same screen rather than to the
 * shell's first destination. It is proved once, on a destination that already
 * rendered, because it is a property of the address and not of the page.
 */
async function checkAddressIsAScreen(page, watched, destination) {
  let last = null;
  for (const attempt of [1, 2]) {
    try {
      const since = { crashes: watched.crashes.length, apiFailures: watched.apiFailures.length };
      await page.reload({ waitUntil: "domcontentloaded" });
      const drew = await judge(page, watched, destination, "by reloading its address", since);
      const again = attempt === 1 ? "" : " (on a second reload)";
      return `${destination.label} came back after a reload${again} — ${drew}`;
    } catch (error) {
      last = error;
    }
  }
  throw last;
}

async function main() {
  const { chromium } = loadPlaywright();
  const token = (await readFile(TOKEN_FILE, "utf8")).trim();
  assert.ok(token !== "", `${TOKEN_FILE} holds no session token`);
  const destinations = await readDestinations();
  const built = destinations.filter((one) => one.built);
  await mkdir(SHOT_DIR, { recursive: true });

  const origin = new URL(TARGET).origin;
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.setDefaultTimeout(20_000);
  const watched = watch(page, origin);

  const results = [];
  const step = async (name, action) => {
    try {
      results.push({ destination: name, pass: true, note: await action() });
    } catch (error) {
      results.push({ destination: name, pass: false, note: why(error) });
    }
  };

  try {
    await step("admission", async () =>
      admit(page, { target: TARGET, tokenFile: TOKEN_FILE, token })
    );
    if (results[0].pass) {
      await step("shell rail", async () => checkRail(page, watched, destinations));

      for (const destination of built) {
        results.push(await walkDestination(page, watched, destination));
      }

      await step("a screen is a link", async () => {
        const opened = built.find((one) =>
          results.some((result) => result.destination === one.key && result.pass)
        );
        assert.ok(opened, "no destination rendered, so no address had a screen to come back to");
        await railLink(page, opened.label).click();
        return checkAddressIsAScreen(page, watched, opened);
      });
    } else {
      // Nothing was walked, and the report says so for every destination rather
      // than leaving the operator to infer it from an absence.
      for (const destination of built) {
        results.push({
          destination: destination.key,
          pass: false,
          attempts: 0,
          note: "not walked: the console did not admit this walk",
        });
      }
    }
  } finally {
    await browser.close();
  }

  const failed = results.filter((one) => !one.pass);
  const walked = new Set(built.map((one) => one.key));
  const clean = results.filter((one) => walked.has(one.destination) && one.pass).length;
  const report = {
    target: TARGET,
    when: new Date().toISOString(),
    map: path.resolve(DESTINATION_MAP),
    walked: built.length,
    clean,
    failed: failed.length,
    results,
  };
  await writeFile(REPORT, `${JSON.stringify(report, null, 2)}\n`, "utf8");

  for (const one of results) {
    console.log(`${one.pass ? "PASS" : "FAIL"} ${one.destination.padEnd(20)} ${one.note}`);
  }
  console.log(
    `\n${String(clean)}/${String(built.length)} built destinations walked clean on ${TARGET}`
  );
  console.log(`screenshots: ${SHOT_DIR}/walk-*.png\nreport: ${REPORT}`);
  if (failed.length > 0) {
    process.exitCode = 1;
  }
}

await main();
