import type { ReactElement } from "react";
import { Button, Input, Mono } from "../../ui/primitives";
import { Checkbox, Field } from "../../ui/form";
import { Mark } from "../../ui/marks";
import { Asking, Malformed, Refused, Unreachable } from "../../wizard/states";
import { sayable } from "./useRevokeAct";
import type { RevokeAct } from "./useRevokeAct";

/**
 * Revoking one address, where the address is.
 *
 * The consequence is named at the point of action rather than in a dialogue the
 * operator has to dismiss to get back to what they were reading, and the reason
 * is a field because the event carries it: this is the sentence that will
 * explain the revocation to whoever reads the record next.
 */
export function RevokeRow({ revoke }: { readonly revoke: RevokeAct }): ReactElement {
  const open = revoke.open;
  if (open === null) {
    return <></>;
  }
  if (revoke.outcome !== null) {
    return <Outcome revoke={revoke} />;
  }

  return (
    <div className="rounded-md border border-danger/40 bg-danger/8 p-3">
      <p className="m-0 flex items-center gap-2 text-sm text-fg">
        <Mark name="warn" />
        <Mono>{open.receipt.seat_key}</Mono> stops answering. Nothing else about this crew changes.
      </p>
      <div className="mt-3">
        <Field label="Reason" hint="Recorded on the revocation event, and read there later.">
          <Input
            value={revoke.reason}
            placeholder="Rotating the credential"
            onChange={(event): void => {
              revoke.setReason(event.target.value);
            }}
          />
        </Field>
      </div>
      <label className="mt-3 flex cursor-pointer items-center gap-3">
        <Checkbox
          checked={revoke.armed}
          onCheckedChange={revoke.setArmed}
          label="Confirm this runs with operator authority"
        />
        <span className="text-sm text-fg">I am revoking this as the operator.</span>
      </label>
      <div className="mt-3 flex items-center gap-2">
        <Button size="sm" variant="quiet" onClick={revoke.cancel}>
          Cancel
        </Button>
        <span className="flex-1" />
        <Button
          size="sm"
          variant="danger"
          disabled={!revoke.armed || !sayable(revoke.reason)}
          onClick={revoke.send}
        >
          Revoke this address
        </Button>
      </div>
    </div>
  );
}

function Outcome({ revoke }: { readonly revoke: RevokeAct }): ReactElement {
  const outcome = revoke.outcome;
  return (
    <div className="space-y-3">
      {outcome === null || outcome.kind === "asking" ? (
        <Asking what="Revoking, and waiting for ctower to accept it" />
      ) : null}
      {outcome?.kind === "refused" ? (
        <Refused
          problem={outcome.problem}
          action="Nothing was revoked. The address still answers."
        />
      ) : null}
      {outcome?.kind === "unreachable" ? (
        <Unreachable
          detail={outcome.detail}
          action="Whether this was revoked is not known. Revoking again reuses the same command."
        />
      ) : null}
      {outcome?.kind === "malformed" ? <Malformed detail={outcome.detail} /> : null}
      {/* The row above already carries the new state; this adds the one fact it
          does not, which is the credential the revocation event is about. */}
      {outcome?.kind === "answered" ? (
        <p className="m-0 flex flex-wrap items-baseline gap-x-2 text-xs text-muted">
          <span>revoked credential</span>
          <Mono>{outcome.value.credential_id}</Mono>
        </p>
      ) : null}
      <Button size="sm" variant="quiet" onClick={revoke.cancel}>
        Done
      </Button>
    </div>
  );
}
