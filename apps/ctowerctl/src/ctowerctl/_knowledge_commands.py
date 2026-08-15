"""Generated-client builders and reads for registered knowledge documents."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import UUID

from pydantic import BaseModel

from ctower_client import CtowerClient
from ctower_client.models import KnowledgeAddRequest, KnowledgeScope
from ctowerctl._command_types import MutationPayload
from ctowerctl._input import read_text

__all__: tuple[str, ...] = ()

_BODY_MAX_BYTES = 1_048_576


def build_mutation(arguments: argparse.Namespace) -> MutationPayload:
    if cast(str, arguments.cli_name) != "knowledge add":
        raise ValueError("usage: unsupported knowledge mutation")
    scope = cast(str, arguments.scope)
    project_key = cast(str | None, arguments.project_key)
    _validate_scope(scope, project_key)
    body, source_ref, title = _content(arguments)
    recorded_at = cast(str | None, arguments.recorded_at)
    recorded_at_dt = datetime.fromisoformat(recorded_at) if recorded_at is not None else None
    return MutationPayload(
        request=KnowledgeAddRequest(
            body=body,
            project_key=project_key,
            recorded_at=recorded_at_dt,
            scope=KnowledgeScope(scope),
            source_ref=source_ref,
            title=title,
        ),
        path_parameters={},
    )


def _validate_scope(scope: str, project_key: str | None) -> None:
    if (scope == "org" and project_key is not None) or (scope == "project" and project_key is None):
        raise ValueError("usage: project scope requires exactly one project key")


def _content(arguments: argparse.Namespace) -> tuple[str | None, str | None, str | None]:
    body_file = cast(Path | None, arguments.body_file)
    source_ref = cast(str | None, arguments.source_ref)
    title = cast(str | None, arguments.title)
    if body_file is None:
        if source_ref is None or title is not None:
            raise ValueError("usage: source registration accepts source-ref without title")
        return None, source_ref, None
    if source_ref is not None or title is None:
        raise ValueError("usage: direct registration requires body-file and title")
    body = read_text(body_file, maximum_bytes=_BODY_MAX_BYTES, label="knowledge body")
    return body, None, title


def mutation_command_names() -> frozenset[str]:
    return frozenset({"knowledge add"})


def query_command_names() -> frozenset[str]:
    return frozenset({"knowledge get", "knowledge list"})


def execute_query(arguments: argparse.Namespace, client: CtowerClient) -> BaseModel:
    cli_name = cast(str, arguments.cli_name)
    scope = cast(str, arguments.scope)
    project_key = cast(str | None, arguments.project_key)
    if cli_name == "knowledge list":
        return client.list_knowledge_documents(scope=scope, project_key=project_key)
    if cli_name == "knowledge get":
        return client.get_knowledge_document(
            cast(UUID, arguments.document_id), scope=scope, project_key=project_key
        )
    raise ValueError("usage: unsupported knowledge query")
