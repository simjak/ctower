/**
 * The agent home's tabs, and the reason each one that is not built is not.
 *
 * Six of the nine have no read behind them, and the reasons are kept here
 * rather than inside the panels so they read as one list — which is the honest
 * summary of what this screen can and cannot say today, and the thing to delete
 * from as each read lands. Every one of them is in the operator's words: what
 * the tab would hold, and what is missing before it can.
 */
export type TabKey =
  | "dashboard"
  | "instructions"
  | "skills"
  | "configuration"
  | "secrets"
  | "tools"
  | "runs"
  | "audit"
  | "budget";

export const UNBUILT: Readonly<Record<TabKey | "harnessName", string>> = {
  dashboard: "",
  instructions:
    "This agent's instructions are its own files. Editing them is the files surface, which is not on this screen yet.",
  skills: "The company records no skill for this agent to hold yet.",
  configuration: "",
  secrets:
    "Secrets are bound on the company as references, never values, and nothing binds one to a single agent.",
  tools: "The company records no tool for this agent to reach yet.",
  runs: "A recorded run keeps the seat that ran it, and nothing ties a seat back to an agent — so a list here would be the team's runs under this agent's name.",
  audit:
    "Recorded history is kept against a task, not against an agent, so there is nothing to gather here yet.",
  budget:
    "No price is recorded against any model, so what this agent has cost cannot be totalled without inventing it.",
  harnessName: "This company records a harness for this agent that this console has no name for.",
};
