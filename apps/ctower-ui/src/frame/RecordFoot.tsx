import type { ReactElement, ReactNode } from "react";
import { recordAdapter } from "@/read/adapter";
import { stampText } from "@/read/elapsed";

/**
 * The provenance line. Every screen states which instance it read, on which
 * origin and path, and when — so a screenshot can never be mistaken for a live
 * claim about a different environment.
 *
 * The API origin is printed deliberately. It is not a credential and grants the
 * browser nothing: reads happen server-side and no bearer or session reaches
 * the page. Naming the origin is the whole point of a provenance line, and
 * hiding it would make a capture from one instance indistinguishable from a
 * capture from another.
 */
export function RecordFoot({
  readPath = null,
  watermark = null,
}: {
  readonly readPath?: string | null;
  readonly watermark?: ReactNode;
}): ReactElement {
  return (
    <div className="foot">
      <span>
        ctower · {recordAdapter.instance.label} instance · read from{" "}
        {recordAdapter.instance.baseUrl}
      </span>
      <span>{recordAdapter.instance.posture}</span>
      <span>read-only v1 · no mutation path exists on this surface</span>
      {readPath === null ? null : <span>read {readPath}</span>}
      {watermark === null ? null : <span>{watermark}</span>}
      <span>rendered {stampText(new Date().toISOString())}</span>
    </div>
  );
}
