import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";
import { sessionToken, SESSION_REFUSED_EVENT } from "../api/session";
import { Admission } from "./Admission";
import { FirstRun } from "../firstrun/FirstRun";
import { Overlay } from "../firstrun/Overlay";
import { Shell } from "../shell/Shell";
import type { DestinationKey } from "../shell/destinations";
import type { Org } from "../shell/OrgSwitcher";
import { TooltipScope } from "../ui/form";
import { Chip } from "../ui/primitives";
import { CompanyPage } from "../wizard/CompanyPage";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import { useSeed } from "../wizard/useSeed";
import { previewFromLocation, seedForPreview } from "./preview";

/**
 * One app, and one decision made here: whether this tower has a company yet.
 *
 * The company is read once, at the top, so the shell and the page cannot
 * disagree about which of the two situations this is. Until that read answers,
 * neither is claimed — the rail says it is still looking rather than going grey
 * as though the answer were "nothing".
 *
 * With no company there is no shell to show. Every destination would be locked,
 * and a rail full of unreachable things is noise at the one moment the operator
 * should be answering a single question, so the wizard takes the whole screen.
 */
export function App(): ReactElement {
  const [admitted, setAdmitted] = useState(sessionToken() !== null);
  const [reloadKey, setReloadKey] = useState(0);
  const real = useSeed(reloadKey);
  const preview = previewFromLocation(window.location.search);
  const previewing = preview !== null;
  const seed = seedForPreview(preview, real);
  const [here, setHere] = useState<DestinationKey>("company");

  const created = useCallback((): void => {
    setReloadKey((count) => count + 1);
  }, []);

  // A restarted server mints a new token, so the one this tab holds stops
  // working mid-session. The chokepoint drops it and says so; the gate comes
  // back rather than every screen quietly failing to read.
  useEffect((): (() => void) => {
    const refused = (): void => {
      setAdmitted(false);
    };
    window.addEventListener(SESSION_REFUSED_EVENT, refused);
    return (): void => {
      window.removeEventListener(SESSION_REFUSED_EVENT, refused);
    };
  }, []);

  if (!admitted) {
    return (
      <Admission
        onAdmitted={(): void => {
          setAdmitted(true);
          setReloadKey((count) => count + 1);
        }}
      />
    );
  }

  if (seed.kind === "answered" && seed.value.kind === "template") {
    return (
      <TooltipScope>
        <Overlay
          previewing={previewing}
          onClose={(): void => {
            window.location.assign(window.location.pathname);
          }}
        >
          <FirstRun onCreated={created} previewing={previewing} />
        </Overlay>
      </TooltipScope>
    );
  }

  return (
    <TooltipScope>
      <Shell
        here={here}
        lockReason={seed.kind === "answered" ? null : "Still reading this company"}
        onGo={setHere}
        org={orgOf(seed)}
        status={statusFor(seed.kind, previewing)}
      >
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
        {seed.kind === "answered" && seed.value.kind === "exported" ? (
          <CompanyPage seed={seed.value} />
        ) : null}
      </Shell>
    </TooltipScope>
  );
}

/**
 * What the header says about the tower, and only what is known.
 *
 * A page snapshot caught this claiming "first run" while the read was still
 * out: locked and first-run are different facts, and one was being inferred
 * from the other.
 */
/** The company, once the read has actually produced one. */
function orgOf(seed: ReturnType<typeof seedForPreview>): Org | null {
  if (seed.kind !== "answered" || seed.value.kind !== "exported") {
    return null;
  }
  const company = seed.value.result.bundle.company;
  return { name: company.display_name, key: company.key };
}

function statusFor(kind: string, previewing: boolean): ReactElement | null {
  return (
    <>
      {previewing ? <Chip tone="amber">preview</Chip> : null}
      {kind === "answered" ? null : <Chip>reading</Chip>}
    </>
  );
}
