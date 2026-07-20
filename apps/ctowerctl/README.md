# ctowerctl boundary

The current development CLI is a thin online Adapter over the generated Python client. It supports
`bootstrap first-tenant` and `ticket create/show/assign`; mutation commands require a caller-supplied stable
command ID. Bootstrap capability and bearer authority are read as one line from stdin and never accepted in
arguments or environment variables.

Successful writes print the server's `durability_pending` result. An unreachable server exits nonzero and
prints `unsent` with the caller command ID; the CLI does not claim acceptance or queue a hidden write.
Encrypted offline spool/quarantine remains deferred. The CLI cannot bypass server authorization, validation,
or custody policy.
