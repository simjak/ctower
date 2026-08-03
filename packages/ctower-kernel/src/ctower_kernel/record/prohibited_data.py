"""One contract-derived prohibited-data-class predicate for intake and Evidence.

D30 clause 3 refuses five stable classes before any byte, event, object, Evidence, or
outbox row commits, and names the class it refused. The class vocabulary is the authored
contract's `ProhibitedDataClass`, never a re-typed local list: a class added to
`contracts/http/openapi.yaml` with no rule below fails this module at import.

Detection is deliberately conservative and pattern-based. Each rule carries D30's own
wording for the class it serves, and each class also names the narrow reference the
decision keeps allowed, so a compliant BH.Loop item — D11 control references, source-host
artifact IDs, de-identified control IDs — is accepted rather than swept up. Free-text
personal identity is out of the pattern set on purpose: staff names and work handles are
allowed by D30 and are indistinguishable in prose from the identities that are not, so
this module refuses the identifiers that are unambiguous (government, financial, birth,
residence, personal contact) instead of guessing at names.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Final
from uuid import UUID

from ctower_client.models import ProhibitedDataClass
from ctower_kernel.record.interface import RecordProblem

__all__ = ["prohibited_data_refusal"]

# Credentials, bearer/session tokens, private or public access keys, signing keys,
# recovery material, and secret values in any form. Allowed: a typed vault/credential
# reference with no value (`SecretBindingReference`, `*_ref`, `vault://…`).
_CREDENTIAL_MATERIAL: Final = (
    r"-----begin [a-z ]*private key-----",
    r"\b(?:bearer|basic)\s+[a-z0-9._\-/+=]{16,}",
    r"\bssh-(?:rsa|ed25519|dss)\s+aaaa[a-z0-9+/=]{16,}",
    r"\bakia[0-9a-z]{16}\b",
    r"\bgh[pousr]_[a-z0-9]{20,}\b",
    r"\beyj[a-z0-9_\-]{8,}\.eyj[a-z0-9_\-]{8,}\.",
    r"\b(?:password|passwd|client_secret|secret_value|access_token|refresh_token"
    r"|session_token|api[_-]?key|private_key|authorization)\b(?!_ref)\s*[:=]\s*"
    r"[\"']?[a-z0-9+/=_\-]{8,}",
)

# Production customer records, payloads, exports, or copied customer artifacts.
# Allowed: a source-host artifact ID/digest that reveals no customer content.
_PRODUCTION_CUSTOMER_DATA: Final = (
    r"\bproduction customer\b",
    r"\bcustomer (?:record|records|export|exports|dump|payload|payloads|data)\b",
    r"\bprod(?:uction)?(?: database)? dump\b",
    r"\bcopied customer\b",
)

# PHI, patient data, clinical content, or any other HIPAA-covered content. Allowed for
# `bh-loop`: D11 control references, GitHub/GitLab artifact IDs, de-identified control IDs.
_PHI_HIPAA_COVERED: Final = (
    r"\bphi\b",
    r"\bhipaa\b",
    r"\bprotected health information\b",
    r"\bpatients?\b",
    r"\bclinical\b",
    r"\bdiagnos(?:is|es)\b",
    r"\b(?:medical|health) record\b",
    r"\bmrn\b",
    r"\bicd-?10\b",
    r"\bprescriptions?\b",
)

# PII beyond staff names and work handles. Allowed: a staff name or work handle needed
# for accountable assignment.
_PII_BEYOND_STAFF_IDENTITY: Final = (
    r"\b\d{3}-\d{2}-\d{4}\b",
    r"\b\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{4}\b",
    r"\bdate of birth\b",
    r"\bdob\b",
    r"\bhome address\b",
    r"\bpassport\b",
    r"\bnational id(?:entity)? (?:number|card)\b",
    r"\bdriver'?s licen[cs]e\b",
    r"\biban\b",
    r"\+\d{9,15}\b",
)

# Live incident indicators, production incident payloads, or operational data that could
# expose an active incident. Allowed: a non-sensitive retrospective control/outcome
# reference after it is no longer live.
_LIVE_INCIDENT_INDICATOR: Final = (
    r"\bsev-?[0-3]\b",
    r"\binc-\d{2,}\b",
    r"\bpager\s?duty\b",
    r"\bactive incident\b",
    r"\bongoing (?:incident|outage)\b",
    r"\bincident in progress\b",
    r"\bproduction outage\b",
    r"\bcurrently (?:down|paging|firing)\b",
    r"\balerts? (?:is |are )?firing\b",
    r"\bon-?call page\b",
)

_PATTERNS: Final[dict[ProhibitedDataClass, tuple[str, ...]]] = {
    ProhibitedDataClass.CREDENTIAL_MATERIAL: _CREDENTIAL_MATERIAL,
    ProhibitedDataClass.PRODUCTION_CUSTOMER_DATA: _PRODUCTION_CUSTOMER_DATA,
    ProhibitedDataClass.PHI_HIPAA_COVERED: _PHI_HIPAA_COVERED,
    ProhibitedDataClass.PII_BEYOND_STAFF_IDENTITY: _PII_BEYOND_STAFF_IDENTITY,
    ProhibitedDataClass.LIVE_INCIDENT_INDICATOR: _LIVE_INCIDENT_INDICATOR,
}

# Indexing by every authored member is the exhaustiveness proof: a contract class with no
# rule raises here, at import, instead of passing unclassified content into the Record.
_RULES: Final[tuple[tuple[ProhibitedDataClass, tuple[re.Pattern[str], ...]], ...]] = tuple(
    (item, tuple(re.compile(pattern) for pattern in _PATTERNS[item]))
    for item in ProhibitedDataClass
)


def prohibited_data_refusal(
    values: Iterable[str | None],
    *,
    command_id: UUID | None = None,
) -> RecordProblem | None:
    """Refuse D30's prohibited classes by name over every supplied caller-authored value."""

    text = "\n".join(value for value in values if value).casefold()
    detected = tuple(
        item for item, patterns in _RULES if any(pattern.search(text) for pattern in patterns)
    )
    if not detected:
        return None
    return RecordProblem(
        code="prohibited-data-class",
        detail=(
            "The command carries prohibited data classes and was refused without any "
            f"mutation: {', '.join(item.value for item in detected)}."
        ),
        status=422,
        title="Prohibited data class",
        command_id=command_id,
        prohibited_classes=detected,
    )
