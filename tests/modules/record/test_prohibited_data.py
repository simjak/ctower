"""D30 clause 3 prohibited-class predicate: every class by name, plus what stays allowed."""

from __future__ import annotations

from uuid import UUID

import pytest

from ctower_client.models import ProhibitedDataClass
from ctower_kernel.record.prohibited_data import prohibited_data_refusal

__all__: tuple[str, ...] = ()

COMMAND_ID = UUID("30000000-0000-4000-8000-000000000001")

_REFUSED = {
    ProhibitedDataClass.CREDENTIAL_MATERIAL: (
        "Authorization: Bearer ya29.a0AfB_byRWt3nQ1kZq7sample",
        "-----BEGIN OPENSSH PRIVATE KEY-----",
        "deploy key AKIAIOSFODNN7EXAMPLE rotated",
        "token ghp_0123456789abcdefghijklmnopqrstuvwxyz",
        "id_token=eyJnotarealheader.eyJnotarealclaims.notarealsignature",
        "runbook step 4: password = notarealsecret",
    ),
    ProhibitedDataClass.PRODUCTION_CUSTOMER_DATA: (
        "attached the production customer table for triage",
        "the customer export from last night reproduces it",
        "reproduced against a prod database dump",
        "copied customer rows into the fixture",
    ),
    ProhibitedDataClass.PHI_HIPAA_COVERED: (
        "the patient could not submit the intake form",
        "clinical notes render out of order",
        "PHI leaked into the debug log",
        "HIPAA-covered fields appear in the export",
        "diagnosis codes are duplicated on retry",
        "medical record lookup times out",
        "MRN column is unindexed",
        "ICD-10 mapping is stale",
        "prescription refill webhook retries forever",
        "protected health information appears in the payload",
    ),
    ProhibitedDataClass.PII_BEYOND_STAFF_IDENTITY: (
        "reporter SSN 123-45-6789 pasted into the issue",
        "card 4111 1111 1111 1111 shown in the trace",
        "the date of birth field is misparsed",
        "DOB validation rejects leap days",
        "home address autocomplete is wrong",
        "passport upload returns 500",
        "national identity number check fails",
        "driver's license scan is rotated",
        "IBAN validation is too strict",
        "callback to +37060000000 never lands",
    ),
    ProhibitedDataClass.LIVE_INCIDENT_INDICATOR: (
        "SEV-1 declared at 03:10, still open",
        "linked to INC-4821 in the incident tracker",
        "PagerDuty escalated twice",
        "active incident on the ingest path",
        "ongoing outage in the EU region",
        "incident in progress; do not deploy",
        "production outage since 02:00",
        "the checkout path is currently down",
        "alerts are firing on the queue depth",
        "on-call page fired again",
    ),
}

# D30's narrow allowed references, and the ordinary engineering prose next to them.
_ALLOWED = (
    "Refs D11-CTL-0091 control coverage for jakit-labs/bh-loop#412.",
    "Artifact sha256:" + "a" * 64 + " recorded against the de-identified control ID BHL-CTL-0091.",
    "The credential is a typed reference: secret_ref = COMPANY_BUNDLE_MANIBO_COMMANDER.",
    "Rotate through the vault-path reference class; no value is carried here.",
    "Post-incident review for the closed retrospective control, no longer live.",
    "Assign to @simjak; the staff work handle is the accountable owner.",
    "gitlab nfq-technologies/call-center#118 mirrors github jakit-labs/manibo#44.",
    "Diagnostic logging is too verbose in the runner.",
)


@pytest.mark.parametrize("prohibited_class", tuple(ProhibitedDataClass))
def test_every_authored_class_refuses_by_its_exact_stable_name(
    prohibited_class: ProhibitedDataClass,
) -> None:
    for sample in _REFUSED[prohibited_class]:
        refusal = prohibited_data_refusal((sample,), command_id=COMMAND_ID)

        assert refusal is not None, sample
        assert refusal.code == "prohibited-data-class"
        assert refusal.command_id == COMMAND_ID
        assert prohibited_class.value in refusal.prohibited_classes, sample


def test_allowed_references_and_ordinary_prose_are_accepted() -> None:
    for sample in _ALLOWED:
        assert prohibited_data_refusal((sample,)) is None, sample
    assert prohibited_data_refusal(_ALLOWED) is None
    assert prohibited_data_refusal((None, "")) is None


def test_a_refusal_names_every_detected_class_and_carries_no_offending_content() -> None:
    content = "SEV-1: patient record exported with password = notarealsecret"

    refusal = prohibited_data_refusal((content,), command_id=COMMAND_ID)

    assert refusal is not None
    assert set(refusal.prohibited_classes) == {
        ProhibitedDataClass.CREDENTIAL_MATERIAL.value,
        ProhibitedDataClass.PHI_HIPAA_COVERED.value,
        ProhibitedDataClass.LIVE_INCIDENT_INDICATOR.value,
    }
    rendered = str(refusal.response_payload())
    for fragment in ("SEV-1", "patient", "notarealsecret", "password"):
        assert fragment not in rendered
    assert refusal.response_payload()["prohibited_classes"] == [
        item.value for item in ProhibitedDataClass if item.value in refusal.prohibited_classes
    ]


def test_detection_reads_every_supplied_value_not_only_the_first() -> None:
    refusal = prohibited_data_refusal(
        ("ordinary title", None, "github-issue", "jakit-labs/bh-loop#412 clinical note"),
    )

    assert refusal is not None
    assert refusal.prohibited_classes == (ProhibitedDataClass.PHI_HIPAA_COVERED.value,)
    assert refusal.command_id is None
