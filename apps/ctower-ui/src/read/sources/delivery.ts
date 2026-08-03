import { NO_PROJECT_HISTORY } from "../futureSources";
import { rankCandidates } from "../selectors";
import { changeFailureRate, mergeCandidates, windowDays } from "./mergeHistory";
import { redacted } from "./redact";
import type {
  DeliveryMeasure,
  DeliveryMetrics,
  DeliveryScope,
  ProjectMerges,
  Reading,
} from "../interface";

/**
 * The delivery measures this record supports, and the ones it does not.
 *
 * Three of the four DORA measures need a fact no project in this portfolio
 * keeps: a deploy event, an incident open/close pair, and a promotion to time
 * a lead against. This module does not compute them from something adjacent and
 * hope — it returns them with `value: null` and the work that would land the
 * record, and the screen renders that as a refusal rather than a zero.
 *
 * The measures that *are* computed name their derivation on the card, because
 * this is the page where a wrong number would be believed.
 */

const DEPLOY_FREQUENCY: DeliveryMeasure = {
  title: "Deploy frequency",
  value: null,
  unit: null,
  target: "no target yet",
  note: "No project in this portfolio records a deploy event, so there is nothing to count. ctower's pipeline ends at merge; the others deploy but keep no ledger this surface can read.",
  source: "src: —",
  lands: "a recorded deploy event, which no work item is filed to add",
};

const LEAD_TIME: DeliveryMeasure = {
  title: "Lead time · merge → deploy",
  value: null,
  unit: null,
  target: "no target yet",
  note: "Half of this join exists: the merge is on the trunk and timed. The promotion it would be timed against is not recorded anywhere, so no interval can be stated.",
  source: "src: trunk history + deploy runs · deploy half missing",
  lands: "a recorded deploy event, which no work item is filed to add",
};

const MTTR: DeliveryMeasure = {
  title: "MTTR",
  value: null,
  unit: null,
  target: "no target yet",
  note: "An incident open and its close are both needed to time a recovery. Neither is recorded as a typed fact, and reading them out of prose would be a guess with a number attached.",
  source: "src: —",
  lands: "a recorded incident open/close pair, which no work item is filed to add",
};

export async function readDeliveryMetrics(): Promise<Reading<DeliveryMetrics>> {
  const now = Date.now();
  const candidates = await mergeCandidates(now);
  const ranked = rankCandidates(candidates, NO_PROJECT_HISTORY);
  if (ranked.state !== "present") {
    return ranked;
  }
  const projects = candidates.flatMap((candidate) =>
    candidate.reading.state === "present" ? [candidate.reading.value] : []
  );
  const scopeOf = (
    key: string,
    label: string,
    subset: readonly ProjectMerges[]
  ): DeliveryScope => ({
    key,
    label,
    projects: subset,
    measures: [DEPLOY_FREQUENCY, LEAD_TIME, changeFailureRate(subset), MTTR].map((measure) => ({
      ...measure,
      note: redacted(measure.note),
    })),
  });
  return {
    state: "present",
    value: {
      projects,
      // one scope per project plus the portfolio, so a number can never belong
      // to a project the selected tab does not name
      scopes: [
        scopeOf("all", "All projects", projects),
        ...projects.map((project) => scopeOf(project.key, project.label, [project])),
      ],
      windowDays: windowDays(now),
      unread: ranked.value.unread,
      considered: ranked.value.considered,
      reason: ranked.value.reason,
      measuredAt: new Date(now).toISOString(),
    },
  };
}
