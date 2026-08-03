"""Executable shim for the record-backed landing-boundary check."""

from tools.landing_boundary.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
