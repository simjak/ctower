import { useState } from "react";
import type { ReactElement } from "react";
import type { CompanyBundleExportResult } from "@ctower/client";
import { Button, Chip, Mono, PageHead } from "../ui/primitives";
import { shortDigest } from "../wizard/bundle";
import { Documents } from "./Documents";
import { projectDocuments, projectScopes } from "./read";
import { ScopeDetail } from "./ScopeDetail";
import { ScopeTable } from "./ScopeTable";
import { useBoards } from "./useBoards";

const PURPOSE = "What this company builds, and what each project owns.";

/**
 * Projects, read from the company that is already in hand.
 *
 * The portfolio costs no read: the active bundle answered before this screen
 * existed, and every project on it is a project some component declares itself
 * scoped to. What it does not carry is what is happening — so each project asks
 * its own board, and those answers arrive one at a time.
 *
 * Nothing here writes. Editing a project is the Company page's job, and a
 * control that cannot honour a press does not get drawn.
 */
export function ProjectsPage({
  result,
  onGoCompany,
}: {
  readonly result: CompanyBundleExportResult;
  /** The one place a project is authored, for the state where none is. */
  readonly onGoCompany: () => void;
}): ReactElement {
  const scopes = projectScopes(result.bundle);
  const documents = projectDocuments(result.bundle);
  const boards = useBoards(scopes.map((scope) => scope.key));
  const [chosen, setChosen] = useState<string | null>(null);
  const here = chosen ?? scopes[0]?.key ?? null;
  const open = scopes.find((scope) => scope.key === here);

  return (
    <>
      <PageHead title="Projects" subtitle={PURPOSE}>
        <Chip>version {result.active_version}</Chip>
        <Mono className="text-muted" title={result.bundle_digest}>
          {shortDigest(result.bundle_digest)}
        </Mono>
      </PageHead>

      {scopes.length === 0 ? (
        <Nothing onGoCompany={onGoCompany} />
      ) : (
        <>
          <ScopeTable scopes={scopes} boards={boards} here={here} onGo={setChosen} />
          {open === undefined ? null : (
            <ScopeDetail scope={open} board={boards.get(open.key) ?? { kind: "asking" }} />
          )}
        </>
      )}

      {documents.length === 0 ? null : <Documents documents={documents} />}
    </>
  );
}

/**
 * A company with no project scope at all. It is a real state and not a broken
 * one: this tower has components and none of them belongs to a project.
 */
function Nothing({ onGoCompany }: { readonly onGoCompany: () => void }): ReactElement {
  return (
    <div className="rounded-md border border-line bg-raised p-4">
      <p className="m-0 text-sm text-fg">Nothing in this company is scoped to a project yet.</p>
      <Button variant="primary" className="mt-3" onClick={onGoCompany}>
        Open Company
      </Button>
    </div>
  );
}
