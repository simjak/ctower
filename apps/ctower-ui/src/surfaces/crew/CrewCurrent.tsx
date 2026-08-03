import Link from "next/link";
import type { ReactElement } from "react";
import { KnownValue } from "@/frame/Declared";
import { StateGlyph } from "@/frame/StateGlyph";
import type { CrewProfile } from "@/read/interface";
import { ActivityMark, CREW_GLYPH } from "./marks";

/**
 * What this crew is bound to right now.
 *
 * One line for the work, then the two liveness facts an operator actually
 * decides on: how long the session has been up, and how long since tmux saw it
 * produce anything. They are different questions — a session up nine hours that
 * last spoke four hours ago is the shape of a stuck crew — so they are never
 * collapsed into one "active" word.
 *
 * The links beneath are the destinations that exist for this crew on this
 * surface. There is no link to a forge: this app holds no credential for one
 * and would have to invent a host to build the URL.
 */

export function CrewCurrent({ profile }: { readonly profile: CrewProfile }): ReactElement {
  const { row } = profile;
  return (
    <section className="panel">
      <header>
        <h2>Current</h2>
        <span className="sub">the work the record binds to this crew</span>
      </header>
      <ul className="crit">
        <li>
          <StateGlyph name={CREW_GLYPH[row.activity]} />
          <div>
            <div className="t">
              <KnownValue value={row.task} />
            </div>
            <div className="proof">
              <span>
                request <KnownValue value={row.request} />
              </span>
              <span>
                slug <KnownValue value={row.slug} />
              </span>
              <span>
                logged <KnownValue value={row.loggedAgo} />
              </span>
            </div>
            <div className="arts">
              {profile.links.map((link) => (
                <Link className="art link" key={link.href} href={link.href} title={link.what}>
                  {link.label}
                </Link>
              ))}
            </div>
          </div>
        </li>
        <li>
          <StateGlyph name="open" />
          <div>
            <div className="t">
              Alive <KnownValue value={row.upFor} /> · <KnownValue value={profile.lastOutput} />
            </div>
            <div className="proof">
              <span>
                running <KnownValue value={profile.running} />
              </span>
              <span>
                state <ActivityMark activity={row.activity} status={row.status} />
              </span>
            </div>
          </div>
        </li>
      </ul>
      <div className="src-line">
        <span>{profile.sourceNote}</span>
        <span>
          liveness is the session listing; the task, status and model are what this crew last wrote
          to the log, so the record lags the work by however long the crew has gone without writing
        </span>
        {row.flag === null ? null : <span>{row.flag}</span>}
      </div>
    </section>
  );
}
