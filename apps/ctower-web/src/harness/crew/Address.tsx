import type { ReactElement } from "react";
import type { SeatCredentialReceipt } from "@ctower/client";
import { Chip, Mono } from "../../ui/primitives";
import { Mark } from "../../ui/marks";

/**
 * An address, drawn from the receipt ctower handed back and from nothing else.
 *
 * `state` is the record's own word and durability says whether that word is
 * settled, so the mark needs both: a command ctower took but has not confirmed
 * is still moving, and drawing it as proven — or as dead — is the single most
 * misleading thing this component could do. `durability_pending` therefore
 * carries `working`, never `done`, and the state's own chip goes amber with it.
 *
 * Nothing here is the credential. `credential_id` is the handle a revocation is
 * addressed to, the reference names where the secret lives, and the secret
 * itself never reached this browser.
 */
export function AddressLine({
  receipt,
  mark = true,
}: {
  readonly receipt: SeatCredentialReceipt;
  /** Off where the line sits under a step that already carries the state's mark. */
  readonly mark?: boolean;
}): ReactElement {
  const active = receipt.state === "active";
  const settled = receipt.durability_state === "accepted";
  return (
    <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
      {mark ? <Mark name={settled ? (active ? "done" : "dead") : "working"} /> : null}
      <Mono className="shrink-0 text-fg">
        {receipt.project_key} / {receipt.seat_key}
      </Mono>
      <Chip tone={settled ? (active ? "ok" : "danger") : "amber"}>{receipt.state}</Chip>
      {settled ? null : <Chip tone="amber">not durable</Chip>}
      <Chip title={receipt.scopes.join(" · ")}>{receipt.scopes.join(" · ")}</Chip>
    </span>
  );
}

/**
 * No address is known, which is not the same as no address existing.
 *
 * ctower serves no read for a seat, so a crew this session did not mint for has
 * a state nothing has reported. `DESIGN.md` is explicit about that case: a state
 * without a recorded fact draws no mark, because borrowing a neighbour's glyph
 * is how a read that never happened gets rendered as a state that did.
 */
export function NoAddress(): ReactElement {
  return <span className="text-sm text-muted">not read</span>;
}
