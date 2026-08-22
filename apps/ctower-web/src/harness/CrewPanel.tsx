import { useCallback, useMemo, useState } from "react";
import type { ReactElement, ReactNode } from "react";
import { ArrowLeft, RotateCw } from "lucide-react";
import type { CompanyBundleDocument } from "@ctower/client";
import { Button } from "../ui/primitives";
import { crewPrefix, profilesOf } from "./crew/binding";
import { CrewReceipt } from "./crew/CrewReceipt";
import { CrewReview, ready } from "./crew/CrewReview";
import { DefineCrew } from "./crew/DefineCrew";
import { blankDraft, unmet } from "./crew/draft";
import { crewsOf, recordedProjects } from "./crew/roster";
import type { Minted, ProjectOption } from "./crew/roster";
import { Roster } from "./crew/Roster";
import { useCrewAct } from "./crew/useCrewAct";
import { useRevokeAct } from "./crew/useRevokeAct";

/**
 * Crew setup: defining a crew is one act.
 *
 * ctower keeps the two halves apart — the company bundle binds an agent profile
 * to a subject, `issueSeatCredential` mints the address that makes the subject
 * addressable — and an operator who has to perform both ceremonies separately
 * has to know that split exists. This screen is where they stop having to: one
 * roster, one form, one review, one confirmation.
 *
 * What the screen cannot do is report a roster of addresses, because the
 * authored contract has no operation that reads one. That gap is drawn rather
 * than filled: a crew this session did not mint for says its address was not
 * read, and no mark is borrowed to suggest otherwise.
 */
export function CrewPanel({
  recorded,
  onRecorded,
}: {
  /** The active bundle, exactly as `exportCompanyBundle` returned it. */
  readonly recorded: CompanyBundleDocument;
  /**
   * An accepted bundle apply changed what is recorded. A host that can re-read
   * should; one that cannot may omit this, and the roster then goes on showing
   * the definition this panel was handed until the page reads again.
   */
  readonly onRecorded?: () => void;
}): ReactElement {
  const bundle = recorded;
  const [minted, setMinted] = useState<readonly Minted[]>([]);
  const record = useCallback((entry: Minted): void => {
    setMinted((held) => [...held, entry]);
  }, []);

  const profiles = useMemo(() => profilesOf(bundle), [bundle]);
  const projects = useMemo(() => recordedProjects(bundle), [bundle]);
  const prefix = useMemo(() => crewPrefix(bundle), [bundle]);
  const crews = useMemo(() => crewsOf(bundle, minted), [bundle, minted]);
  const first = projects.find((project) => project.addressable);

  const act = useCrewAct(record, onRecorded, blankDraft(profiles[0]?.key ?? "", first?.key ?? ""));
  const revoke = useRevokeAct(record);
  const sending = act.sending;

  if (sending !== null && act.stage === "sent") {
    return (
      <>
        <CrewReceipt
          subject={sending.subject}
          moving={sending.binding !== null}
          bound={act.bound}
          address={act.address}
        />
        <Footer>
          <Button variant="quiet" onClick={act.back}>
            <ArrowLeft /> Define another crew
          </Button>
          <span className="flex-1" />
          {act.retry === null ? null : (
            <Button variant="primary" onClick={act.retry}>
              <RotateCw /> Send the same command again
            </Button>
          )}
        </Footer>
      </>
    );
  }

  if (sending !== null) {
    return (
      <>
        <CrewReview
          subject={sending.subject}
          binding={sending.binding}
          body={sending.body}
          armed={act.armed}
          onArm={act.setArmed}
        />
        <Footer>
          <Button variant="quiet" onClick={act.back}>
            <ArrowLeft /> Back to the definition
          </Button>
          <span className="flex-1" />
          <Button
            variant="primary"
            disabled={!act.armed || !ready(sending.binding)}
            onClick={act.run}
          >
            Define as operator
          </Button>
        </Footer>
      </>
    );
  }

  const blocked = unmet(act.draft);
  const missing = whatIsMissing(profiles.length, projects);
  const profile = profiles.find((option) => option.key === act.draft.profileKey);

  return (
    <div className="space-y-4">
      <Roster crews={crews} revoke={revoke} />
      {missing === null ? null : <p className="m-0 text-sm text-muted">{missing}</p>}
      <DefineCrew
        draft={act.draft}
        onDraft={act.setDraft}
        prefix={prefix}
        profiles={profiles}
        projects={projects}
      />
      <Footer>
        {blocked === null ? null : <span className="text-xs text-muted">{blocked}</span>}
        <span className="flex-1" />
        <Button
          variant="primary"
          disabled={blocked !== null || profile === undefined}
          onClick={(): void => {
            if (profile !== undefined) {
              act.openReview(bundle, profile, `${prefix}:${act.draft.name}`);
            }
          }}
        >
          Review this crew →
        </Button>
      </Footer>
    </div>
  );
}

/**
 * What this company would have to gain before a crew can be defined at all.
 *
 * Both halves can be missing at once, and saying only the first would send an
 * operator to fix one thing and meet the other on the way back. A company that
 * records projects none of which can carry an address is a third case, and it
 * is the record's own shape rather than something to fix here.
 */
function whatIsMissing(profiles: number, projects: readonly ProjectOption[]): string | null {
  const addressable = projects.some((project) => project.addressable);
  if (profiles === 0 && projects.length === 0) {
    return "A crew runs an agent profile and works in a project. This company records neither yet.";
  }
  if (profiles === 0) {
    return "No agent profile is recorded, and a crew runs one.";
  }
  if (projects.length === 0) {
    return "This company declares no project, and a crew works in one.";
  }
  return addressable
    ? null
    : "Every project here is declared under a key an address cannot carry: an address key has no dots.";
}

function Footer({ children }: { readonly children: ReactNode }): ReactElement {
  return (
    <footer className="mt-6 flex flex-wrap items-center gap-2 border-t border-line pt-4">
      {children}
    </footer>
  );
}
