import type {
  PoolAuthState,
  PoolCreditState,
  PoolDriftFindingKind,
  PoolEnactmentPath,
  PoolQuotaState,
  PoolReachState,
  PoolRegistrationState,
} from "@ctower/client";
import { read } from "./httpRecordAdapter";
import {
  asArray,
  asBoolean,
  asInteger,
  asIntegerOrNull,
  asMember,
  asRecord,
  asString,
  asStringOrNull,
} from "./json";
import { reading } from "./outcome";
import type { Reading } from "./interface";
import type {
  PoolDrift,
  PoolEntry,
  PoolHarnessKey,
  PoolLimits,
  PoolProfile,
  PoolWeight,
} from "./poolLimitsInterface";

/**
 * The harness credential-pool read, parsed field by named field.
 *
 * `GET /v1/pools` answers with the latest sweep per harness profile. Its
 * entries come from a place credential material lives, which is why the
 * authored read projection is a closed object with no field a token, key or
 * fingerprint can occupy — the observation that feeds it may carry a
 * fingerprint; the read may not.
 *
 * That is why every field below is named. Copying the payload, spreading it, or
 * keeping an unread remainder would carry whatever the record answered with
 * onto the screen, and the projection would be an intention rather than a
 * boundary. A field the contract adds later arrives here as a deliberate edit
 * or does not arrive at all.
 *
 * Nothing is aggregated. The record states each account's own three axes and
 * its own reset clock, and states per profile how many of them are selectable;
 * a pool-level verdict composed here would be this surface's own opinion
 * wearing the record's authority.
 */

const REGISTRATION_STATES: readonly PoolRegistrationState[] = ["enrolled", "discovered"];
const AUTH_STATES: readonly PoolAuthState[] = ["healthy", "lineage-dead", "chain-burned"];
const QUOTA_STATES: readonly PoolQuotaState[] = ["available", "capped", "unfunded", "unknown"];
const REACH_STATES: readonly PoolReachState[] = ["ok", "edge-challenged", "unknown"];
const CREDIT_STATES: readonly PoolCreditState[] = ["metered", "unmetered"];
const DRIFT_FINDINGS: readonly PoolDriftFindingKind[] = ["missing", "unregistered"];
const ENACTMENTS: readonly PoolEnactmentPath[] = ["operator-ceremony", "secret-reference"];
const HARNESSES: readonly PoolHarnessKey[] = ["hermes", "claude-code"];

function toEntry(value: unknown): PoolEntry {
  const row = asRecord(value, "pools.profiles[].entries[]");
  return {
    providerKey: asString(row.provider_key, "pools.profiles[].entries[].provider_key"),
    subscriptionIdentity: asStringOrNull(
      row.subscription_identity,
      "pools.profiles[].entries[].subscription_identity"
    ),
    entryLabel: asStringOrNull(row.entry_label, "pools.profiles[].entries[].entry_label"),
    registrationState: asMember(
      row.registration_state,
      "pools.profiles[].entries[].registration_state",
      REGISTRATION_STATES
    ),
    authState: asMember(row.auth_state, "pools.profiles[].entries[].auth_state", AUTH_STATES),
    quotaState: asMember(row.quota_state, "pools.profiles[].entries[].quota_state", QUOTA_STATES),
    quotaResetAt: asStringOrNull(row.quota_reset_at, "pools.profiles[].entries[].quota_reset_at"),
    reachState: asMember(row.reach_state, "pools.profiles[].entries[].reach_state", REACH_STATES),
    selectable: asBoolean(row.selectable, "pools.profiles[].entries[].selectable"),
    requestCount: asInteger(row.request_count, "pools.profiles[].entries[].request_count"),
    lastStatusObserved: asStringOrNull(
      row.last_status_observed,
      "pools.profiles[].entries[].last_status_observed"
    ),
    creditState: asMember(
      row.credit_state,
      "pools.profiles[].entries[].credit_state",
      CREDIT_STATES
    ),
    meteredMillicredits: asIntegerOrNull(
      row.metered_millicredits,
      "pools.profiles[].entries[].metered_millicredits"
    ),
    observedAt: asString(row.observed_at, "pools.profiles[].entries[].observed_at"),
  };
}

function toDrift(value: unknown): PoolDrift {
  const row = asRecord(value, "pools.profiles[].drift[]");
  return {
    finding: asMember(row.finding, "pools.profiles[].drift[].finding", DRIFT_FINDINGS),
    providerKey: asString(row.provider_key, "pools.profiles[].drift[].provider_key"),
    subscriptionIdentity: asStringOrNull(
      row.subscription_identity,
      "pools.profiles[].drift[].subscription_identity"
    ),
    enactment: asMember(row.enactment, "pools.profiles[].drift[].enactment", ENACTMENTS),
    detail: asString(row.detail, "pools.profiles[].drift[].detail"),
  };
}

function toWeight(value: unknown): PoolWeight {
  const row = asRecord(value, "pools.weights[]");
  return {
    subscriptionKey: asString(row.subscription_key, "pools.weights[].subscription_key"),
    modelRef: asString(row.model_ref, "pools.weights[].model_ref"),
    inputMillicreditsPerMtok: asInteger(
      row.input_millicredits_per_mtok,
      "pools.weights[].input_millicredits_per_mtok"
    ),
    cachedInputMillicreditsPerMtok: asInteger(
      row.cached_input_millicredits_per_mtok,
      "pools.weights[].cached_input_millicredits_per_mtok"
    ),
    outputMillicreditsPerMtok: asInteger(
      row.output_millicredits_per_mtok,
      "pools.weights[].output_millicredits_per_mtok"
    ),
  };
}

function toProfile(value: unknown): PoolProfile {
  const row = asRecord(value, "pools.profiles[]");
  return {
    harnessKey: asMember(row.harness_key, "pools.profiles[].harness_key", HARNESSES),
    profileKey: asString(row.profile_key, "pools.profiles[].profile_key"),
    entries: asArray(row.entries, "pools.profiles[].entries").map(toEntry),
    drift: asArray(row.drift, "pools.profiles[].drift").map(toDrift),
    selectableEntryCount: asInteger(
      row.selectable_entry_count,
      "pools.profiles[].selectable_entry_count"
    ),
    earliestKnownResetAt: asStringOrNull(
      row.earliest_known_reset_at,
      "pools.profiles[].earliest_known_reset_at"
    ),
    observedAt: asString(row.observed_at, "pools.profiles[].observed_at"),
  };
}

/** Parse the complete credential-limits read without inventing defaults. */
export function poolLimitsFrom(value: unknown): PoolLimits {
  const row = asRecord(value, "pools");
  return {
    profiles: asArray(row.profiles, "pools.profiles").map(toProfile),
    weights: asArray(row.weights, "pools.weights").map(toWeight),
    topologyRevision: asInteger(row.topology_revision, "pools.topology_revision"),
  };
}

export async function readPoolLimits(): Promise<Reading<PoolLimits>> {
  return await reading(async () => poolLimitsFrom(await read("/v1/pools")));
}
