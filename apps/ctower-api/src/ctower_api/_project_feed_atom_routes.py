"""Authenticated Atom 1.0 rendering of the project movement view."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import cast

from fastapi import FastAPI, Request
from fastapi.responses import Response

from ctower_api._http_support import UnscopedAuthentication as _UnscopedAuthentication
from ctower_api._http_support import authenticate as _authenticate
from ctower_api._http_support import problem_response as _problem_response
from ctower_api._http_support import telemetry_context as _telemetry
from ctower_api._http_support import validation_problem as _validation_problem
from ctower_api.telemetry import TelemetryRecorder
from ctower_kernel.access import Access
from ctower_kernel.record import Record, RecordProblem
from ctower_kernel.record.movement_events import MovementEvent

__all__: tuple[str, ...] = ()

_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_DEFAULT_LIMIT = 50
_ATOM_NS = "http://www.w3.org/2005/Atom"
_NO_MOVEMENT_EPOCH = "1970-01-01T00:00:00Z"

ET.register_namespace("", _ATOM_NS)


def install_project_feed_atom_routes(
    app: FastAPI,
    access: Access,
    record: Record,
    recorder: TelemetryRecorder,
) -> None:
    """Install the Atom 1.0 twin of the movement view (same stream, same auth)."""

    @app.get("/v1/projects/{project_key}/movement.atom")
    def get_movement_atom(
        project_key: str,
        request: Request,
        cursor: int = 0,
        limit: int = _DEFAULT_LIMIT,
    ) -> Response:
        actor = _authenticate(
            access,
            recorder,
            request,
            required_scope=_UnscopedAuthentication.ALLOWED,
        )
        if isinstance(actor, RecordProblem):
            return _problem_response(actor)
        try:
            telemetry = _telemetry(request)
            parsed_project_key = _project_key(project_key)
        except ValueError:
            return _problem_response(_validation_problem())
        telemetry = telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
        )
        recorder.emit("access.authenticate", telemetry, outcome="ok", reason="authorized")
        outcome = record.event_audit.movement_events(
            actor, parsed_project_key, cursor=cursor, limit=limit, telemetry=telemetry
        )
        if isinstance(outcome, RecordProblem):
            return _problem_response(outcome)
        return Response(
            content=_atom_document(
                outcome.events,
                outcome.project_key,
                cursor=cursor,
                limit=limit,
                next_cursor=outcome.next_cursor,
            ),
            status_code=200,
            media_type="application/atom+xml",
        )


def _project_key(value: str) -> str:
    if _PROJECT_KEY.fullmatch(value) is None:
        raise ValueError("invalid project key")
    return value


def _atom_document(
    events: tuple[MovementEvent, ...],
    project_key: str,
    *,
    cursor: int,
    limit: int,
    next_cursor: int | None,
) -> bytes:
    feed = ET.Element(f"{{{_ATOM_NS}}}feed")
    ET.SubElement(feed, f"{{{_ATOM_NS}}}title").text = f"ctower movement: {project_key}"
    ET.SubElement(feed, f"{{{_ATOM_NS}}}id").text = f"urn:ctower:movement:{project_key}"
    ET.SubElement(
        feed, f"{{{_ATOM_NS}}}link", {"rel": "self", "href": _page_href(project_key, cursor, limit)}
    )
    if next_cursor is not None:
        ET.SubElement(
            feed,
            f"{{{_ATOM_NS}}}link",
            {"rel": "next", "href": _page_href(project_key, next_cursor, limit)},
        )
    ET.SubElement(feed, f"{{{_ATOM_NS}}}updated").text = _feed_updated(events)
    for event in events:
        entry = ET.SubElement(feed, f"{{{_ATOM_NS}}}entry")
        ET.SubElement(entry, f"{{{_ATOM_NS}}}id").text = f"urn:uuid:{event.event_id}"
        ET.SubElement(
            entry, f"{{{_ATOM_NS}}}title"
        ).text = f"workflow.changed: {event.from_stage} -> {event.to_stage}"
        ET.SubElement(entry, f"{{{_ATOM_NS}}}updated").text = _rfc3339(event.occurred_at)
        ET.SubElement(
            entry,
            f"{{{_ATOM_NS}}}link",
            {"rel": "alternate", "href": f"/v1/tickets/{event.ticket_id}/timeline"},
        )
    return cast(bytes, ET.tostring(feed, encoding="utf-8", xml_declaration=True))


def _page_href(project_key: str, cursor: int, limit: int) -> str:
    return f"/v1/projects/{project_key}/movement.atom?cursor={cursor}&limit={limit}"


def _feed_updated(events: tuple[MovementEvent, ...]) -> str:
    stamps = [_rfc3339(event.occurred_at) for event in events]
    return max(stamps) if stamps else _NO_MOVEMENT_EPOCH


def _rfc3339(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
