import { KeyRound } from "lucide-react";
import { useState } from "react";
import type { ReactElement } from "react";
import { probeAdmission } from "../api/bounded";
import { Button, Card, CardBody, Input, Mono } from "../ui/primitives";
import { Mark } from "../ui/marks";

/**
 * The gate, and the whole of what it protects.
 *
 * The process serving this page holds the operator credential and attaches it
 * to everything it proxies. Reaching the port is therefore reaching operator
 * authority, and the port is on the tailnet so the operator can walk the wizard
 * from a laptop. The server prints one token at startup; this screen is where it
 * is pasted, once per tab.
 *
 * It proves the token before keeping it, so a bad paste is answered here rather
 * than as an unexplained refusal four screens later.
 */
export function Admission({ onAdmitted }: { readonly onAdmitted: () => void }): ReactElement {
  const [typed, setTyped] = useState("");
  const [checking, setChecking] = useState(false);
  const [refused, setRefused] = useState(false);

  const offer = (): void => {
    setChecking(true);
    setRefused(false);
    void (async (): Promise<void> => {
      const admitted = await probeAdmission(typed);
      setChecking(false);
      if (admitted) {
        onAdmitted();
        return;
      }
      setRefused(true);
    })();
  };

  return (
    <main className="grid min-h-dvh place-content-center px-6">
      <Card className="w-[min(440px,100%)]">
        <CardBody>
          <div className="flex items-start gap-4">
            <span
              aria-hidden
              className="grid size-10 shrink-0 place-content-center rounded-sm bg-raised text-muted"
            >
              <KeyRound className="size-5" />
            </span>
            <div className="min-w-0 flex-1">
              <h1 className="m-0 text-lg leading-tight font-bold tracking-[-0.02em]">
                Unlock this console
              </h1>
              <p className="mt-1 mb-0 text-sm text-muted">
                Paste the session token this server printed when it started.
              </p>
            </div>
          </div>

          <form
            className="mt-6"
            onSubmit={(event): void => {
              event.preventDefault();
              offer();
            }}
          >
            <label className="mb-1.5 block text-xs text-muted" htmlFor="session-token">
              Session token
            </label>
            <Input
              id="session-token"
              className="h-11 font-mono text-sm"
              autoFocus
              autoComplete="off"
              spellCheck={false}
              disabled={checking}
              value={typed}
              onChange={(event): void => {
                setTyped(event.target.value);
                setRefused(false);
              }}
            />
            {refused ? (
              <p className="mt-3 mb-0 flex items-start gap-2 text-sm text-fg">
                <Mark name="dead" className="mt-0.5" /> That token is not this server&apos;s.
                Restarting the server prints a new one.
              </p>
            ) : null}
            <div className="mt-6 flex items-center justify-end">
              <Button
                type="submit"
                variant="primary"
                disabled={checking || typed.trim() === ""}
                onClick={offer}
              >
                {checking ? "Checking" : "Unlock"}
              </Button>
            </div>
          </form>

          <p className="mt-6 mb-0 border-t border-line pt-4 text-xs text-muted">
            It admits you to <Mono>{window.location.host}</Mono> and nothing else. ctower never sees
            it, and it grants nothing there.
          </p>
        </CardBody>
      </Card>
    </main>
  );
}
