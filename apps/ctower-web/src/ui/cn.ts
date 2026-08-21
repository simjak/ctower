import { clsx } from "clsx";
import type { ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** paperclip's own class composer, so a variant can be overridden at a call site. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
