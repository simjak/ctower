import { Buffer } from "node:buffer";
import { timingSafeEqual } from "node:crypto";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import type { Plugin } from "vite";

/**
 * The development server, and the two authorities it holds.
 *
 * `docs/internal/SPEC.md` states it twice — the browser receives no API bearer,
 * and no API token reaches browser JavaScript. So the operator credential lives
 * in this Node process for the life of the server and nowhere else: the browser
 * asks its own origin for `/v1/...`, this proxy attaches the credential, and the
 * API remains the one authorization authority. There is no code path that hands
 * the token to the client bundle, and `import.meta.env` carries none.
 *
 * That arrangement makes the server itself operator authority for anyone who can
 * reach the port. On a loopback bind that is the operator; bound to the tailnet
 * so the operator can walk the wizard from a laptop, it is every host on the
 * tailnet. So the server admits nobody without a session token it prints at
 * startup and the operator pastes once. The token is admission to *this process*
 * and is stripped before anything is forwarded — it is not the API bearer, it
 * carries no authority at the API, and possessing it proves only that its holder
 * could read this server's own terminal.
 *
 * Both requirements are checked when the server starts serving, not when this
 * file is imported, so `vite build` produces the bundle on any host — a package
 * that cannot be built without a live credential cannot be built by a gate.
 */

const SESSION_HEADER = "x-ctower-web-session";
/** How a refusal from this server is told apart from a refusal by the API. */
const GATE_HEADER = "x-ctower-web-gate";
const CHECK_PATH = "/__ctower-web-session";

const apiOrigin = process.env.CTOWER_WEB_API_ORIGIN ?? "http://127.0.0.1:8091";

function required(name: string): string {
  const value = process.env[name];
  if (value === undefined || value === "") {
    throw new Error(
      `${name} is unset. Start through apps/ctower-web/serve-development.sh, which resolves ` +
        "the operator credential from the instance's own secret reference and mints a session token."
    );
  }
  return value;
}

function admits(offered: unknown, expected: string): boolean {
  if (typeof offered !== "string") {
    return false;
  }
  const held = Buffer.from(offered, "utf8");
  const wanted = Buffer.from(expected, "utf8");
  return held.length === wanted.length && timingSafeEqual(held, wanted);
}

/**
 * The admission gate, installed ahead of the proxy.
 *
 * A `configureServer` hook runs before Vite adds its own middlewares, so this is
 * the first thing an API-bound request meets. Nothing reaches the proxy — and so
 * nothing acquires the operator credential — without the session token.
 */
function admission(): Plugin {
  let expected = "";
  return {
    name: "ctower-web-admission",
    apply: "serve",
    configureServer(server) {
      required("CTOWER_WEB_API_TOKEN");
      expected = required("CTOWER_WEB_SESSION_TOKEN");
      server.middlewares.use((request, response, next) => {
        const path = request.url ?? "";
        if (path !== CHECK_PATH && !path.startsWith("/v1")) {
          next();
          return;
        }
        if (!admits(request.headers[SESSION_HEADER], expected)) {
          response.statusCode = 401;
          response.setHeader(GATE_HEADER, "refused");
          response.setHeader("content-type", "application/json");
          response.end(
            JSON.stringify({
              gate: "refused",
              detail: "This server admits only the session token it printed at startup.",
            })
          );
          return;
        }
        // Admission ends here. The token is this server's own and travels no
        // further; the API sees the operator credential and nothing else.
        delete request.headers[SESSION_HEADER];
        if (path === CHECK_PATH) {
          response.statusCode = 204;
          response.end();
          return;
        }
        next();
      });
    },
  };
}

export default defineConfig({
  plugins: [admission(), react(), tailwindcss()],
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
        configure: (proxy): void => {
          proxy.on("proxyReq", (outbound) => {
            outbound.setHeader("authorization", `Bearer ${required("CTOWER_WEB_API_TOKEN")}`);
          });
        },
      },
    },
  },
});
