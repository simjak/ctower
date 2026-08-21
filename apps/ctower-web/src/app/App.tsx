import { useCallback, useState } from "react";
import type { ReactElement } from "react";
import { FirstRun } from "../firstrun/FirstRun";
import { Shell } from "../shell/Shell";
import type { DestinationKey } from "../shell/destinations";
import { TooltipScope } from "../ui/form";
import { Chip } from "../ui/primitives";
import { CompanyPage } from "../wizard/CompanyPage";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import { useSeed } from "../wizard/useSeed";

/**
 * One app, one shell, and one decision made here: whether this tower has a
 * company yet.
 *
 * The company is read once, at the top, so the rail, the header and the page
 * cannot disagree about which of the two situations this is. Until that read
 * answers, neither is claimed — the rail says it is still looking rather than
 * going grey as though the answer were "nothing".
 */
export function App(): ReactElement {
  const [reloadKey, setReloadKey] = useState(0);
  const seed = useSeed(reloadKey);
  const [here, setHere] = useState<DestinationKey>("company");

  const created = useCallback((): void => {
    setReloadKey((count) => count + 1);
  }, []);

  const firstRun = seed.kind === "answered" && seed.value.kind === "template";
  const lockReason = lockReasonFor(seed.kind, firstRun);

  return (
    <TooltipScope>
      <Shell here={here} lockReason={lockReason} onGo={setHere} status={statusFor(seed.kind)}>
        {seed.kind === "asking" ? <Asking what="Reading this company" /> : null}
        {seed.kind === "refused" ? (
          <Refused problem={seed.problem} action="Nothing was read. Reload to ask again." />
        ) : null}
        {seed.kind === "unreachable" ? (
          <Unreachable
            detail={seed.detail}
            action="This is not an empty tower; it is a tower that was not read. Reload to ask again."
          />
        ) : null}
        {seed.kind === "malformed" ? <Malformed detail={seed.detail} /> : null}
        {seed.kind === "answered" ? (
          seed.value.kind === "template" ? (
            <FirstRun onCreated={created} />
          ) : (
            <CompanyPage seed={seed.value} />
          )
        ) : null}
      </Shell>
    </TooltipScope>
  );
}

function lockReasonFor(kind: string, firstRun: boolean): string | null {
  if (firstRun) {
    return "Create the company first";
  }
  return kind === "answered" ? null : "Still reading this company";
}

function statusFor(kind: string): ReactElement | null {
  return kind === "answered" ? null : <Chip>reading</Chip>;
}
