import type {
  PoolAuthState,
  PoolCreditState,
  PoolDriftFindingKind,
  PoolEnactmentPath,
  PoolProfileLimits,
  PoolQuotaState,
  PoolReachState,
  PoolRegistrationState,
} from "@ctower/client";

/**
 * What the harness credential pools read carries, and what it deliberately does not.
 *
 * The record answers this one per *entry*: one account, its own three axes, its
 * own reset clock. There is no pool-level state in the contract and none is
 * derived here — a profile holding two capped accounts and one available one is
 * not one word, and the moment a type on this side offered such a word a screen
 * would print it.
 *
 * The axis unions come from the generated contract, so a state this surface can
 * render cannot drift from the authored schema without a compile failure. The
 * harness key is read off the contract's own profile type for the same reason
 * rather than being retyped as a second list of harnesses.
 *
 * Nothing here has a field a credential value can occupy. That is not this
 * module's own restraint: the authored read projection has no such field, while
 * the observation that feeds it may carry a fingerprint. Reading the record's
 * fields one named field at a time is what keeps those two facts the same fact.
 */

export type PoolHarnessKey = PoolProfileLimits["harness_key"];

/** One credential-pool account, exactly as the record's read projection states it. */
export interface PoolEntry {
  readonly providerKey: string;
  readonly subscriptionIdentity: string | null;
  readonly entryLabel: string | null;
  readonly registrationState: PoolRegistrationState;
  readonly authState: PoolAuthState;
  readonly quotaState: PoolQuotaState;
  /** This account's own clock; `null` is "the record holds no reset time". */
  readonly quotaResetAt: string | null;
  readonly reachState: PoolReachState;
  readonly selectable: boolean;
  readonly requestCount: number;
  readonly lastStatusObserved: string | null;
  readonly creditState: PoolCreditState;
  readonly meteredMillicredits: number | null;
  readonly observedAt: string;
}

/** An account the topology and the sweep disagree about, and which way. */
export interface PoolDrift {
  readonly finding: PoolDriftFindingKind;
  readonly providerKey: string;
  readonly subscriptionIdentity: string | null;
  readonly enactment: PoolEnactmentPath;
  readonly detail: string;
}

/** One authored per-model weight, in the millicredits the record states. */
export interface PoolWeight {
  readonly subscriptionKey: string;
  readonly modelRef: string;
  readonly inputMillicreditsPerMtok: number;
  readonly cachedInputMillicreditsPerMtok: number;
  readonly outputMillicreditsPerMtok: number;
}

/** One harness profile's latest sweep: its accounts, and what drifted. */
export interface PoolProfile {
  readonly harnessKey: PoolHarnessKey;
  readonly profileKey: string;
  readonly entries: readonly PoolEntry[];
  readonly drift: readonly PoolDrift[];
  /** The record's own count. The surface never recounts the rows it was given. */
  readonly selectableEntryCount: number;
  readonly earliestKnownResetAt: string | null;
  readonly observedAt: string;
}

/** The complete credential-limits read, in the order the record answered it. */
export interface PoolLimits {
  readonly profiles: readonly PoolProfile[];
  readonly weights: readonly PoolWeight[];
  readonly topologyRevision: number;
}
