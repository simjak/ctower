import type { ReactElement } from "react";
import { INERT_CONTROL, INERT_FIELD } from "@/frame/inert";

/**
 * Steering, as a disabled affordance.
 *
 * The Inbox composer is a real write — it asks a server-authorized inbox
 * command. This one is not: injecting a turn into a running session is an
 * audited mutation ctower exposes no path for, and pretending otherwise would
 * put an unaudited write in front of the operator. So the control is present
 * and visibly inert, with its verdict on the control itself rather than in a
 * page banner.
 *
 * The de-texting amendment moved the explanation off the screen: the disabled
 * field and button say it cannot be pressed, the chip says why in three words,
 * and the fuller caveat is the hover — where the craft rules put a caveat. The
 * screen-reader line keeps the whole sentence, because a hover is not a
 * sentence a screen reader can reach.
 */

const STEER_CAVEAT =
  "sending would be an audited injection recorded on the ticket, and ctower exposes no path for one from a browser; no work item is filed for it yet";

export function Composer(): ReactElement {
  return (
    <div className="composer">
      <div className="hd">
        <span className="k">Steer this session</span>
        <span className="verdict v-held" title={STEER_CAVEAT}>
          no steering path
        </span>
      </div>
      <div className="steer-row">
        <textarea
          aria-describedby="steer-readonly"
          className="field"
          disabled
          placeholder="steering is not wired"
          rows={2}
          style={INERT_FIELD}
          title={STEER_CAVEAT}
        />
        <button className="btn" disabled style={INERT_CONTROL} title={STEER_CAVEAT} type="button">
          Send
        </button>
      </div>
      <span className="sr" id="steer-readonly">
        {STEER_CAVEAT}
      </span>
    </div>
  );
}
