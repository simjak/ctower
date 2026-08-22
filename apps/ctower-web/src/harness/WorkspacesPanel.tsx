import type { ReactElement } from "react";
import type { CompanyBundleResource } from "@ctower/client";
import { Hint } from "../ui/form";
import { Card, CardBody, CardHeader, CardTitle, Chip, Mono } from "../ui/primitives";
import { useSeed } from "../wizard/useSeed";

/**
 * Workspaces, and the honest state of them.
 *
 * `DESIGN.md`: what is unbuilt renders honestly and never pretends. There is no
 * workspace UI on this screen because there is nothing behind one — the
 * authored contract declares no operation that creates, lists, mounts or closes
 * a workspace, and a screen with buttons that reach nothing is exactly the
 * pretending that rule forbids.
 *
 * What the contract *does* carry is a declaration: `workspace` is a component
 * kind, and its authored schema fixes `persistence` to `not_authoritative` and
 * `execution` to `not_exercised`. So a company can say which checkout an agent
 * would work in, and the record says in its own words that nothing has run
 * there. That declaration is shown, because a screen claiming the record holds
 * nothing would be its own kind of pretending.
 *
 * The one dependency is named rather than hidden: the runner owns creating,
 * mounting and cleaning up an agent's work directory, and the spawn record's
 * workspace reference stays empty until it does.
 */
const WAITING_ON =
  "Workspaces wait on the runner that creates and cleans up an agent's work directory.";

const CONTRACT_FACT =
  "The authored contract declares no operation that creates, lists, mounts or closes a workspace; " +
  "the runner's spawn record carries a workspace reference that stays empty until one exists.";

export function WorkspacesPanel(): ReactElement {
  const seed = useSeed(0);
  const declared =
    seed.kind === "answered" && seed.value.kind === "exported"
      ? seed.value.result.bundle.resources.filter(
          (resource) => resource.component.kind === "workspace"
        )
      : [];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Workspaces</CardTitle>
          <span className="flex-1" />
          <Hint text={CONTRACT_FACT} />
          <Chip>not built</Chip>
        </CardHeader>
        <CardBody>
          <p className="m-0 text-sm text-muted">{WAITING_ON}</p>
        </CardBody>
      </Card>

      {declared.length === 0 ? null : (
        <Card>
          <CardHeader>
            <CardTitle>Declared today</CardTitle>
            <span className="flex-1" />
            <Mono className="text-muted">{declared.length}</Mono>
          </CardHeader>
          <CardBody className="space-y-2">
            {declared.map((resource) => (
              <DeclaredRow key={resource.component.key} resource={resource} />
            ))}
          </CardBody>
        </Card>
      )}
    </div>
  );
}

/**
 * One declared workspace, in the record's own words. No mark: `not_exercised`
 * is what the payload says, and saying it is more honest than choosing a glyph
 * for it.
 */
function DeclaredRow({ resource }: { readonly resource: CompanyBundleResource }): ReactElement {
  return (
    <div className="flex items-center gap-3">
      <Mono className="min-w-0 flex-1 truncate">{resource.component.key}</Mono>
      {["mode", "persistence", "execution"].map((field) => (
        <Mono key={field} className="text-muted" title={field}>
          {word(resource.payload[field])}
        </Mono>
      ))}
    </div>
  );
}

function word(value: unknown): string {
  return typeof value === "string" ? value : "—";
}
