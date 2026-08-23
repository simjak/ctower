import { useCallback, useState } from "react";
import type { ReactElement } from "react";
import type { CompanyBundleDocument, CompanyBundleResource } from "@ctower/client";
import { cn } from "../ui/cn";
import { Button, Card, CardBody, CardHeader, CardTitle, Chip, Mono } from "../ui/primitives";
import { shortDigest } from "../wizard/bundle";
import { ReviewPanel } from "../wizard/review/ReviewPanel";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import { useSeed } from "../wizard/useSeed";
import { FileEditor } from "./files/FileEditor";
import { fileResources, idOf, nameOf } from "./files/read";
import { useAgentFiles } from "./files/useAgentFiles";

/**
 * The agent's files.
 *
 * A persona, a skill and a tool are what an agent is made of, and all three are
 * components of the company definition — there is no filesystem-file operation
 * in the authored contract and this screen does not invent one. So editing a
 * file is editing the company: the same check, the same plan, the same command
 * under the operator's own authority, and the registry recomputes the digest
 * that pins the result.
 *
 * This panel reads the company itself, so an accepted apply has to be announced
 * twice: once here, and once to whatever page is holding this panel. A host
 * that read the bundle to build its own screen is now a version behind — the
 * operator's own edit is what made it stale — and a neighbouring tab authoring
 * from that document proposes against a superseded version and is refused. So
 * `onApplied` is called on acceptance and only on acceptance. A host with
 * nothing to re-read may omit it; this panel still refreshes itself.
 */
export function FilesPanel({
  onApplied,
}: {
  /** An accepted apply changed what is recorded; a host that reads should re-read. */
  readonly onApplied?: () => void;
}): ReactElement {
  const [reloadKey, setReloadKey] = useState(0);
  const seed = useSeed(reloadKey);
  const reread = useCallback((): void => {
    setReloadKey((count) => count + 1);
    onApplied?.();
  }, [onApplied]);

  switch (seed.kind) {
    case "asking":
      return <Asking what="Reading this company" />;
    case "refused":
      return <Refused problem={seed.problem} action="Nothing was read. Reload to ask again." />;
    case "unreachable":
      return (
        <Unreachable
          detail={seed.detail}
          action="This is not a company without files; it is a company that was not read."
        />
      );
    case "malformed":
      return <Malformed detail={seed.detail} />;
    case "answered":
      return seed.value.kind === "template" ? (
        <Empty what="This tower has no company yet, so there is nothing to edit." />
      ) : (
        <Files document={seed.value.result.bundle} onApplied={reread} />
      );
  }
}

function Files({
  document,
  onApplied,
}: {
  readonly document: CompanyBundleDocument;
  readonly onApplied: () => void;
}): ReactElement {
  const files = useAgentFiles(document, fileResources(document), onApplied);

  if (files.mode === "review") {
    return (
      <ReviewPanel
        review={files.review}
        applied={files.applied}
        armed={files.armed}
        onArm={files.setArmed}
        onApply={files.apply}
        onRetry={files.retry}
        onBack={files.closeReview}
        backLabel="Back to the file"
      />
    );
  }

  if (files.files.length === 0) {
    return <Empty what="This company declares no agent files yet." />;
  }

  return (
    <div className="space-y-4">
      <p className="m-0 text-sm text-muted">
        A persona, a skill and a tool are the files an agent is made of.
      </p>
      <div className="grid gap-4 md:grid-cols-[300px_minmax(0,1fr)]">
        <FileList files={files.files} openId={files.openId} onOpen={files.open} />
        {files.draft === null ? (
          <Card>
            <CardBody>
              <p className="m-0 text-sm text-muted">Choose a file to read or edit it.</p>
            </CardBody>
          </Card>
        ) : (
          <div className="space-y-4">
            <FileEditor document={document} draft={files.draft} onDraft={files.setDraft} />
            {files.edited ? (
              <footer className="flex items-center gap-2 border-t border-line pt-4">
                <span className="flex-1" />
                <Button variant="primary" onClick={files.openReview}>
                  Review changes →
                </Button>
              </footer>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * The files, each carrying the two facts that pin it: the revision it is at and
 * the digest of its bytes. Neither carries a mark — a file has no execution
 * fact of its own, and borrowing a neighbour's glyph is how a thing that was
 * never run gets drawn as a thing that ran.
 */
function FileList({
  files,
  openId,
  onOpen,
}: {
  readonly files: readonly CompanyBundleResource[];
  readonly openId: string | null;
  readonly onOpen: (id: string) => void;
}): ReactElement {
  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle>Files</CardTitle>
        <span className="flex-1" />
        <Mono className="text-muted">{files.length}</Mono>
      </CardHeader>
      <CardBody className="p-1.5">
        {files.map((resource) => {
          const id = idOf(resource.component);
          return (
            <button
              key={id}
              type="button"
              aria-current={id === openId}
              onClick={(): void => {
                onOpen(id);
              }}
              className={cn(
                "block w-full cursor-pointer rounded-sm border-l-2 px-2.5 py-2 text-left",
                id === openId ? "border-amber bg-raised" : "border-transparent hover:bg-raised"
              )}
            >
              <span className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-sm font-medium">
                  {nameOf(resource)}
                </span>
                <Chip>{resource.component.kind}</Chip>
              </span>
              <span className="mt-0.5 flex items-center gap-2">
                <Mono className="min-w-0 flex-1 truncate text-muted">{resource.component.key}</Mono>
                <Mono className="text-muted">r{resource.component.revision}</Mono>
              </span>
              <Mono
                className="mt-0.5 block truncate text-muted"
                title={resource.component.content_digest}
              >
                {shortDigest(resource.component.content_digest)}
              </Mono>
            </button>
          );
        })}
      </CardBody>
    </Card>
  );
}

function Empty({ what }: { readonly what: string }): ReactElement {
  return (
    <Card>
      <CardBody>
        <p className="m-0 text-sm text-muted">{what}</p>
      </CardBody>
    </Card>
  );
}
