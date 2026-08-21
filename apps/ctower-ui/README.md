# ctower-ui — retained empty shell

`ctower-ui` is the small Next.js shell reserved for the future company-creation
wizard. It is intentionally not the read-only product UI that was removed in
R3129 and it is not `apps/ctower-web`.

The shell contains the shared routing frame, the approved theme/token stylesheet
under `design-reference/`, and exactly one rendered route:

- `/setup` — `Company setup — feature 1, building`

There are no record reads, mutations, product pages, browser dogfood controls,
or product-surface claims in this app. The retained `design-reference/` files are
mockup inputs and are not runtime data sources.

Run the shell locally with:

```text
pnpm --filter @ctower/ui dev
```

Build and typecheck it with:

```text
pnpm --filter @ctower/ui build
pnpm --filter @ctower/ui typecheck
```
