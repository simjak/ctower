import type { ReactElement } from "react";
import { Chrome } from "@/frame/Chrome";

export default function SetupPage(): ReactElement {
  return (
    <Chrome>
      <main className="setup-page">
        <section className="setup-card" aria-labelledby="setup-title">
          <p className="setup-kicker">Setup</p>
          <h1 className="setup-title" id="setup-title">
            Company setup — feature 1, building
          </h1>
          <p className="setup-copy">
            The company-creation wizard has not been built yet. This is its future home.
          </p>
        </section>
      </main>
    </Chrome>
  );
}
