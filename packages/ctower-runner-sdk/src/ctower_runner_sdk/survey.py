"""The answered capability survey, and the per-layer role it decides.

The one thing that varies most between harnesses is not how they are launched but how much
resilience they already ship. So the role is read from the answers and never from the
harness's name: where the harness has the layer the adapter configures and observes it,
where it lacks the layer the adapter provides it, and never both. Two rotation policies
over one credential set do not add redundancy — they add a race over single-use refresh
chains, which is the failure that revokes every grant from one login at once.

An unanswered survey has no decidable role. That is a refusal, not a gap: guessing is
exactly how a second rotation policy gets built over a working one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "SURVEY_QUESTIONS",
    "CredentialSurvey",
    "LayerRole",
    "LayerRoles",
    "ResetSemantics",
    "derive_roles",
]

type LayerRole = Literal["configure", "provide"]
type ResetSemantics = Literal[
    "provider_reset_at", "rolling_block", "weekly_plan", "prepaid_balance", "unknown"
]

# The eight answers AC-HAD-01 requires before a binding may register. They are the
# questions whose answers change the code, in the order the seam asks them.
SURVEY_QUESTIONS: tuple[str, ...] = (
    "native_pool",
    "native_fallback",
    "config_surface",
    "identity_proof",
    "reset_semantics",
    "rotation_cache",
    "subagent_inheritance",
    "egress_topology",
)


@dataclass(frozen=True, slots=True)
class CredentialSurvey:
    """One binding's answers. Every field is answered or the binding does not register."""

    native_pool: bool
    native_fallback: bool
    config_surface: Literal["authored_config_only", "account_file", "env_overridable"]
    identity_proof: Literal["decoded_claim", "account_file", "none"]
    reset_semantics: ResetSemantics
    rotation_cache: Literal["proxy_restart", "config_home_respawn", "none"]
    subagent_inheritance: Literal["per_task_lease", "parent_credential", "separate"]
    egress_topology: Literal["shared", "per_entry"]

    def shares_egress(self) -> bool:
        """Whether identical simultaneous failures are evidence about the path.

        Entries behind one egress fail together when the provider's edge challenges it, so
        correlated identical failure across independent identities is a shared-path signal
        rather than N broken credentials.
        """

        return self.egress_topology == "shared"

    def to_mapping(self) -> dict[str, object]:
        return {
            "config_surface": self.config_surface,
            "egress_topology": self.egress_topology,
            "identity_proof": self.identity_proof,
            "native_fallback": self.native_fallback,
            "native_pool": self.native_pool,
            "reset_semantics": self.reset_semantics,
            "rotation_cache": self.rotation_cache,
            "subagent_inheritance": self.subagent_inheritance,
        }


@dataclass(frozen=True, slots=True)
class LayerRoles:
    """Ctower's role for each resilience layer of one harness."""

    pool: LayerRole
    fallback: LayerRole

    def to_mapping(self) -> dict[str, str]:
        return {"fallback": self.fallback, "pool": self.pool}


def derive_roles(survey: CredentialSurvey) -> LayerRoles:
    """Return the only roles this survey admits.

    A declared role that disagrees with this derivation is refused rather than honoured,
    which is what makes `never both` checkable instead of remembered.
    """

    return LayerRoles(
        pool="configure" if survey.native_pool else "provide",
        fallback="configure" if survey.native_fallback else "provide",
    )
