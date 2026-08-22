import { useState } from "react";
import type { ReactElement } from "react";
import { Send as SendGlyph } from "lucide-react";
import type { InboxCorrespondent, InboxCorrespondentList } from "@ctower/client";
import type { Held } from "./reads";
import { Field } from "../ui/form";
import { Button, Mono, Select, Textarea } from "../ui/primitives";
import { routeTo, seatsOffered } from "./address";
import type { Route } from "./address";
import { useSend } from "./commands";
import type { Severity } from "./commands";
import { Priority } from "./Priority";
import { Sent } from "./Sent";
import { Unanswered } from "./Unanswered";

/**
 * The form, once ctower has said who this address may write to.
 *
 * The list is not an ornament on the form, it is the form's closed world, so
 * the fields do not exist before it answers: an unread list drawn as an empty
 * one would offer the operator a message with nowhere to send it.
 */
export function ComposeBox({
  offered,
  to,
  threadId,
  onRecorded,
}: {
  readonly offered: Held<InboxCorrespondentList>;
  readonly to: string | null;
  readonly threadId: string | null;
  readonly onRecorded: () => void;
}): ReactElement {
  if (offered.last === null) {
    return (
      <Unanswered
        answer={offered.answer}
        what="Reading who you can write to"
        action="Nothing was read, so nothing can be addressed. Re-read to ask again."
      />
    );
  }
  return (
    <>
      <Unanswered
        answer={offered.answer}
        action="These are the addresses ctower last offered. Re-read to ask again."
      />
      <Composer
        correspondents={offered.last.correspondents}
        to={to}
        threadId={threadId}
        onRecorded={onRecorded}
      />
    </>
  );
}

/**
 * Writing one message, and the two facts it may not invent.
 *
 * Every message carries an address and a project key. The addresses are exactly
 * the ones ctower offered — that list is defined as the set the send command
 * accepts — and the key comes from the same list rather than from a field the
 * operator fills in, because a key that does not register the seat is refused
 * and a key that two projects share is ambiguous. Where the pairing cannot be
 * resolved the form says so and does not arm; it never guesses one.
 */
function Composer({
  correspondents,
  to,
  threadId,
  onRecorded,
}: {
  readonly correspondents: readonly InboxCorrespondent[];
  /** Fixed when this answers a thread; chosen when it opens one. */
  readonly to: string | null;
  readonly threadId: string | null;
  readonly onRecorded: () => void;
}): ReactElement {
  const offered = seatsOffered(correspondents);
  const [chosen, setChosen] = useState<string>(offered[0] ?? "");
  const [severity, setSeverity] = useState<Severity>("info");
  const [text, setText] = useState("");
  const send = useSend(onRecorded);

  const recipient = to ?? (chosen === "" ? null : chosen);
  const route = recipient === null ? null : routeTo(correspondents, recipient);
  const [project, setProject] = useState<string>("");
  const projectKey = keyOf(route, project);
  const sending = send.outcome?.kind === "asking";
  const armed = recipient !== null && projectKey !== null && text.trim() !== "" && !sending;

  if (to === null && offered.length === 0) {
    return (
      <p className="m-0 py-6 text-sm text-muted">
        ctower offers this address no one to write to. A correspondent appears once another seat is
        registered in this company.
      </p>
    );
  }

  return (
    <form
      className="space-y-3"
      onSubmit={(event): void => {
        event.preventDefault();
        if (recipient === null || projectKey === null || !armed) {
          return;
        }
        send.send({ threadId, to: recipient, projectKey, severity, text: text.trim() });
        setText("");
      }}
    >
      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
        <Field label="To">
          {to === null ? (
            <Select
              value={chosen}
              aria-label="To"
              onChange={(event): void => {
                setChosen(event.target.value);
                setProject("");
              }}
            >
              {offered.map((seat) => (
                <option key={seat} value={seat}>
                  {seat}
                </option>
              ))}
            </Select>
          ) : (
            <Mono className="flex h-9 items-center text-sm text-fg">{to}</Mono>
          )}
        </Field>
        <Field
          label="Project"
          hint="Which project registers this seat; ctower resolves the address with it."
        >
          <Project route={route} chosen={project} onChoose={setProject} />
        </Field>
        <Priority value={severity} onChange={setSeverity} />
      </div>

      <Textarea
        rows={4}
        value={text}
        aria-label="Message"
        placeholder={threadId === null ? "Write the message" : "Write your reply"}
        onChange={(event): void => {
          setText(event.target.value);
        }}
      />

      <div className="flex items-center gap-3">
        {route?.kind === "unknown" ? (
          <p className="m-0 text-xs text-muted">
            No project registers this seat, so no key can be composed for it.
          </p>
        ) : null}
        <span className="flex-1" />
        <Button type="submit" variant="primary" disabled={!armed}>
          <SendGlyph /> Send
        </Button>
      </div>

      <Sent outcome={send.outcome} again={send.again} />
    </form>
  );
}

/** The project key this message will carry, once one is settled. */
function keyOf(route: Route | null, chosen: string): string | null {
  if (route === null) {
    return null;
  }
  switch (route.kind) {
    case "single":
      return route.projectKey;
    case "ambiguous":
      return route.projectKeys.includes(chosen) ? chosen : null;
    case "unknown":
      return null;
  }
}

function Project({
  route,
  chosen,
  onChoose,
}: {
  readonly route: Route | null;
  readonly chosen: string;
  readonly onChoose: (projectKey: string) => void;
}): ReactElement {
  if (route === null || route.kind === "unknown") {
    return <Mono className="flex h-9 items-center text-sm text-muted">—</Mono>;
  }
  if (route.kind === "single") {
    return <Mono className="flex h-9 items-center text-sm text-fg">{route.projectKey}</Mono>;
  }
  return (
    <Select
      value={chosen}
      aria-label="Project"
      onChange={(event): void => {
        onChoose(event.target.value);
      }}
    >
      <option value="">Two projects share this seat — pick one</option>
      {route.projectKeys.map((projectKey) => (
        <option key={projectKey} value={projectKey}>
          {projectKey}
        </option>
      ))}
    </Select>
  );
}
