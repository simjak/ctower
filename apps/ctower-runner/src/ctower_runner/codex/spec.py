"""The authored `codex` HarnessSpec document, and the survey that decides its roles.

This document declares the **direct CLI** harness and nothing else. Codex reached as a runtime
under a hermes profile is not this binding and is not a harness at all — that distinction is
`route.py`'s, and it is the reason this file exists in the shape it does.

The direct CLI holds a single active account per config home and ships neither a credential
pool nor an in-session fallback, so both survey answers are `no` and ctower PROVIDES both
layers. It provides them by wrapping the ceremonies the fleet already runs rather than by
writing a fifth rotation implementation; `ceremonies.py` is that wrapping and `pool.py` is the
guard over it. The roles are not written here from the harness's name: `derive_roles` reads
them off the eight answers at registration and refuses a document declaring anything else.

The two digests are inputs rather than constants. They pin the artifact and the config home of
one real install, so a spec written with a digest of something that does not exist would be a
claim rather than a pin.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta

__all__ = [
    "CODEX_CAPABILITIES",
    "CODEX_COOLDOWN",
    "CODEX_KEY",
    "CODEX_REVISION",
    "CODEX_SATURATION_PERCENT",
    "POOL_CACHE_INVALIDATION_HOOK",
    "digest_of",
    "harness_spec_document",
]

CODEX_KEY = "codex"
CODEX_REVISION = 1

# The fleet's floor: a lane at or past 90% of its own declared window is saturated. The
# threshold is a percentage because the ratio's units prove nothing on their own.
CODEX_SATURATION_PERCENT = 90

# The cooldown `tools/codex-pool` has kept since it was written: a capped codex account is
# rested for five hours rather than re-probed, because no ceremony adds quota.
CODEX_COOLDOWN = timedelta(hours=5)

# Credentials are read out of the config home at spawn, so a rotated account reaches a running
# lane only by respawning it against its home. Nothing is believed before that completes.
POOL_CACHE_INVALIDATION_HOOK = "codex-home-respawn"

# Deliberately no INTERRUPT_AND_RESUME: this TUI queues a mid-turn paste into its composer, so
# input into a working lane would be swallowed rather than delivered. POOL_ROTATE_RECORD *is*
# declared, and that is the difference between providing a layer and implementing one: the
# rotation is performed by the fleet's own ceremony and this binding records what it did.
CODEX_CAPABILITIES: tuple[str, ...] = (
    "CHECKPOINT",
    "PARK",
    "REAP",
    "POOL_OBSERVE",
    "POOL_ROTATE_RECORD",
    "POOL_PROBE",
)

_PROVIDERS: tuple[str, ...] = ("openai-codex",)

_SURVEY: dict[str, object] = {
    # One active account per `CODEX_HOME`; there is no pool inside this CLI to configure.
    "native_pool": False,
    # No in-session rung either, which is what makes a failover a new attempt.
    "native_fallback": False,
    # The account file on disk is the config surface, not an authored, pinned configuration.
    "config_surface": "account_file",
    # Every entry carries a decodable identity claim, which is why the pool keys on identity
    # and treats a label as a display attribute with no authority: two labels have pointed at
    # the wrong account, and one of them hid two accounts behind one name.
    "identity_proof": "decoded_claim",
    # A ~5h rolling block that carries its own reset time, and a weekly window above it.
    "reset_semantics": "rolling_block",
    # Whatever holds the credential caches it, so the seat is respawned against its home.
    "rotation_cache": "config_home_respawn",
    # Subagents run on the parent's credential; delegation acquires nothing of its own.
    "subagent_inheritance": "parent_credential",
    # Every account leaves this host by one egress, so a provider edge challenge hits all of
    # them at once and correlated identical failure is evidence about the path.
    "egress_topology": "shared",
}


def digest_of(payload: bytes) -> str:
    """Return the contract's digest spelling for one real artifact or config file."""

    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def harness_spec_document(*, artifact_digest: str, config_digest: str) -> dict[str, object]:
    """Return the authored spec document for one pinned direct-CLI codex install."""

    return {
        "schema": "ctower.harness-spec/v1",
        "key": CODEX_KEY,
        "revision": CODEX_REVISION,
        "artifact_digest": artifact_digest,
        "config_digest": config_digest,
        # The launcher carries `--model` and the config home carries the credential lineage.
        # Those are two different references and the seam pins both: a launcher named after
        # the model it was asked for is exactly how a phantom harness category is born.
        "input_protocol": {"kind": "wrapper_script_exec", "submit_separately": True},
        "output_protocol": {"kind": "session_transcript"},
        "capabilities": list(CODEX_CAPABILITIES),
        "ack_predicate": {
            "kind": "composer_cleared",
            "detail": "the composer is empty and no pasted-content block is left holding the brief",
        },
        "liveness_sources": _liveness_sources(),
        "context_window_percent": CODEX_SATURATION_PERCENT,
        "probe": {
            "product": "codex-cli",
            "endpoint": "/backend-api/codex/responses",
            "model_ref": "gpt-5.6-sol",
            "workload_shape": "representative",
            "classified_on": "response_body",
        },
        "pool": {
            "cache_invalidation_hook": POOL_CACHE_INVALIDATION_HOOK,
            "providers": list(_PROVIDERS),
        },
        "survey": dict(_SURVEY),
        "layers": {"pool": "provide", "fallback": "provide"},
        "status": "active",
    }


def _liveness_sources() -> list[dict[str, str]]:
    """Declare every source, and what each one actually proves.

    For a codex child process the **launch argv is request-ground-truth and outranks a
    status-bar text match**. The status line does print a model name, and that is precisely
    why it is not declared here: it echoes what the launcher asked for, so believing it would
    turn the request into its own corroboration. What actually answered is recorded per turn
    in the session rollout under the config home, and that is this binding's serving truth.

    The pool is declared as its own source because on this harness it disagrees with the
    substrate: exhaustion arrives as a non-retryable 401 on the first real call while the pane
    is still rendering a healthy composer.
    """

    return [
        {"fact": "served_model", "source": "session_transcript", "proves": "serving"},
        {"fact": "served_model", "source": "launch_argv", "proves": "request"},
        {"fact": "context_used_pct", "source": "pane_footer", "proves": "observation"},
        {"fact": "cap", "source": "pane_footer", "proves": "observation"},
        {"fact": "working", "source": "pane_footer", "proves": "observation"},
        {"fact": "pool", "source": "pool_state", "proves": "observation"},
    ]
