"""The authored `claude-code` HarnessSpec document, and the survey that decides its roles.

This harness ships neither a credential pool nor an in-session fallback and holds one account
per config home. Both answers are `no`, so ctower PROVIDES both layers — the opposite of the
`hermes` binding, and the reason the two of them together are what earns the public Seam. The
roles are not written here from the harness's name: `derive_roles` reads them off the eight
answers at registration and refuses a document declaring anything else, which is what makes
`never both` checkable rather than remembered.

The two digests are inputs rather than constants. They pin the artifact and the config home of
one real install, so a spec written with a digest of something that does not exist would be a
claim rather than a pin.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta

__all__ = [
    "CLAUDE_CODE_CAPABILITIES",
    "CLAUDE_CODE_KEY",
    "CLAUDE_CODE_REVISION",
    "CLAUDE_CODE_SATURATION_PERCENT",
    "POOL_CACHE_INVALIDATION_HOOK",
    "TRANSCRIPT_STALE_AFTER",
    "digest_of",
    "harness_spec_document",
]

CLAUDE_CODE_KEY = "claude-code"
CLAUDE_CODE_REVISION = 1

# The fleet's floor: a lane at or past 90% of its own declared window is saturated. The
# threshold is a percentage because the ratio's units prove nothing on their own.
CLAUDE_CODE_SATURATION_PERCENT = 90

# A stale transcript in a shared worktree once reported a dead session's model as live truth.
TRANSCRIPT_STALE_AFTER = timedelta(hours=1)

# Credentials are cached per config home, so respawning the seat against its home is what
# makes a rotated entry's state believable. Nothing is believed before it completes.
POOL_CACHE_INVALIDATION_HOOK = "config-home-respawn"

# Deliberately no INTERRUPT_AND_RESUME: this TUI queues a mid-turn paste into its composer
# instead of refusing it, so input into a working lane would be silently swallowed rather
# than delivered. Deliberately no POOL_ROTATE_RECORD: there is no engine rotation to record,
# because ctower performs the rotation itself.
CLAUDE_CODE_CAPABILITIES: tuple[str, ...] = (
    "CHECKPOINT",
    "PARK",
    "REAP",
    "POOL_OBSERVE",
    "POOL_PROBE",
)

_PROVIDERS: tuple[str, ...] = ("anthropic-claude-code",)

_SURVEY: dict[str, object] = {
    # One account per config home; there is no pool inside this harness to configure.
    "native_pool": False,
    # No in-session rung at all, which is what makes a failover a new attempt.
    "native_fallback": False,
    # The config home is an account file on disk, not an authored, pinned configuration.
    "config_surface": "account_file",
    # The account file names its own identity; there is no decodable pool claim to key on.
    "identity_proof": "account_file",
    # Five-hour blocks that carry their own reset time.
    "reset_semantics": "rolling_block",
    # Whatever holds the credential caches it, so the seat is respawned against its home.
    "rotation_cache": "config_home_respawn",
    # Subagents run on the parent's credential; delegation needs no separate acquisition.
    "subagent_inheritance": "parent_credential",
    # Every account reaches the provider over this host's one egress, so a CDN challenge
    # hits all of them at once and correlated failure is evidence about the path.
    "egress_topology": "shared",
}


def digest_of(payload: bytes) -> str:
    """Return the contract's digest spelling for one real artifact or config file."""

    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def harness_spec_document(*, artifact_digest: str, config_digest: str) -> dict[str, object]:
    """Return the authored spec document for one pinned claude-code install."""

    return {
        "schema": "ctower.harness-spec/v1",
        "key": CLAUDE_CODE_KEY,
        "revision": CLAUDE_CODE_REVISION,
        "artifact_digest": artifact_digest,
        "config_digest": config_digest,
        # The brief is typed literally and submitted separately: this TUI does not accept a
        # single combined send, and the composer is verified clear before a receipt exists.
        "input_protocol": {"kind": "wrapper_script_exec", "submit_separately": True},
        "output_protocol": {"kind": "session_transcript"},
        "capabilities": list(CLAUDE_CODE_CAPABILITIES),
        "ack_predicate": {
            "kind": "composer_cleared",
            "detail": "the composer is empty and the pane shows an active turn after submit",
        },
        "liveness_sources": _liveness_sources(),
        "context_window_percent": CLAUDE_CODE_SATURATION_PERCENT,
        "probe": {
            "product": "claude-code",
            "endpoint": "/v1/messages",
            "model_ref": "claude-opus-5",
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

    These panes carry no model name anywhere on screen — the footer is a permission mode, a
    running-shell count, and an interrupt hint — so the transcript's own assistant rows are
    the only serving truth this harness has. What was *requested* is the `--model` the wrapper
    was launched with, carried on the attempt's pin. Recording that as a second observation
    rather than as agreement is what makes a silent downgrade visible at all, because on this
    harness the pane looks identical either way.
    """

    return [
        {"fact": "served_model", "source": "session_transcript", "proves": "serving"},
        {"fact": "served_model", "source": "launch_argv", "proves": "request"},
        {"fact": "context_used_pct", "source": "pane_footer", "proves": "observation"},
        {"fact": "cap", "source": "pane_footer", "proves": "observation"},
        {"fact": "working", "source": "pane_footer", "proves": "observation"},
        {"fact": "working", "source": "pane_content_hash", "proves": "observation"},
    ]
