import { useState } from "react";
import { X } from "lucide-react";
import type { ReactElement } from "react";
import { Button, Card, CardBody, CardHeader, CardTitle, Input, Select } from "../../ui/primitives";
import { BINDINGS } from "./fixtures";
import { Mark } from "./Marks";

/**
 * A project's own variables, and the one thing this card refuses to be.
 *
 * The reference draws `KEY → secret ref` as two more rows in the details list.
 * Here it is a card, for two reasons the reference does not have to care about.
 * A list that grows is a table, not a row. And the rule the reference states in
 * passing — a project's value beats the same name set on an agent — is a
 * sentence about precedence that has to live somewhere a person will read it.
 *
 * The second half of the value is a **chooser over the company's own secret
 * bindings**, never a text box. ctower's hard boundary is that secrets are
 * references and never values, and the wire cannot enforce that on its own: a
 * free string field accepts a pasted token and the contract is none the wiser.
 * A control that can only emit a name already in the bundle makes the mistake
 * unavailable rather than merely forbidden.
 */
export function Environment({ marked }: { readonly marked: boolean }): ReactElement {
  const [rows, setRows] = useState(SEEDED);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Environment</CardTitle>
        <span className="flex-1" />
        <Mark mark="needs-schema" why="env" on={marked} />
      </CardHeader>
      <CardBody className="space-y-2.5">
        <p className="m-0 text-2xs text-muted">
          A variable set here beats the same name set on an agent.
        </p>
        {rows.map((row, index) => (
          <div key={row.id} className="flex flex-wrap items-center gap-2">
            <Input
              value={row.name}
              aria-label="Variable name"
              placeholder="VARIABLE_NAME"
              className="w-full sm:w-56"
              onChange={(event): void => {
                setRows(rename(rows, index, event.target.value.toUpperCase()));
              }}
            />
            <span aria-hidden className="text-muted">
              →
            </span>
            <Select
              defaultValue={row.binding}
              aria-label="Where its value comes from"
              className="w-full sm:w-64"
            >
              {BINDINGS.map((binding) => (
                <option key={binding} value={binding}>
                  {readable(binding)}
                </option>
              ))}
            </Select>
            <Button
              variant="quiet"
              size="sm"
              aria-label={`Remove ${row.name}`}
              onClick={(): void => {
                setRows(rows.filter((held) => held.id !== row.id));
              }}
            >
              <X />
            </Button>
          </div>
        ))}
        <Button
          variant="ghost"
          size="sm"
          onClick={(): void => {
            setRows([...rows, { id: rows.length + 1, name: "", binding: BINDINGS[0] ?? "" }]);
          }}
        >
          + Variable
        </Button>
      </CardBody>
    </Card>
  );
}

function rename(rows: readonly Variable[], index: number, name: string): readonly Variable[] {
  return rows.map((row, at) => (at === index ? { ...row, name } : row));
}

/**
 * A binding named as the person who created it would say it.
 *
 * The bundle keeps `SOURCE_CONTROL_TOKEN` because that is a name in an
 * allowlist; the operator picking one is choosing a thing, and the standing
 * rule says a thing renders as the name a person gave it. The underscores go
 * and nothing else changes — the value behind it never renders at all.
 */
function readable(binding: string): string {
  const words = binding.toLowerCase().replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

interface Variable {
  readonly id: number;
  readonly name: string;
  readonly binding: string;
}

/**
 * One variable, and the two halves deliberately do not match: the name is what
 * the project's own tooling reads, the binding is what the company already
 * holds. Drawing them identical would hide that this row is a mapping.
 */
const SEEDED: readonly Variable[] = [
  { id: 1, name: "GITHUB_TOKEN", binding: "SOURCE_CONTROL_TOKEN" },
];
