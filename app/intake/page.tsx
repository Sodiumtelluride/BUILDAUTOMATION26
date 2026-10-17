import type { Metadata } from "next";
import { IntakeForm } from "@/src/components/intake/IntakeForm";

export const metadata: Metadata = { title: "Start a website project" };

export default function IntakePage() {
  return <IntakeForm />;
}
