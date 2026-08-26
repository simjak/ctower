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
 * A head that is a fact of the company being walked rather than of the product.
 *
 * The rail's Tickets opens the project's own screen on its Tasks tab — one
 * tickets surface, says `TicketsPage` — so its head is that project's name, and
 * no pattern authored here could know it. Accepting anything would let a
 * Tickets destination that opened *another* project's screen walk clean, so the
 * walk asks the rail which project this workspace is about and holds the head to
 * that. `Tickets` and `Board` are the other truth: a project key the company
 * records no document for has no name to draw, and a company with no project at
 * all has no board to read, so each screen says what it is instead.
 */
const PROJECT_NAME = "the project the rail says this workspace is about";

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
  tickets: PROJECT_NAME,
  board: PROJECT_NAME,
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
 * The way in to a destination the rail draws as a section rather than as a link.
 *
 * `destinations.ts` names which key that is (`RAIL_SECTION`); what the section's
 * own way in *says* is product text, so it is authored here beside the heads for
 * the same reason they are. The count travels with the label once the section is
 * capped, so the pattern accepts it rather than the walk breaking on a seventh
 * agent — and it is a pattern rather than a prefix match so that a company with
 * no agent at all still has to draw the entry.
 */
const SECTION_ENTRY = {
  agents: /^See all agents( \(\d+\))?$/,
};

/**
 * The product's map, read from the product.
 *
 * The union of keys is parsed alongside the list and the two are required to
 * agree. A reformat that made the list pattern miss an entry would otherwise
 * walk fewer destinations and still report a clean run.
 *
 * The map is two workspaces now, and the shape it is read in follows: a
 * destination declares the `workspace` it belongs to, the rail draws the
 * workspaces in their own declared order, and one destination — the one
 * `RAIL_SECTION` names — is drawn as a section of the rail rather than as a link
 * in it. All three of those are parsed out of the same file rather than assumed,
 * because a second copy of the map is exactly what this function exists to
 * refuse.
 */
async function readDestinations() {
  const source = await readFile(DESTINATION_MAP, "utf8");

  const union = source.match(/export type DestinationKey =([^;]+);/);
  assert.ok(union, `${DESTINATION_MAP} declares no DestinationKey union`);
  const declared = [...union[1].matchAll(/"([a-z-]+)"/g)].map((match) => match[1]);

  const listed = [
    ...source.matchAll(
      /\{\s*key:\s*"([a-z-]+)",\s*label:\s*"([^"]+)",\s*workspace:\s*"([A-Z]+)",\s*built:\s*(true|false)\s*\}/g
    ),
  ].map(([, key, label, workspace, built]) => ({ key, label, workspace, built: built === "true" }));

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

  const order = source.match(/export const WORKSPACES: readonly Workspace\[\] =([^;]+);/);
  assert.ok(order, `${DESTINATION_MAP} declares no WORKSPACES order`);
  const workspaces = [...order[1].matchAll(/"([A-Z]+)"/g)].map((match) => match[1]);
  const unplaced = listed.filter((one) => !workspaces.includes(one.workspace));
  assert.ok(
    unplaced.length === 0,
    `the map puts ${unplaced.map((one) => one.label).join(", ")} in a workspace the rail does not draw`
  );

  const section = source.match(/export const RAIL_SECTION: DestinationKey = "([a-z-]+)";/);
  assert.ok(section, `${DESTINATION_MAP} declares no RAIL_SECTION`);
  assert.ok(
    declared.includes(section[1]),
    `the map draws "${section[1]}" as a rail section and declares no such destination`
  );
  assert.ok(
    SECTION_ENTRY[section[1]],
    `the map draws "${section[1]}" as a rail section and this walk has no way in authored for it`
  );

  return { destinations: listed, workspaces, section: section[1] };
}

/**
 * The destinations the rail draws as ordinary links, in the order it draws them:
 * each workspace in turn, and the section's own destination in neither, because
 * a link labelled "Agents" beside the AGENTS section would be a second door to
 * one room. This is `linksIn` over `WORKSPACES`, read rather than restated.
 */
function railedLinks({ destinations, workspaces, section }) {
  return workspaces.flatMap((workspace) =>
    destinations.filter((one) => one.workspace === workspace && one.key !== section)
  );
}

/**
 * The rail offers exactly the map, and offers it honestly.
 *
 * This is also the walk's guard against a stale surface: if the console being
 * walked serves an older tree than the checkout this script reads its map from,
 * the two disagree here, at one clearly-named step, instead of as a confusing
 * failure four destinations later.
 */
async function checkRail(page, watched, map) {
  const rail = page.locator(RAIL);
  await rail.waitFor();
  await settle(page, watched);

  // Only the rail's own links. The project dropdown and the agents section live
  // inside the workspace they belong to, so they are one level further down —
  // and counting them here would read the rail as offering destinations that
  // are not on the map.
  const offered = await rail.locator("> div > button").evaluateAll((buttons) =>
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
  const links = railedLinks(map);
  const railed = offered.map((one) => one.label).join(", ");
  const mapped = links.map((one) => one.label).join(", ");
  assert.ok(
    railed === mapped,
    `the rail this console serves is not the map this checkout declares: rail ${railed} against map ${mapped}`
  );
  for (const [index, destination] of links.entries()) {
    assert.ok(
      offered[index].disabled === !destination.built,
      `the rail offers ${destination.label} as ${offered[index].disabled ? "unbuilt" : "built"}, ` +
        `and the map declares it ${destination.built ? "built" : "unbuilt"}`
    );
  }

  // The one destination that is a section rather than a link still has to be
  // reachable, and it is reachable through the section's own way in. A rail
  // that drew the staff and no way to the whole list would walk clean here and
  // leave a built destination with no door.
  const way = sectionEntry(page, map.section);
  assert.ok(
    (await way.count()) === 1,
    `the rail draws no way in to ${map.section}: its section is missing or has no entry leading to its page`
  );

  return (
    `${String(links.length)} destinations offered as links across ` +
    `${String(map.workspaces.length)} workspaces, ` +
    `${String(links.filter((one) => one.built).length)} of them reachable, ` +
    `plus the ${map.section} section`
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

  // An address says two things now: which screen, and — for a screen that is
  // about one project — which project. `destinations.ts` puts the second one
  // there on purpose ("sending someone `?at=board` alone would open whichever
  // project their own console happened to remember"), so this reads the address
  // by what it means rather than by the one string it used to be.
  const address = new URL(page.url()).search;
  const asked = new URLSearchParams(address);
  assert.ok(
    asked.get("at") === key,
    `${label} was opened ${from} and the address says "${address}" instead of "?at=${key}"`
  );
  const named = asked.get("project") ?? "";
  if (destination.workspace === "PROJECT") {
    assert.ok(
      named !== "",
      `${label} is about one project and was opened ${from} with an address that names none: "${address}"`
    );
    notes.push(`scoped to one project`);
  } else {
    assert.ok(
      named === "",
      `${label} is about the company and was opened ${from} with an address that names a project: "${address}"`
    );
  }
  const current = page.locator(`${RAIL} button[aria-current="page"]`);
  const marked = await current.count();
  assert.ok(marked === 1, `the rail marks ${String(marked)} places as here, not one`);
  const railSays = (await current.innerText()).trim();
  // A destination the rail draws as a section is marked on that section's own
  // way in, which says what the section says and not what the map calls the
  // destination. Both are the rail agreeing with the address; only the words
  // differ, so only the words are read differently.
  const entry = SECTION_ENTRY[key];
  assert.ok(
    entry === undefined ? railSays === label : entry.test(railSays),
    `the address says ${label} and the rail says the operator is on ${railSays}`
  );

  const authored = HEADING[key];
  assert.ok(authored, `${key} is built and this walk has no head authored for it`);
  const expected = authored === PROJECT_NAME ? await headOfProject(page) : authored;
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
async function visit(page, watched, destination, map, reload) {
  const since = { crashes: watched.crashes.length, apiFailures: watched.apiFailures.length };
  if (reload) {
    await page.goto(`${TARGET}${addressOf(page, destination)}`, { waitUntil: "domcontentloaded" });
    return judge(page, watched, destination, "by its own address", since);
  }
  const link = wayTo(page, destination, map);
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
 * The address a destination is written as, for the arrival that loads one
 * directly.
 *
 * The project comes off the console rather than out of a second copy of
 * `addressFor`: the walk has no opinion about which project this tower is on,
 * and the address bar has already been told. A bare `?at=board` would open
 * whichever project the console remembered, which is a different screen from
 * the one the rail just showed — so a project screen is reloaded with its
 * project and a company screen with none.
 */
function addressOf(page, destination) {
  const on = new URLSearchParams(new URL(page.url()).search).get("project") ?? "";
  const written = new URLSearchParams({ at: destination.key });
  if (destination.workspace === "PROJECT" && on !== "") {
    written.set("project", on);
  }
  return `?${written.toString()}`;
}

/**
 * The head a project's own screen has to draw, taken from the rail.
 *
 * The dropdown at the head of the project workspace is what says which project
 * that half of the rail is about, so it is the one thing on screen a project
 * screen's own title can be held to. The name is escaped before it becomes a
 * pattern: an operator is free to call a project `C++ (rewrite)`, and a title
 * that failed to match because of how it was punctuated would be this walk
 * reporting a defect it invented.
 */
async function headOfProject(page) {
  const chooser = page.locator(`${RAIL} > div > div > button span.block.truncate`);
  assert.ok(
    (await chooser.count()) === 1,
    "the rail draws no project dropdown, so nothing says which project this workspace is about"
  );
  const named = (await chooser.innerText()).trim();
  return new RegExp(`^(${named.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}|Tickets|Board)$`);
}

/**
 * The rail's own way to a destination, whichever of the two shapes it has.
 *
 * Most are links. One is a section, and the way to its page is the entry inside
 * that section — the operator's route, and the only route: there is no link
 * beside the section carrying the destination's label, and asking for one would
 * be this walk insisting on a rail the product deliberately does not draw.
 */
function wayTo(page, destination, map) {
  return destination.key === map.section
    ? sectionEntry(page, map.section)
    : railLink(page, destination.label);
}

/**
 * A destination in the rail, found by the label the operator reads.
 *
 * Not by accessible name: an unreachable destination carries its reason in that
 * name, so asking for one by name finds nothing and the walk would time out
 * instead of saying the rail declined to move.
 *
 * Scoped to the rail's own links, so a member of staff who happens to share a
 * destination's name cannot stand in for it.
 */
function railLink(page, label) {
  return page.locator(`${RAIL} > div > button:has(span.truncate:text-is("${label}"))`);
}

/**
 * The entry inside a rail section that leads to that section's own page.
 *
 * A section sits one level in from the rail's links, and so does the project
 * dropdown, so the text is what tells them apart. It is deliberately not
 * narrowed to the first hit: exactly one entry may lead to the page, and a
 * second one is a defect the caller should be told about rather than one this
 * helper quietly picks between.
 */
function sectionEntry(page, section) {
  return page.locator(`${RAIL} > div > div button`).filter({ hasText: SECTION_ENTRY[section] });
}

/**
 * A destination, walked, with one retry.
 *
 * Opening a destination and reading what it drew is a safe read, so repeating it
 * is the same act — the rule the app's own chokepoint retries under. A second
 * attempt is recorded rather than hidden: a destination that only renders the
 * second time is a fact an operator should see.
 */
async function walkDestination(page, watched, destination, map) {
  const refused = [];
  for (const attempt of [1, 2]) {
    try {
      const drew = await visit(page, watched, destination, map, attempt === 2);
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
  const map = await readDestinations();
  const built = map.destinations.filter((one) => one.built);
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
      await step("shell rail", async () => checkRail(page, watched, map));

      for (const destination of built) {
        results.push(await walkDestination(page, watched, destination, map));
      }

      await step("a screen is a link", async () => {
        const opened = built.find((one) =>
          results.some((result) => result.destination === one.key && result.pass)
        );
        assert.ok(opened, "no destination rendered, so no address had a screen to come back to");
        await wayTo(page, opened, map).click();
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
