import type { CompanyBundleDocument } from "@ctower/client";
import { agentsIn } from "../agents/read";
import { projectsIn } from "../projects/read";

/**
 * The two lists the pop-up offers, drawn from the company record and from
 * nothing else.
 *
 * Neither is invented and neither is a placeholder. The people are this
 * company's own agents, by the name a person gave them; the projects are the
 * projects it records, by name and by the ticket prefix their tickets will
 * carry. What the record cannot do — hand a ticket to one of those people — is
 * said on the row rather than hidden by leaving the row out.
 */
export interface Staff {
  /** Addresses the row in a list; it never renders. */
  readonly key: string;
  readonly name: string;
}

export interface Where {
  /** The key every project-addressed read takes. It travels; it does not render. */
  readonly key: string;
  readonly name: string;
  readonly prefix: string | null;
}

export function staffIn(document: CompanyBundleDocument): readonly Staff[] {
  return agentsIn(document).map((listed) => ({ key: listed.key, name: listed.agent.name }));
}

/**
 * The projects a ticket may be raised on, with the one being looked at first
 * when the company records no document for it.
 *
 * A project screen can be open on a key whose document this bundle does not
 * carry — a scope a component declares and nothing names. The pop-up still has
 * to say where the ticket is going, so that key is offered as the project it
 * is, named for what it is rather than by the key that addresses it.
 */
export function whereIn(document: CompanyBundleDocument, projectKey: string): readonly Where[] {
  const recorded = projectsIn(document).map((project) => ({
    key: project.key,
    name: project.name,
    prefix: project.prefix,
  }));
  if (recorded.some((project) => project.key === projectKey)) {
    return recorded;
  }
  return [{ key: projectKey, name: "This project", prefix: null }, ...recorded];
}
