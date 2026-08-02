import { httpRecordAdapter } from "./httpRecordAdapter";
import type { RecordAdapter } from "./interface";

/**
 * The one-module swap point.
 *
 * Screens import `recordAdapter` and nothing else from the read layer's
 * implementations. Landing the #186 typed feed replaces the right-hand side of
 * this binding; no surface file changes.
 */
export const recordAdapter: RecordAdapter = httpRecordAdapter;
