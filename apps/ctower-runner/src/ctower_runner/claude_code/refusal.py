"""A refusal a caller can act on without reading a pane.

Observed, meaning, action — in the refusal itself. A refusal that names only what broke
sends the reader back to the substrate to work out what it costs them, which on a credential
fault is how a reachability problem gets routed to a mint ceremony that burns a working
grant.

SEAM INTEGRATION (CT-I1-041): this value collapses onto the SDK's own `Refusal` when the
seam lands. It is authored here against D72 and the row's refusal-body requirement so the
binding-private half can be proven before the seam exists, not to introduce a second one.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Refusal"]


@dataclass(frozen=True, slots=True)
class Refusal:
    """One named refusal, carrying what a reader needs to act."""

    name: str
    observed: str
    meaning: str
    action: str
    detail: tuple[tuple[str, str], ...] = ()

    def to_mapping(self) -> dict[str, object]:
        return {
            "action": self.action,
            "detail": [list(row) for row in self.detail],
            "meaning": self.meaning,
            "name": self.name,
            "observed": self.observed,
        }
