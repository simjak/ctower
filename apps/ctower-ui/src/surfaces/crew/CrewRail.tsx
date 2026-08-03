import type { ReactElement } from "react";
import { KnownValue } from "@/frame/Declared";
import type { Accountability, CrewProfile, DeliveredChange, LadderStep } from "@/read/interface";
import { mapKnown } from "@/read/sources/maybe";

/**
 * The rail: where this crew works, what it delivered, what it is trusted with,
 * and what its work cost.
 *
 * Three of the four are read. The fourth is not recorded at all, and that panel
 * says so on its face and names the work that would record it — an invented
 * cost is the one number an operator would believe without checking.
 */

const VERDICT_TONE = {
  landed: "verdict v-pass",
  "not-on-trunk": "verdict v-filed",
  unchecked: "verdict v-changes",
} as const;

export function CrewWhere({ profile }: { readonly profile: CrewProfile }): ReactElement {
  return (
    <section className="panel">
      <header>
        <h2>Where it works</h2>
      </header>
      <ul className="links">
        <li>
          <span className="k">Session</span>
          <span className="v mono">{profile.sessionName}</span>
        </li>
        <li>
          <span className="k">Worktree</span>
          <span className="v mono">
            <KnownValue value={profile.worktree} />
          </span>
        </li>
        <li>
          <span className="k">Branch</span>
          <span className="v mono">
            <KnownValue value={profile.branch} />
          </span>
        </li>
        <li>
          <span className="k">Head</span>
          <span className="v mono">
            <KnownValue value={profile.head} />
          </span>
        </li>
        <li>
          <span className="k">Subject</span>
          <span className="v">
            <KnownValue value={profile.headSubject} />
          </span>
        </li>
        <li>
          <span className="k">Spawned</span>
          <span className="v mono">
            <KnownValue value={profile.spawnedAt} />
          </span>
        </li>
      </ul>
      <div className="src-line">
        <span>
          src: the session listing and its pane&rsquo;s working directory, then git read in that
          directory
        </span>
        <span>
          the worktree is where the pane is standing now, not where the crew was dispatched to —
          nothing records the second
        </span>
      </div>
    </section>
  );
}

function Change({
  change,
  spellOut,
}: {
  readonly change: DeliveredChange;
  /** The design audit's say-it-once rule: the first offending row explains. */
  readonly spellOut: boolean;
}): ReactElement {
  return (
    <li className="pr">
      <span className="k">{change.reference}</span>
      <span className="v">
        <KnownValue value={change.detail} />
      </span>
      <span className="meta">
        <span className={VERDICT_TONE[change.verdict]}>{change.verdictLabel}</span>
        <span>cited in {change.citedIn}</span>
        <span
          title={
            change.projectFromCrew
              ? "the record that named this change is filed under no project, so the crew's own project decided which trunk to check"
              : "the project the record that named this change is filed under"
          }
        >
          against <KnownValue value={change.project} />
          {change.projectFromCrew && spellOut ? " — the crew's project, not this record's" : null}
        </span>
      </span>
    </li>
  );
}

export function CrewDelivered({ profile }: { readonly profile: CrewProfile }): ReactElement {
  const landed = profile.delivered.filter((change) => change.verdict === "landed").length;
  const derived = profile.delivered.find((change) => change.projectFromCrew)?.reference ?? null;
  return (
    <section className="panel">
      <header>
        <h2>Delivered</h2>
        <span className="sub">
          {profile.delivered.length === 0
            ? "no change referenced"
            : `${String(profile.delivered.length)} referenced · ${String(landed)} on the trunk`}
        </span>
      </header>
      {profile.delivered.length === 0 ? null : (
        <ul className="links">
          {profile.delivered.map((change) => (
            <Change
              change={change}
              key={`${change.reference}-${change.citedIn}`}
              spellOut={change.reference === derived}
            />
          ))}
        </ul>
      )}
      <div className="src-line">
        <span>{profile.deliveredNote}</span>
        <span>
          a reference is this crew&rsquo;s own claim; only the trunk verdict beside it was checked,
          and no forge was reached to ask what a reviewer decided
        </span>
      </div>
    </section>
  );
}

function Rung({
  step,
  at,
  note,
}: {
  readonly step: LadderStep;
  readonly at: boolean;
  readonly note: string | null;
}): ReactElement {
  return (
    <div className={at ? "lstep at" : "lstep"}>
      <span className="pip" />
      <span className="t">
        <span className="k">{step.label}</span>
        <span className="d">
          {at && note !== null ? <span className="now">{note} </span> : null}
          {step.what}. Entered by {step.entered}.
        </span>
      </span>
    </div>
  );
}

export function CrewAccountability({
  accountability,
}: {
  readonly accountability: Accountability;
}): ReactElement {
  const { counted, defaultNote } = accountability;
  return (
    <section className="panel">
      <header>
        <h2>Accountability</h2>
        <span className="sub">seat-level, not crew-level</span>
      </header>
      <div className="ladder">
        {accountability.steps.map((step) => (
          <Rung
            key={step.rung}
            step={step}
            at={step.rung === accountability.rung}
            note={counted ? "Where this crew's seat stands." : "Default — not a recorded state."}
          />
        ))}
      </div>
      <ul className="links">
        <li>
          <span className="k">Escapes</span>
          <span className="v">
            <KnownValue
              value={mapKnown(
                accountability.escapes,
                (count) => `${String(count)} charged to this seat`
              )}
            />
          </span>
        </li>
        {accountability.charged.map((entry) => (
          <li key={entry}>
            <span className="k">Charged</span>
            <span className="v">{entry}</span>
          </li>
        ))}
      </ul>
      <div className="src-line">
        {defaultNote === null ? null : <span>{defaultNote}</span>}
        <span>src: {accountability.ledgerSource}</span>
        <span>{accountability.ruleSource}</span>
        <span>{accountability.scopeNote}</span>
      </div>
    </section>
  );
}

export function CrewCost({ profile }: { readonly profile: CrewProfile }): ReactElement {
  return (
    <section className="panel">
      <header>
        <h2>Session cost</h2>
        <span className="sub">time · tokens</span>
      </header>
      <div className="gap">
        <span className="big">— · —</span>
        <span className="why">
          Not recorded. <b>ctower emits no per-session duration or token event</b>, so this panel
          would have to invent both — and an invented cost is the one number an operator would
          believe without checking.
        </span>
        <span className="src">
          <span>
            lands with <b>{profile.cost.lands}</b> — {profile.cost.what}
          </span>
        </span>
      </div>
    </section>
  );
}

export function CrewRepair({ profile }: { readonly profile: CrewProfile }): ReactElement {
  const route = profile.claims.find((claim) => claim.ifThisBreaks.known === "value");
  return (
    <section className="panel">
      <header>
        <h2>If this breaks</h2>
      </header>
      <div className="gap">
        {route === undefined ? (
          <span className="why">
            No signature this crew wrote records a repair route. The seat is still re-summoned to
            repair anything it signed — this surface just has nothing to quote about how.
          </span>
        ) : (
          <span className="why">
            <KnownValue value={route.ifThisBreaks} />
          </span>
        )}
        <span className="src">
          <span>
            {route === undefined
              ? "src: this crew's own status files, which carry no if-this-breaks line"
              : `quoted from ${route.file}`}
          </span>
          <span>the signing seat is re-summoned to repair anything it signed</span>
        </span>
      </div>
    </section>
  );
}
