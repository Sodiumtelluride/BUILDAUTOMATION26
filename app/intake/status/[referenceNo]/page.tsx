import type { Metadata } from "next";
import { JobStatusView } from "@/src/components/intake/JobStatusView";
import { normalizeReferenceNo } from "@/src/lib/intake/job-status";

export const metadata: Metadata = { title: "Your website project" };

// Stable, bookmarkable URL tied to the reference number (Intake PRD §6.1).
// ?chose=<family> is set by the design picker for a one-time confirmation line.
export default async function IntakeStatusPage({
  params,
  searchParams,
}: {
  params: Promise<{ referenceNo: string }>;
  searchParams: Promise<{ chose?: string | string[] }>;
}) {
  const { referenceNo } = await params;
  const { chose } = await searchParams;
  const family = typeof chose === "string" && /^[a-z][a-z_-]{0,29}$/i.test(chose) ? chose : null;
  return <JobStatusView referenceNo={normalizeReferenceNo(referenceNo)} chosenFamily={family} />;
}
