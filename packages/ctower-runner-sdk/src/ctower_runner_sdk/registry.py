"""What may register, and what may publish.

Registration is where `never both` is enforced, because it is the only place that can see a
binding's answered survey and its declared roles at the same time. Publication is separate
and stricter: the public Seam publishes only when two real bindings plus one deterministic
fault-injection fake pass one shared conformance suite. Seven candidate adapters do not
earn it faster, and one real binding does not earn it at all.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from ctower_runner_sdk.refusals import Refusal
from ctower_runner_sdk.spec import HarnessSpec, parse_harness_spec
from ctower_runner_sdk.survey import LayerRoles, derive_roles

__all__ = [
    "REQUIRED_REAL_BINDINGS",
    "BindingClass",
    "HarnessRegistry",
    "RegistrationAuthority",
    "RegistrationRoute",
    "RoleRow",
]

type BindingClass = Literal["real", "fault_injection_fake"]


class RegistrationRoute(Protocol):
    """One route derived from a trusted parent-harness registration authority."""

    @property
    def harness_ref(self) -> str: ...

    @property
    def authority_digest(self) -> str: ...

    def refusal_for(self, proposed_key: str) -> Refusal | None: ...


class RegistrationAuthority(Protocol):
    """The trusted parent context that constructs a route for one proposed key."""

    def route_for(self, proposed_key: str) -> RegistrationRoute: ...


# D10's earning rule, unchanged: two real Adapters plus one deterministic fake.
REQUIRED_REAL_BINDINGS = 2


@dataclass(frozen=True, slots=True)
class RoleRow:
    """One row of the per-layer role table, derived from a survey and not from a name."""

    harness_key: str
    binding_class: BindingClass
    roles: LayerRoles
    native_pool: bool
    native_fallback: bool

    def to_mapping(self) -> dict[str, object]:
        return {
            "binding_class": self.binding_class,
            "harness_key": self.harness_key,
            "native_fallback": self.native_fallback,
            "native_pool": self.native_pool,
            "roles": self.roles.to_mapping(),
        }


class HarnessRegistry:
    """The closed set of registered bindings, and the publication verdict over them."""

    def __init__(self, *, authorities: Sequence[RegistrationAuthority]) -> None:
        if not authorities:
            raise ValueError("HarnessRegistry requires trusted registration authorities")
        self._authorities = tuple(authorities)
        self._specs: dict[str, HarnessSpec] = {}
        self._classes: dict[str, BindingClass] = {}

    def register(
        self,
        document: Mapping[str, object],
        binding_class: BindingClass,
    ) -> HarnessSpec | Refusal:
        """Parse, resolve the survey, and admit — or refuse by exact name."""

        parsed = parse_harness_spec(document)
        if isinstance(parsed, Refusal):
            return parsed
        authority_refusal = self._authority_refusal(parsed)
        if authority_refusal is not None:
            return authority_refusal
        conflict = _semantic_refusal(parsed)
        if conflict is not None:
            return conflict
        duplicate = self._duplicate_refusal(parsed)
        if duplicate is not None:
            return duplicate
        self._specs[parsed.key] = parsed
        self._classes[parsed.key] = binding_class
        return parsed

    def _authority_refusal(self, spec: HarnessSpec) -> Refusal | None:
        first_route_refusal: Refusal | None = None
        first_digest_refusal: Refusal | None = None
        for authority in self._authorities:
            route = authority.route_for(spec.key)
            route_refusal = route.refusal_for(spec.key)
            if route_refusal is not None:
                first_route_refusal = first_route_refusal or route_refusal
                continue
            authority_refusal = _authority_refusal(spec, route)
            if authority_refusal is None:
                return None
            first_digest_refusal = first_digest_refusal or authority_refusal
        return (
            first_digest_refusal
            or first_route_refusal
            or Refusal(
                name="harness-registration-authority-unavailable",
                observed=f"no trusted authority admits HarnessSpec {spec.key!r}",
                meaning="registration requires a known parent-harness context before mutation",
                action="register the parent harness authority before registering this binding",
                detail=(("proposed_harness_ref", spec.key),),
            )
        )

    def resolve(self, harness_ref: str) -> HarnessSpec | Refusal:
        """Return the registered spec for an observed harness value, or refuse by name.

        The observed value is carried byte-for-byte into the refusal: an unknown harness is
        displayed as observed, never normalized down to something the registry recognizes.
        """

        spec = self._specs.get(harness_ref)
        if spec is not None:
            return spec
        return Refusal(
            name="harness-spec-unknown",
            observed=f"no HarnessSpec is registered for harness_ref {harness_ref!r}",
            meaning="there is no composition to pin, so there is nothing to dispatch",
            action="register the binding's spec; there is no fallback to a generic process",
            detail=(("harness_ref", harness_ref),),
        )

    def role_table(self) -> tuple[RoleRow, ...]:
        """Every registered binding's per-layer role, in registration-key order."""

        return tuple(
            RoleRow(
                harness_key=key,
                binding_class=self._classes[key],
                roles=spec.layers,
                native_pool=spec.survey.native_pool,
                native_fallback=spec.survey.native_fallback,
            )
            for key, spec in sorted(self._specs.items())
        )

    def real_bindings(self) -> tuple[str, ...]:
        return tuple(sorted(key for key, kind in self._classes.items() if kind == "real"))

    def publication(self) -> Refusal | None:
        """`None` once the Seam is earned; a refusal, by name, while it is not."""

        real = self.real_bindings()
        fakes = [key for key, kind in self._classes.items() if kind == "fault_injection_fake"]
        if len(real) >= REQUIRED_REAL_BINDINGS and fakes:
            return None
        return Refusal(
            name="harness-seam-unpublished",
            observed=f"{len(real)} real bindings and {len(fakes)} fault-injection fakes registered",
            meaning="a contract proven by one implementation is not proven",
            action=(
                f"land {REQUIRED_REAL_BINDINGS} real bindings plus one deterministic fake "
                "against the unchanged conformance suite"
            ),
            detail=tuple(("real_binding", key) for key in real),
        )

    def _duplicate_refusal(self, spec: HarnessSpec) -> Refusal | None:
        existing = self._specs.get(spec.key)
        if existing is None:
            return None
        return Refusal(
            name="harness-spec-incompatible",
            observed=f"{spec.key!r} is already registered at revision {existing.revision}",
            meaning="a duplicate declaration is rejected at registration, never at runtime",
            action="supersede the registered revision explicitly",
            detail=(("registered_revision", str(existing.revision)),),
        )


def _semantic_refusal(spec: HarnessSpec) -> Refusal | None:
    if spec.probe.classified_on == "status_line":
        return Refusal(
            name="pool-probe-classifier-refused",
            observed=f"{spec.key!r} declares a status-line probe classifier",
            meaning="401, 402, 403, and 429 mean four different things and one word loses all four",
            action="declare a body classifier before registering this binding",
            detail=(("classified_on", spec.probe.classified_on),),
        )
    derived = derive_roles(spec.survey)
    if derived == spec.layers:
        return None
    return Refusal(
        name="harness-layer-conflict",
        observed=(
            f"{spec.key!r} declares {spec.layers.to_mapping()} against a survey implying "
            f"{derived.to_mapping()}"
        ),
        meaning=(
            "two policies over one credential set are a race over single-use refresh chains, "
            "not redundancy"
        ),
        action="configure where the harness has the layer, provide where it does not, never both",
        detail=(
            ("declared_pool", spec.layers.pool),
            ("derived_pool", derived.pool),
            ("declared_fallback", spec.layers.fallback),
            ("derived_fallback", derived.fallback),
        ),
    )


def _authority_refusal(spec: HarnessSpec, route: RegistrationRoute) -> Refusal | None:
    if route.harness_ref != spec.key:
        return Refusal(
            name="harness-registration-route-mismatch",
            observed=(
                f"route authorizes harness_ref {route.harness_ref!r}, "
                f"but the proposed document is {spec.key!r}"
            ),
            meaning="a proposed document cannot choose the harness context that admits it",
            action="derive the route from the trusted parent-harness registration context",
            detail=(
                ("route_harness_ref", route.harness_ref),
                ("proposed_harness_ref", spec.key),
            ),
        )
    expected_digest = spec.composition_digest()
    if route.authority_digest == expected_digest:
        return None
    return Refusal(
        name="harness-registration-authority-mismatch",
        observed=(
            f"route authority digest {route.authority_digest!r} does not match "
            f"the proposed spec digest {expected_digest!r}"
        ),
        meaning="registration must be bound to the exact trusted spec revision and composition",
        action="derive the route from the same trusted parent-harness spec revision",
        detail=(
            ("route_authority_digest", route.authority_digest),
            ("proposed_spec_digest", expected_digest),
        ),
    )
