# Examples

Future examples demonstrate generated HTTP clients, runner components, and declarative packs without becoming a second contract source. Every example must compile or validate in `just verify`; examples never contain live credentials or mutable provider identifiers.

`first-tenant/bootstrap-request.example.json` is intentionally body-only and secret-free. The one-use capability travels from stdin in a protected header, and `Idempotency-Key` is a separate header; neither belongs in the example payload.
