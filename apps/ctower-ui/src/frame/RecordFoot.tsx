import type { ReactElement } from "react";
import { recordAdapter } from "@/read/adapter";
import { stampText } from "@/read/elapsed";

/**
 * The provenance line. Every screen states which instance it read, on which
 * path, and when — so a screenshot can never be mistaken for a live claim
 * about a different environment.
 */
export function RecordFoot({
  readPath = null,
  watermark = null,
}: {
  readonly readPath?: string | null;
  readonly watermark?: string | null;
}): ReactElement {
  return (
    <div className="foot">
      <span>
        ctower · {recordAdapter.instance.label} instance · {recordAdapter.instance.baseUrl}
      </span>
      <span>{recordAdapter.instance.posture}</span>
      <span>read-only v1 · no mutation path exists on this surface</span>
      {readPath === null ? null : <span>read {readPath}</span>}
      {watermark === null ? null : <span>{watermark}</span>}
      <span>rendered {stampText(new Date().toISOString())}</span>
    </div>
  );
}
