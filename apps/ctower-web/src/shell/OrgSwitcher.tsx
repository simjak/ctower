import { Check, ChevronsUpDown, Plus } from "lucide-react";
import { DropdownMenu } from "radix-ui";
import type { ReactElement } from "react";
import { Mono } from "../ui/primitives";
import { cn } from "../ui/cn";

export interface Org {
  readonly name: string;
  readonly key: string;
}

/**
 * The company, at the top of the rail, with the way to another one under it.
 *
 * The reference console's shape, with two of its rows deliberately absent: there is no
 * invite and no sign out, because a tailnet-private console has one reader and
 * neither verb exists for them yet. Drawing either would be offering a control
 * over a thing that is not there.
 *
 * The chip is the company key rather than a short prefix. That console shows a
 * ticket prefix because it has one; ctower's record does not carry one, and the
 * key is the real thing that identifies this company.
 */
export function OrgSwitcher({ org }: { readonly org: Org }): ReactElement {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          className="flex w-full cursor-pointer items-center gap-2.5 px-4 py-3 text-left hover:bg-raised"
        >
          <Avatar name={org.name} />
          <span className="min-w-0 flex-1 truncate text-sm font-semibold text-fg">{org.name}</span>
          <ChevronsUpDown aria-hidden className="size-3.5 shrink-0 text-muted" />
        </button>
      </DropdownMenu.Trigger>

      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="start"
          sideOffset={4}
          className="z-50 w-[288px] rounded-md border border-line bg-card p-1"
        >
          <DropdownMenu.Label className="px-3 py-2 text-2xs tracking-[0.1em] text-muted">
            SWITCH COMPANY
          </DropdownMenu.Label>

          <DropdownMenu.Item className="flex items-center gap-2.5 rounded-sm px-3 py-2 outline-none data-[highlighted]:bg-raised">
            <Avatar name={org.name} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm text-fg">{org.name}</span>
              <Mono className="block truncate text-muted">{org.key}</Mono>
            </span>
            <Check aria-hidden className="size-3.5 shrink-0 text-ok" />
            <span className="sr-only">current</span>
          </DropdownMenu.Item>

          <DropdownMenu.Separator className="my-1 h-px bg-line" />

          <DropdownMenu.Item
            disabled
            className="flex items-center gap-2.5 rounded-sm px-3 py-2 text-muted outline-none"
          >
            <Plus aria-hidden className="size-3.5 shrink-0" />
            <span className="flex-1 truncate text-sm">Create new organization…</span>
            <span className="shrink-0 text-2xs">not built</span>
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function Avatar({ name }: { readonly name: string }): ReactElement {
  const initial = name.trim().slice(0, 1).toUpperCase();
  return (
    <span
      aria-hidden
      className={cn(
        "grid size-6 shrink-0 place-content-center rounded-sm",
        "bg-amber text-2xs font-bold text-on-amber"
      )}
    >
      {initial === "" ? "·" : initial}
    </span>
  );
}
