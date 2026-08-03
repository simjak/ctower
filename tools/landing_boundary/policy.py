"""Verdict-tier visibility: a degraded signature must not read as a full one.

The routing policy degrades rather than stalls, so a security-class or release-gating
verdict can be signed by a weaker model than the policy tier while still looking, in the
record, exactly like a full signature.  This module loads the authored tier ranking and
the per-class floor so the check can flag such a verdict for re-verification instead of
accepting it silently.  Model names and floors are data; no model name is written here.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from tools.landing_boundary.models import LandingBoundaryError

__all__ = ["DEFAULT_POLICY_PATH", "VerdictTierPolicy", "load_verdict_tier_policy"]

DEFAULT_POLICY_PATH = Path(__file__).with_name("policy.toml")
_SCHEMA = "ctower.verdict-tier-policy/v1"
_MANIFEST_FIELDS = {"schema", "revision", "tier", "class_floor"}
_TIER_FIELDS = {"key", "rank", "models"}
_FLOOR_FIELDS = {"verdict_class", "minimum_tier"}


@dataclass(frozen=True, slots=True)
class VerdictTierPolicy:
    """One authored ranking of signing models and the floor each verdict class owes."""

    revision: int
    model_ranks: Mapping[str, int]
    class_floors: Mapping[str, int]

    def is_below_floor(self, verdict_class: str, signing_model: str) -> bool:
        """Report whether this class owes a stronger signature than it received."""

        floor = self.class_floors.get(verdict_class)
        if floor is None:
            return False
        rank = self.model_ranks.get(signing_model)
        return rank is None or rank > floor


def load_verdict_tier_policy(path: Path = DEFAULT_POLICY_PATH) -> VerdictTierPolicy:
    """Load the authored tier policy, failing closed on any malformed field."""

    document = _read_document(path)
    if set(document) != _MANIFEST_FIELDS:
        raise LandingBoundaryError("verdict-tier policy fields do not match its schema")
    if document["schema"] != _SCHEMA:
        raise LandingBoundaryError("verdict-tier policy schema is unsupported")
    ranks_by_tier, model_ranks = _tiers(_tables(document["tier"], "tier"))
    floors = _floors(_tables(document["class_floor"], "class_floor"), ranks_by_tier)
    return VerdictTierPolicy(
        revision=_positive(document["revision"], "revision"),
        model_ranks=model_ranks,
        class_floors=floors,
    )


def _read_document(path: Path) -> Mapping[str, object]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise LandingBoundaryError(f"unreadable verdict-tier policy: {error}") from error


def _tiers(tables: tuple[Mapping[str, object], ...]) -> tuple[dict[str, int], dict[str, int]]:
    ranks_by_tier: dict[str, int] = {}
    model_ranks: dict[str, int] = {}
    for table in tables:
        if set(table) != _TIER_FIELDS:
            raise LandingBoundaryError("verdict-tier entry fields do not match its schema")
        key = _text(table["key"], "tier.key")
        rank = _positive(table["rank"], "tier.rank")
        if key in ranks_by_tier or rank in ranks_by_tier.values():
            raise LandingBoundaryError("verdict-tier keys and ranks must each be unique")
        ranks_by_tier[key] = rank
        _record_models(_strings(table["models"], "tier.models"), rank, model_ranks)
    if not ranks_by_tier:
        raise LandingBoundaryError("verdict-tier policy must declare at least one tier")
    return ranks_by_tier, model_ranks


def _record_models(models: tuple[str, ...], rank: int, model_ranks: dict[str, int]) -> None:
    for model in models:
        if model in model_ranks:
            raise LandingBoundaryError(f"signing model is ranked twice: {model}")
        model_ranks[model] = rank


def _floors(
    tables: tuple[Mapping[str, object], ...], ranks_by_tier: Mapping[str, int]
) -> dict[str, int]:
    floors: dict[str, int] = {}
    for table in tables:
        if set(table) != _FLOOR_FIELDS:
            raise LandingBoundaryError("verdict-class floor fields do not match its schema")
        verdict_class = _text(table["verdict_class"], "class_floor.verdict_class")
        tier = _text(table["minimum_tier"], "class_floor.minimum_tier")
        if verdict_class in floors:
            raise LandingBoundaryError(f"verdict class is floored twice: {verdict_class}")
        if tier not in ranks_by_tier:
            raise LandingBoundaryError(f"verdict-class floor names an undeclared tier: {tier}")
        floors[verdict_class] = ranks_by_tier[tier]
    return floors


def _tables(value: object, label: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise LandingBoundaryError(f"{label} must be an array of tables")
    return tuple(item for item in value if isinstance(item, dict))


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise LandingBoundaryError(f"{label} must be an array of strings")
    return tuple(item for item in value if isinstance(item, str))


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise LandingBoundaryError(f"{label} must be a nonempty string")
    return value


def _positive(value: object, label: str) -> int:
    if type(value) is not int or value < 1:
        raise LandingBoundaryError(f"{label} must be a positive integer")
    return value
