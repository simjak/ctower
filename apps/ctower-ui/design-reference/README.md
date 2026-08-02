# ctower UI — phase 1 mockups (R2704 · R2710 · R2707)

Nine static pages sharing one frame, one nav, one stylesheet and two themes.

| Page | What it shows |
|---|---|
| `board.html` | The portfolio ticket board: seven pipeline stages as columns on the desk and as a stacked, jump-linked list on a phone. Cards carry the id, priority, PR link, project chip, accountable seat and time-in-stage, plus a one-line reason on anything held, changes-requested or waiting on a human. |
| `ticket.html` | One ticket in full (`gh#192`, seat credential issuance — the live adoption blocker): header and custody line, the seven-stage strip, brief, acceptance criteria with what proves each, the **work timeline** (who · what · duration · tokens · outcome, over a totals bar), a typed evidence gallery, and append-only signed comments. |
| `workflow.html` | The software factory as configuration: the stage sequence with grips and an add slot, a card per stage listing exactly what it must produce to be left, project overlay tabs that reveal what `lastmachines` and `bh-loop` each add, and a **YAML** tab rendering the same workflow as the config file the kernel reads — layer 5 of the company → projects → team → ticket-schema → workflows model. |
| `heartbeats.html` | The cadence registry: every scheduled wake in the portfolio — owning seat, schedule, last fire, next fire, health — over a totals strip. A late and a dead beat each state, on the row, why they stopped arriving. |
| `inbox.html` | One seat's durable inbox. The seat selector switches the whole surface; the seat's exact addressing name and the `tools/notify` line that reaches it are the loudest thing on the page, because addressing the wrong name is how messages get lost. |
| `feed.html` | A live session as a conversation: agent turns as bubbles with their reasoning, tool calls as collapsed chips that expand to their output, the moment a gate fires as a system line across the thread, and operator injections as right-hand messages carrying their audit trailer. A composer at the foot sends an audited turn, and a **Raw terminal** switch top-right returns the timestamped monospace stream for debugging. |
| `files.html` | The files editor: a tree over souls, skills, crew guides, project rules and repo root; the selected file open with line numbers; and a save that shows the branch, PR and review gate it would go through rather than writing anything. |
| `workspace.html` | What a session is handed at start: bound ticket, task file, worktree, branch, project, harness and model, persona, access mode, and the literal `bin/mux spawn` command — then its state transitions. |
| `explorer.html` | The session's worktree with a File / Diff switch: the file as it stands, or the unified diff of the branch against main, with per-file counts. |

`app.css` is shared by all nine so the frame, tokens, glyph vocabulary and stage colours cannot drift.

**Two themes, one markup.** Light is the default and is built on the manibo web app's active Vercel
token pack (`manibo/packages/ui/src/tokens/themes/vercel.css`): the same neutral scale, `#eaeaea`
borders, 4–8px radii, single teal accent, semantic success/warning/error/info set, and that pack's
`--shadow-sm: none` — so there are no shadows, gradients or glows in either theme. Dark is the
original surface refined onto the identical semantic names, with one correction: v1 used amber for
both "selected" and "needs a human", so those are now split into accent (selection) and warning
(needs-you) exactly as in light. Nothing but CSS variables changes between them — both themes render
identical page geometry, which is the check that the re-skin stayed a re-skin. The sun/moon button
at the top right of every page swaps a `theme-dark` class on `<html>` and stores the choice in
`localStorage`; an inline script in `<head>` applies it before first paint, so a dark-theme reader
never gets a white flash.

**Real vs invented.** The tickets, projects, issue and PR numbers, seat and crew names, stage
positions, verdicts, blocking reasons, beat names and schedules, addressing names, inbox messages,
commit subjects, and every workflow requirement (each is a line already enforced by a checklist, a
decision or a hard rule in this repo) are real, taken from the fleet as of 2026-08-02 08:34 Vilnius. `gh#192` really
is held on file-disjointness against `#191`; `PR #182` really is CHANGES_REQUESTED; `PR #3391`
really is waiting on an operator approval a bot approval cannot satisfy; the expanded inbox message
is the actual R2710 dispatch that ordered the round-2 screens; the workflow's five config
layers are the R2707 product direction as the operator stated it. Invented, because ctower does not
record them yet, are: per-session **durations and token counts** (and therefore every total), the
feed's line-by-line reasoning text, the file contents shown in the editor (real in substance,
abridged to fit), the diff hunks, commit shas, some clock times, and the manibo PR numbers
`#3388`/`#3396`. The work timeline, the per-beat health state and the
workflow's YAML shape are the parts this mockup is proposing — both are drawn from facts the fleet already holds, plus per-session cost, which is the
one genuinely new fact the record would have to start carrying.

**Controls that really work.** No build step, no external requests. The project filter, the inbox
seat selector, the files tree, the explorer File/Diff switch, the workflow Stages/YAML switch and
project overlays, the feed's Chat/Raw switch, the tool-call chips, the stage jump links, the nav and
every GitHub link are real. The tool chips are native `<details>` and need no script at all. Five
things do use JavaScript, all inline and small: the theme toggle, the feed composer (which posts an
audited operator turn into *both* the chat and the raw stream), the files Save (which reveals the
branch and gate the commit would go through), the inbox seat swap, and the workflow overlay — which
recomputes every stage count from the rows actually visible, so a badge cannot drift from its list.
The workflow's reorder grips and `+ stage` slot are deliberately inert structure, not buttons, with
the caveat in a tooltip rather than a banner. Nothing else is clickable, by design. Every board
card links to `ticket.html`, the only ticket detail page in the set. The six state marks — proven, not started, in flight, held, parked, needs-you — are drawn
in CSS rather than set as the `● ○ ⟳ ⛔ ⏸ ⚠` characters `ctowerctl` prints, because half that set
renders as full-colour emoji in a browser and depends on the reader's device fonts. ctower's
`staging` stage honestly reads `no infrastructure` rather than pretending an environment exists.

**Screenshots** — 26 in all: `board` and `ticket` in both themes at 390 and 1440, the six round-2
pages in light at 390 and 1440, the round-3 `workflow` in both its Stages and YAML views, plus
`shot-board-light-1440-tail` (the rail scrolled to the later stages) and
`shot-board-light-1440-filtered-manibo` (the filter in use). Every page is measured for
horizontal overflow in *both* themes even where only light is captured, so a theme cannot hide one.
