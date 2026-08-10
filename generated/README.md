# Generated artifacts

Do not edit files in this directory. Regenerate them from authored contracts with:

```text
python3 -m tools.codegen --root . --write
```

`python/ctower_client` and `typescript/ctower-client` are strict OpenAPI client/model
packages. The Python operation registry is the complete closed boundary inventory for the
protected CLI and browser-only routes; it is not an arbitrary dispatcher. Both clients expose
the authored JSON client subset and validate operation-specific success and problem payloads
at runtime before returning them. Browser-session and streaming operations explicitly remain
browser-bound and are not emitted as bearer clients.

`python/ctower_contracts` vendors authored JSON schemas into a local-only runtime resource.
Resolution rejects network references and paths that escape the authored contract tree.

Both packages and `ctower_contracts/schemas.json` are included in the verified development
wheel. Generated presence does not establish a stable external API, supported package release,
deployment, or runtime/effect activation. Exact source/output digests are owned by
`.generated-manifest.json`.
