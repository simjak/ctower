"""AC-PD-10: a checkpoint's delivery-surface declaration is three explicit states."""

from __future__ import annotations

import pytest

from ctower_kernel.projections import (
    BoardDeliverySurfaceAvailability,
    BoardDeliverySurfaceState,
)
from ctower_kernel.projections.project_delivery import (
    CheckpointDefinition,
    DeliveryState,
    DeliverySurfaceDeclaration,
    SurfaceDeclarationState,
    SurfaceEnvironmentsField,
    SurfaceIdentityField,
    delivery_surface_from_columns,
)

__all__: tuple[str, ...] = ()

_APPLICABLE_STATES = frozenset({DeliveryState.PLANNED, DeliveryState.DONE})
_EXPLICIT_STATE_COUNT = 3


def test_delivery_surface_declaration_reads_three_explicit_states() -> None:
    """Undeclared, declared-absent, and declared-present never collapse into each other."""

    undeclared = delivery_surface_from_columns(None, None, None)
    assert undeclared.landing_boundary.state is SurfaceDeclarationState.UNDECLARED
    assert undeclared.landing_boundary.identity is None
    assert undeclared.non_production_environments.state is SurfaceDeclarationState.UNDECLARED
    assert undeclared.non_production_environments.environments == ()

    absent = delivery_surface_from_columns(
        {"declared": "absent"},
        {"declared": "absent"},
        {"declared": "absent"},
    )
    assert absent.landing_boundary.state is SurfaceDeclarationState.DECLARED_ABSENT
    assert absent.landing_boundary.identity is None
    assert absent.non_production_environments.state is SurfaceDeclarationState.DECLARED_ABSENT
    assert absent.non_production_environments.environments == ()

    present = delivery_surface_from_columns(
        {"declared": "present", "identity": "release/train-284"},
        {"declared": "present", "environments": ["staging", "canary"]},
        {"declared": "present", "identity": "customer-facing-rollout"},
    )
    assert present.landing_boundary.state is SurfaceDeclarationState.DECLARED_PRESENT
    assert present.landing_boundary.identity == "release/train-284"
    assert present.non_production_environments.state is SurfaceDeclarationState.DECLARED_PRESENT
    assert present.non_production_environments.environments == ("staging", "canary")
    assert present.externally_effective_outcome.identity == "customer-facing-rollout"

    # The three states are pairwise distinct: no two collapse under equality.
    assert len({undeclared, absent, present}) == _EXPLICIT_STATE_COUNT


def test_surface_identity_field_cannot_carry_identity_while_undeclared_or_absent() -> None:
    """A mutation proof: only a declared-present field may carry an identity."""

    with pytest.raises(ValueError, match="present"):
        SurfaceIdentityField(SurfaceDeclarationState.UNDECLARED, identity="should not parse")
    with pytest.raises(ValueError, match="present"):
        SurfaceIdentityField(SurfaceDeclarationState.DECLARED_PRESENT, identity=None)


def test_surface_environments_field_cannot_carry_environments_while_not_present() -> None:
    with pytest.raises(ValueError, match="present"):
        SurfaceEnvironmentsField(SurfaceDeclarationState.DECLARED_ABSENT, environments=("staging",))
    with pytest.raises(ValueError, match="present"):
        SurfaceEnvironmentsField(SurfaceDeclarationState.DECLARED_PRESENT, environments=())


def test_checkpoint_definition_delivery_surface_defaults_undeclared_for_any_key() -> None:
    """Name-inference anti-fixture: the checkpoint key's spelling carries no signal."""

    for key in ("I1.7", "ctower.weird-Key_123", "a"):
        definition = CheckpointDefinition(
            key=key,
            label="Some checkpoint",
            outcome="Some outcome",
            accountable_owner="operator",
            criteria=("only-criterion",),
            applicable_states=_APPLICABLE_STATES,
        )
        assert definition.delivery_surface == DeliverySurfaceDeclaration()
        assert definition.delivery_surface.landing_boundary.state is (
            SurfaceDeclarationState.UNDECLARED
        )


def test_board_delivery_surface_availability_carries_checkpoint_only_while_qualifying() -> None:
    """A mutation proof: checkpoint_key and declaration are present together, or not at all."""

    no_checkpoint = BoardDeliverySurfaceAvailability(
        BoardDeliverySurfaceState.NO_QUALIFYING_CHECKPOINT
    )
    assert no_checkpoint.response_payload() == {"state": "no_qualifying_checkpoint"}

    qualifying = BoardDeliverySurfaceAvailability(
        BoardDeliverySurfaceState.QUALIFYING_CHECKPOINT,
        checkpoint_key="I1.7",
        declaration=delivery_surface_from_columns(None, None, None),
    )
    payload = qualifying.response_payload()
    assert payload["state"] == "qualifying_checkpoint"
    assert payload["checkpoint_key"] == "I1.7"
    assert payload["landing_boundary"] == {"state": "undeclared", "identity": None}

    with pytest.raises(ValueError, match="qualifies"):
        BoardDeliverySurfaceAvailability(BoardDeliverySurfaceState.QUALIFYING_CHECKPOINT)
    with pytest.raises(ValueError, match="qualifies"):
        BoardDeliverySurfaceAvailability(
            BoardDeliverySurfaceState.NO_QUALIFYING_CHECKPOINT,
            checkpoint_key="I1.7",
            declaration=delivery_surface_from_columns(None, None, None),
        )
