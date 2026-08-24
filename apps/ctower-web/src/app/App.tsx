import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";
import { AdminPage } from "../admin/AdminPage";
import { AgentsPage } from "../agents/AgentsPage";
import { AgentsRail } from "../agents/AgentsRail";
import { agentsIn } from "../agents/read";
import type { AgentFacts } from "../agents/read";
import { sessionToken, SESSION_REFUSED_EVENT } from "../api/session";
import { Admission } from "./Admission";
import { BoardPage } from "../board/BoardPage";
import { FirstRun } from "../firstrun/FirstRun";
import { HarnessPage } from "../harness/HarnessPage";
import { Overlay } from "../firstrun/Overlay";
import { InboxPage } from "../inbox/InboxPage";
import { ProjectsPage } from "../projects/ProjectsPage";
import { RequestsPage } from "../requests/RequestsPage";
import { Shell } from "../shell/Shell";
import { addressFor, destinationFromSearch, projectFromSearch } from "../shell/destinations";
import type { DestinationKey } from "../shell/destinations";
import type { Org } from "../shell/OrgSwitcher";
import { ProjectSwitcher, projectChoices, useCurrentProject } from "../shell/ProjectSwitcher";
import type { ProjectChoice } from "../shell/ProjectSwitcher";
import { TicketsPage } from "../tickets/TicketsPage";
import { TooltipScope } from "../ui/form";
import { Chip } from "../ui/primitives";
import { Cockpit } from "../cockpit/Cockpit";
import { CompanyPage } from "../wizard/CompanyPage";
import { WorkflowsPage } from "../workflows/WorkflowsPage";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import { useSeed } from "../wizard/useSeed";
import type { Seed } from "../wizard/useSeed";
import { previewFromLocation, seedForPreview } from "./preview";

/**
 * One app, and one decision made here: whether this tower has a company yet.
 *
 * The company is read once, at the top, so the shell and the page cannot
 * disagree about which of the two situations this is. Until that read answers,
 * neither is claimed — the rail says it is still looking rather than going grey
 * as though the answer were "nothing".
 *
 * With no company there is no shell to show. Every destination would be locked,
 * and a rail full of unreachable things is noise at the one moment the operator
 * should be answering a single question, so the wizard takes the whole screen.
 *
 * With a company there are built destinations, and which one is drawn is the
 * address: `?at=…` is where the operator is, so a screen is a link, a reload
 * comes back to it and Back means back. There is still no router — the map in
 * `destinations.ts` is the only map, and this reads the address against it
 * rather than keeping a second copy of it.
 */
export function App(): ReactElement {
  const [admitted, setAdmitted] = useState(sessionToken() !== null);
  const [reloadKey, setReloadKey] = useState(0);
  // The read and the gate share one fact: until the server admits this tab,
  // asking for the company would only collect the gate's own refusals, so the
  // hook holds its ask until admission arrives.
  const real = useSeed(reloadKey, admitted);
  const preview = previewFromLocation(window.location.search);
  const previewing = preview !== null;
  const seed = seedForPreview(preview, real);
  // The address is where the operator is, so a screen is a link and a reload
  // comes back to it. It only ever names a destination that is actually built.
  const [here, setHere] = useState<DestinationKey>(
    () => destinationFromSearch(window.location.search) ?? "company"
  );
  const projects = projectsOf(seed);
  const { current, choose } = useCurrentProject(projects);
  // Whether the operator is making one of the things a company has — a project
  // or an agent. The pop-up is a moment, not a place, so it lives here rather
  // than in the address, and the screen it is open on is the one being looked
  // at: moving to another screen closes it rather than carrying it there.
  const [creating, setCreating] = useState(false);
  // Which project the Projects screen has open, if it has one. Entering a card
  // is a place — `?at=projects&project=…` reopens that project's own screen —
  // so it is the address that says so, and the rail's own Projects always
  // means the whole list.
  const [opened, setOpened] = useState<string | null>(() => openedIn(window.location.search));
  // Which agent the Agents screen has open, if it has one — named from the
  // rail or opened from the list, both the same place. Same rule as a project's
  // own screen: opening one is a place, so the address says so and a reload
  // comes back to it, while the rail's own "See all agents" means the list.
  const [agent, setAgent] = useState<string | null>(() => agentIn(window.location.search));
  const project = current?.key ?? null;

  const created = useCallback((): void => {
    setReloadKey((count) => count + 1);
  }, []);

  const go = useCallback(
    (key: DestinationKey, place: Readonly<Record<string, string>> = {}): void => {
      window.history.pushState(null, "", addressFor(key, project, place));
      setHere(key);
      setOpened(null);
      setAgent(place.agent ?? null);
      // A pop-up is a moment, not a place. Two screens now share this one flag,
      // so leaving the screen that opened it has to close it — otherwise the
      // pop-up that makes an agent reopens as the one that makes a project.
      // `createProject` sets it after this runs, so its own way in still works.
      setCreating(false);
    },
    [project]
  );

  // Entering a project scopes every project screen to it, which is what
  // entering it is for.
  const enterProject = useCallback(
    (key: string): void => {
      choose(key);
      setOpened(key);
      window.history.pushState(null, "", `?at=projects&project=${encodeURIComponent(key)}`);
    },
    [choose]
  );

  // Making a project is one act with two ways in — the rail's own "New
  // project…" and the Company page's Projects card — and both are this. A
  // second handler is how two entry points to one act start disagreeing about
  // where it happens.
  const createProject = useCallback((): void => {
    go("projects");
    setCreating(true);
  }, [go]);

  // Switching the project moves the whole project workspace at once, and it
  // moves the address with it, so the screen someone is sent is the screen they
  // open. It is a step in history rather than a replacement: Back goes back to
  // the project the operator was on.
  const chooseProject = useCallback(
    (key: string): void => {
      choose(key);
      window.history.pushState(null, "", addressFor(here, key));
    },
    [choose, here]
  );

  // Back and Forward move the shell, not just the page inside it, so the
  // address and what is drawn cannot disagree about where the operator is. The
  // project moves with it: it is half of where the operator is, and a Back that
  // restored the destination while leaving the rail on another project would
  // draw a screen the address does not describe.
  useEffect((): (() => void) => {
    const walked = (): void => {
      const search = window.location.search;
      setHere(destinationFromSearch(search) ?? "company");
      setOpened(openedIn(search));
      setAgent(agentIn(search));
      const asked = projectFromSearch(search);
      if (asked !== null) {
        choose(asked);
      }
    };
    window.addEventListener("popstate", walked);
    return (): void => {
      window.removeEventListener("popstate", walked);
    };
  }, [choose]);

  // A restarted server mints a new token, so the one this tab holds stops
  // working mid-session. The chokepoint drops it and says so; the gate comes
  // back rather than every screen quietly failing to read.
  useEffect((): (() => void) => {
    const refused = (): void => {
      setAdmitted(false);
    };
    window.addEventListener(SESSION_REFUSED_EVENT, refused);
    return (): void => {
      window.removeEventListener(SESSION_REFUSED_EVENT, refused);
    };
  }, []);

  if (!admitted) {
    return (
      <Admission
        onAdmitted={(): void => {
          setAdmitted(true);
          setReloadKey((count) => count + 1);
        }}
      />
    );
  }

  if (seed.kind === "answered" && seed.value.kind === "template") {
    return (
      <TooltipScope>
        <Overlay
          previewing={previewing}
          onClose={(): void => {
            window.location.assign(window.location.pathname);
          }}
        >
          <FirstRun onCreated={created} previewing={previewing} />
        </Overlay>
      </TooltipScope>
    );
  }

  return (
    <TooltipScope>
      <Shell
        here={here}
        lockReason={seed.kind === "answered" ? null : "Still reading this company"}
        onGo={go}
        org={orgOf(seed)}
        project={
          <ProjectSwitcher
            projects={projects}
            current={current}
            onChoose={chooseProject}
            // One place makes a project: the Projects screen, in a pop-up over
            // its list. This is the way to it rather than a second form in the
            // rail, and it travels the way the rail does.
            onAdd={createProject}
          />
        }
        agents={
          <AgentsRail
            agents={agentsOf(seed)}
            here={here === "agents"}
            current={agent}
            onOpen={(key): void => {
              go("agents", { agent: key });
            }}
            onSeeAll={(): void => {
              go("agents");
            }}
          />
        }
        status={statusFor(seed.kind, previewing)}
        fill={here === "crews"}
      >
        {seed.kind === "asking" ? <Asking what="Reading this company" /> : null}
        {seed.kind === "refused" ? (
          <Refused problem={seed.problem} action="Nothing was read. Reload to ask again." />
        ) : null}
        {seed.kind === "unreachable" ? (
          <Unreachable
            detail={seed.detail}
            action="This is not an empty tower; it is a tower that was not read. Reload to ask again."
          />
        ) : null}
        {seed.kind === "malformed" ? <Malformed detail={seed.detail} /> : null}
        {seed.kind === "answered" && seed.value.kind === "exported" ? (
          <Here
            here={here}
            seed={seed.value}
            project={project}
            agent={agent}
            opened={opened}
            creating={creating}
            onCreating={setCreating}
            onCreateProject={createProject}
            onEnter={enterProject}
            onApplied={created}
            onGo={go}
          />
        ) : null}
      </Shell>
    </TooltipScope>
  );
}

/**
 * The screen the rail is pointing at.
 *
 * Every destination is named, and the unbuilt ones are named together: the rail
 * refuses to move to one, so their branch is unreachable and says so instead of
 * standing in for a page the operator did not ask for. Naming them costs a line
 * and buys the guarantee that a destination cannot become built without this
 * file being made to say which screen it is.
 *
 * Every built destination reads the same company the shell already holds, so
 * none of them re-asks for it and none can disagree with the rail about which
 * tower this is. The rail only offers a destination it has marked built, so an
 * unbuilt key never actually arrives here; naming one costs a line and keeps
 * the guarantee that this file has to say which screen a destination is before
 * the rail can call it built.
 *
 * A project workspace screen carries the project as its React key. Each one
 * opens on the project the address names and then keeps its own place inside
 * it — which ticket is open, which priority is filtered — and that place means
 * nothing under a different project. Re-keying retires the old screen instead
 * of handing a second project a first project's state.
 */
function Here({
  here,
  seed,
  project,
  agent,
  opened,
  creating,
  onCreating,
  onCreateProject,
  onEnter,
  onApplied,
  onGo,
}: {
  readonly here: DestinationKey;
  readonly seed: Extract<Seed, { readonly kind: "exported" }>;
  /** The project the rail's switcher is pointed at, when this company has one. */
  readonly project: string | null;
  /** The agent the Agents screen has open, when the rail or the list named one. */
  readonly agent: string | null;
  /** The project the Projects screen has open, when it has one. */
  readonly opened: string | null;
  /** Whether a screen is showing the pop-up that makes a project or an agent. */
  readonly creating: boolean;
  readonly onCreating: (creating: boolean) => void;
  readonly onEnter: (key: string) => void;
  readonly onApplied: () => void;
  /** Where a screen sends the operator when the thing it needs is elsewhere. */
  readonly onGo: (key: DestinationKey, place?: Readonly<Record<string, string>>) => void;
  /** The one act that makes a project, shared with the rail's own way to it. */
  readonly onCreateProject: () => void;
}): ReactElement {
  switch (here) {
    case "requests":
      return <RequestsPage key={project} />;
    case "inbox":
      return <InboxPage />;
    case "crews":
      return <Cockpit document={seed.result.bundle} />;
    case "tickets":
      return <TicketsPage key={project} document={seed.result.bundle} />;
    case "board":
      return <BoardPage key={project} projectKey={project} onGoProjects={onGo} />;
    case "workflows":
      return <WorkflowsPage key={project} seed={seed.result} onApplied={onApplied} />;
    case "projects":
      return (
        <ProjectsPage
          result={seed.result}
          opened={opened}
          creating={creating}
          onCreating={onCreating}
          onEnter={onEnter}
          onApplied={onApplied}
          onGo={onGo}
        />
      );
    case "agents":
      return (
        <AgentsPage
          result={seed.result}
          opened={agent}
          creating={creating}
          onCreating={onCreating}
          // Opening an agent from the list is the same act as naming one in the
          // rail, so it is the same address rather than a second handler that
          // would eventually disagree with it about where an agent lives.
          onOpen={(key): void => {
            onGo("agents", { agent: key });
          }}
          onBack={(): void => {
            onGo("agents");
          }}
          onApplied={onApplied}
        />
      );
    case "admin":
      return <AdminPage />;
    case "company":
      return <CompanyPage seed={seed} onApplied={onApplied} onCreateProject={onCreateProject} />;
    case "harnesses":
      return <HarnessPage recorded={seed.result.bundle} onApplied={onApplied} />;
    case "lanes":
      return <p className="m-0 py-6 text-sm text-muted">Not built yet.</p>;
  }
}

/**
 * What the header says about the tower, and only what is known.
 *
 * A page snapshot caught this claiming "first run" while the read was still
 * out: locked and first-run are different facts, and one was being inferred
 * from the other.
 */
/** The company, once the read has actually produced one. */
function orgOf(seed: ReturnType<typeof seedForPreview>): Org | null {
  if (seed.kind !== "answered" || seed.value.kind !== "exported") {
    return null;
  }
  const company = seed.value.result.bundle.company;
  return { name: company.display_name, key: company.key };
}

/**
 * The project the Projects screen has open, read out of the address. Only that
 * screen carries one: everywhere else `project` is which project the workspace
 * is about, not which project's own screen is being looked at.
 */
function openedIn(search: string): string | null {
  return destinationFromSearch(search) === "projects" ? projectFromSearch(search) : null;
}

/**
 * The agent the Agents screen has open, read out of the address. Only that
 * screen carries one, and only when it is the screen being looked at;
 * everywhere else the key would name nothing.
 */
function agentIn(search: string): string | null {
  if (destinationFromSearch(search) !== "agents") {
    return null;
  }
  const asked = new URLSearchParams(search).get("agent");
  return asked === null || asked === "" ? null : asked;
}

/** The agents that company records, once the read has produced them. */
function agentsOf(seed: ReturnType<typeof seedForPreview>): readonly AgentFacts[] {
  if (seed.kind !== "answered" || seed.value.kind !== "exported") {
    return [];
  }
  return agentsIn(seed.value.result.bundle);
}

/** The projects that company records, once the read has produced them. */
function projectsOf(seed: ReturnType<typeof seedForPreview>): readonly ProjectChoice[] {
  if (seed.kind !== "answered" || seed.value.kind !== "exported") {
    return [];
  }
  return projectChoices(seed.value.result.bundle);
}

function statusFor(kind: string, previewing: boolean): ReactElement | null {
  return (
    <>
      {previewing ? <Chip tone="amber">preview</Chip> : null}
      {kind === "answered" ? null : <Chip>reading</Chip>}
    </>
  );
}
