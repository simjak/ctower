import { resolve } from "node:path";
import type { NextConfig } from "next";

/**
 * Read-only phase-1 operator surface. No rewrites, no proxy, no image
 * optimisation: every read is made server-side by the record adapter, and the
 * browser is never handed a base URL or a credential.
 *
 * `turbopack.root` is pinned to this boundary so a build run from inside a
 * worktree cannot silently adopt the parent checkout as its root.
 *
 * `agentRules` is off because it is not off by default: `next dev` writes its
 * own guidance into `AGENTS.md`/`CLAUDE.md` at the turbopack root, and at this
 * root those are the tracked engineering constitution and the symlink to it.
 * One `next dev` overwrote CLAUDE.md with a single `@AGENTS.md` line.
 */
const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  agentRules: false,
  turbopack: { root: resolve(import.meta.dirname, "..", "..") },
  typescript: { ignoreBuildErrors: false },
};

export default config;
