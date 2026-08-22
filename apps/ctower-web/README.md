# ctower-web boundary

One screen: the company-creation wizard. Compose a company bundle, validate it,
plan it, and hand the apply to the operator. Nothing else exists in this
application — no second route, no navigation, and no control that is not wired
to a real operation.

## The four steps are four operations

The left column is what the operator sees. The right column is this repository's
own vocabulary and **never renders**: a step is named after the job a person
does, not after the call behind it.

| Step, as drawn | Operation behind it | What it is |
| --- | --- | --- |
| Company details | `exportCompanyBundle` | seeds from the active bundle when one exists, else an empty template |
| Check the bundle | `validateCompanyBundle` | the real check; a refusal renders as a refusal |
| Review changes | `planCompanyBundle` | the real diff — adds, changes, removes |
| Apply | `applyCompanyBundle` | gated: it runs with the operator's own authority (D30) |

## The stack, and what ports from paperclip

React + Vite + Tailwind v4, the stack shape of `/srv/projects/paperclip-eval/ui`.
Per `docs/internal/design/operator-cockpit.md` D8 the port is **the token layer
only**: the tokens, the component vocabulary and the copy rules cross, the data
layer does not. The values are `DESIGN.md`'s, which the operator approved.

## The browser holds no credential

`docs/internal/SPEC.md` states it twice: the browser receives no API bearer, and
no API token reaches browser JavaScript. The browser therefore calls its own
origin at `/v1/...`; the development server attaches the operator credential,
which it resolves from the same Secret Service reference the instance itself
uses. Nothing in the client bundle, in `import.meta.env`, or in any rendered
state carries a token. Secrets on this screen are references, never values.

## The one network chokepoint

`src/api/bounded.ts` is the only place in this application that names `fetch`,
and the generated client is constructed with it, so every generated request
inherits per-attempt timeouts, a finite attempt count and deadline, jittered
capped backoff, a typed retry predicate, and a typed exhaustion.
`tests/repository/test_browser_network_chokepoint.py` derives that claim from
the tree and fails closed when a new call site appears.

## Running it

```
apps/ctower-web/serve-development.sh
CTOWER_WEB_HOST=<tailscale-address> CTOWER_WEB_PORT=<free-port> apps/ctower-web/serve-development.sh
```
