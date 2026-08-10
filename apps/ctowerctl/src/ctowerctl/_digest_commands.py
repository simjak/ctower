"""Generated-client read and deterministic STE renderer for the morning digest."""

from __future__ import annotations

import argparse
from datetime import date
from typing import cast

from ctower_client import CtowerClient
from ctower_client.models import (
    DigestUnreachedScope,
    MorningDigest,
    MorningDigestDecisionSection,
    MorningDigestProofSection,
    MorningDigestRulingSection,
)

__all__: tuple[str, ...] = ()


def execute_query(arguments: argparse.Namespace, client: CtowerClient) -> MorningDigest:
    if cast(str, arguments.cli_name) != "digest morning":
        raise ValueError("usage: unsupported digest query")
    selected = cast(date | None, arguments.date)
    return client.get_morning_digest(date=None if selected is None else selected.isoformat())


def query_command_names() -> frozenset[str]:
    return frozenset({"digest morning"})


def morning_text(digest: MorningDigest) -> str:
    lines = [
        f"Morning digest — {digest.digest_date} ({digest.timezone})",
        f"State: {digest.state.value.upper()}",
        f"Observed: {digest.observed_at.isoformat()}",
        "",
        f"Open decisions — {_count(digest.open_decisions)}",
    ]
    _unreached(lines, digest.open_decisions.unreached)
    lines.extend(_decision_lines(digest))
    lines.extend(("", f"Yesterday's rulings — {_count(digest.yesterday_rulings)}"))
    _unreached(lines, digest.yesterday_rulings.unreached)
    lines.extend(_ruling_lines(digest))
    lines.extend(("", f"Proof — {_count(digest.proof)}"))
    _unreached(lines, digest.proof.unreached)
    lines.extend(_proof_lines(digest))
    lines.extend(("", f"Artifact: {digest.artifact_key}", f"SHA-256: {digest.artifact_sha256}"))
    return "\n".join(lines)


def _decision_lines(digest: MorningDigest) -> list[str]:
    lines: list[str] = []
    for decision in digest.open_decisions.items:
        decision_state = decision.state.value.upper()
        lines.extend(
            (
                f"{decision.request_reference} · {decision.project_key} · {decision_state}",
                f"What: {decision.brief.what}",
                f"Origin: {decision.brief.origin}",
            )
        )
        if decision.brief.choices:
            lines.append("Choices:")
            lines.extend(
                f"- {choice.label} ({choice.completeness}/10): {choice.outcome}"
                for choice in decision.brief.choices
            )
        elif decision.state.value == "complete":
            lines.append("Choices: 0")
        else:
            lines.append(f"Choices: UNKNOWN ({decision.unknown_reason or 'not-recorded'})")
        lines.append(
            "Recommendation: " + (decision.brief.recommendation or "UNKNOWN (not-recorded)")
        )
        lines.append(f"Safe default: {decision.brief.safe_default}")
        if decision.unknown_reason is not None:
            lines.append(f"Unknown: {decision.unknown_reason}")
    return lines


def _ruling_lines(digest: MorningDigest) -> list[str]:
    lines: list[str] = []
    for ruling in digest.yesterday_rulings.items:
        lines.extend(
            (
                f"{ruling.ruling_id} · {ruling.project_key} · {ruling.state.value.upper()}",
                f"Ruling: {ruling.verbatim}",
            )
        )
        if ruling.executions:
            lines.append("Executions:")
            lines.extend(
                f"- {item.request_reference} · {item.state} · tickets={len(item.ticket_ids)}"
                for item in ruling.executions
            )
        elif ruling.unknown_reason is not None:
            lines.append(f"Executions: UNKNOWN ({ruling.unknown_reason})")
        else:
            lines.append("Executions: 0")
    return lines


def _proof_lines(digest: MorningDigest) -> list[str]:
    lines: list[str] = []
    for proof in digest.proof.items:
        count = "UNKNOWN" if proof.current_proof_count is None else str(proof.current_proof_count)
        lines.append(f"{proof.request_reference} · {proof.project_key} · current proof={count}")
        lines.extend(
            f"- {ticket.purpose}: {ticket.ticket_id} {ticket.href}" for ticket in proof.tickets
        )
    return lines


def _count(
    section: MorningDigestDecisionSection | MorningDigestRulingSection | MorningDigestProofSection,
) -> str:
    if section.total_count is None:
        return f"UNKNOWN total; {section.visible_count} visible; {section.state.value.upper()}"
    return f"{section.total_count}; {section.state.value.upper()}"


def _unreached(lines: list[str], scopes: tuple[DigestUnreachedScope, ...]) -> None:
    lines.extend(f"Unreached: {item.key} ({item.reason})" for item in scopes)
