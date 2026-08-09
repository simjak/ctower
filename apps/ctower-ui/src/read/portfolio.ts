import { httpRecordAdapter } from "./httpRecordAdapter";
import { portfolioOf } from "./portfolioProjection";
import { configuredProjects } from "./projects";
import type { PortfolioBoardRead } from "./portfolioProjection";
import type { Portfolio, Reading } from "./interface";

/**
 * The portfolio's reads: one board per configured project, and one inbox.
 *
 * Four requests, fixed. The board read here is the card-only one — the
 * portfolio counts cards and never shows a card's recorded source or age, so
 * paying for the per-card ticket join would be four hundred requests spent on
 * nothing the screen renders.
 *
 * The project list is `read/projects.ts` and nothing else, which is what makes
 * the issue's "a new project appears when its scope registers" true: a fourth
 * project is one entry there and no edit here or on the screen.
 *
 * Each read keeps its own failure. They are deliberately not raced into one
 * outcome: a portfolio where manibo did not answer is still a portfolio, and
 * the row that failed says so beside three that did.
 */
export async function readPortfolio(): Promise<Reading<Portfolio>> {
  const projects = configuredProjects();
  const boards: readonly PortfolioBoardRead[] = await Promise.all(
    projects.map(async (project): Promise<PortfolioBoardRead> => {
      return {
        key: project.key,
        boardHref: `/board?project=${encodeURIComponent(project.key)}`,
        board: await httpRecordAdapter.boardCards(project.key),
      };
    })
  );
  const inbox = await httpRecordAdapter.inbox();
  return {
    state: "present",
    value: portfolioOf(boards, inbox, new Date().toISOString()),
  };
}
