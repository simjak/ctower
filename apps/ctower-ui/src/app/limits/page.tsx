import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { StateGlyph } from "@/frame/StateGlyph";
import { recordAdapter, SOURCE_LABELS } from "@/read/adapter";
import type { PoolLimits, PoolWeight } from "@/read/interface";
import { ProfilePanel } from "@/surfaces/limits/ProfilePanel";

export const dynamic = "force-dynamic";

/** One authored rate, in the units the record states it in. */
function rateOf(weight: PoolWeight): string {
  return (
    `in ${weight.inputMillicreditsPerMtok.toString()}` +
    ` · cached ${weight.cachedInputMillicreditsPerMtok.toString()}` +
    ` · out ${weight.outputMillicreditsPerMtok.toString()} millicredits per Mtok`
  );
}

function WeightRow({ weight }: { readonly weight: PoolWeight }): ReactElement {
  return (
    <li>
      <span className="k">{`${weight.subscriptionKey} · ${weight.modelRef}`}</span>
      <span className="v mono">{rateOf(weight)}</span>
    </li>
  );
}

/**
 * The authored weight table behind every metered figure above.
 *
 * It is on the screen because a millicredit balance means nothing without the
 * rate that produced it, and because a weight is authored rather than observed:
 * a reader who disagrees with a cost is disagreeing with this table, and can
 * only see that if the table is visible.
 */
function Weights({ weights }: { readonly weights: readonly PoolWeight[] }): ReactElement {
  return (
    <section className="panel" style={{ marginTop: "16px" }}>
      <header>
        <h2>Model weights</h2>
        <span className="sub">authored rates · subscription · model</span>
      </header>
      {weights.length === 0 ? (
        <div className="limits-empty">
          <StateGlyph name="open" />
          <span>the record holds no authored weights</span>
        </div>
      ) : (
        <ul className="kv">
          {weights.map((weight) => (
            <WeightRow key={`${weight.subscriptionKey}·${weight.modelRef}`} weight={weight} />
          ))}
        </ul>
      )}
    </section>
  );
}

function LimitsBody({ limits }: { readonly limits: PoolLimits }): ReactElement {
  return (
    <>
      <Chrome section="Limits" />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Limits</h1>
          </div>

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Per account</h2>
              <span className="sub">auth · quota · reach, each with its own clock</span>
            </header>
            <div className="limits-note">
              <span>
                Every row below is one account. The record states no single pool verdict and none is
                composed here: a profile holding two capped accounts and one available one has three
                clocks, not one state.
              </span>
              <span className="verdict v-held">read-only</span>
              <span className="mono">ctowerctl pools observe</span>
            </div>
          </section>

          {limits.profiles.length === 0 ? (
            <section className="panel" style={{ marginTop: "16px" }}>
              <div className="limits-empty">
                <StateGlyph name="open" />
                <span>the record holds no credential-pool sweep yet</span>
              </div>
            </section>
          ) : (
            limits.profiles.map((profile) => (
              <ProfilePanel key={`${profile.harnessKey}·${profile.profileKey}`} profile={profile} />
            ))
          )}

          <Weights weights={limits.weights} />

          <RecordFoot
            readPath={SOURCE_LABELS.limits}
            watermark={`topology revision ${limits.topologyRevision.toString()}`}
          />
        </div>
      </main>
    </>
  );
}

/**
 * The credential limits an operator can otherwise only reach through a CLI.
 *
 * This is a shadow read of a shipped API and nothing more: the browser receives
 * no credential, the surface writes nothing, and a sweep is recorded by the
 * harness seat that took it rather than from here — which is why the one command
 * that changes anything on this screen is printed as a command instead of drawn
 * as a control that cannot be pressed.
 */
export default async function LimitsPage(): Promise<ReactNode> {
  const limits = await recordAdapter.poolLimits();
  return (
    <Resolved
      reading={limits}
      subject="the credential-pool read"
      frame={(declared) => (
        <>
          <Chrome section="Limits" />
          <main className="page">
            <div className="wrap">
              <div className="lede">
                <h1>Limits</h1>
              </div>
              <section className="panel" style={{ marginTop: "16px" }}>
                <header>
                  <h2>Credential-pool read</h2>
                </header>
                {declared}
              </section>
              <RecordFoot readPath={SOURCE_LABELS.limits} />
            </div>
          </main>
        </>
      )}
    >
      {(view) => <LimitsBody limits={view} />}
    </Resolved>
  );
}
