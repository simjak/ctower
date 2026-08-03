import Link from "next/link";
import type { ReactElement } from "react";
import { KnownValue } from "@/frame/Declared";
import { StateGlyph } from "@/frame/StateGlyph";
import type { CrewProfile } from "@/read/interface";
import { ActivityVerdict, CREW_GLYPH } from "./marks";

/**
 * Who this crew is.
 *
 * A **seat** is durable and outlives every job it does; a **crew** is one
 * engagement of it. The custody line reads left to right in exactly that order
 * — seat, then the crew it spawned, then when — so the distinction the product
 * turns on is legible before any panel below is read.
 *
 * Every chip is a recorded field. A field the crew log is silent about prints
 * its own reason instead of vanishing, because a header that quietly drops the
 * model is a header that looks complete and is not.
 */

export function CrewHead({ profile }: { readonly profile: CrewProfile }): ReactElement {
  const { row } = profile;
  return (
    <div className="thead">
      <div className="crumbs">
        <Link href="/team">Org</Link>
        <span>/</span>
        {row.seatLabel.known === "value" ? (
          <Link href={`/team?seat=${encodeURIComponent(row.seatLabel.value)}`}>
            {row.seatLabel.value}
          </Link>
        ) : (
          <KnownValue value={row.seatLabel} />
        )}
        <span>/</span>
        <span className="id">{profile.sessionName}</span>
      </div>

      <h1>
        <StateGlyph name={CREW_GLYPH[row.activity]} />
        {row.name}
      </h1>

      <div className="tmeta">
        <span className="chip">
          <i
            className="av"
            style={{
              width: "15px",
              height: "15px",
              fontSize: "8px",
              border: 0,
              background: "none",
            }}
          >
            <KnownValue value={row.seatInitials} render={(mark) => mark} />
          </i>
          <KnownValue value={row.seat} />
        </span>
        <span className="chip proj">
          <KnownValue value={row.project} />
        </span>
        <span className="chip">
          <KnownValue value={row.model} />
        </span>
        <span className="chip">
          <KnownValue value={row.harness} />
        </span>
        <ActivityVerdict activity={row.activity} status={row.status} />
      </div>

      <div className="custody">
        <span className="k">seat</span>
        <span className="mono">
          <KnownValue value={row.seat} />
        </span>
        <span className="arrow">→</span>
        <span className="k">crew</span>
        <span className="mono">{row.name}</span>
        <span className="arrow">→</span>
        <span className="k">spawned</span>
        <span className="mono">
          <KnownValue value={profile.spawnedAt} />
        </span>
        <span className="arrow">·</span>
        <span className="k">alive</span>
        <span className="mono">
          <KnownValue value={row.upFor} />
        </span>
      </div>
    </div>
  );
}
