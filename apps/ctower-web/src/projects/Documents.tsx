import type { ReactElement } from "react";
import { Hint } from "../ui/form";
import { Card, CardBody, CardHeader, CardTitle, Mono } from "../ui/primitives";
import type { ProjectDocument } from "./read";

const JOIN =
  "A document's key is authored on its own; nothing in this bundle binds one to a project above.";

const PREFIX =
  "The prefix a project stamps on its ticket keys. A bundle written before prefixes existed carries none.";

/**
 * The `project` documents the bundle carries: a name, a ticket prefix, the
 * repository the work lands in, and the goals it serves.
 *
 * They sit under the portfolio rather than inside it because no recorded fact
 * joins the two, and the (i) on the title is where that is said once. A prefix
 * the payload does not carry is drawn as missing, never as empty.
 */
export function Documents({
  documents,
}: {
  readonly documents: readonly ProjectDocument[];
}): ReactElement {
  return (
    <Card className="mt-6">
      <CardHeader>
        <CardTitle>Project documents</CardTitle>
        <Hint text={JOIN} />
      </CardHeader>
      <CardBody className="p-0">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-line text-2xs text-muted">
              <th className="py-1.5 pl-4 text-left font-normal">Document</th>
              <th className="py-1.5 pl-6 text-left font-normal">
                <span className="inline-flex items-center gap-1.5">
                  Prefix
                  <Hint text={PREFIX} />
                </span>
              </th>
              <th className="py-1.5 pl-6 text-left font-normal">Repository</th>
              <th className="py-1.5 pr-4 pl-6 text-left font-normal">Goals</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((document) => (
              <Row key={document.id} document={document} />
            ))}
          </tbody>
        </table>
      </CardBody>
    </Card>
  );
}

function Row({ document }: { readonly document: ProjectDocument }): ReactElement {
  return (
    <tr className="border-b border-line text-sm last:border-b-0">
      <td className="py-2 pl-4">
        <div className="font-medium text-fg">{document.name}</div>
        <Mono className="text-muted">
          {document.key}@{document.revision}
        </Mono>
      </td>
      <td className="py-2 pl-6">
        {document.prefix === null ? (
          <span className="text-xs text-muted">not recorded</span>
        ) : (
          <Mono className="text-fg">{document.prefix}</Mono>
        )}
      </td>
      <td className="max-w-[20rem] py-2 pl-6">
        {document.repository === null ? (
          <span className="text-xs text-muted">not recorded</span>
        ) : (
          <Mono className="block truncate text-muted" title={document.repositoryTitle ?? ""}>
            {document.repository}
          </Mono>
        )}
      </td>
      <td className="py-2 pr-4 pl-6 text-xs text-muted">{document.goals.join(" · ")}</td>
    </tr>
  );
}
