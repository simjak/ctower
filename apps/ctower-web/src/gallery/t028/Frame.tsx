import type { ReactElement, ReactNode } from "react";
import { Shell } from "../../shell/Shell";
import { ProjectSwitcher } from "../../shell/ProjectSwitcher";
import { AgentsRail } from "../../agents/AgentsRail";
import { PAYROLL } from "../stories";
import { COMPANY, HERE, PROJECTS } from "./fixtures";

/**
 * The real shell, around a screen that is not wired to anything.
 *
 * The rail, the company switcher, the staff section and the project dropdown
 * are the app's own components with fixture props — nothing here is a drawing
 * of them. So a mock board sits at the same width, under the same header,
 * beside the same navigation the operator will actually get, and a judgement
 * made about the mock holds for the screen.
 *
 * The rail is on **Board**, because that is where this screen is reached from.
 * Whether Board keeps a rail row of its own once the list carries a toggle to
 * it is a question for the operator, not one this bench answers quietly.
 */
export function Frame({ children }: { readonly children: ReactNode }): ReactElement {
  return (
    <Shell
      here="board"
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
      agents={
        <AgentsRail
          agents={PAYROLL}
          here={false}
          current={null}
          onOpen={(): void => undefined}
          onSeeAll={(): void => undefined}
        />
      }
    >
      {children}
    </Shell>
  );
}
