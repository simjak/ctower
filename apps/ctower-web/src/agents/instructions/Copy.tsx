import { Check, Copy as CopyGlyph } from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactElement } from "react";

/**
 * Take one machine value somewhere else.
 *
 * The only reason to open the Advanced disclosure is to carry a value out of
 * it, so the control that does that sits on every line rather than asking the
 * operator to select truncated monospace by hand.
 *
 * It reports what happened and then stops reporting. A copy that silently did
 * nothing — a browser without clipboard permission is the ordinary case — is
 * how someone pastes the wrong thing two screens later, so the glyph changes
 * only on success and the button says so in its own accessible name.
 */
export function Copy({
  what,
  label,
}: {
  readonly what: string;
  readonly label: string;
}): ReactElement {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) {
      return;
    }
    const timer = setTimeout(() => {
      setCopied(false);
    }, COPIED_FOR);
    return (): void => {
      clearTimeout(timer);
    };
  }, [copied]);

  return (
    <button
      type="button"
      aria-label={copied ? `${label} copied` : `Copy ${label.toLowerCase()}`}
      className="inline-flex shrink-0 cursor-pointer text-muted hover:text-fg"
      onClick={(): void => {
        void navigator.clipboard.writeText(what).then(
          () => {
            setCopied(true);
          },
          () => {
            // The clipboard refused. Nothing was copied, so nothing is said —
            // the one dishonest thing here would be a tick over a failed copy.
          }
        );
      }}
    >
      {copied ? <Check className="size-3 text-ok" /> : <CopyGlyph className="size-3" />}
    </button>
  );
}

/** Long enough to read the tick, short enough not to outlast the glance. */
const COPIED_FOR = 1500;
