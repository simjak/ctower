"""Cohesive policy evaluation over one parsed repository model."""

from __future__ import annotations

import fnmatch
from dataclasses import replace
from pathlib import Path

from tools.checks._impl.config import PolicyConfigurationError, load_exceptions, load_policy
from tools.checks._impl.generated import verify_generated_manifest
from tools.checks._impl.model import (
    Budget,
    ClassMetric,
    ExceptionRecord,
    FunctionMetric,
    ImportRef,
    OwnershipRule,
    PolicyConfig,
    SourceMetric,
)
from tools.checks._impl.source import analyze_source, discover_sources
from tools.checks.report import Finding, PolicyReport, Severity

__all__ = ["run_verification"]


def _finding(
    rule_id: str,
    metric: SourceMetric,
    message: str,
    severity: Severity,
    *,
    line: int | None = None,
    observed: int = 1,
    limit: int = 0,
) -> Finding:
    return Finding(rule_id, metric.path, message, severity, line, observed, limit)


def _budget_findings(
    rule_id: str,
    metric: SourceMetric,
    label: str,
    observed: int,
    budget: Budget,
    line: int | None = None,
) -> list[Finding]:
    if observed > budget.failure:
        severity = Severity.ERROR
        limit = budget.failure
    elif observed > budget.warning:
        severity = Severity.WARNING
        limit = budget.warning
    else:
        return []
    return [
        _finding(
            rule_id,
            metric,
            f"{label} is {observed}; limit is {limit}",
            severity,
            line=line,
            observed=observed,
            limit=limit,
        )
    ]


def _source_findings(metric: SourceMetric, policy: PolicyConfig) -> list[Finding]:
    if metric.parse_error is not None:
        return [_finding("source.parse", metric, metric.parse_error, Severity.ERROR)]
    findings = _budget_findings(
        "source.file-lines",
        metric,
        "authored logical file lines",
        metric.logical_lines,
        policy.budgets["file"],
    )
    for function in metric.functions:
        findings.extend(_function_findings(metric, function, policy))
    for class_metric in metric.classes:
        findings.extend(_class_findings(metric, class_metric, policy))
    findings.extend(
        _budget_findings(
            "source.public-exports",
            metric,
            "public exports",
            len(metric.public_exports),
            policy.budgets["public_exports"],
        )
    )
    if metric.absolute_path.stem in policy.forbidden_module_stems:
        findings.append(
            _finding(
                "architecture.catch-all-module",
                metric,
                f"module stem {metric.absolute_path.stem!r} is forbidden; "
                "name the cohesive decision",
                Severity.ERROR,
            )
        )
    return findings


def _function_findings(
    metric: SourceMetric, function: FunctionMetric, policy: PolicyConfig
) -> list[Finding]:
    checks = (
        ("source.function-lines", "logical lines", function.logical_lines, "function"),
        ("source.complexity", "complexity", function.complexity, "complexity"),
        ("source.nesting", "nesting", function.nesting, "nesting"),
    )
    return [
        item
        for rule_id, label, observed, budget_key in checks
        for item in _budget_findings(
            rule_id,
            metric,
            f"function {function.name} {label}",
            observed,
            policy.budgets[budget_key],
            function.line,
        )
    ]


def _class_findings(
    metric: SourceMetric, class_metric: ClassMetric, policy: PolicyConfig
) -> list[Finding]:
    return _budget_findings(
        "source.class-methods",
        metric,
        f"class {class_metric.name} public methods",
        class_metric.public_methods,
        policy.budgets["class_methods"],
        class_metric.line,
    )


def _owner_for_path(path: str, ownership: tuple[OwnershipRule, ...]) -> OwnershipRule | None:
    matches = [
        rule for rule in ownership if any(fnmatch.fnmatch(path, pattern) for pattern in rule.paths)
    ]
    return matches[0] if len(matches) == 1 else None


def _module_path(root: Path, module: str) -> str | None:
    relative = module.replace(".", "/")
    for candidate in (f"{relative}.py", f"{relative}/__init__.py"):
        if (root / candidate).is_file():
            return candidate
    return None


def _ownership_findings(root: Path, metric: SourceMetric, policy: PolicyConfig) -> list[Finding]:
    owner = _owner_for_path(metric.path, policy.ownership)
    findings: list[Finding] = []
    if (
        any(metric.path.startswith(f"{prefix.rstrip('/')}/") for prefix in policy.protected_roots)
        and owner is None
    ):
        findings.append(
            _finding(
                "architecture.unowned-source", metric, "source has no unique owner", Severity.ERROR
            )
        )
        return findings
    if owner is None:
        return findings
    dependencies: set[str] = set()
    for import_ref in metric.imports:
        dependency, import_findings = _evaluate_import(root, metric, owner, policy, import_ref)
        if dependency is not None:
            dependencies.add(dependency)
        findings.extend(import_findings)
    findings.extend(
        _budget_findings(
            "architecture.dependency-fanout",
            metric,
            "direct owned-module dependency fan-out",
            len(dependencies),
            policy.budgets["dependency_fanout"],
        )
    )
    return findings


def _evaluate_import(
    root: Path,
    metric: SourceMetric,
    owner: OwnershipRule,
    policy: PolicyConfig,
    import_ref: ImportRef,
) -> tuple[str | None, tuple[Finding, ...]]:
    target_path = _module_path(root, import_ref.module)
    target_owner = (
        _owner_for_path(target_path, policy.ownership) if target_path is not None else None
    )
    if target_owner is None or target_owner.name == owner.name:
        return None, ()
    findings: list[Finding] = []
    if target_owner.name not in owner.allowed_dependencies:
        findings.append(
            _finding(
                "architecture.dependency",
                metric,
                f"owner {owner.name} may not depend on {target_owner.name} via {import_ref.module}",
                Severity.ERROR,
                line=import_ref.line,
            )
        )
    private = any(
        part.startswith("_") and part != "__future__" for part in import_ref.module.split(".")
    )
    if private:
        findings.append(
            _finding(
                "architecture.private-import",
                metric,
                f"owner {owner.name} imports private module {import_ref.module}",
                Severity.ERROR,
                line=import_ref.line,
            )
        )
    return target_owner.name, tuple(findings)


def _apply_exceptions(
    findings: list[Finding],
    exceptions: tuple[ExceptionRecord, ...],
    non_waivable: tuple[str, ...],
) -> list[Finding]:
    used: set[str] = set()
    result: list[Finding] = []
    for finding in findings:
        updated, used_id = _apply_one_exception(finding, exceptions, non_waivable)
        result.append(updated)
        if used_id is not None:
            used.add(used_id)
    result.extend(
        Finding(
            rule_id="exception.unmatched",
            path=exception.path,
            message=f"exception {exception.exception_id} matches no active finding",
            severity=Severity.ERROR,
        )
        for exception in exceptions
        if exception.exception_id not in used
    )
    return result


def _apply_one_exception(
    finding: Finding,
    exceptions: tuple[ExceptionRecord, ...],
    non_waivable: tuple[str, ...],
) -> tuple[Finding, str | None]:
    exception = next(
        (
            item
            for item in exceptions
            if item.rule_id == finding.rule_id and item.path == finding.path
        ),
        None,
    )
    if exception is None or finding.severity is Severity.WARNING:
        return finding, None
    if finding.rule_id in non_waivable:
        return finding, None
    observed = finding.observed if finding.observed is not None else 1
    if observed > exception.temporary_limit:
        return finding, None
    updated = replace(
        finding,
        severity=Severity.WARNING,
        message=f"{finding.message}; temporarily allowed until {exception.expires_on}",
        exception_id=exception.exception_id,
    )
    return updated, exception.exception_id


def run_verification(root: Path, profile: str) -> PolicyReport:
    policy, configuration_report = _configuration(root, profile)
    if policy is None:
        if configuration_report is None:
            raise RuntimeError("configuration loader returned neither policy nor report")
        return configuration_report
    sources = tuple(analyze_source(root, path) for path in discover_sources(root, policy))
    findings = _evaluate_checks(root, policy, profile, sources)
    exceptions, exception_errors = load_exceptions(root)
    findings.extend(
        Finding("exception.invalid", "tools/checks/exceptions.yaml", error, Severity.ERROR)
        for error in exception_errors
    )
    findings = _apply_exceptions(findings, exceptions, policy.non_waivable_rules)
    ordered = tuple(
        sorted(findings, key=lambda item: (item.path, item.line or 0, item.rule_id, item.message))
    )
    return PolicyReport(profile=profile, scanned_files=len(sources), findings=ordered)


def _configuration(root: Path, profile: str) -> tuple[PolicyConfig | None, PolicyReport | None]:
    try:
        policy = load_policy(root)
    except PolicyConfigurationError as error:
        report = PolicyReport(
            profile=profile,
            scanned_files=0,
            findings=(
                Finding("policy.invalid", "tools/checks/policy.toml", str(error), Severity.ERROR),
            ),
        )
        return None, report
    if profile not in policy.profiles:
        report = PolicyReport(
            profile=profile,
            scanned_files=0,
            findings=(
                Finding(
                    "policy.profile",
                    "tools/checks/policy.toml",
                    f"unknown profile {profile}",
                    Severity.ERROR,
                ),
            ),
        )
        return None, report
    return policy, None


def _evaluate_checks(
    root: Path,
    policy: PolicyConfig,
    profile: str,
    sources: tuple[SourceMetric, ...],
) -> list[Finding]:
    findings: list[Finding] = []
    checks = policy.profiles[profile]
    if "source" in checks:
        findings.extend(item for metric in sources for item in _source_findings(metric, policy))
    if "ownership" in checks:
        findings.extend(
            item for metric in sources for item in _ownership_findings(root, metric, policy)
        )
    if "generated" in checks:
        findings.extend(verify_generated_manifest(root, policy.generated))
    return findings
