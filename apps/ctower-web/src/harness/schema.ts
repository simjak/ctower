/**
 * Adapter configuration, declared rather than coded.
 *
 * Paperclip's `getConfigSchema()` is the mechanic being adopted: an adapter
 * declares its fields and the UI renders them generically, so there is no React
 * per harness and a new adapter needs no UI change at all.
 *
 * Every adapter here declares **no** fields today, and that is the honest state
 * rather than a placeholder. The two things a ctower harness component records
 * are the adapter and its capabilities, and capabilities are the binding's
 * declaration — "declared data, never a runtime discovery", says the capability
 * contract — so an operator choosing them in a browser would be claiming
 * something on the binding's behalf. When the harness surface lands and
 * adapters declare their own fields, this list fills and the renderer below
 * draws them unchanged.
 */
export type FieldType = "text" | "select" | "toggle" | "number";

export interface FieldOption {
  readonly value: string;
  readonly label: string;
}

export interface FieldSchema {
  readonly key: string;
  readonly label: string;
  readonly type: FieldType;
  readonly options?: readonly FieldOption[];
  readonly hint?: string;
  readonly group: string;
  readonly required?: boolean;
}

export interface Adapter {
  readonly key: string;
  readonly label: string;
  readonly blurb: string;
  /** At most one adapter carries this: a field of equals recommends nothing. */
  readonly recommended: boolean;
  /** What this adapter declares as its settings. Empty is a real answer. */
  readonly config: readonly FieldSchema[];
}

/**
 * The three adapters the runner actually has a binding for. A card for anything
 * else would be offering a harness with nothing behind it, which is how a stub
 * becomes an adapter by accident.
 */
export const ADAPTERS: readonly Adapter[] = [
  {
    key: "claude-code",
    label: "Claude Code",
    blurb: "Claude Code CLI harness",
    recommended: true,
    config: [],
  },
  { key: "codex", label: "Codex", blurb: "Codex CLI harness", recommended: false, config: [] },
  {
    key: "hermes",
    label: "Hermes",
    blurb: "Hermes profile harness",
    recommended: false,
    config: [],
  },
];

export function adapterFor(key: string): Adapter | undefined {
  return ADAPTERS.find((adapter) => adapter.key === key);
}
