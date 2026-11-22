import type { Metadata } from "next";
import { DesignSelectionView } from "@/src/components/intake/DesignSelectionView";
import { normalizeReferenceNo } from "@/src/lib/intake/job-status";

export const metadata: Metadata = { title: "Choose your design" };

export default async function IntakeDesignsPage({ params }: { params: Promise<{ referenceNo: string }> }) {
  const { referenceNo } = await params;
  return <DesignSelectionView referenceNo={normalizeReferenceNo(referenceNo)} />;
}
