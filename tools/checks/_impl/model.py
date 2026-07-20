"""Private immutable policy and source models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Budget:
    warning: int
    failure: int


@dataclass(frozen=True, slots=True)
class OwnershipRule:
    name: str
    paths: tuple[str, ...]
    allowed_dependencies: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GeneratedPathPolicy:
    manifest_path: str
    output_root: str
    input_roots: tuple[str, ...]
    input_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    source_extensions: tuple[str, ...]
    module_roots: tuple[str, ...]
    excludes: tuple[str, ...]
    protected_roots: tuple[str, ...]
    forbidden_module_stems: tuple[str, ...]
    non_waivable_rules: tuple[str, ...]
    budgets: dict[str, Budget]
    ownership: tuple[OwnershipRule, ...]
    generated: GeneratedPathPolicy
    profiles: dict[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class FunctionMetric:
    name: str
    line: int
    logical_lines: int
    complexity: int
    nesting: int


@dataclass(frozen=True, slots=True)
class ClassMetric:
    name: str
    line: int
    public_methods: int


@dataclass(frozen=True, slots=True)
class ImportRef:
    module: str
    line: int


@dataclass(frozen=True, slots=True)
class SourceMetric:
    absolute_path: Path
    path: str
    logical_lines: int
    functions: tuple[FunctionMetric, ...]
    classes: tuple[ClassMetric, ...]
    public_exports: tuple[str, ...]
    imports: tuple[ImportRef, ...]
    parse_error: str | None = None


@dataclass(frozen=True, slots=True)
class ExceptionRecord:
    exception_id: str
    rule_id: str
    path: str
    temporary_limit: int
    owner: str
    reason: str
    ticket: str
    approver: str
    created_on: str
    expires_on: str
