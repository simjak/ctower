import type { ReactElement } from "react";
import { Button, Card, CardBody, CardHeader, CardTitle, Mono } from "../../ui/primitives";
import { AddressLine, NoAddress } from "./Address";
import { RevokeRow } from "./RevokeRow";
import type { CrewRow } from "./roster";
import type { RevokeAct } from "./useRevokeAct";

/**
 * The crew this company records.
 *
 * The rows are the bundle's own assignments — a subject carrying an agent
 * profile — so the roster is exactly as long as the record says and no row is
 * inferred. The address column is the honest half: ctower has no operation that
 * lists a seat, so it reports what this session minted and says "not read" for
 * everything else rather than drawing an idle mark over an unknown.
 */
export function Roster({
  crews,
  revoke,
}: {
  readonly crews: readonly CrewRow[];
  readonly revoke: RevokeAct;
}): ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Roster</CardTitle>
        <span className="flex-1" />
        <Mono className="text-muted">{crews.length}</Mono>
      </CardHeader>
      <CardBody className="p-0">
        {crews.length === 0 ? (
          <p className="m-0 px-4 py-3 text-sm text-muted">
            No crew is in this company yet. Define one below.
          </p>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-line">
                <Head>Crew</Head>
                <Head>Profile</Head>
                <Head>Address</Head>
                <th className="w-0" />
              </tr>
            </thead>
            <tbody>
              {crews.map((crew) => (
                <Row key={crew.subject} crew={crew} revoke={revoke} />
              ))}
            </tbody>
          </table>
        )}
      </CardBody>
      <p className="m-0 border-t border-line px-4 py-2.5 text-xs text-muted">
        An address shows here only where this session minted it; ctower serves no read for a seat.
      </p>
    </Card>
  );
}

function Row({
  crew,
  revoke,
}: {
  readonly crew: CrewRow;
  readonly revoke: RevokeAct;
}): ReactElement {
  const address = crew.address;
  const revocable = address !== null && address.state === "active";
  const opened = revoke.open !== null && revoke.open.subject === crew.subject;

  return (
    <>
      <tr className="border-b border-line last:border-b-0">
        <td className="px-4 py-2.5 align-top">
          <span className="font-medium text-fg">{crew.name}</span>
          <Mono className="ml-2 text-muted">{crew.prefix}</Mono>
        </td>
        <td className="px-4 py-2.5 align-top">
          <Mono className="text-muted">{crew.profileKey}</Mono>
        </td>
        <td className="px-4 py-2.5 align-top">
          {address === null ? <NoAddress /> : <AddressLine receipt={address} />}
        </td>
        <td className="px-4 py-2.5 text-right align-top">
          {!revocable || opened ? null : (
            <Button
              size="sm"
              variant="danger"
              onClick={(): void => {
                revoke.start({ subject: crew.subject, receipt: address });
              }}
            >
              Revoke
            </Button>
          )}
        </td>
      </tr>
      {opened ? (
        <tr className="border-b border-line last:border-b-0">
          <td colSpan={4} className="px-4 pb-4">
            <RevokeRow revoke={revoke} />
          </td>
        </tr>
      ) : null}
    </>
  );
}

function Head({ children }: { readonly children: string }): ReactElement {
  return <th className="px-4 py-2 text-left text-2xs font-medium text-muted">{children}</th>;
}
