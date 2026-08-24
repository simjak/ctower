import type { ReactElement, ReactNode } from "react";
import { Shell } from "../../shell/Shell";
import type { DestinationKey } from "../../shell/destinations";
import { ProjectSwitcher } from "../../shell/ProjectSwitcher";
import { COMPANY, HERE, PROJECTS } from "./fixtures";

/**
 * The real shell, around a screen that is not wired to anything.
 *
 * The rail, the company switcher and the project dropdown are the app's own
 * components with fixture props — nothing here is a drawing of them. So a mock
 * screen on this bench sits at the same width, under the same header, beside
 * the same navigation the operator will actually get, and a judgement made
 * about the mock holds for the screen.
 */
export function Frame({
  here,
  children,
}: {
  readonly here: DestinationKey;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <Shell
      here={here}
      lockReason={null}
      onGo={(): void => undefined}
      org={{ name: COMPANY, key: "manibo" }}
      project={
        <ProjectSwitcher
          projects={PROJECTS}
          current={HERE}
          onChoose={(): void => undefined}
          onAdd={(): void => undefined}
        />
      }
    >
      {children}
    </Shell>
  );
}
