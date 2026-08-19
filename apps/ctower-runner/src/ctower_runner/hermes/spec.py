"""The authored `hermes` HarnessSpec document, and the survey that decides its roles.

Hermes ships the resilience layers: per-provider credential pools with four rotation
strategies, error-class recovery, a pools-first-then-fallback-providers layering,
reference-only borrowed secrets, and per-task credential leasing for subagents. So this
binding **configures and observes both layers and implements neither**. Building a second
pool over a working one would be the same category error one layer down: two rotation
policies over one credential set are a race over single-use refresh chains, which is the
failure that revokes every grant derived from one login at once.

The two digests are inputs rather than constants. They pin the artifact and the profile
config of one real install, so a spec written with a digest of something that does not exist
would be a claim rather than a pin.
"""

from __future__ import annotations

import hashlib

__all__ = [
    "HERMES_CAPABILITIES",
    "HERMES_KEY",
    "HERMES_REVISION",
    "HERMES_SATURATION_PERCENT",
    "digest_of",
    "harness_spec_document",
]

HERMES_KEY = "hermes"
HERMES_REVISION = 1

# The fleet's floor: a lane at or past 90% of its own declared window is saturated. The
# threshold is a percentage because the ratio's units prove nothing on their own — a
# 1.1M-window lane at 295K reads 28% and is healthy, while 178K against a 131.1K window
# reads 136% and is one step from signing a verdict it cannot still hold the evidence for.
HERMES_SATURATION_PERCENT = 90

# Deliberately no INTERRUPT_AND_RESUME. Steering into a live hermes turn is how an hour of
# a reviewer's real finding was nearly lost, so input into a working lane refuses by name
# rather than being delivered on the hope that the turn was between messages.
HERMES_CAPABILITIES: tuple[str, ...] = (
    "STEER_DURABLE_COMMAND_ID",
    "CHECKPOINT",
    "PARK",
    "REAP",
    "POOL_OBSERVE",
    "POOL_ROTATE_RECORD",
    "POOL_PROBE",
)

# The providers actually present in this fleet's `credential_pool.<provider>[]`.
_PROVIDERS: tuple[str, ...] = ("openai-codex", "zai", "openrouter", "alibaba")

_SURVEY: dict[str, object] = {
    # Hermes ships the pool engine and the ordered ladder; ctower configures both.
    "native_pool": True,
    "native_fallback": True,
    # "Fallback configuration is a deliberate choice, not something a stale shell export
    # should override" — the engine's own principle, adopted verbatim.
    "config_surface": "authored_config_only",
    # Every entry carries a decodable identity claim, which is why the registry keys on
    # identity and treats a label as a display attribute with no authority.
    "identity_proof": "decoded_claim",
    "reset_semantics": "provider_reset_at",
    # A pool proxy caches state in memory, so a rotation is incomplete until it restarts.
    "rotation_cache": "proxy_restart",
    "subagent_inheritance": "per_task_lease",
    # One egress serves the whole pool, so a CDN challenge hits every entry at once and
    # correlated identical failure is evidence about the path, not about N credentials.
    "egress_topology": "shared",
}


def digest_of(payload: bytes) -> str:
    """Return the contract's digest spelling for one real artifact or config file."""

    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def harness_spec_document(*, artifact_digest: str, config_digest: str) -> dict[str, object]:
    """Return the authored spec document for one pinned hermes install."""

    return {
        "schema": "ctower.harness-spec/v1",
        "key": HERMES_KEY,
        "revision": HERMES_REVISION,
        "artifact_digest": artifact_digest,
        "config_digest": config_digest,
        # HERMES_HOME points at a profile directory whose own config owns model and
        # reasoning effort. Model-in-the-launcher is how a launcher gets named after a
        # model and a phantom harness category is born.
        "input_protocol": {"kind": "profile_directory_exec", "submit_separately": True},
        "output_protocol": {"kind": "pane_footer"},
        "capabilities": list(HERMES_CAPABILITIES),
        "ack_predicate": {
            "kind": "composer_cleared",
            "detail": "the composer is empty and the footer timer advanced after submit",
        },
        "liveness_sources": _liveness_sources(),
        "context_window_percent": HERMES_SATURATION_PERCENT,
        "probe": {
            "product": "hermes-gateway",
            "endpoint": "/v1/chat/completions",
            "model_ref": "gpt-5.6-sol",
            "workload_shape": "representative",
            "classified_on": "response_body",
        },
        "pool": {
            "cache_invalidation_hook": "pool-proxy-restart",
            "providers": list(_PROVIDERS),
        },
        "survey": dict(_SURVEY),
        "layers": {"pool": "configure", "fallback": "configure"},
        "status": "active",
    }


def _liveness_sources() -> list[dict[str, str]]:
    """Declare every source, and what each one actually proves.

    The footer shows the *requested* model: a review pane once read `gpt-5.6-terra` while
    the gateway served something else. So the gateway/provider log is serving truth and the
    footer is recorded as a conflict, never as truth.
    """

    return [
        {"fact": "served_model", "source": "gateway_log", "proves": "serving"},
        {"fact": "served_model", "source": "pane_footer", "proves": "request"},
        {"fact": "context_used_pct", "source": "pane_footer", "proves": "observation"},
        {"fact": "cap", "source": "pane_footer", "proves": "observation"},
        {"fact": "working", "source": "pane_footer", "proves": "observation"},
        {"fact": "pool", "source": "pool_state", "proves": "observation"},
    ]
