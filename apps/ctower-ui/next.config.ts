import { resolve } from "node:path";
import type { NextConfig } from "next";

/**
 * The retained empty shell has no data adapter, rewrites, proxy, or image
 * optimization. Pin the build root to this checkout so a worktree build cannot
 * silently adopt the primary checkout as its root.
 */
const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  turbopack: { root: resolve(import.meta.dirname, "..", "..") },
  typescript: { ignoreBuildErrors: false },
};

export default config;
