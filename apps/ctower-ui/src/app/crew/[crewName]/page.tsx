import type { Metadata } from "next";
import Link from "next/link";
import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { KnownValue, Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { StateGlyph } from "@/frame/StateGlyph";
import { recordAdapter, SOURCE_LABELS } from "@/read/adapter";
import type { CrewProfile, CrewUnknown, TailNote } from "@/read/interface";
import { redacted } from "@/read/sources/redact";
import { CrewCurrent } from "@/surfaces/crew/CrewCurrent";
import { CrewHead } from "@/surfaces/crew/CrewHead";
import { CrewClaims, CrewLifecycle } from "@/surfaces/crew/CrewHistory";
import {
  CrewAccountability,
  CrewCost,
  CrewDelivered,
  CrewRepair,
  CrewWhere,
} from "@/surfaces/crew/CrewRail";

export const dynamic = "force-dynamic";

/**
 * One crew in full.
 *
 * A **seat** is durable — one accountable persona that outlives every job it
 * does. A **crew** is one engagement of that seat, and this is the page that
 * answers what this one has done and who stands behind it.
 *
 * Read-only, like every screen here, and honest in the same three ways: a fact
 * the record carries is shown, a fact it does not carries its own reason, and a
 * read that failed says *that* instead — never emptiness. The one panel with no
 * record at all is session cost, and it says so on its face and names the work
 * that would land it.
 */

function Foot({ tail }: { readonly tail: TailNote }): ReactElement {
  const notes = [
    `${tail.totalLines.toString()} complete crew-log lines`,
    tail.partialTail ? "1 line at the tail was mid-write and is not shown" : "no partial tail",
    tail.malformed === 0 ? "none malformed" : `${tail.malformed.toString()} malformed`,
  ];
  return <span>{notes.join(" · ")}</span>;
}

function Profile({ profile }: { readonly profile: CrewProfile }): ReactElement {
  return (
    <>
      <Chrome section="Crew" back={{ href: "/team", label: "Org" }} />
      <main className="page">
        <div className="wrap">
          <CrewHead profile={profile} />

          <div className="cols">
            <div className="main">
              <CrewCurrent profile={profile} />
              <CrewLifecycle profile={profile} />
              <CrewClaims profile={profile} />
            </div>

            <div className="rail-r">
              <CrewWhere profile={profile} />
              <CrewDelivered profile={profile} />
              <CrewAccountability accountability={profile.accountability} />
              <CrewCost profile={profile} />
              <CrewRepair profile={profile} />
            </div>
          </div>

          <div className="foot">
            <span>
              a crew is one engagement of a seat — the seat outlives it, and the ladder above is the
              seat&rsquo;s state, not something this crew earned alone
            </span>
            <span>everything above is read; nothing on this page writes</span>
          </div>

          <RecordFoot readPath={SOURCE_LABELS.crew} watermark={<Foot tail={profile.tail} />} />
        </div>
      </main>
    </>
  );
}

/**
 * A name the fleet does not run.
 *
 * This is an answer, not a failure — tmux was reached and lists no such
 * session — so the page says what *was* checked and what the crew log holds
 * for the name, which is how a reaped crew is told apart from one that never
 * existed. It is never a blank page, and it never renders the panels above with
 * nothing in them, because a shell with empty fields reads as a crew with no
 * work rather than as a crew that is not there.
 */
function NotFound({ missing }: { readonly missing: CrewUnknown }): ReactElement {
  return (
    <>
      <Chrome section="Crew" back={{ href: "/team", label: "Org" }} />
      <main className="page">
        <div className="wrap">
          <div className="thead">
            <div className="crumbs">
              <Link href="/team">Org</Link>
              <span>/</span>
              <span className="id">{missing.crew}</span>
            </div>
            <h1>
              <StateGlyph name="attn" />
              No crew by that name is running
            </h1>
            <div className="tmeta">
              <span className="verdict v-filed">not on the fleet</span>
              <span className="chip">{missing.liveCrews} crews alive</span>
            </div>
          </div>

          <section className="panel" style={{ marginTop: "18px" }}>
            <header>
              <h2>What the record holds for this name</h2>
            </header>
            <ul className="links">
              <li>
                <span className="k">Crew log</span>
                <span className="v">
                  <KnownValue value={missing.logged} />
                </span>
              </li>
            </ul>
            <div className="src-line">
              <span>
                {missing.logged.known === "value"
                  ? "the crew log has recorded this name, and no session is running it now — a crew that was reaped, not one that never existed"
                  : "no session is running this name and the crew log has never recorded it"}
              </span>
              <span>
                this page shows no identity, lifecycle, delivery or accountability panel, because
                every one of them would be empty and an empty panel reads as a crew with no work
                rather than as a crew that is not here
              </span>
            </div>
          </section>

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>What was checked</h2>
            </header>
            <ul className="links">
              {missing.checked.map((source) => (
                <li key={source}>
                  <span className="k">Source</span>
                  <span className="v mono">{source}</span>
                </li>
              ))}
            </ul>
            <div className="src-line">
              <span>
                every source above answered; none of them runs or holds a live session for this
                name, so this is a recorded absence and not a failed read
              </span>
            </div>
          </section>

          <div className="foot">
            <span>
              <Link href="/team">Org lists every crew alive on the fleet</Link>
            </span>
          </div>

          <RecordFoot readPath={SOURCE_LABELS.crew} />
        </div>
      </main>
    </>
  );
}

function Frame({
  crew,
  declared,
}: {
  readonly crew: string;
  readonly declared: ReactElement;
}): ReactElement {
  return (
    <>
      <Chrome section="Crew" back={{ href: "/team", label: "Org" }} />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Crew</h1>
            <p>One engagement of one seat, read from the fleet&rsquo;s own records.</p>
          </div>
          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>{crew}</h2>
            </header>
            {declared}
          </section>
          <RecordFoot readPath={SOURCE_LABELS.crew} />
        </div>
      </main>
    </>
  );
}

/**
 * The tab carries the crew name, so a screenshot of one profile is not
 * indistinguishable from a screenshot of another. The name comes from the URL,
 * so it is redacted here rather than trusted: a title is rendered chrome like
 * any other string this surface prints.
 */
export async function generateMetadata({
  params,
}: {
  readonly params: Promise<{ readonly crewName: string }>;
}): Promise<Metadata> {
  const { crewName } = await params;
  return { title: `${redacted(crewName)} · ctower` };
}

export default async function CrewPage({
  params,
}: {
  readonly params: Promise<{ readonly crewName: string }>;
}): Promise<ReactNode> {
  const { crewName } = await params;
  const lookup = await recordAdapter.crewProfile(crewName);
  return (
    <Resolved reading={lookup} frame={(declared) => <Frame crew={crewName} declared={declared} />}>
      {(value) =>
        value.found === "crew" ? (
          <Profile profile={value.profile} />
        ) : (
          <NotFound missing={value.missing} />
        )
      }
    </Resolved>
  );
}
