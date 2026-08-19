"""A runtime under a harness is not a harness, and this is where the seam says so.

This module exists to refuse a category. On this fleet there is no codex crew: codex models are
reached through a hermes profile's codex runtime, and naming a launcher after the model it was
asked for is exactly what produced a phantom harness value once already. `codex` remains a
legal harness value — for the direct CLI, which really is a harness with its own artifact,
config home, and credential lineage — and that legitimacy is precisely what makes the confusion
available: the same word names a harness in one route and a runtime in the other.

So the seam pins **two** references rather than one. `AttemptPin.harness_ref` is the harness
that is running, carried byte-for-byte as observed; `AttemptPin.profile_ref` is the
runtime/profile reference that carries the credential lineage. A route decides which is which,
and the decision is read off the spec of the harness that is actually running the runtime —
never off the runtime's own name, because a name is what is being disputed.

The consequence cuts through credentials too, which is why this matters more than taxonomy.
Codex under a hermes profile is one entry class inside that engine's own pool: configure and
observe, no special case. Codex as a direct CLI has one active account per config home and no
native layer at all, so ctower provides both — and if the routed runtime were allowed to mint
its own harness value, it would arrive carrying a second pool over the same single-use refresh
chains that the hermes pool is already rotating.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ctower_runner.codex.spec import CODEX_KEY
from ctower_runner_sdk.refusals import Refusal
from ctower_runner_sdk.spec import HarnessSpec
from ctower_runner_sdk.survey import LayerRoles, derive_roles

__all__ = [
    "CodexRoute",
    "RouteClass",
    "classify_route",
    "mint_refusal",
]

type RouteClass = Literal["runtime_under_harness", "direct_cli_harness"]


@dataclass(frozen=True, slots=True)
class CodexRoute:
    """One observed codex reference, resolved into the two references the seam pins.

    `harness_ref` is the harness whose spec, guard decision, and conformance column this
    attempt actually runs under. `runtime_ref` is the profile or config home that carries the
    credential lineage. They are separate fields because on one route they differ, and a model
    that keeps only one of them cannot tell a routed runtime from a harness of its own.
    """

    harness_ref: str
    runtime_ref: str
    route_class: RouteClass
    layers: LayerRoles

    def mints_a_harness_value(self) -> bool:
        """Whether this route is entitled to a harness value of its own."""

        return self.route_class == "direct_cli_harness"

    def to_mapping(self) -> dict[str, object]:
        return {
            "harness_ref": self.harness_ref,
            "layers": self.layers.to_mapping(),
            "route_class": self.route_class,
            "runtime_ref": self.runtime_ref,
        }


def classify_route(*, runtime_ref: str, spec: HarnessSpec) -> CodexRoute:
    """Resolve one runtime reference against the spec of the harness running it.

    The roles come from `derive_roles` on that harness's own answered survey in both branches.
    Reading them off the runtime's name instead is the mistake this whole module refuses: the
    routed runtime would inherit `provide` from a table row and start a second rotation policy
    over credentials another pool is already rotating.
    """

    if spec.key == CODEX_KEY:
        return CodexRoute(
            harness_ref=CODEX_KEY,
            runtime_ref=runtime_ref,
            route_class="direct_cli_harness",
            layers=derive_roles(spec.survey),
        )
    return CodexRoute(
        harness_ref=spec.key,
        runtime_ref=runtime_ref,
        route_class="runtime_under_harness",
        layers=derive_roles(spec.survey),
    )


def mint_refusal(route: CodexRoute, proposed_key: str) -> Refusal | None:
    """Refuse a harness value minted for something reached as a runtime. Zero registration.

    The proposed value is echoed byte-for-byte. An observed value nobody registered is
    displayed as observed rather than normalized down to something the registry recognizes,
    and that is doubly true here, where the value is being refused for what it names.
    """

    if route.mints_a_harness_value() or proposed_key == route.harness_ref:
        return None
    return Refusal(
        name="harness-runtime-not-a-harness",
        observed=(
            f"{proposed_key!r} was proposed as a harness while it is reached as a runtime "
            f"under {route.harness_ref!r}"
        ),
        meaning=(
            "a model or runtime routed through another harness has no artifact, config home, "
            "or credential lineage of its own to pin"
        ),
        action=(
            f"pin harness_ref {route.harness_ref!r} with runtime {route.runtime_ref!r}; "
            "register a harness only where a direct binding exists"
        ),
        detail=(
            ("proposed_harness_ref", proposed_key),
            ("resolved_harness_ref", route.harness_ref),
            ("runtime_ref", route.runtime_ref),
            ("route_class", route.route_class),
        ),
    )
