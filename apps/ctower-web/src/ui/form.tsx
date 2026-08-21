import { Checkbox as CheckboxPrimitive, Tooltip as TooltipPrimitive } from "radix-ui";
import { Check, CircleHelp } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { cn } from "./cn";

/**
 * The field, and the one affordance that carries an explanation.
 *
 * D9: a control's caveat lives on the control, on hover or press, in one line.
 * If it does not fit one line it is documentation, not UI — so `Hint` has room
 * for a sentence and nothing more, and no field on this screen carries a
 * paragraph.
 */
export function Field({
  label,
  hint,
  children,
}: {
  readonly label: string;
  readonly hint?: string;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <div className="min-w-0">
      <div className="mb-1.5 flex items-center gap-1.5">
        <span className="text-2xs text-muted">{label}</span>
        {hint === undefined ? null : <Hint text={hint} />}
      </div>
      {children}
    </div>
  );
}

export function Hint({ text }: { readonly text: string }): ReactElement {
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>
        <button type="button" aria-label={text} className="inline-flex text-muted hover:text-muted">
          <CircleHelp className="size-3" />
        </button>
      </TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side="top"
          sideOffset={6}
          className="z-50 max-w-xs rounded-md border border-line bg-card px-2.5 py-1.5 text-2xs text-fg"
        >
          {text}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

export function TooltipScope({ children }: { readonly children: ReactNode }): ReactElement {
  return <TooltipPrimitive.Provider delayDuration={200}>{children}</TooltipPrimitive.Provider>;
}

export function Checkbox({
  checked,
  onCheckedChange,
  label,
}: {
  readonly checked: boolean;
  readonly onCheckedChange: (checked: boolean) => void;
  readonly label: string;
}): ReactElement {
  return (
    <CheckboxPrimitive.Root
      checked={checked}
      aria-label={label}
      onCheckedChange={(next): void => {
        onCheckedChange(next === true);
      }}
      className={cn(
        "peer size-4 shrink-0 rounded-sm border border-line bg-bg",
        "",
        "data-[state=checked]:border-amber data-[state=checked]:bg-amber",
        "outline-none focus-visible:ring-2 focus-visible:outline-amber"
      )}
    >
      <CheckboxPrimitive.Indicator className="grid place-content-center text-on-amber">
        <Check className="size-3" strokeWidth={3} />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}
