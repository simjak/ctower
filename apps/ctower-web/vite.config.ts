import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * The development server, and the reason this app has a proxy at all.
 *
 * `docs/internal/SPEC.md` states it twice — the browser receives no API bearer,
 * and no API token reaches browser JavaScript. So the credential lives in this
 * Node process for the life of the server and nowhere else: the browser asks
 * its own origin for `/v1/...`, this proxy attaches the operator credential,
 * and the API remains the one authorization authority. There is no code path
 * that hands the token to the client bundle, and `import.meta.env` carries none.
 *
 * The credential is resolved by `serve-development.sh` from the same Secret
 * Service reference the instance itself uses; it is never written to a file,
 * never passed as an argument, and never committed. An unset credential refuses
 * to start rather than silently proxying an unauthenticated request, because a
 * blanket `401` renders as "the API refused you" and would be a lie about why.
 */
const apiOrigin = process.env.CTOWER_WEB_API_ORIGIN ?? "http://127.0.0.1:8091";
const credential = process.env.CTOWER_WEB_API_TOKEN;

if (credential === undefined || credential === "") {
  throw new Error(
    "CTOWER_WEB_API_TOKEN is unset. Start through apps/ctower-web/serve-development.sh, " +
      "which resolves it from the instance's own secret reference."
  );
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: process.env.CTOWER_WEB_HOST ?? "127.0.0.1",
    port: Number(process.env.CTOWER_WEB_PORT ?? "3141"),
    strictPort: true,
    // Tailnet-only exposure: the dev server binds the Tailscale interface and the
    // operator reaches it by MagicDNS name, so those names must pass Vite's host check.
    allowedHosts: ["agents-engineering-02.tail615f37.ts.net", "agents-engineering-02"],
    proxy: {
      // The generated client builds absolute paths from the authored contract,
      // so the proxy key is the contract's own prefix and nothing is rewritten.
      // The app's base URL is its own origin; the operation table stays the one
      // source of truth for every path.
      "/v1": {
        target: apiOrigin,
        changeOrigin: false,
        headers: { Authorization: `Bearer ${credential}` },
      },
    },
  },
});
