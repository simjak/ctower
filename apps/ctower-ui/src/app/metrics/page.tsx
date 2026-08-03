import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { NoSourceYet, Resolved } from "@/frame/Declared";
import { INERT_CONTROL, INERT_FIELD } from "@/frame/inert";
import { RecordFoot } from "@/frame/RecordFoot";
import { StateGlyph } from "@/frame/StateGlyph";
import { recordAdapter, SOURCE_LABELS } from "@/read/adapter";
import { clockText } from "@/read/elapsed";
import type { DeliveryMetrics, DeliveryScope } from "@/read/interface";
import { DeliveryCards } from "@/surfaces/metrics/DeliveryCards";
import { MergeBars } from "@/surfaces/metrics/MergeBars";

export const dynamic = "force-dynamic";

function Lede(): ReactElement {
  return (
    <div className="lede">
      <h1>Metrics</h1>
      <p>
        How fast each factory ships, how often it breaks, and how long it takes to recover — over
        the backlog it is burning down and the merges that burned it. Every number names the record
        it is read from, and a measure with no record says so instead of showing a zero.
      </p>
    </div>
  );
}

/** The fan-out across projects can be partly unreadable; say so above the numbers. */
function Unread({ metrics }: { readonly metrics: DeliveryMetrics }): ReactElement | null {
  if (metrics.unread === 0) {
    return null;
  }
  return (
    <div className="slots" style={{ gridTemplateColumns: "minmax(0, 1fr)", paddingBottom: 0 }}>
      <div
        className="slot"
        style={{ borderColor: "var(--warn-line)", background: "var(--warn-bg)" }}
      >
        <StateGlyph name="attn" />
        <div className="e">
          <div className="k">these totals are incomplete</div>
          <div className="d">
            {metrics.unread.toString()} of {metrics.considered.toString()} project histories could
            not be read, so every total and rate below is measured over the rest. It is not the
            portfolio figure and must not be quoted as one.
          </div>
          {metrics.reason === null ? null : (
            <div className="f" style={{ overflowWrap: "anywhere" }}>
              <span className="req">{metrics.reason}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * The define-metric disclosure, inert in read-only v1.
 *
 * The approved mockup writes the YAML the commit would carry as you type and
 * reveals the gate on save. This surface holds no authority to write a file, so
 * the form renders with the reason on the control rather than pretending.
 */
function DefineMetric(): ReactElement {
  return (
    <details className="mtnew">
      <summary>
        Define a metric <span className="hint">read-only v1 · writes nothing</span>
      </summary>
      <div className="mtform">
        <div className="mtfields">
          <label className="mtf">
            Name
            <input
              className="inp"
              disabled
              style={INERT_FIELD}
              placeholder="staging lead time p95"
            />
          </label>
          <div className="mtf">
            Scope
            <div className="mtro">taken from the project tab</div>
          </div>
        </div>
        <div className="mtyaml">
          {[
            "# the file this form would commit",
            "metric:",
            "  name: <name>",
            "  scope: <project>",
            "  source: <a record that exists>",
            "# nothing is written: this surface holds no authority to commit",
          ].join("\n")}
        </div>
        <div className="mtsave">
          <button className="btn" type="button" disabled style={INERT_CONTROL}>
            Save — commit via review
          </button>
          <span className="note">
            A saved metric would open a branch and a pull request through the same cross-family
            review as code. Read-only v1 opens none of it, so the control is inert by design.
          </span>
        </div>
      </div>
    </details>
  );
}

const SCOPE_INPUT: Readonly<Record<string, string>> = {
  all: "s-all",
  ctower: "s-ctower",
  manibo: "s-manibo",
  bhloop: "s-bhloop",
};

/**
 * The project scope control, as the approved page defines it: four radios at
 * body level and one `.mtscope` block per project. The vendored stylesheet does
 * the switching, so this needs no script and cannot leave a card visible that
 * belongs to a project the selected tab does not name.
 */
function ScopeInputs({ scopes }: { readonly scopes: readonly DeliveryScope[] }): ReactElement {
  return (
    <>
      {scopes.map((scope, index) => (
        <input
          className="filters"
          type="radio"
          name="scope"
          id={SCOPE_INPUT[scope.key] ?? `s-${scope.key}`}
          key={scope.key}
          defaultChecked={index === 0}
        />
      ))}
    </>
  );
}

function ScopeTabs({ scopes }: { readonly scopes: readonly DeliveryScope[] }): ReactElement {
  return (
    <nav className="tabs" aria-label="Filter by project">
      {scopes.map((scope) => (
        <label
          className={scope.key === "all" ? "tab" : `tab t-${scope.key}`}
          htmlFor={SCOPE_INPUT[scope.key] ?? `s-${scope.key}`}
          key={scope.key}
        >
          {scope.key === "all" ? null : <i className="swatch" />}
          {scope.label}
        </label>
      ))}
    </nav>
  );
}

function MetricsBody({ metrics }: { readonly metrics: DeliveryMetrics }): ReactElement {
  return (
    <>
      <ScopeInputs scopes={metrics.scopes} />
      <Chrome section="Metrics" />
      <main className="page">
        <div className="wrap">
          <Lede />
          <ScopeTabs scopes={metrics.scopes} />
          <Unread metrics={metrics} />

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Delivery</h2>
              <span className="sub">
                {metrics.windowDays.length.toString()} days to {clockText(metrics.measuredAt)} ·
                changes measured, deploys not recorded
              </span>
            </header>
            {metrics.scopes.map((scope) => (
              <div className="mtscope" data-scope={scope.key} key={scope.key}>
                <div className="mtgrid">
                  <DeliveryCards measures={scope.measures} />
                </div>
              </div>
            ))}
          </section>

          <div className="mtcharts">
            <section className="panel">
              <header>
                <h2>Changes per day</h2>
                <span className="sub">to each trunk · read from the repositories</span>
              </header>
              <div className="body">
                {metrics.scopes.map((scope) => (
                  <div className="mtscope" data-scope={scope.key} key={scope.key}>
                    <MergeBars projects={scope.projects} days={metrics.windowDays} />
                  </div>
                ))}
              </div>
            </section>

            <section className="panel">
              <header>
                <h2>Drain burn-down</h2>
                <span className="sub">open items over time</span>
              </header>
              <div className="body">
                <NoSourceYet
                  title="no series to draw"
                  source={{
                    lands: "#186 / G5",
                    what: "the drain ledger as a machine-readable series — it exists today only as prose in the migration status note, and reading a burn-down out of prose would be a guess with a chart around it",
                  }}
                />
              </div>
            </section>
          </div>

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Custom metrics</h2>
              <span className="sub">none defined</span>
            </header>
            <div className="mtdefs">
              <NoSourceYet
                title="no metric defined"
                source={{
                  lands: "#186 / G5",
                  what: "a metric definition file the kernel reads, and the deploy and per-session token records the proposed examples would join against",
                }}
              />
              <DefineMetric />
            </div>
          </section>

          <RecordFoot
            readPath={SOURCE_LABELS.metrics}
            watermark={`${metrics.projects.map((project) => `${project.label} ${project.trunk}`).join(" · ")} · ${metrics.unread.toString()} of ${metrics.considered.toString()} unread`}
          />
        </div>
      </main>
    </>
  );
}

export default async function MetricsPage(): Promise<ReactNode> {
  const metrics = await recordAdapter.deliveryMetrics();
  return (
    <Resolved
      reading={metrics}
      frame={(declared) => (
        <>
          <Chrome section="Metrics" />
          <main className="page">
            <div className="wrap">
              <Lede />
              <section className="panel" style={{ marginTop: "16px" }}>
                <header>
                  <h2>Delivery</h2>
                </header>
                {declared}
              </section>
              <RecordFoot readPath={SOURCE_LABELS.metrics} />
            </div>
          </main>
        </>
      )}
    >
      {(value) => <MetricsBody metrics={value} />}
    </Resolved>
  );
}
