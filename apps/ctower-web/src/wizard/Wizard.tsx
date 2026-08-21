import type { ReactElement } from "react";
import { PageHead } from "../ui/primitives";
import { Asking, Malformed, Refused, Unreachable } from "./states";
import { Frame } from "./Frame";
import { Steps } from "./Steps";
import { useSeed } from "./useSeed";

/**
 * The wizard, and the only screen this application has.
 *
 * Nothing is composed until the company has been read, because a company that
 * could not be read and a company with nothing in it are different facts and
 * seeding a draft from the second would invent the first.
 */
export function Wizard(): ReactElement {
  const seed = useSeed();

  if (seed.kind === "answered") {
    return <Steps seed={seed.value} />;
  }

  return (
    <Frame current="company" reached="company">
      <PageHead title="Company details" subtitle="" />
      {seed.kind === "asking" ? <Asking what="Reading this company" /> : null}
      {seed.kind === "refused" ? (
        <Refused problem={seed.problem} action="Nothing was composed. Reload to ask again." />
      ) : null}
      {seed.kind === "unreachable" ? (
        <Unreachable
          detail={seed.detail}
          action="This is not an empty company; it is a company that was not read. Reload to ask again."
        />
      ) : null}
      {seed.kind === "malformed" ? <Malformed detail={seed.detail} /> : null}
    </Frame>
  );
}
