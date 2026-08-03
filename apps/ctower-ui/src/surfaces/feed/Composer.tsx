import type { ReactElement } from "react";
import { INERT_CONTROL, INERT_FIELD } from "@/frame/inert";

/**
 * Steering, as a disabled affordance.
 *
 * Read-only v1 has no mutation path: this surface holds no authority to inject
 * an operator turn, and pretending otherwise would put an unaudited write in
 * front of the operator. The control is present and visibly inert, with the
 * reason on the control itself rather than in a page banner.
 */
export function Composer(): ReactElement {
  return (
    <div className="composer">
      <div className="hd">
        <span className="k">Send to this session</span>
        <span className="verdict v-held">read-only v1 · disabled</span>
        <span className="note">
          Sending would be an audited injection recorded on the ticket. This surface makes no
          mutation, so the composer is inert by design. No work item is filed yet for steering a
          session from a browser, and naming one that does not cover it would be worse than saying
          so.
        </span>
      </div>
      <div className="steer-row">
        <textarea
          className="field"
          rows={2}
          disabled
          aria-describedby="steer-readonly"
          placeholder="steering is not wired in read-only v1"
          style={INERT_FIELD}
        />
        <button className="btn" type="button" disabled style={INERT_CONTROL}>
          Send
        </button>
      </div>
      <span className="sr" id="steer-readonly">
        The steering composer is disabled in read-only v1; no message is sent.
      </span>
    </div>
  );
}
