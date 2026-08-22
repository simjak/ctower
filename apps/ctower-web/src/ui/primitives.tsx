import { cva } from "class-variance-authority";
import type { VariantProps } from "class-variance-authority";
import type { ComponentProps, ReactElement } from "react";
import { cn } from "./cn";

/**
 * The component vocabulary, bound to `DESIGN.md`.
 *
 * Nothing here names a colour, a size or a radius directly — they come from the
 * token layer and from the closed seven-step scale. Two of that file's rules
 * show up here as absences rather than as code: there is no transition on a
 * hover, because stillness is the brand and hover choreography is not real work
 * moving; and there is no blue variant, because blue does not exist here.
 */

export function Card({ className, ...props }: ComponentProps<"section">): ReactElement {
  return <section className={cn("rounded-md border border-line bg-card", className)} {...props} />;
}

export function CardHeader({ className, ...props }: ComponentProps<"header">): ReactElement {
  return (
    <header
      className={cn("flex items-center gap-3 border-b border-line px-4 py-3", className)}
      {...props}
    />
  );
}

export function CardTitle({ className, ...props }: ComponentProps<"h2">): ReactElement {
  return <h2 className={cn("m-0 text-md leading-none font-semibold", className)} {...props} />;
}

export function CardBody({ className, ...props }: ComponentProps<"div">): ReactElement {
  return <div className={cn("p-4", className)} {...props} />;
}

/**
 * One primary per screen. The primary is the amber fill carrying `--on-amber`;
 * a destructive action is an outline that names its consequence, rather than a
 * red block shouting before the operator has read anything.
 */
const buttonVariants = cva(
  cn(
    "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 whitespace-nowrap",
    "rounded-sm border border-transparent text-sm font-semibold",
    "disabled:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
    // A control that is not yet armed says so by going quiet, not by wearing a
    // dimmed version of its own fill.
    "disabled:border-line disabled:bg-transparent disabled:text-muted disabled:opacity-55"
  ),
  {
    variants: {
      variant: {
        // The preview flips the label to white on hover; that measures 3.56:1 on
        // `--amber-strong`, under AA for 13.5px bold. Keeping `--on-amber` across
        // both ends of the ramp measures 5.21:1 and changes no hue.
        primary: "bg-amber text-on-amber hover:bg-amber-strong",
        ghost: "border-line bg-transparent text-fg hover:bg-raised",
        quiet: "text-muted hover:bg-raised hover:text-fg",
        danger: "border-danger bg-transparent text-danger",
      },
      size: {
        base: "h-9 px-4",
        sm: "h-7 px-2.5 text-xs",
      },
    },
    defaultVariants: { variant: "ghost", size: "base" },
  }
);

export function Button({
  className,
  variant,
  size,
  ...props
}: ComponentProps<"button"> & VariantProps<typeof buttonVariants>): ReactElement {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

export function Input({ className, ...props }: ComponentProps<"input">): ReactElement {
  return (
    <input
      className={cn(
        "h-9 w-full min-w-0 rounded-sm border border-line bg-bg px-3 text-sm text-fg",
        "placeholder:text-muted disabled:cursor-not-allowed disabled:opacity-50",
        "focus:border-transparent focus:outline-2 focus:outline-offset-0 focus:outline-amber",
        className
      )}
      {...props}
    />
  );
}

const chipVariants = cva("chip", {
  variants: {
    tone: { neutral: "", amber: "chip-amber", ok: "chip-ok", danger: "chip-danger" },
  },
  defaultVariants: { tone: "neutral" },
});

/** A state, never a sentence: two words is the budget. */
export function Chip({
  className,
  tone,
  ...props
}: ComponentProps<"span"> & VariantProps<typeof chipVariants>): ReactElement {
  return <span className={cn(chipVariants({ tone }), className)} {...props} />;
}

/** Machine-owned text: keys, digests, ports, refs, counts. */
export function Mono({ className, ...props }: ComponentProps<"span">): ReactElement {
  return <span className={cn("mono", className)} {...props} />;
}

/**
 * A page's own head: what this is, one line of what it is for, and the state it
 * is in. No hero, no marketing voice — the title is 22px and the screen gets on
 * with it.
 */
export function PageHead({
  title,
  subtitle,
  children,
}: {
  readonly title: string;
  readonly subtitle?: ComponentProps<"span">["children"];
  readonly children?: ComponentProps<"div">["children"];
}): ReactElement {
  return (
    <div className="mb-4 flex flex-wrap items-start gap-3">
      <div className="min-w-0 flex-1">
        <h1 className="m-0 text-xl leading-tight font-bold tracking-[-0.02em]">{title}</h1>
        {subtitle === undefined ? null : (
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
            {subtitle}
          </div>
        )}
      </div>
      {children === undefined ? null : <div className="flex items-center gap-2">{children}</div>}
    </div>
  );
}
