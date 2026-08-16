"""AC-CAT-01 admission checks for public repository content."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path

from tools.checks.report import Finding, Severity

__all__ = ["catalog_admission_findings"]

TENANT_CONTENT_REFUSAL = "tenant-catalog-content-in-public-repository"
_FIELD = "catalog_content"
_TENANT_VALUE = "tenant"
_YAML_MARKER = re.compile(
    rf"^\s*{re.escape(_FIELD)}\s*:\s*['\"]?{re.escape(_TENANT_VALUE)}['\"]?\s*(?:#.*)?$"
)
_JSON_MARKER = re.compile(
    rf"^\s*['\"]{re.escape(_FIELD)}['\"]\s*:\s*['\"]{re.escape(_TENANT_VALUE)}['\"]\s*,?\s*$"
)
_EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "node_modules",
        "site",
    }
)


def catalog_admission_findings(root: Path) -> tuple[Finding, ...]:
    """Refuse explicit tenant-content markers in the public repository tree."""

    findings: list[Finding] = []
    for path in _files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if _YAML_MARKER.fullmatch(line) or _JSON_MARKER.fullmatch(line):
                relative = path.relative_to(root).as_posix()
                findings.append(
                    Finding(
                        TENANT_CONTENT_REFUSAL,
                        relative,
                        f"{TENANT_CONTENT_REFUSAL}: explicit tenant catalog content marker",
                        Severity.ERROR,
                        line=line_number,
                        observed=1,
                        limit=0,
                    )
                )
    return tuple(findings)


def _files(root: Path) -> Iterator[Path]:
    for directory, names, filenames in os.walk(root, topdown=True, followlinks=False):
        names[:] = sorted(name for name in names if name not in _EXCLUDED_DIRECTORIES)
        for filename in sorted(filenames):
            path = Path(directory) / filename
            if path.is_file():
                yield path
