# Repository setup

Set up a checkout to run ctower's verification gates. This prepares a development repository; it does not
install a ctower product runtime.

## Prerequisites

- Git.
- A Python verification environment. CI uses Python 3.13.14; project metadata permits Python `>=3.12,<3.15`
  while the product-runtime selection remains unresolved.
- Node 24 and pnpm 10.20.0 for the frozen browser workspace checks.
- `just`, Actionlint, and Gitleaks on `PATH` for the canonical local gates.
- Docker Compose when running `just verify`; the acceptance tests use it for disposable PostgreSQL fixtures.

The repository pins CI verification inputs and hashes. Those pins make verification reproducible; they do
not select a supported ctower runtime.

## Clone and install verification dependencies

```bash
git clone https://github.com/simjak/ctower.git
cd ctower
python3 -m pip install --require-hashes -r requirements/verify.txt
pnpm install --frozen-lockfile --ignore-scripts
```

Run the warm, non-mutating gate while developing:

```bash
just check
```

Run the complete clean-tree gate when the Docker Compose prerequisite is available:

```bash
just verify
```

`just verify` rejects a dirty candidate. It also runs complete-history secret scanning, so use only a
candidate you intend to validate.

## Next

Read [Exercise the development walking slice](../getting-started.md) for the test topology and its limits,
then the [Development guide](../contributing/development.md) before changing code or contracts.
