"""Codex credential meter and refusal-sink containment acceptance tests."""

from __future__ import annotations

from typing import cast

from _codex_fixtures import (
    _ADJACENT,
    _HEALTHY,
    _PROFILE,
    _STALE_GENERATION,
    _Ceremonies,
    _pool,
    _spec,
    _store,
)

from ctower_runner.codex.ceremonies import CeremonyOutcome
from ctower_runner_sdk.credentials import MeterObservation
from ctower_runner_sdk.refusals import Refusal

__all__: tuple[str, ...] = ()


def test_meter_projects_named_fields_and_preserves_the_authoritative_lease() -> None:
    pool = _pool()
    lease = pool.acquire(model_ref=_spec().probe.model_ref, tier=_PROFILE)
    assert not isinstance(lease, Refusal), lease

    hostile = cast(
        MeterObservation,
        {
            "event": "spawn",
            "model_ref": lease.model_ref,
            "lease_id": "caller-overwrite",
            "credential_canary": _ADJACENT,
        },
    )
    pool.meter(lease, hostile)

    row = pool.metered[-1]
    assert row["lease_id"] == str(lease.lease_id)
    assert row["event"] == "spawn"
    assert row["model_ref"] == lease.model_ref
    assert _ADJACENT not in str(row)


def test_ceremony_refusal_does_not_project_opaque_external_detail() -> None:
    refused = CeremonyOutcome(
        ceremony="codex-rotate-fallback",
        installed_identity=_HEALTHY,
        installed_generation=_STALE_GENERATION,
        hook_completed=True,
        refusal_name="stale-snapshot",
        detail=_ADJACENT,
    )

    outcome = _pool(_store(), _Ceremonies(refused)).rotate("observed a 401")

    assert isinstance(outcome, Refusal), outcome
    assert _ADJACENT not in str(outcome.to_mapping())
