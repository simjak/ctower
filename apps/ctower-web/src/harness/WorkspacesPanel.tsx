import type { ReactElement } from "react";
import type { CompanyBundleDocument, CompanyBundleResource } from "@ctower/client";
import { Hint } from "../ui/form";
import { Card, CardBody, CardHeader, CardTitle, Chip, Mono } from "../ui/primitives";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import { useSeed } from "../wizard/useSeed";

/**
 * Workspaces: what this company declares, and what nothing can do with them yet.
 *
 * `workspace` is a declared component kind with its own authored schema
 * (`contracts/components/workspace.schema.json`), so a company can say which
 * checkout an agent would work in. That declaration is real and this screen
 * shows it.
 *
 * What does not exist is any operation that manages one. Nothing in the
 * authored contract creates, edits, or spawns against a workspace, and the
 * runner binding that would consume one is phase-gated behind CT-I2-013. So
 * this screen carries no control: not a disabled button, not a greyed-out
 * field. A control that reaches nothing is the pretending `DESIGN.md` forbids,
 * and a disabled one is the same claim in a quieter voice — it says the action
 * exists and is merely unavailable. The limit is said in words instead.
 *
 * Every column is the payload's own word. `execution` reads `not_exercised`,
 * which is why no row carries a mark: nothing has run here, and borrowing a
 * neighbour's glyph is how a thing that never ran gets drawn as a thing that did.
 */
const CANNOT =
  "Declared only. Nothing creates, edits or spawns against a workspace yet — that waits on CT-I2-013.";

const CONTRACT_FACT =
  "The authored contract declares the workspace component and no operation that manages one; " +
  "the runner spawn binding that resolves a workspace is CT-I2-013, which is phase-gated.";

const COLUMNS = ["mode", "persistence", "execution"] as const;

export function WorkspacesPanel(): ReactElement {
  const seed = useSeed(0);

  switch (seed.kind) {
    case "asking":
      return <Asking what="Reading this company" />;
    case "refused":
      return <Refused problem={seed.problem} action="Nothing was read. Reload to ask again." />;
    case "unreachable":
      return (
        <Unreachable
          detail={seed.detail}
          action="This is not a company without workspaces; it is a company that was not read."
        />
      );
    case "malformed":
      return <Malformed detail={seed.detail} />;
    case "answered":
      return (
        <Workspaces
          declared={
            seed.value.kind === "exported" ? workspacesIn(seed.value.result.bundle) : undefined
          }
        />
      );
  }
}

function workspacesIn(document: CompanyBundleDocument): readonly CompanyBundleResource[] {
  return document.resources
    .filter((resource) => resource.component.kind === "workspace")
    .toSorted((left, right) => left.component.key.localeCompare(right.component.key));
}

/**
 * The declared set, or the honest reason there is none. A tower with no company
 * and a company with no workspace are different facts and say so differently;
 * neither is drawn as an empty table, which would claim a list was read.
 */
function Workspaces({
  declared,
}: {
  readonly declared: readonly CompanyBundleResource[] | undefined;
}): ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Workspaces</CardTitle>
        <span className="flex-1" />
        <Hint text={CONTRACT_FACT} />
        {declared === undefined || declared.length === 0 ? null : (
          <Mono className="text-muted">{declared.length}</Mono>
        )}
        <Chip>read only</Chip>
      </CardHeader>
      <CardBody className="space-y-4">
        <p className="m-0 text-sm text-muted">{CANNOT}</p>
        <DeclaredOrWhyNot declared={declared} />
      </CardBody>
    </Card>
  );
}

function DeclaredOrWhyNot({
  declared,
}: {
  readonly declared: readonly CompanyBundleResource[] | undefined;
}): ReactElement {
  if (declared === undefined) {
    return (
      <p className="m-0 text-sm text-muted">
        This tower has no company yet, so nothing declares a workspace.
      </p>
    );
  }
  if (declared.length === 0) {
    return <p className="m-0 text-sm text-muted">This company declares no workspace.</p>;
  }
  return <Declared rows={declared} />;
}

/** One row per declaration, in the record's own words and nothing added. */
function Declared({ rows }: { readonly rows: readonly CompanyBundleResource[] }): ReactElement {
  return (
    <table className="w-full border-collapse text-[13.5px]">
      <thead>
        <tr className="text-left text-xs text-muted">
          <th className="pb-1 font-medium">Key</th>
          {COLUMNS.map((column) => (
            <th key={column} className="pb-1 font-medium">
              {column}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((resource) => (
          <tr key={resource.component.key} className="border-t border-line">
            <td className="py-2 pr-4">
              <Mono>{resource.component.key}</Mono>
            </td>
            {COLUMNS.map((column) => (
              <td key={column} className="py-2 pr-4">
                <Mono className="text-muted">{word(resource.payload[column])}</Mono>
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function word(value: unknown): string {
  return typeof value === "string" ? value : "—";
}
