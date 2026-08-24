import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";
import { AdminPage } from "../admin/AdminPage";
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
import { destinationFromSearch } from "../shell/destinations";
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

  const created = useCallback((): void => {
    setReloadKey((count) => count + 1);
  }, []);

  const go = useCallback((key: DestinationKey): void => {
    window.history.pushState(null, "", `?at=${key}`);
    setHere(key);
  }, []);

  // Back and Forward move the shell, not just the page inside it, so the
  // address and what is drawn cannot disagree about where the operator is.
  useEffect((): (() => void) => {
    const walked = (): void => {
      setHere(destinationFromSearch(window.location.search) ?? "company");
    };
    window.addEventListener("popstate", walked);
    return (): void => {
      window.removeEventListener("popstate", walked);
    };
  }, []);

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
            onChoose={choose}
            // A project is made on the harness screen, and that screen opens on
            // its Projects tab. One place authors a project, and this is the
            // way to it rather than a second form in the rail. It travels the
            // way the rail does, so the address says where the operator went.
            onAdd={(): void => {
              go("harnesses");
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
            project={current?.key ?? null}
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
 */
function Here({
  here,
  seed,
  project,
  onApplied,
  onGo,
}: {
  readonly here: DestinationKey;
  readonly seed: Extract<Seed, { readonly kind: "exported" }>;
  /** The project key the rail's switcher is pointed at, when this company has one. */
  readonly project: string | null;
  readonly onApplied: () => void;
  /** Projects and Company send the operator to the screens they point at. */
  readonly onGo: (key: DestinationKey) => void;
}): ReactElement {
  switch (here) {
    case "requests":
      return <RequestsPage />;
    case "inbox":
      return <InboxPage />;
    case "crews":
      return <Cockpit document={seed.result.bundle} />;
    case "tickets":
      return <TicketsPage document={seed.result.bundle} />;
    case "board":
      return <BoardPage company={seed.result.bundle} />;
    case "workflows":
      return <WorkflowsPage seed={seed.result} onApplied={onApplied} />;
    case "projects":
      return (
        <ProjectsPage
          result={seed.result}
          onGoCompany={(): void => {
            onGo("company");
          }}
        />
      );
    case "admin":
      return <AdminPage />;
    case "company":
      return (
        <CompanyPage
          seed={seed}
          onApplied={onApplied}
          // The rail's Add and the Projects card's Create go the same way,
          // because there is one screen that authors a project and this is it.
          onCreateProject={(): void => {
            onGo("harnesses");
          }}
        />
      );
    case "harnesses":
      return <HarnessPage recorded={seed.result.bundle} project={project} onApplied={onApplied} />;
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
