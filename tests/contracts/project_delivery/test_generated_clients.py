"""Generated clients preserve generic Project Delivery rows exactly."""

from __future__ import annotations

import json
from pathlib import Path

from ..http._generated_client_runtime import (
    compile_typescript_client,
    node_executable,
    python_client,
    run_command,
)
from ._fixture import DIGEST, project_delivery_view

__all__: tuple[str, ...] = ()


def test_generated_python_client_round_trips_assigned_and_signing_seats() -> None:
    payload = project_delivery_view()
    client = python_client(json.dumps(payload), status=200)

    model = client.get_project_delivery("quarterly-close")
    round_trip = model.model_dump(mode="json", by_alias=True)
    client.close()

    assert round_trip == payload
    slot = round_trip["rows"][0]["qualifying_stage_slots"][0]
    assert slot["assigned_seat"] == {
        "state": "assigned",
        "seat": {
            "seat_key": "preparer",
            "seat_label": "Preparer",
            "catalog_revision": {
                "catalog_key": "ledger.delivery-seats",
                "revision": 1,
                "content_digest": DIGEST,
            },
        },
    }
    assert slot["signing_seat"] == {
        "seat_key": "approver",
        "seat_label": "Approver",
        "catalog_revision": {
            "catalog_key": "ledger.delivery-seats",
            "revision": 1,
            "content_digest": DIGEST,
        },
    }


def test_generated_typescript_client_round_trips_assigned_and_signing_seats(
    tmp_path: Path,
) -> None:
    payload = project_delivery_view()
    compile_typescript_client(tmp_path)
    runner = tmp_path / "project-delivery-round-trip.mjs"
    runner.write_text(_typescript_runner(payload), encoding="utf-8")

    completed = run_command((node_executable(), str(runner)), cwd=tmp_path)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "project delivery round trip: passed"


def _typescript_runner(payload: dict[str, object]) -> str:
    return f"""
import {{ CtowerClient }} from "./index.js";

const payload = {json.dumps(payload, sort_keys=True)};
const canonical = (value) => {{
  if (Array.isArray(value)) return value.map(canonical);
  if (value !== null && typeof value === "object") {{
    return Object.fromEntries(
      Object.entries(value).sort(([left], [right]) => left.localeCompare(right))
        .map(([key, nested]) => [key, canonical(nested)]),
    );
  }}
  return value;
}};
const client = new CtowerClient({{
  baseUrl: "http://contract.invalid",
  telemetry: () => ({{}}),
  fetch: async (request) => {{
    if (new URL(request).pathname !== "/v1/projects/quarterly-close/delivery") {{
      throw new Error("configured project key was not preserved in the request");
    }}
    return new Response(JSON.stringify(payload), {{
      status: 200,
      headers: {{"content-type": "application/json"}},
    }});
  }},
}});
const roundTrip = await client.getProjectDelivery({{projectKey: "quarterly-close"}});
const slot = roundTrip.rows[0]?.qualifying_stage_slots[0];
if (slot?.assigned_seat.state !== "assigned") {{
  throw new Error("generated TypeScript client lost the assigned seat");
}}
if (
  slot.assigned_seat.seat.seat_key !== "preparer" ||
  slot.signing_seat?.seat_key !== "approver"
) throw new Error("generated TypeScript client changed carried seat identities");
if (
  JSON.stringify(canonical(roundTrip)) !==
  JSON.stringify(canonical(payload))
) throw new Error("generated TypeScript client changed the Project Delivery row");
console.log("project delivery round trip: passed");
""".lstrip()
