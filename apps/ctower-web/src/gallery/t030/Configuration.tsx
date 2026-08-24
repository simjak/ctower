import { useState } from "react";
import { ExternalLink, X } from "lucide-react";
import type { ReactElement } from "react";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Chip,
  Input,
  Select,
  Textarea,
} from "../../ui/primitives";
import { Environment } from "./Environment";
import { GOALS, HERE, REPOSITORY } from "./fixtures";
import { Legend, Mark, Row } from "./Marks";

/**
 * The Configuration tab as it should be, once a project can be described.
 *
 * This is the T-024 amendment 2 reference in ctower's own type: labeled rows,
 * goals as chips, a codebase card, an archive zone. Four of its rows are the
 * record's today; the rest are a **proposal**, and the whole point of the bench
 * is that the proposal can be looked at before a contract moves to meet it.
 * `?screen=configuration-marked` draws the same screen with each row's
 * disposition beside it.
 *
 * Nothing here reads or writes. The fields take local state so the screen can
 * be seen doing what it does — an edit arms the one primary — and that state
 * dies with the tab.
 */
export function Configuration({ marked }: { readonly marked: boolean }): ReactElement {
  const [name, setName] = useState(HERE.name);
  const [prefix, setPrefix] = useState(HERE.prefix ?? "");
  const [about, setAbout] = useState(ABOUT);
  const [status, setStatus] = useState("active");
  const [goals, setGoals] = useState<readonly string[]>(GOALS);

  const dirty =
    name !== HERE.name || prefix !== (HERE.prefix ?? "") || about !== ABOUT || goals !== GOALS;

  return (
    <div className="space-y-4">
      {marked ? <Legend /> : null}

      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardBody className="space-y-0 py-1">
          <Row label="Name" mark={<Mark mark="record-backed" why="name" on={marked} />}>
            <Input
              value={name}
              aria-label="Name"
              onChange={(event): void => {
                setName(event.target.value);
              }}
            />
          </Row>
          <Row label="Ticket prefix" mark={<Mark mark="record-backed" why="prefix" on={marked} />}>
            <Input
              value={prefix}
              aria-label="Ticket prefix"
              className="w-24"
              onChange={(event): void => {
                setPrefix(event.target.value.toUpperCase());
              }}
            />
          </Row>
          <Row
            label="Description"
            tall
            mark={<Mark mark="needs-schema" why="description" on={marked} />}
          >
            <Textarea
              rows={2}
              value={about}
              aria-label="Description"
              placeholder="Say what this project is for…"
              onChange={(event): void => {
                setAbout(event.target.value);
              }}
            />
          </Row>
          <Row label="Status" mark={<Mark mark="needs-schema" why="status" on={marked} />}>
            <Select
              value={status}
              aria-label="Status"
              className="w-44"
              onChange={(event): void => {
                setStatus(event.target.value);
              }}
            >
              {STATUSES.map((choice) => (
                <option key={choice.value} value={choice.value}>
                  {choice.label}
                </option>
              ))}
            </Select>
          </Row>
          <Row label="Goals" mark={<Mark mark="record-backed" why="goals" on={marked} />}>
            <span className="flex flex-wrap items-center gap-1.5">
              {goals.map((goal) => (
                <Chip key={goal} tone="amber" className="gap-1 pr-1">
                  {goal}
                  <button
                    type="button"
                    aria-label={`Stop serving ${goal}`}
                    className="cursor-pointer rounded-sm p-0.5 hover:bg-raised"
                    onClick={(): void => {
                      setGoals(goals.filter((held) => held !== goal));
                    }}
                  >
                    <X aria-hidden className="size-3" />
                  </button>
                </Chip>
              ))}
              <Button variant="ghost" size="sm">
                + Goal
              </Button>
            </span>
          </Row>
          <Row label="Created" mark={<Mark mark="needs-read" why="created" on={marked} />}>
            21 August
          </Row>
          <Row label="Updated" mark={<Mark mark="needs-read" why="updated" on={marked} />}>
            Today, 2:46pm
          </Row>
        </CardBody>
      </Card>

      <Environment marked={marked} />

      <Card>
        <CardHeader>
          <CardTitle>Codebase</CardTitle>
        </CardHeader>
        <CardBody className="space-y-0 py-1">
          <Row label="Repository" mark={<Mark mark="record-backed" why="repository" on={marked} />}>
            <span className="flex flex-wrap items-center gap-3">
              <a
                href={REPOSITORY.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-fg underline decoration-line underline-offset-2 hover:decoration-amber"
              >
                <ExternalLink aria-hidden className="size-3.5 shrink-0 text-muted" />
                {REPOSITORY.label}
              </a>
              <Button variant="quiet" size="sm">
                Change
              </Button>
            </span>
          </Row>
        </CardBody>
      </Card>

      <Card className="border-danger/50">
        <CardHeader className="border-danger/50">
          <CardTitle className="text-danger">Danger zone</CardTitle>
          <span className="flex-1" />
          <Mark mark="needs-ceremony" why="archive" on={marked} />
        </CardHeader>
        <CardBody className="flex flex-wrap items-center gap-3">
          <p className="m-0 min-w-0 flex-1 text-sm text-muted">
            Archiving hides this project from the rail and from every chooser. Nothing is deleted:
            the record only ever grows.
          </p>
          <Button variant="danger">Archive project</Button>
        </CardBody>
      </Card>

      <SaveBar dirty={dirty} />
    </div>
  );
}

/**
 * The one primary, and what pressing it actually does.
 *
 * A row on this tab is not a field that can be updated — a recorded project is
 * a document, and changing one authors a superseding revision of it through the
 * same validate → plan → apply the Projects screen already runs. So the screen
 * collects the whole edit and offers a single act, and says what that act costs
 * before it is pressed. Nothing autosaves: an append-only record with an
 * autosaving form would mint a revision per keystroke.
 */
function SaveBar({ dirty }: { readonly dirty: boolean }): ReactElement {
  return (
    <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
      <p className="m-0 min-w-0 flex-1 text-2xs text-muted">
        {dirty
          ? "Saving records a new version of this project. You will see what moves first."
          : "Nothing has changed yet."}
      </p>
      <Button variant="quiet" disabled={!dirty}>
        Discard
      </Button>
      <Button variant="primary" disabled={!dirty}>
        Save changes
      </Button>
    </div>
  );
}

const ABOUT =
  "The control plane the crews run on: the record, the kernel, the API and this console.";

const STATUSES: readonly { readonly value: string; readonly label: string }[] = [
  { value: "planned", label: "Planned" },
  { value: "active", label: "Active" },
  { value: "paused", label: "Paused" },
  { value: "done", label: "Done" },
];
