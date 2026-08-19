"""Spend in provider-native credits, because tokens are not the billing unit.

Tokens are what the model consumed; **credits are what the subscription paid**, and only
the second answers "which model on which account drained this plan". The two differ by more
than a constant factor, because providers weight per model *and* per direction — a lane on
the expensive rung can outrank a lane with an order of magnitude more tokens.

The table is not authored here. Ctower's registry publishes it, revision-pinned, and this
module prices against the copy it was handed. A stale or missing table refuses rather than
silently mispricing, because a plausible wrong number is worse than an absent one.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ctower_runner_sdk.refusals import Refusal

__all__ = [
    "MTOK",
    "ModelWeight",
    "SpendRow",
    "TokenUsage",
    "WeightTable",
]

MTOK = 1_000_000


@dataclass(frozen=True, slots=True)
class ModelWeight:
    """One model's provider-native cost, per direction, in millicredits per Mtok."""

    subscription_key: str
    model_ref: str
    input_millicredits_per_mtok: int
    cached_input_millicredits_per_mtok: int
    output_millicredits_per_mtok: int


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Raw counts, kept alongside credits rather than replaced by them."""

    input_tokens: int
    cached_input_tokens: int
    output_tokens: int

    def total(self) -> int:
        return self.input_tokens + self.cached_input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class SpendRow:
    """Credits by model x account, with the task class kept separate from the main line.

    Aux spend rides the same seat and attempt as the main model and is attributed on its own
    row: compression in particular runs on long-context lanes, which are exactly the
    expensive ones, so folding it in hides a real and variable cost.
    """

    model_ref: str
    subscription_identity: str | None
    task_class: str
    millicredits: int
    tokens: TokenUsage

    def to_mapping(self) -> dict[str, object]:
        return {
            "input_tokens": self.tokens.input_tokens,
            "millicredits": self.millicredits,
            "model_ref": self.model_ref,
            "output_tokens": self.tokens.output_tokens,
            "subscription_identity": self.subscription_identity,
            "task_class": self.task_class,
        }


@dataclass(frozen=True, slots=True)
class WeightTable:
    """A revision-pinned copy of the registry's weights, as received."""

    revision: int
    weights: tuple[ModelWeight, ...]

    @classmethod
    def from_rows(cls, revision: int, rows: Iterable[ModelWeight]) -> WeightTable:
        return cls(revision=revision, weights=tuple(rows))

    def price(
        self,
        *,
        model_ref: str,
        subscription_identity: str | None,
        task_class: str,
        tokens: TokenUsage,
        expected_revision: int,
    ) -> SpendRow | Refusal:
        """Return one attributed spend row, or refuse rather than misprice."""

        if self.revision != expected_revision:
            return _table_refusal(
                observed=f"weight table revision {self.revision} against pin {expected_revision}",
                action="re-read the registry's current weight table before metering",
            )
        weight = next((row for row in self.weights if row.model_ref == model_ref), None)
        if weight is None:
            return _table_refusal(
                observed=f"no weight row for model {model_ref!r}",
                action="publish this model's per-direction weights, then meter",
            )
        return SpendRow(
            model_ref=model_ref,
            subscription_identity=subscription_identity,
            task_class=task_class,
            millicredits=_millicredits(weight, tokens),
            tokens=tokens,
        )


def _millicredits(weight: ModelWeight, tokens: TokenUsage) -> int:
    """Exact integer arithmetic; a credit total is never a float that rounds twice."""

    scaled = (
        weight.input_millicredits_per_mtok * tokens.input_tokens
        + weight.cached_input_millicredits_per_mtok * tokens.cached_input_tokens
        + weight.output_millicredits_per_mtok * tokens.output_tokens
    )
    return scaled // MTOK


def _table_refusal(*, observed: str, action: str) -> Refusal:
    return Refusal(
        name="weight-table-unavailable",
        observed=observed,
        meaning="a spend figure priced from an unknown table is a plausible wrong number",
        action=action,
    )
