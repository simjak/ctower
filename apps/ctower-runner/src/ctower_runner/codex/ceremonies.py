"""The fleet's existing credential ceremonies, wrapped rather than reimplemented.

Four tools already own enrolment, per-account re-mint, generation-guarded rotation, and the
multi-account cooldown. Each is the product of an incident, and none is reproduced here: this
module states which tool answers which need, exactly what each may be asked, and what an answer
is allowed to look like. `pool.py` guards and records; the ceremony acts.

**A mutating credential verb answers a question with usage, never with a side effect.**
`tools/codex-rotate-fallback --help` once *rotated live credentials*, because the tool ignored
the flag it did not recognize and fell through to its one real invocation. The hardening it
received that day is the law encoded here, one level up: a ceremony that mutates refuses an
argument it does not declare, and a question is answered by returning usage with nothing run.

The plan a ceremony is asked for is a value, not a call. Nothing in this module executes
anything — a `CeremonyInvocation` is what `CeremonyPort` is handed, and a refusal is returned
in its place, so a refused ceremony is not merely unperformed but unrequested.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from ctower_runner_sdk.refusals import Refusal

__all__ = [
    "CEREMONIES",
    "QUESTION_FLAGS",
    "Ceremony",
    "CeremonyInvocation",
    "CeremonyNeed",
    "CeremonyOutcome",
    "UsageAnswer",
    "ceremony_for",
    "mutating_ceremonies",
    "plan_ceremony",
]

type CeremonyNeed = Literal["enrol", "re-mint", "rotate", "cooldown"]
type ArgumentShape = Literal["nothing", "free_values", "declared_subcommand"]

# A question, in every spelling the fleet's own tools accept. Asked of a mutating ceremony,
# each of these must produce usage and nothing else.
QUESTION_FLAGS: frozenset[str] = frozenset({"-h", "--help", "--usage"})


@dataclass(frozen=True, slots=True)
class Ceremony:
    """One tool of the fleet's family, and the complete set of things it may be asked.

    `mutates` is a declaration rather than a name check, in the same shape the credentials
    survey uses: the law is read off the answer. All four of these answer `True`, which is why
    the unknown-flag rule below is unqualified — every ceremony ctower wraps for this harness
    changes credential state, and there is no read-only member to exempt.
    """

    name: str
    mutates: bool
    accepts: ArgumentShape
    usage: str
    known_arguments: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class CeremonyInvocation:
    """What a ceremony would be asked to do. Held as a value until something runs it."""

    ceremony: str
    argv: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UsageAnswer:
    """A question answered with usage. Nothing was run and nothing changed."""

    ceremony: str
    usage: str


@dataclass(frozen=True, slots=True)
class CeremonyOutcome:
    """What a ceremony reported. Its own refusal is carried, never re-derived.

    `refusal_name` is the ceremony's verdict on the chain it owns — a snapshot older than the
    live refresh generation is refused inside `codex-rotate-fallback`, where that guard was
    hardened after a stale install revoked every grant derived from one login at once.
    """

    ceremony: str
    installed_identity: str | None
    installed_generation: int
    hook_completed: bool
    refusal_name: str | None = None
    detail: str = ""


CEREMONIES: dict[CeremonyNeed, Ceremony] = {
    "enrol": Ceremony(
        name="codex-auth-all",
        mutates=True,
        accepts="free_values",
        usage="tools/codex-auth-all [profile ...]  # every account into every persona profile",
    ),
    "re-mint": Ceremony(
        name="codex-grant-ceremony",
        mutates=True,
        accepts="free_values",
        usage="tools/codex-grant-ceremony [account-label]  # one account, one flow per profile",
    ),
    "rotate": Ceremony(
        name="codex-rotate-fallback",
        mutates=True,
        accepts="nothing",
        usage="tools/codex-rotate-fallback  # no arguments; generation-guarded, never a copy",
    ),
    "cooldown": Ceremony(
        name="codex-pool",
        mutates=True,
        accepts="declared_subcommand",
        usage="tools/codex-pool <cap|rotate|next|status|use|save-active>  # ~5h cooldown model",
        known_arguments=frozenset({"cap", "rotate", "next", "status", "use", "save-active"}),
    ),
}


def mutating_ceremonies() -> tuple[Ceremony, ...]:
    """Every ceremony that changes credential state, in need order."""

    return tuple(ceremony for ceremony in CEREMONIES.values() if ceremony.mutates)


def ceremony_for(need: CeremonyNeed, identity: str | None = None) -> CeremonyInvocation | Refusal:
    """Compose the invocation the fleet already has for one need, validated as it is composed.

    A named identity narrows enrolment to that account's own re-mint, because running the
    full-grid ceremony to repair one lineage burns a fresh device flow on every other profile.

    This is the ACTING path, so a question does not become one: an identity that arrives
    spelled `--help` is an argument this verb cannot act on, and it refuses rather than
    falling through to the one real invocation — which is precisely what happened the day a
    `--help` rotated live credentials.
    """

    narrowed = "re-mint" if need == "enrol" and identity is not None else need
    ceremony = CEREMONIES[narrowed]
    argv = () if identity is None else (identity,)
    planned = plan_ceremony(ceremony, argv)
    if isinstance(planned, UsageAnswer):
        return _unknown_flag_refusal(ceremony, argv)
    return planned


def plan_ceremony(
    ceremony: Ceremony, argv: Sequence[str]
) -> CeremonyInvocation | UsageAnswer | Refusal:
    """Turn a request into an invocation, a usage answer, or a refusal. Never a side effect."""

    asked = tuple(argv)
    if any(argument in QUESTION_FLAGS for argument in asked):
        return UsageAnswer(ceremony=ceremony.name, usage=ceremony.usage)
    if ceremony.accepts == "declared_subcommand" and len(asked) != 1:
        return _grammar_refusal(ceremony, asked)
    unknown = _undeclared(ceremony, asked)
    if unknown:
        return _unknown_flag_refusal(ceremony, unknown)
    return CeremonyInvocation(ceremony=ceremony.name, argv=asked)


def _undeclared(ceremony: Ceremony, asked: Sequence[str]) -> tuple[str, ...]:
    """Every argument this ceremony does not declare, in the order it was asked."""

    if ceremony.accepts == "nothing":
        return tuple(asked)
    if ceremony.accepts == "declared_subcommand":
        return tuple(item for item in asked if item not in ceremony.known_arguments)
    return tuple(item for item in asked if item.startswith("-"))


def _unknown_flag_refusal(ceremony: Ceremony, unknown: Sequence[str]) -> Refusal:
    return Refusal(
        name="credential-verb-unknown-flag",
        observed=f"{ceremony.name} was asked {', '.join(repr(item) for item in unknown)}",
        meaning="a mutating verb that ignores what it cannot read acts on a question",
        action=f"ask only what it declares, or read its usage: {ceremony.usage}",
        detail=(("ceremony", ceremony.name), *(("unknown_argument", item) for item in unknown)),
    )


def _grammar_refusal(ceremony: Ceremony, asked: Sequence[str]) -> Refusal:
    return Refusal(
        name="credential-verb-grammar-invalid",
        observed=f"{ceremony.name} received {len(asked)} subcommand arguments",
        meaning=(
            "a declared-subcommand ceremony accepts exactly one action, "
            "never zero or a sequence"
        ),
        action=f"provide exactly one declared subcommand: {ceremony.usage}",
        detail=(("expected_arity", "1"), ("actual_arity", str(len(asked)))),
    )
