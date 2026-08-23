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
 *
 * The order is the record's. The bundle export is normalized and deterministic
 * (`SPEC.md`, § CompanyBundle), so the first-appearance order of the scopes is
 * the export's own sequence; sorting them here would overrule the record with
 * a client-side rule no authored document declares, and two surfaces reading
 * one bundle would then have to agree by coincidence rather than by contract.
 */
export function workProjectsIn(document: CompanyBundleDocument): readonly string[] {
  const seen = new Set<string>();
  const projects: string[] = [];
  for (const resource of document.resources) {
    const key = resource.component.scope.project;
    if (key !== null && !seen.has(key)) {
      seen.add(key);
      projects.push(key);
    }
  }
  return projects;
}
