"""`HarnessSpec`: the revision-pinned binding manifest, parsed as data.

The document is validated against its authored contract and then frozen into typed values.
Nothing here imports, executes, or resolves package code from the document: an adapter that
cannot declare a capability does not discover it at runtime, and a spec that does not parse
is a refusal rather than a fallback to a generic process.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

from ctower_contracts import validator_for

from ctower_runner_sdk.refusals import Refusal
from ctower_runner_sdk.survey import CredentialSurvey, LayerRole, LayerRoles, ResetSemantics

__all__ = [
    "SPEC_SCHEMA_REF",
    "AckPredicate",
    "Capability",
    "HarnessSpec",
    "LivenessSource",
    "PoolShape",
    "ProbeShape",
    "parse_harness_spec",
]

SPEC_SCHEMA_REF = "ctower.harness-spec/v1"

type Capability = Literal[
    "LIVE_INPUT",
    "INTERRUPT_AND_RESUME",
    "STEER_DURABLE_COMMAND_ID",
    "CHECKPOINT",
    "PARK",
    "REAP",
    "POOL_OBSERVE",
    "POOL_ROTATE_RECORD",
    "POOL_PROBE",
]


@dataclass(frozen=True, slots=True)
class AckPredicate:
    """What proves the brief was accepted. Delivery is not acknowledgement."""

    kind: Literal["composer_cleared", "durable_command_id", "in_process_fake"]
    detail: str


type LivenessFactName = Literal["served_model", "context_used_pct", "cap", "working", "pool"]
type LivenessSourceName = Literal[
    "gateway_log",
    "session_transcript",
    "launch_argv",
    "pane_footer",
    "pane_content_hash",
    "pool_state",
    "in_process_fake",
]


@dataclass(frozen=True, slots=True)
class LivenessSource:
    """One declared evidence source, and whether it proves serving or only the request."""

    fact: LivenessFactName
    source: LivenessSourceName
    proves: Literal["serving", "request", "observation"]


@dataclass(frozen=True, slots=True)
class ProbeShape:
    """The declared probe. Its product, endpoint, and model must be the ones seats run."""

    product: str
    endpoint: str
    model_ref: str
    workload_shape: Literal["representative", "single_token", "constant"]
    classified_on: Literal["response_body", "status_line"]

    def measures(self, model_ref: str) -> bool:
        """Whether this probe reports on `model_ref`'s own rung or on something else."""

        return self.model_ref == model_ref and self.workload_shape == "representative"


@dataclass(frozen=True, slots=True)
class PoolShape:
    """The pool's providers and the hook a rotation is incomplete without."""

    cache_invalidation_hook: str
    providers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HarnessSpec:
    """One binding's whole declaration, pinned by revision and two digests."""

    key: str
    revision: int
    artifact_digest: str
    config_digest: str
    input_protocol_kind: str
    submit_separately: bool
    output_protocol_kind: str
    capabilities: frozenset[Capability]
    ack_predicate: AckPredicate
    liveness_sources: tuple[LivenessSource, ...]
    context_window_percent: int
    probe: ProbeShape
    pool: PoolShape
    survey: CredentialSurvey
    layers: LayerRoles
    status: Literal["active", "revoked"]

    def composition_digest(self) -> str:
        """The pin an attempt carries. A changed artifact or config is a different spec."""

        return f"{self.key}@{self.revision}+{self.artifact_digest}+{self.config_digest}"

    def serving_source(self) -> LivenessSource | None:
        """The one source that proves serving truth, if this binding declares one."""

        for source in self.liveness_sources:
            if source.fact == "served_model" and source.proves == "serving":
                return source
        return None

    def declares(self, capability: Capability) -> bool:
        return capability in self.capabilities


def parse_harness_spec(document: Mapping[str, object]) -> HarnessSpec | Refusal:
    """Validate one authored document and freeze it, or refuse by name."""

    errors = sorted(
        validator_for(SPEC_SCHEMA_REF).iter_errors(document), key=lambda error: error.json_path
    )
    if errors:
        return _parse_refusal(errors[0].json_path, errors[0].message)
    if document["status"] == "revoked":
        return Refusal(
            name="harness-spec-revoked",
            observed=f"HarnessSpec {document['key']!r} revision {document['revision']} is revoked",
            meaning="this binding may not dispatch; a revoked spec is not a degraded one",
            action="register a superseding revision, or route the attempt to another binding",
        )
    return _freeze(document)


def _parse_refusal(json_path: str, message: str) -> Refusal:
    return Refusal(
        name=_refusal_name(json_path, message),
        observed=f"{json_path}: {message}",
        meaning="the document is not a HarnessSpec this runtime can parse",
        action="repair the authored spec; nothing dispatches on an unparsed composition",
        detail=(("json_path", json_path),),
    )


def _refusal_name(json_path: str, message: str) -> str:
    """Name the fault by what it costs a reader, not by where the validator stopped.

    An unanswered survey question is singled out because its consequence is specific: the
    per-layer role becomes undecidable, and guessing it is how a second rotation policy
    gets built over a working one.
    """

    if json_path.endswith(("artifact_digest", "config_digest")):
        return "harness-spec-digest-mismatch"
    if json_path == "$.survey" or json_path.startswith("$.survey."):
        return "harness-survey-incomplete"
    if json_path == "$" and "'survey'" in message:
        return "harness-survey-incomplete"
    return "harness-spec-incompatible"


def _freeze(document: Mapping[str, object]) -> HarnessSpec:
    """Build the frozen value field by field, never by splatting a validated mapping.

    The schema has already closed every enumeration, so each read below is a narrowing of
    something proven rather than a hope. Naming the fields keeps the frozen value and the
    authored contract visibly the same shape.
    """

    inputs = _section(document, "input_protocol")
    return HarnessSpec(
        key=_text(document["key"]),
        revision=_number(document["revision"]),
        artifact_digest=_text(document["artifact_digest"]),
        config_digest=_text(document["config_digest"]),
        input_protocol_kind=_text(inputs["kind"]),
        submit_separately=bool(inputs["submit_separately"]),
        output_protocol_kind=_text(_section(document, "output_protocol")["kind"]),
        capabilities=frozenset(
            cast("Capability", item) for item in cast("list[str]", document["capabilities"])
        ),
        ack_predicate=_ack(_section(document, "ack_predicate")),
        liveness_sources=tuple(
            _source(item)
            for item in cast("list[Mapping[str, object]]", document["liveness_sources"])
        ),
        context_window_percent=_number(document["context_window_percent"]),
        probe=_probe(_section(document, "probe")),
        pool=_pool(_section(document, "pool")),
        survey=_survey(_section(document, "survey")),
        layers=_layers(_section(document, "layers")),
        status="active",
    )


def _section(document: Mapping[str, object], name: str) -> Mapping[str, object]:
    return cast("Mapping[str, object]", document[name])


def _text(value: object) -> str:
    return cast("str", value)


def _number(value: object) -> int:
    return cast("int", value)


def _ack(raw: Mapping[str, object]) -> AckPredicate:
    return AckPredicate(
        kind=cast(
            "Literal['composer_cleared', 'durable_command_id', 'in_process_fake']", raw["kind"]
        ),
        detail=_text(raw["detail"]),
    )


def _source(raw: Mapping[str, object]) -> LivenessSource:
    return LivenessSource(
        fact=cast("LivenessFactName", raw["fact"]),
        source=cast("LivenessSourceName", raw["source"]),
        proves=cast("Literal['serving', 'request', 'observation']", raw["proves"]),
    )


def _probe(raw: Mapping[str, object]) -> ProbeShape:
    return ProbeShape(
        product=_text(raw["product"]),
        endpoint=_text(raw["endpoint"]),
        model_ref=_text(raw["model_ref"]),
        workload_shape=cast(
            "Literal['representative', 'single_token', 'constant']", raw["workload_shape"]
        ),
        classified_on=cast("Literal['response_body', 'status_line']", raw["classified_on"]),
    )


def _pool(shape: Mapping[str, object]) -> PoolShape:
    return PoolShape(
        cache_invalidation_hook=_text(shape["cache_invalidation_hook"]),
        providers=tuple(cast("list[str]", shape["providers"])),
    )


def _survey(raw: Mapping[str, object]) -> CredentialSurvey:
    return CredentialSurvey(
        native_pool=bool(raw["native_pool"]),
        native_fallback=bool(raw["native_fallback"]),
        config_surface=cast(
            "Literal['authored_config_only', 'account_file', 'env_overridable']",
            raw["config_surface"],
        ),
        identity_proof=cast(
            "Literal['decoded_claim', 'account_file', 'none']", raw["identity_proof"]
        ),
        reset_semantics=cast("ResetSemantics", raw["reset_semantics"]),
        rotation_cache=cast(
            "Literal['proxy_restart', 'config_home_respawn', 'none']", raw["rotation_cache"]
        ),
        subagent_inheritance=cast(
            "Literal['per_task_lease', 'parent_credential', 'separate']",
            raw["subagent_inheritance"],
        ),
        egress_topology=cast("Literal['shared', 'per_entry']", raw["egress_topology"]),
    )


def _layers(raw: Mapping[str, object]) -> LayerRoles:
    return LayerRoles(
        pool=cast("LayerRole", raw["pool"]), fallback=cast("LayerRole", raw["fallback"])
    )
