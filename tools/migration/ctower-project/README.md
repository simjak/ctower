# ctower-project deterministic source tool

This directory contains the isolated, one-time CT-I1.7B source tool. It reads a
reviewed synthetic closure, proves two independent canonical exports, plans only
the four frozen generated-client migration operations, and reconciles generated
read results. It has no source-write adapter and does not activate a live
cutover, fence, epoch, or product write path.

Run the focused proof with the repository verification interpreter:

```text
/srv/projects/ctower/.venv/bin/python -m pytest tests/modules/migration/source_tool -q
```

`main.py export` is the only command that reads source files. Paths are relative
to an explicit allowlisted root, every component is checked without following
symlinks, and only regular files are accepted. `main.py plan` is read-only and
emits canonical generated DTO batches. Mutation is available only through the
library's explicit `apply=True` generated-client workflow; its default is a
dry-run and the CT-I1.7B command line deliberately exposes no network transport.

Private Ed25519 material is supplied through a protected key-reference map. The
tool never generates signing keys, accepts a private key value on the command
line, or includes private material in an artifact or refusal.
