# Generated artifacts

Do not edit files in this directory. Regenerate them from authored contracts with:

```text
python3 -m tools.codegen --root . --write
```

`python/ctower_client` is the strict OpenAPI client/model package. Its generated operation
registry is the closed replay inventory for the protected CLI; it is not an arbitrary
dispatcher.

`python/ctower_contracts` vendors authored JSON schemas into a local-only runtime resource.
Resolution rejects network references and paths that escape the authored contract tree.

Both packages and `ctower_contracts/schemas.json` are included in the verified development
wheel. Generated presence does not establish a stable external API, supported package release,
deployment, or runtime/effect activation. Exact source/output digests are owned by
`.generated-manifest.json`.
