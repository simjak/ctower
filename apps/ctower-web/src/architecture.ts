export type PrimarySurface = "analytics" | "board" | "fleet" | "home" | "ticket";

export const primarySurfaces = [
  "home",
  "board",
  "ticket",
  "fleet",
  "analytics",
] as const satisfies readonly PrimarySurface[];
