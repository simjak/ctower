import type { ReactElement } from "react";
import type { SeatCredentialReceipt } from "@ctower/client";
import { Chip, Mono } from "../../ui/primitives";
import { Mark } from "../../ui/marks";

/**
 * An address, drawn from the receipt ctower handed back and from nothing else.
 *
 * `state` is the record's own word, so it carries the mark: an address that is
 * answering is proven, and a revoked one is dead. Durability is a separate fact
 * and is drawn separately — a command ctower took but has not confirmed is not
 * an address yet, and calling it one is the single most misleading thing this
 * component could do.
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
  return (
    <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
      {mark ? <Mark name={active ? "done" : "dead"} /> : null}
      <Mono className="shrink-0 text-fg">
        {receipt.project_key} / {receipt.seat_key}
      </Mono>
      <Chip tone={active ? "ok" : "danger"}>{receipt.state}</Chip>
      {receipt.durability_state === "accepted" ? null : <Chip tone="amber">not durable</Chip>}
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
