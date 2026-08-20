# The operator cockpit — design (R3109)

**Status:** design proposal. Non-normative.

This document proposes; it does not approve. `docs/internal/SPEC.md` remains the only place that
may activate scope, `docs/internal/DECISIONS.md` the only place that may record a decision, and
this file adds a row to neither. R3109 has no stable CT ticket, so nothing here is buildable
product behaviour yet — the constitution puts product behaviour out of scope until its ticket and
dependencies are active. What this file is for is that when R3109 does earn a ticket, the design
argument is already made, already checked against the seam contract, and already carries its
citations.

Companion artifact: `operator-cockpit.html` beside this file — one static mockup of the four-pane
shell, openable with no build step.

**Direction, verbatim (operator, 2026-08-20):** *"I want the same clean UI as paperclip has for
ctower."* Paperclip's visual language is the target aesthetic. Two reads were granted with it:
paperclip's source at `/srv/projects/paperclip-eval/ui` for the real design system, and the live
instance at `http://127.0.0.1:3100`. This document cites source wherever source exists, and says
so explicitly on the few claims that rest on a screenshot instead.

---

## 1. The target

The brief: a four-pane cockpit. LEFT — projects and their crew members, the commander included,
each row carrying live `+adds −dels` badges. CENTER — tabbed chat with the selected crew: agent
turns with collapsible thinking, inline tool-call rows, `INTERRUPTED BY USER` chips, elapsed
time, a composer with a model indicator. RIGHT-TOP — the crew's workspace: changed files with
per-file `+N −N`, a diff view, a Create-PR button. RIGHT-BOTTOM — tabs Setup / Run / Terminal.

The operator's own words for the goal: *"ChatGPT/Claude-desktop experience with crew members… I
want in UI run harness setup wizard, and have open crews view and communication. no tmux or
whatever."*

The Conductor reference screenshot (`cmux-drop-a58d9154…png`, 5088×2822) reads pane by pane:

| Pane | What Conductor actually draws |
| --- | --- |
| Left rail | account switcher · Dashboard/Home/Create/Search · **Projects**, each with its workspaces indented under it, each workspace carrying a live `+1k −21` / `+333 −182` / `+3` badge and an unread count |
| Centre | workspace tabs (`import-scenari…` · **Create Simulation Page** · `Create agent simulation p…` · `+`) over a transcript: tool rows as *icon · label · truncated monospace command*, `Thinking` as a collapsible line, an `INTERRUPTED BY USER` chip, an elapsed stamp (`5m, 42s`), the operator's own turns as a right-side grey bubble, assistant markdown, per-turn duration + copy + more, and a `Next unread ›` jump |
| Composer | `Ask to make changes, @mention files, run /commands` · `⌘L to focus` · model chip `✳ Opus 4.8 1M` · a thinking-effort meter (`Max`) · attach/mic/send |
| Right-top | `All files · Changes 11 · Checks` + `Review`, `11 files changed +1012 −21`, per row a dimmed directory + bold basename and a right-aligned `U +39` / `+11 −9`, with `Create PR` in the window chrome |
| Right-bottom | `Setup · Run · ● Terminal · +` with a collapse chevron |

That is the shape to hit. The rest of this document is how ctower hits it without lying — because
almost every pane above states a fact that ctower is only sometimes able to observe, and the
difference between "renders the fact" and "renders a plausible number" is the whole design.

---

## 2. This is an assembly problem, not a green field

`apps/ctower-ui` already contains most of the cockpit, built against the approved phase-1 screen
set. Anyone scoping this as a new build will duplicate work that exists:

| Cockpit part | Already in `apps/ctower-ui` |
| --- | --- |
| Three-pane workspace shell | `src/app/conductor.css` — `grid-template-columns: 276px minmax(0, 1fr) 372px` at `min-width: 1100px` (`conductor.css:55–58`), collapsing to one route-chosen pane below that |
| Conversation list, transcript, composer, delivery state | `src/surfaces/chat/{ThreadList,Transcript,Composer,ThreadHead,NewThread,Delivery,LinkTicket}.tsx` |
| Work pane beside the conversation | `src/surfaces/chat/WorkPanel.tsx` |
| Live session pane under the work pane | `src/surfaces/chat/SessionPane.tsx`, `src/surfaces/terminal/{TerminalPane,LivePoll}.tsx` |
| File tree with `+N` badges | `src/surfaces/tree/TreePane.tsx` (`badge`, `badgeTone: "changed" \| "added"`) |
| File/Diff switch | `src/surfaces/explorer/FileDiffSwitch.tsx` |
| Crew rail, crew head, crew history | `src/surfaces/crew/{CrewRail,CrewHead,CrewCurrent,CrewHistory,marks}.tsx` |
| Worktree / git-tree / landed-change reads | `src/read/sources/{worktrees,gitTree,landedChanges,mergeHistory,tmuxBridge}.ts` |

`conductor.css` opens by naming the operator's north star in its own words — *"a list of
conversations on the left, the transcript in the middle with the composer under it, the work the
conversation is about on the right, and the live session under that"* — so the shell was already
built toward this target.

Three things are genuinely missing, and only one of them is UI work:

1. **The left rail is a conversation list, not a project→crew→workspace tree.** UI work.
2. **The fourth pane is a session view under the work panel, not a first-class tab strip.** UI work.
3. **The centre column is bound to an inbox thread, not to a crew session.** *Not* UI work. That
   binding is the harness-adapter seam's `spawn` / `liveness` / `collect` / `writeback`
   (CT-I1-041, CT-I1-042) plus the API operations §7 enumerates. The cockpit's plumbing and the
   harness-adapter epic's finish line are the same work. Nothing in this document asks for a
   second one.

One boundary fact that governs all of it: `apps/ctower-ui` is explicitly a non-product boundary —
its README's first line is *"This is **not** `apps/ctower-web`"* — an operator surface over a
running development instance, whose browser receives no API bearer, no session, and no credential
of any kind, because every read happens server-side. The cockpit lands there. It does not land on
`apps/ctower-web`, and §6.5 says why it may not arrive there by accretion.
