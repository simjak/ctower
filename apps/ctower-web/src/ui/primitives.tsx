import { cva } from "class-variance-authority";
import type { VariantProps } from "class-variance-authority";
import type { ComponentProps, ReactElement } from "react";
import { cn } from "./cn";

/**
 * The component vocabulary, ported from paperclip's shadcn `new-york` set and
 * rewired to ctower's own token names (D3: port the mechanism, keep the marks).
 * One component per job, variants as props — paperclip's Principle 1.
 *
 * Nothing here names a colour or a type size directly: colours are tokens from
 * `styles/app.css` and sizes come from the type scale, never from an arbitrary
 * pixel value (paperclip Principle 2).
 */

const FOCUS =
  "outline-none focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:border-accent";

export function Card({ className, ...props }: ComponentProps<"section">): ReactElement {
  return (
    <section className={cn("rounded-lg border border-line bg-surface-2", className)} {...props} />
  );
}

export function CardHeader({ className, ...props }: ComponentProps<"header">): ReactElement {
  return (
    <header
      className={cn("flex items-center gap-3 border-b border-line px-5 py-3.5", className)}
      {...props}
    />
  );
}

export function CardTitle({ className, ...props }: ComponentProps<"h2">): ReactElement {
  return (
    <h2 className={cn("m-0 text-sm leading-none font-semibold text-ink", className)} {...props} />
  );
}

export function CardBody({ className, ...props }: ComponentProps<"div">): ReactElement {
  return <div className={cn("p-5", className)} {...props} />;
}

const buttonVariants = cva(
  cn(
    "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-md",
    "text-sm font-medium transition-colors duration-(--motion-duration-fast)",
    "disabled:pointer-events-none disabled:opacity-45 [&_svg]:size-4 [&_svg]:shrink-0",
    FOCUS
  ),
  {
    variants: {
      variant: {
        /** The one commit on a screen: paperclip's own `cta` weight. */
        cta: "bg-ink text-bg hover:bg-ink/90",
        primary: "bg-accent text-white hover:bg-accent-deep",
        outline: "border border-line-2 bg-surface-2 text-ink hover:bg-raised",
        ghost: "text-ink-2 hover:bg-raised hover:text-ink",
        danger: "bg-refuse text-white hover:bg-refuse-deep",
      },
      size: {
        base: "h-9 px-4",
        sm: "h-8 px-3 text-xs",
      },
    },
    defaultVariants: { variant: "outline", size: "base" },
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
        "h-9 w-full min-w-0 rounded-md border border-line-2 bg-bg px-3 text-sm text-ink",
        "placeholder:text-ink-4 transition-colors duration-(--motion-duration-fast)",
        "disabled:cursor-not-allowed disabled:opacity-55",
        FOCUS,
        className
      )}
      {...props}
    />
  );
}

const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium",
  {
    variants: {
      tone: {
        neutral: "border-line-2 bg-raised text-ink-2",
        proven: "chip chip-proven",
        refuse: "chip chip-refuse",
        warn: "chip chip-warn",
        info: "chip chip-info",
        unknown: "chip chip-unknown",
      },
    },
    defaultVariants: { tone: "neutral" },
  }
);

/** A state, never a sentence: two words is the budget. */
export function Badge({
  className,
  tone,
  ...props
}: ComponentProps<"span"> & VariantProps<typeof badgeVariants>): ReactElement {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

/** Machine values look machine-made: ids, digests, keys, counts, timestamps. */
export function Mono({ className, ...props }: ComponentProps<"span">): ReactElement {
  return <span className={cn("mono", className)} {...props} />;
}

/**
 * The screen's own head: what this is, what state it is in, and the one action
 * that leaves it. Paperclip puts the title, the subtitle and the action cluster
 * on one line at the top of the content column, and a screen without one reads
 * as a fragment rather than a page.
 */
export function PageHead({
  title,
  subtitle,
  children,
}: {
  readonly title: string;
  readonly subtitle: ComponentProps<"span">["children"];
  readonly children?: ComponentProps<"div">["children"];
}): ReactElement {
  return (
    <div className="mb-5 flex flex-wrap items-start gap-3">
      <div className="min-w-0 flex-1">
        <h1 className="m-0 text-2xl leading-tight font-semibold tracking-[-0.01em] text-ink">
          {title}
        </h1>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-ink-3">{subtitle}</div>
      </div>
      {children === undefined ? null : <div className="flex items-center gap-2">{children}</div>}
    </div>
  );
}
