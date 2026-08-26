import type { ReactElement } from "react";
import { cn } from "../ui/cn";
import { Mono } from "../ui/primitives";
import type { Repository } from "./read";

/**
 * Where a project's code is — and, when this console can address the host, the
 * way to it.
 *
 * Nothing machine-owned reaches the surface here. The row says the repository's
 * name, the hover says which site it opens, and the recorded reference — scheme,
 * host and the commit behind it — stays in the reader. A person cannot act on
 * forty hex characters, so they are not put in front of one.
 *
 * A host with no address is drawn as text. Turning an unknown host into a URL
 * would be this screen inventing a domain the record never named, and a dead
 * link is worse than a plain fact.
 *
 * The ink is the caller's and nothing else is. A company row carries this as a
 * supporting fact under a name and wants it quiet; a project's Codebase card
 * carries it as the row's own answer and wants it read. What may not vary is
 * the rest — the mark, the label, and what happens when the host has no address
 * — because those are what make one repository look like one repository
 * wherever it is drawn.
 */
export function RepositoryLink({
  repository,
  className,
}: {
  readonly repository: Repository;
  /** The ink and the spacing this row wants; never a display or a layout. */
  readonly className?: string;
}): ReactElement {
  // An addressable repository has both an address and a name for the site it
  // sits on; a host the reader could not place has neither.
  if (repository.href === null || repository.site === null) {
    return <Mono className={cn("block truncate", className)}>{repository.label}</Mono>;
  }

  return (
    <a
      href={repository.href}
      target="_blank"
      rel="noreferrer"
      title={`Open on ${repository.site}`}
      className={cn(
        "inline-flex max-w-full items-center gap-1.5 hover:text-amber-ink hover:underline",
        className
      )}
    >
      {repository.host === "github" ? <GitHubMark /> : null}
      <Mono className="truncate">{repository.label}</Mono>
    </a>
  );
}

/**
 * GitHub's own mark, authored here rather than imported.
 *
 * `lucide-react` — the icon set `DESIGN.md` names — carries no brand glyphs at
 * all, and a brand mark is not a state mark, so it does not belong in
 * `ui/marks.tsx` beside the six the CLI prints. It is one path in `currentColor`
 * at lucide's own 24-unit box, so it inherits the ink and the size of every icon
 * beside it.
 */
function GitHubMark(): ReactElement {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      fill="currentColor"
      className="size-3.5 shrink-0"
      focusable="false"
    >
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
    </svg>
  );
}
