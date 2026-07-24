# Documentation policy

Documentation helps the next developer or agent understand the current system without first reading the
full specification. It is part of the product boundary: a page that overclaims is a defect.

## Progressive disclosure

Start with scope, maturity, setup, and the current capability boundary. Put advanced architecture behind
explicit links to the canonical specification, architecture atlas, decision log, contracts, and source. Do
not copy those authoritative documents into tutorials or create a second source of truth.

## Code truth and current state

Code, contracts, tests, and accepted operational evidence decide what documentation may claim. Distinguish
development-fixture behaviour, verifier-only proof, planned work, and unsupported product surfaces. A
schema, package, test fixture, or roadmap entry is not a supported feature by itself.

Update relevant public documentation in the same pull request as a changed user-visible behaviour, contract,
configuration key, compatibility promise, or operational procedure. Preserve clear residuals rather than
writing around them.

## Examples

Label an example **Executable** only when the repository validates it or the page gives the exact validation
command and prerequisites. Otherwise label it illustrative and do not make it look like an install or
production procedure. Never put secrets, credentials, personal data, private URLs, or machine-local paths
in documentation.

## Release documentation

Before a release pull request, build the site with `just docs-check`, update guidance for each changed public
surface, and state compatibility, migration, rollback, and known exclusions where relevant. A successful
site build proves publication only; it does not prove a ctower runtime is operational.

For release mechanics, read [Releases](releases.md). For source ownership and verification, read the
[Development guide](development.md).
