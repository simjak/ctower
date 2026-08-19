import { poolLimitsFrom } from "../../apps/ctower-ui/src/read/poolLimits.ts";

function outcome(run: () => unknown): { readonly thrown: boolean; readonly value?: unknown } {
  try {
    return { thrown: false, value: run() };
  } catch {
    return { thrown: true };
  }
}

const POISON = "sha256:00000000000000000000000000000000000000000000000000000000deadbeef";

const capped = {
  provider_key: "openai-codex",
  subscription_identity: "first@example.invalid",
  entry_label: "primary",
  registration_state: "enrolled",
  auth_state: "healthy",
  quota_state: "capped",
  quota_reset_at: "2026-08-20T06:29:00Z",
  reach_state: "ok",
  selectable: false,
  request_count: 412,
  last_status_observed: "exhausted",
  credit_state: "unmetered",
  metered_millicredits: null,
  observed_at: "2026-08-17T20:00:00Z",
};

const available = {
  ...capped,
  subscription_identity: "second@example.invalid",
  entry_label: null,
  quota_state: "available",
  quota_reset_at: null,
  selectable: true,
  request_count: 3,
  last_status_observed: null,
  credit_state: "metered",
  metered_millicredits: 1250,
};

const view = {
  profiles: [
    {
      harness_key: "hermes",
      profile_key: "engineer",
      entries: [capped, available],
      drift: [
        {
          finding: "missing",
          provider_key: "openai-codex",
          subscription_identity: "third@example.invalid",
          enactment: "operator-ceremony",
          detail: "the topology names this account and the sweep did not observe it",
        },
      ],
      selectable_entry_count: 1,
      earliest_known_reset_at: "2026-08-20T06:29:00Z",
      observed_at: "2026-08-17T20:00:00Z",
    },
    {
      harness_key: "claude-code",
      profile_key: "reviewer",
      entries: [],
      drift: [],
      selectable_entry_count: 0,
      earliest_known_reset_at: null,
      observed_at: "2026-08-17T19:00:00Z",
    },
  ],
  weights: [
    {
      subscription_key: "codex-plus",
      model_ref: "gpt-5",
      input_millicredits_per_mtok: 1000,
      cached_input_millicredits_per_mtok: 100,
      output_millicredits_per_mtok: 8000,
    },
  ],
  topology_revision: 4,
};

// what a sweep whose source objects sat beside real credential material looks
// like on the wire: the allowlisted fields, plus two the read projection has no
// place for at all
const poisonedEntry = {
  ...capped,
  secret_fingerprint: POISON,
  access_token: POISON,
};

process.stdout.write(
  JSON.stringify({
    parsed: poolLimitsFrom(view),
    poisoned: poolLimitsFrom({
      ...view,
      profiles: [{ ...view.profiles[0], entries: [poisonedEntry] }, view.profiles[1]],
    }),
    poison: POISON,
    rejectsUnknownQuotaState: outcome(() =>
      poolLimitsFrom({
        ...view,
        profiles: [
          { ...view.profiles[0], entries: [{ ...capped, quota_state: "nearly" }] },
          view.profiles[1],
        ],
      })
    ),
    rejectsUnknownHarness: outcome(() =>
      poolLimitsFrom({
        ...view,
        profiles: [{ ...view.profiles[0], harness_key: "codex" }, view.profiles[1]],
      })
    ),
    rejectsMissingSelectable: outcome(() =>
      poolLimitsFrom({
        ...view,
        profiles: [
          { ...view.profiles[0], entries: [{ ...capped, selectable: undefined }] },
          view.profiles[1],
        ],
      })
    ),
    rejectsMissingDriftDetail: outcome(() =>
      poolLimitsFrom({
        ...view,
        profiles: [
          { ...view.profiles[0], drift: [{ ...view.profiles[0].drift[0], detail: undefined }] },
          view.profiles[1],
        ],
      })
    ),
    rejectsMissingTopologyRevision: outcome(() =>
      poolLimitsFrom({ profiles: view.profiles, weights: view.weights })
    ),
  })
);
