import type { ReactNode } from "react";
import { selectedProjectKey } from "@/read/projects";
import { readParam } from "@/surfaces/screenParams";
import { TicketScreen } from "@/surfaces/ticket/TicketScreen";

export const dynamic = "force-dynamic";

export default async function TicketPage({
  params,
  searchParams,
}: {
  readonly params: Promise<{ readonly ticketId: string }>;
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactNode> {
  const { ticketId } = await params;
  const project = selectedProjectKey(readParam(await searchParams, "project"));
  return <TicketScreen ticketId={ticketId} projectKey={project} />;
}
