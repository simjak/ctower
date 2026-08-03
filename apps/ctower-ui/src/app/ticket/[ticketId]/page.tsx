import type { ReactNode } from "react";
import { TicketScreen } from "@/surfaces/ticket/TicketScreen";

export const dynamic = "force-dynamic";

export default async function TicketPage({
  params,
}: {
  readonly params: Promise<{ readonly ticketId: string }>;
}): Promise<ReactNode> {
  const { ticketId } = await params;
  return <TicketScreen ticketId={ticketId} />;
}
