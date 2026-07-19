"""Load and validate repository policy configuration once."""

from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from tools.checks._impl.model import (
    Budget,
    ExceptionRecord,
    GeneratedPathPolicy,
    OwnershipRule,
    PolicyConfig,
)

__all__ = ["PolicyConfigurationError", "load_exceptions", "load_policy"]


class PolicyConfigurationError(ValueError):
    """The authored repository policy is invalid or incomplete."""


_MAX_EXCEPTION_DAYS = 30


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PolicyConfigurationError(f"{label} must be a mapping")
    return value


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PolicyConfigurationError(f"{label} must be a list of strings")
    return tuple(value)


def _budget(value: object, label: str) -> Budget:
    table = _mapping(value, label)
    warning = table.get("warning")
    failure = table.get("failure")
    if not isinstance(warning, int) or not isinstance(failure, int) or warning >= failure:
        raise PolicyConfigurationError(f"{label} needs integer warning < failure")
    return Budget(warning=warning, failure=failure)


def _repository_paths(value: object, label: str) -> tuple[str, ...]:
    values = _strings(value, label)
    if len(values) != len(set(values)):
        raise PolicyConfigurationError(f"{label} must not contain duplicates")
    for item in values:
        path = PurePosixPath(item)
        if not path.parts or path.is_absolute() or ".." in path.parts or str(path) != item:
            raise PolicyConfigurationError(
                f"{label} entries must be normalized repository-relative paths"
            )
    return values


def _generated_policy(value: Mapping[str, Any]) -> GeneratedPathPolicy:
    required = {"manifest", "output_root", "input_roots", "input_files"}
    if set(value) != required:
        raise PolicyConfigurationError(f"generated fields must be exactly {sorted(required)}")
    manifest = _repository_paths([value["manifest"]], "generated.manifest")[0]
    output_root = _repository_paths([value["output_root"]], "generated.output_root")[0]
    input_roots = _repository_paths(value["input_roots"], "generated.input_roots")
    input_files = _repository_paths(value["input_files"], "generated.input_files")
    if output_root != "generated":
        raise PolicyConfigurationError("generated.output_root must be canonical 'generated'")
    output_path = PurePosixPath(output_root)
    if not PurePosixPath(manifest).is_relative_to(output_path) or manifest == output_root:
        raise PolicyConfigurationError("generated.manifest must be below generated.output_root")
    if any(PurePosixPath(path).is_relative_to(output_path) for path in input_roots + input_files):
        raise PolicyConfigurationError(
            "generated inputs must be authored paths outside output_root"
        )
    return GeneratedPathPolicy(
        manifest_path=manifest,
        output_root=output_root,
        input_roots=input_roots,
        input_files=input_files,
    )


def load_policy(root: Path) -> PolicyConfig:
    policy_path = root / "tools/checks/policy.toml"
    try:
        data = tomllib.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise PolicyConfigurationError(f"cannot load {policy_path}: {error}") from error
    source = _mapping(data.get("source"), "source")
    architecture = _mapping(data.get("architecture"), "architecture")
    generated = _mapping(data.get("generated"), "generated")
    budget_data = _mapping(data.get("budgets"), "budgets")
    profiles_data = _mapping(data.get("profiles"), "profiles")
    ownership_data = data.get("ownership")
    if not isinstance(ownership_data, list):
        raise PolicyConfigurationError("ownership must be an array of tables")
    ownership = tuple(
        OwnershipRule(
            name=str(_mapping(item, "ownership entry")["name"]),
            paths=_strings(_mapping(item, "ownership entry")["paths"], "ownership.paths"),
            allowed_dependencies=_strings(
                _mapping(item, "ownership entry").get("allowed_dependencies", []),
                "ownership.allowed_dependencies",
            ),
        )
        for item in ownership_data
    )
    return PolicyConfig(
        source_extensions=_strings(source.get("extensions"), "source.extensions"),
        excludes=_strings(source.get("exclude"), "source.exclude"),
        protected_roots=_strings(source.get("protected_roots"), "source.protected_roots"),
        forbidden_module_stems=_strings(
            architecture.get("forbidden_module_stems"), "architecture.forbidden_module_stems"
        ),
        non_waivable_rules=_strings(
            architecture.get("non_waivable_rules"), "architecture.non_waivable_rules"
        ),
        budgets={name: _budget(value, f"budgets.{name}") for name, value in budget_data.items()},
        ownership=ownership,
        generated=_generated_policy(generated),
        profiles={
            name: _strings(value, f"profiles.{name}") for name, value in profiles_data.items()
        },
    )


def load_exceptions(root: Path) -> tuple[tuple[ExceptionRecord, ...], tuple[str, ...]]:
    path = root / "tools/checks/exceptions.yaml"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return (), (f"cannot load {path}: {error}",)
    if not isinstance(data, dict) or data.get("schema") != "ctower.repository-exceptions/v1":
        return (), ("exception store must use ctower.repository-exceptions/v1",)
    entries = data.get("exceptions")
    if not isinstance(entries, list):
        return (), ("exceptions must be a list",)
    records: list[ExceptionRecord] = []
    errors: list[str] = []
    for index, entry in enumerate(entries):
        record, entry_errors = _parse_exception(entry, index)
        errors.extend(entry_errors)
        if record is not None:
            records.append(record)
    return tuple(records), tuple(errors)


_EXCEPTION_FIELDS = {
    "id",
    "rule",
    "path",
    "temporary_limit",
    "owner",
    "reason",
    "ticket",
    "approver",
    "created_on",
    "expires_on",
}


def _parse_exception(entry: object, index: int) -> tuple[ExceptionRecord | None, tuple[str, ...]]:
    if not isinstance(entry, dict) or set(entry) != _EXCEPTION_FIELDS:
        message = f"exceptions[{index}] must contain exactly {sorted(_EXCEPTION_FIELDS)}"
        return None, (message,)
    try:
        created = date.fromisoformat(str(entry["created_on"]))
        expires = date.fromisoformat(str(entry["expires_on"]))
        temporary_limit = int(entry["temporary_limit"])
    except (TypeError, ValueError) as error:
        return None, (f"exceptions[{index}] has invalid date or limit: {error}",)
    errors = _exception_bound_errors(index, created, expires, temporary_limit)
    if errors:
        return None, errors
    return (
        ExceptionRecord(
            exception_id=str(entry["id"]),
            rule_id=str(entry["rule"]),
            path=str(entry["path"]),
            temporary_limit=temporary_limit,
            owner=str(entry["owner"]),
            reason=str(entry["reason"]),
            ticket=str(entry["ticket"]),
            approver=str(entry["approver"]),
            created_on=created.isoformat(),
            expires_on=expires.isoformat(),
        ),
        (),
    )


def _exception_bound_errors(
    index: int, created: date, expires: date, temporary_limit: int
) -> tuple[str, ...]:
    errors: list[str] = []
    if expires < datetime.now(UTC).date():
        errors.append(f"exceptions[{index}] expired on {expires.isoformat()}")
    if (expires - created).days > _MAX_EXCEPTION_DAYS or expires < created:
        errors.append(f"exceptions[{index}] expiry must be 0..30 days after creation")
    if temporary_limit < 1:
        errors.append(f"exceptions[{index}] temporary_limit must be positive")
    return tuple(errors)
