import type { ReactElement } from "react";
import { Hint } from "../ui/form";
import { Card, CardBody, CardHeader, CardTitle, Chip } from "../ui/primitives";

/**
 * Workspaces, and the honest state of them.
 *
 * `DESIGN.md`: what is unbuilt renders honestly and never pretends. There is no
 * workspace UI on this screen because there is nothing behind one — the
 * authored contract declares no operation that creates, lists, mounts or closes
 * a workspace, and a screen with buttons that reach nothing is exactly the
 * pretending that rule forbids.
 *
 * So this panel reads nothing and shows nothing but its own state. An earlier
 * version listed the `workspace` components a company happens to declare; that
 * is a real fact of the record, but a list of workspaces on a Workspaces screen
 * reads as the built thing, and whether that declaration belongs on this screen
 * at all is a ticket's ruling and not this lane's. The finding is recorded
 * where a ruling can be made; the screen stays unbuilt until there is one.
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
  return (
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
  );
}
