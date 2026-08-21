import type { ReactElement } from "react";
import { PoolEntryRow } from "./PoolEntryRow";
import { StateGlyph } from "@/frame/StateGlyph";
import { stampText } from "@/read/elapsed";
import type { PoolDrift, PoolProfile } from "@/read/interface";

/**
 * One harness profile's latest sweep.
 *
 * The panel head carries the two facts the record states about the profile as a
 * whole — how many of its accounts are selectable, and the earliest clock among
 * them — and nothing else. Everything a reader might want summarised here is a
 * per-account fact and stays on its account's own row.
 *
 * Drift is a separate block because it is a different claim. An entry is what
 * the sweep saw; a drift finding is where the sweep and the authored topology
 * disagree, and which of the two is missing the other. It names the enactment
 * path because that is what decides who closes it: an `operator-ceremony` row
 * is a device flow the operator performs on the host, and a `secret-reference`
 * row is an alias the fleet binds. Neither is a control this screen can offer —
 * ctower asks for credential material and never performs the mint — so the
 * enactment is stated and no button is drawn beside it.
 */

function DriftRow({ finding }: { readonly finding: PoolDrift }): ReactElement {
  return (
    <li className="limits-drift-row">
      <StateGlyph name="attn" />
      <span className="verdict v-changes">{finding.finding}</span>
      <span className="limits-provider">{finding.providerKey}</span>
      <span className="limits-identity">
        {finding.subscriptionIdentity ?? "no account name recorded"}
      </span>
      {/* neutral on purpose: the two paths differ in custody, not in severity,
          and a hue between them would rank one of them as the worse finding */}
      <span className="verdict v-filed">{finding.enactment}</span>
      <span className="limits-drift-detail">{finding.detail}</span>
    </li>
  );
}

function Drift({ findings }: { readonly findings: readonly PoolDrift[] }): ReactElement | null {
  if (findings.length === 0) {
    return null;
  }
  return (
    <div className="limits-drift">
      <div className="limits-drift-head">
        <span className="limits-drift-title">Drift</span>
        <span className="limits-drift-sub">the topology and the sweep disagree</span>
      </div>
      <ul className="limits-drift-list">
        {findings.map((finding) => (
          <DriftRow finding={finding} key={`${finding.providerKey}·${finding.detail}`} />
        ))}
      </ul>
    </div>
  );
}

/** The two facts the record states about the profile itself, as one line. */
function summaryOf(profile: PoolProfile): string {
  const swept = `${profile.selectableEntryCount.toString()} selectable · swept ${stampText(profile.observedAt)}`;
  return profile.earliestKnownResetAt === null
    ? `${swept} · no reset time recorded on any account`
    : `${swept} · earliest reset ${stampText(profile.earliestKnownResetAt)}`;
}

export function ProfilePanel({ profile }: { readonly profile: PoolProfile }): ReactElement {
  return (
    <section className="panel" style={{ marginTop: "16px" }}>
      <header>
        <h2>{`${profile.harnessKey} · ${profile.profileKey}`}</h2>
        <span className="sub">{summaryOf(profile)}</span>
      </header>
      {profile.entries.length === 0 ? (
        <div className="limits-empty">
          <StateGlyph name="open" />
          <span>this sweep recorded no accounts for this profile</span>
        </div>
      ) : (
        <div className="limits-pool">
          {profile.entries.map((entry) => (
            <PoolEntryRow
              entry={entry}
              key={`${entry.providerKey}·${entry.subscriptionIdentity ?? entry.entryLabel ?? ""}`}
            />
          ))}
        </div>
      )}
      <Drift findings={profile.drift} />
    </section>
  );
}
