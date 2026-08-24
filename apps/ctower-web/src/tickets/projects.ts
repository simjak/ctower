import type { CompanyBundleDocument } from "@ctower/client";

/**
 * Which projects this console can ask the work plane about.
 *
 * A **scope** — `component.scope.project`, which every component in
 * `exportCompanyBundle`'s bundle declares — is the identifier every
 * project-addressed read takes, `getBoard` included. A project **document** key
 * (`ctower.control-plane`) is a different identifier family, and the authored
 * contract records no edge between the two: no operation turns one into the
 * other, and their shapes do not even agree (a scope may carry dots and run to
 * 128 characters; `project_key` may not and does not). So this reader takes the
 * scopes as they are recorded and derives nothing from a document — which is
 * also why a project offered here carries no display name: the name lives in a
 * document that nothing joins to a scope.
 *
 * No declared operation enumerates work-plane projects, so this list is an
 * offer and never the whole truth. Any other key can still be named, the same
 * shape `ctowerctl board query <project_key>` already has.
 */
export function workProjectsIn(document: CompanyBundleDocument): readonly string[] {
  const scopes = new Set(
    document.resources
      .map((resource) => resource.component.scope.project)
      .filter((key): key is string => key !== null)
  );
  return [...scopes].sort();
}
