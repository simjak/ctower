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
          <span>No weights are authored for this topology.</span>
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

/**
 * The three facts about the screen itself, as three elements rather than as a
 * paragraph about them.
 *
 * This block used to carry the argument for the layout below it — that the
 * record states no single pool verdict, that a profile of three accounts has
 * three clocks — which is reviewer-facing prose shipped inside an
 * operator-facing screen, and precisely what the copy budget was written
 * against. The rule it argued for is enforced by the shape: one row per
 * account, three chips on each, one clock on each. What survives here is what
 * an operator cannot see from the shape — that nothing on this screen writes,
 * that no credential value is on it, and the command that does change it.
 */
function ScreenFacts(): ReactElement {
  return (
    <div className="limits-note">
      <span className="sub">one row per account, with its own clock</span>
      <span className="limits-gap" />
      <span className="verdict v-held">read-only</span>
      <span className="verdict v-filed">references only</span>
      <span className="mono">ctowerctl pools observe</span>
    </div>
  );
}

function LimitsBody({ limits }: { readonly limits: PoolLimits }): ReactElement {
  return (
    <>
      <Chrome section="Credentials" />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Credentials</h1>
          </div>

          <ScreenFacts />

          {limits.profiles.length === 0 ? (
            <section className="panel" style={{ marginTop: "16px" }}>
              <div className="limits-empty">
                <StateGlyph name="open" />
                <span>No pool has been swept yet.</span>
                <span className="mono">ctowerctl pools observe</span>
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
 * Credentials — the accounts the fleet draws on, which an operator can
 * otherwise only reach through a CLI.
 *
 * The screen is named for what it holds rather than for the read that serves
 * it. `readPoolLimits` is the repository's word and `Limits` was the screen
 * wearing it; an operator arriving here wants to know whether the crew can sign
 * in and whether there is quota left, and the accepted navigation calls that
 * Credentials. The route keeps its `/limits` path and the rail keeps its label
 * until the shared navigation registry is renamed on the design branch.
 *
 * This is a shadow read of a shipped API and nothing more: the browser receives
 * no credential, the surface writes nothing, and a sweep is recorded by the
 * harness seat that took it rather than from here — which is why the one command
 * that changes anything on this screen is printed as a command instead of drawn
 * as a control that cannot be pressed.
 *
 * No credential material reaches this page, and the guarantee is structural
 * rather than editorial: `read/poolLimits.ts` parses the record one named field
 * at a time, and the contract's read projection has no field a token, key or
 * fingerprint can occupy. What the screen renders about an account is a
 * provider key, a decoded identity and an alias — never a value.
 */
export default async function LimitsPage(): Promise<ReactNode> {
  const limits = await recordAdapter.poolLimits();
  return (
    <Resolved
      reading={limits}
      subject="the credential-pool read"
      frame={(declared) => (
        <>
          <Chrome section="Credentials" />
          <main className="page">
            <div className="wrap">
              <div className="lede">
                <h1>Credentials</h1>
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
