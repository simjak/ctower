import { X } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { ThemeToggle } from "../app/ThemeToggle";
import { Button, Chip } from "../ui/primitives";

/**
 * The wizard covers everything.
 *
 * A guided first run is not a panel inside a shell whose every destination is
 * locked — there is nothing behind it to look at, and showing a rail full of
 * things that cannot be reached is noise at the one moment the operator should
 * be answering a single question. So it is a full-screen overlay, the way
 * the reference console does it.
 *
 * The close control exists only when a preview is being forced: on a real first
 * run there is nowhere to close to.
 */
export function Overlay({
  previewing,
  onClose,
  children,
}: {
  readonly previewing: boolean;
  readonly onClose: () => void;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-bg">
      <div className="flex h-13 items-center gap-3 px-4">
        {previewing ? (
          <Button
            variant="quiet"
            size="sm"
            className="px-2"
            aria-label="Close the preview"
            onClick={onClose}
          >
            <X />
          </Button>
        ) : null}
        <span className="text-sm font-semibold">
          c<span className="text-amber">tower</span>
        </span>
        {previewing ? <Chip tone="amber">preview</Chip> : null}
        <span className="flex-1" />
        <ThemeToggle />
      </div>
      {children}
    </div>
  );
}
