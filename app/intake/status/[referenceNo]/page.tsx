import type { Metadata } from "next";
import { JobStatusView } from "@/src/components/intake/JobStatusView";
import { normalizeReferenceNo } from "@/src/lib/intake/job-status";

export const metadata: Metadata = { title: "Your website project" };

// Stable, bookmarkable URL tied to the reference number (Intake PRD §6.1).
export default async function IntakeStatusPage({ params }: { params: Promise<{ referenceNo: string }> }) {
  const { referenceNo } = await params;
  return <JobStatusView referenceNo={normalizeReferenceNo(referenceNo)} />;
}
