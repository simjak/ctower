"""Strict CompanyBundle file boundary and generated-client commands."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ValidationError
from ruamel.yaml import YAML

from ctower_client import CtowerClient
from ctower_client.models import (
    CompanyBundleApplyRequest,
    CompanyBundleDocument,
    CompanyBundleExportResult,
    CompanyBundleRequest,
)
from ctowerctl._command_types import MutationPayload
from ctowerctl._input import JsonValue, load_yaml_json

__all__: tuple[str, ...] = ()


def load_bundle(path: Path) -> CompanyBundleDocument:
    """Load and generated-model-validate one bounded desired-state document."""

    try:
        payload = load_yaml_json(path, label="bundle input")
        return CompanyBundleDocument.model_validate_json(
            json.dumps(payload, allow_nan=False, separators=(",", ":"))
        )
    except (TypeError, ValidationError, ValueError) as error:
        raise ValueError("bundle input does not match the authored contract") from error


def build_mutation(arguments: argparse.Namespace) -> MutationPayload:
    """Build the sole CompanyBundle mutation from one exact desired-state file."""

    request = CompanyBundleApplyRequest(
        bundle=load_bundle(arguments.bundle_file),
        expected_active_version=cast(int, arguments.expected_active_version),
        plan_digest=cast(str, arguments.plan_digest),
    )
    return MutationPayload(request=request, path_parameters={})


def execute_query(arguments: argparse.Namespace, client: CtowerClient) -> BaseModel:
    """Invoke one explicit CompanyBundle read-only operation."""

    cli_name = cast(str, arguments.cli_name)
    if cli_name == "company bundle export":
        return client.export_company_bundle()
    request = CompanyBundleRequest(bundle=load_bundle(arguments.bundle_file))
    if cli_name == "company bundle validate":
        return client.validate_company_bundle(request)
    if cli_name == "company bundle plan":
        return client.plan_company_bundle(request)
    raise ValueError("usage: unsupported CompanyBundle query")


def mutation_command_names() -> frozenset[str]:
    return frozenset({"company bundle apply"})


def query_command_names() -> frozenset[str]:
    return frozenset(
        {
            "company bundle validate",
            "company bundle plan",
            "company bundle export",
        }
    )


def export_yaml(result: CompanyBundleExportResult) -> str:
    """Render only desired state as deterministic block YAML with one trailing LF."""

    payload = cast(dict[str, JsonValue], result.bundle.model_dump(mode="json", by_alias=True))
    canonical = _ordered_bundle(payload)
    yaml = YAML(typ="safe", pure=True)
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.width = 4096
    stream = io.StringIO()
    yaml.dump(canonical, stream)
    return stream.getvalue().rstrip("\n") + "\n"


def _ordered_bundle(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    resources = cast(list[dict[str, JsonValue]], payload["resources"])
    assignments = cast(list[dict[str, JsonValue]], payload["assignments"])
    secret_refs = cast(list[dict[str, JsonValue]], payload["secret_binding_refs"])
    ordered_resources = [_ordered_resource(resource) for resource in resources]
    ordered_resources.sort(key=_resource_key)
    assignments.sort(key=_assignment_key)
    secret_refs.sort(key=lambda item: (str(item["name"]), str(item["reference_class"])))
    return {
        "schema": payload["schema"],
        "company": payload["company"],
        "resources": cast(JsonValue, ordered_resources),
        "assignments": cast(JsonValue, assignments),
        "secret_binding_refs": cast(JsonValue, secret_refs),
    }


def _ordered_resource(resource: dict[str, JsonValue]) -> dict[str, JsonValue]:
    component = cast(dict[str, JsonValue], resource["component"])
    compatibility = cast(dict[str, JsonValue], component["compatibility"])
    requires = cast(list[dict[str, JsonValue]], compatibility["requires"])
    provenance = cast(list[dict[str, JsonValue]], component["provenance"])
    requires.sort(key=_reference_key)
    provenance.sort(key=lambda item: (str(item["kind"]), str(item["source"]), str(item["digest"])))
    return resource


def _resource_key(resource: dict[str, JsonValue]) -> tuple[str, str, int, str]:
    component = cast(dict[str, JsonValue], resource["component"])
    return (
        str(component["kind"]),
        str(component["key"]),
        int(cast(int, component["revision"])),
        str(component["content_digest"]),
    )


def _assignment_key(assignment: dict[str, JsonValue]) -> tuple[str, str, tuple[str, str, int, str]]:
    return (
        str(assignment["subject"]),
        str(assignment["slot"]),
        _reference_key(cast(dict[str, JsonValue], assignment["component"])),
    )


def _reference_key(reference: dict[str, JsonValue]) -> tuple[str, str, int, str]:
    return (
        str(reference["kind"]),
        str(reference["key"]),
        int(cast(int, reference["revision"])),
        str(reference["content_digest"]),
    )
