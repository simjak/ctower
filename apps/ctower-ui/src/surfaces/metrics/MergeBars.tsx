import type { ReactElement } from "react";
import type { ProjectMerges } from "@/read/interface";

/**
 * Merges per day, as the approved stacked bars.
 *
 * Every height is a count the git history returned; nothing is smoothed,
 * estimated or extrapolated. Today's column is marked `now` because the day is
 * still running — it is "13 so far", not a finished 13, and the mockup makes
 * that distinction on purpose.
 */

const SERIES: Readonly<Record<string, string>> = {
  ctower: "s-ct",
  manibo: "s-mb",
  bhloop: "s-bh",
};

function heightOf(count: number, ceiling: number): string {
  return ceiling === 0 ? "0%" : `${((count / ceiling) * 100).toFixed(1)}%`;
}

export function MergeBars({
  projects,
  days,
}: {
  readonly projects: readonly ProjectMerges[];
  readonly days: readonly string[];
}): ReactElement {
  const totals = days.map((day) =>
    projects.reduce(
      (sum, project) => sum + (project.days.find((entry) => entry.day === day)?.count ?? 0),
      0
    )
  );
  const ceiling = Math.max(1, ...totals);
  const landed = projects.reduce((sum, project) => sum + project.landed, 0);
  const mean = days.length === 0 ? 0 : Math.round(landed / days.length);
  const today = days.at(-1);

  return (
    <>
      <div className="mtbarwrap">
        <div className="mtbars">
          {days.map((day, index) => (
            <div className={day === today ? "mtcol now" : "mtcol"} key={day}>
              <div
                className="mtbar"
                style={{ height: heightOf(totals[index] ?? 0, ceiling) }}
                title={`${day}: ${(totals[index] ?? 0).toString()} changes`}
              >
                {projects.map((project) => {
                  const count = project.days.find((entry) => entry.day === day)?.count ?? 0;
                  const share = totals[index] === 0 ? 0 : (count / (totals[index] ?? 1)) * 100;
                  return count === 0 ? null : (
                    <span
                      className={SERIES[project.key] ?? "s-ct"}
                      key={project.key}
                      style={{ height: `${share.toFixed(1)}%` }}
                    />
                  );
                })}
              </div>
            </div>
          ))}
        </div>
        <div className="mtmean">
          <b>mean {mean.toString()}</b>
        </div>
      </div>
      <div className="mtxb">
        {days.map((day) => (
          <div className={day === today ? "now" : undefined} key={day}>
            <span className="c">
              {projects
                .reduce(
                  (sum, project) =>
                    sum + (project.days.find((entry) => entry.day === day)?.count ?? 0),
                  0
                )
                .toString()}
            </span>
            {day === today ? "today" : day.slice(5)}
          </div>
        ))}
      </div>
      <div className="legend">
        {projects.map((project) => (
          <span key={project.key}>
            <i style={{ background: `var(--p-${project.key})` }} />
            {project.label} {project.landed.toString()}
          </span>
        ))}
      </div>
      <div className="mtnote">
        {landed.toString()} changes reached a trunk in {days.length.toString()} days, one per
        first-parent entry. Today&rsquo;s column is still running — it is the count <b>so far</b>,
        not a finished day.
      </div>
    </>
  );
}
