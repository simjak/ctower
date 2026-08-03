import type { ReactElement } from "react";
import { KnownValue } from "@/frame/Declared";
import type { CrewProfile, SignedClaim } from "@/read/interface";
import { ActivityMark } from "./marks";

/**
 * What this crew has done, and what it signed for.
 *
 * The lifecycle is the crew log's own entries for this name, oldest first. The
 * log carries no notion of an engagement, so the only mark for "this crew was
 * pointed at something else" is a task line that changed — which is stated as
 * the derivation it is rather than drawn as a recorded boundary.
 *
 * The signatures are quoted, never summarised. The fleet's rule is that an
 * artifact without a signature block is not reviewable, mergeable or
 * releasable; a paraphrase of one is not a signature, so the claim and what the
 * seat stood under arrive as the crew wrote them.
 */

function Signature({ claim }: { readonly claim: SignedClaim }): ReactElement {
  return (
    <pre className="sig">
      <span className="k">SIGNED-OFF</span>
      {"\n  "}
      <span className="k">seat:</span> <KnownValue value={claim.seat} />
      {"\n  "}
      <span className="k">model:</span> <KnownValue value={claim.model} />
      {"\n  "}
      <span className="k">claim:</span>{" "}
      <b>
        <KnownValue value={claim.claim} />
      </b>
      {"\n  "}
      <span className="k">stood-under:</span> <KnownValue value={claim.stoodUnder} />
      {"\n  "}
      <span className="k">quoted from:</span> {claim.file}
    </pre>
  );
}

export function CrewLifecycle({ profile }: { readonly profile: CrewProfile }): ReactElement {
  return (
    <section className="panel">
      <header>
        <h2>Lifecycle</h2>
        <span className="sub">{profile.lifecycleNote}</span>
      </header>
      {profile.lifecycle.length === 0 ? (
        <div className="src-line">
          <span>
            the crew log holds no entry for this name, so this crew has recorded nothing about
            itself — it is alive on the fleet and silent in the record
          </span>
        </div>
      ) : (
        <ul className="tl">
          {profile.lifecycle.map((entry, index) => (
            <li key={`${entry.at}-${String(index)}`}>
              <span className="who">
                <i className="av">
                  <KnownValue value={profile.row.seatInitials} render={(mark) => mark} />
                </i>
              </span>
              <div className="e">
                <div className="hdr">
                  <span className="seat">
                    <KnownValue value={entry.status} />
                  </span>
                  <span className="crew">
                    {entry.opensEngagement ? "new task line" : "same task line"}
                  </span>
                  <span className="when">{entry.at}</span>
                </div>
                <div className="did">
                  <KnownValue value={entry.task} />
                </div>
                <div className="arts">
                  <span className="art">
                    <KnownValue value={entry.model} />
                  </span>
                  <span className="art">
                    <KnownValue value={entry.ago} />
                  </span>
                  {entry.comment.known === "value" ? (
                    <span className="art">{entry.comment.value}</span>
                  ) : null}
                </div>
                <div className="row">
                  <ActivityMark activity={entry.activity} status={entry.status} />
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
      <div className="src-line">
        <span>src: {profile.tail.sourcePath}</span>
        <span>
          the log records no engagement boundary; &ldquo;new task line&rdquo; is this surface
          comparing an entry&rsquo;s task against the one before it, and is a derivation, not a
          recorded fact
        </span>
        <span>times are the stamps the log wrote, in the zone this host writes them</span>
      </div>
    </section>
  );
}

export function CrewClaims({ profile }: { readonly profile: CrewProfile }): ReactElement {
  return (
    <section className="panel">
      <header>
        <h2>Signed claims</h2>
        <span className="sub">
          {profile.claims.length === 0
            ? "none quoted"
            : `${String(profile.signatures)} ${profile.signatures === 1 ? "signature" : "signatures"} · ${String(profile.claims.length)} quoted, newest first`}
        </span>
      </header>
      {profile.claims.length === 0 ? (
        <div className="src-line">
          <span>{profile.claimsNote}</span>
          <span>
            an artifact without a signature block is not reviewable, mergeable or releasable — this
            crew has signed nothing this surface can quote
          </span>
        </div>
      ) : (
        <>
          <div className="slots" style={{ gridTemplateColumns: "minmax(0,1fr)" }}>
            {profile.claims.map((claim, index) => (
              <Signature claim={claim} key={`${claim.file}-${String(index)}`} />
            ))}
          </div>
          <div className="src-line">
            <span>src: {profile.claimsNote}</span>
            {profile.signatures > profile.claims.length ? (
              <span>
                the {String(profile.signatures - profile.claims.length)} older{" "}
                {profile.signatures - profile.claims.length === 1
                  ? "signature is"
                  : "signatures are"}{" "}
                counted above and not quoted here; the newest is the one still standing
              </span>
            ) : null}
            <span>
              a block whose own <span className="mono">crew:</span> names a different crew is not
              shown here: a status file may quote another seat&rsquo;s signature, and attributing
              that to this crew would put a claim under a name that never made it
            </span>
          </div>
        </>
      )}
    </section>
  );
}
