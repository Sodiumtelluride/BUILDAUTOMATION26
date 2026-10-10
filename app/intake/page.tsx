import { Inter } from "next/font/google";
import { IntakeForm } from "@/src/components/intake/IntakeForm";

const inter = Inter({ subsets: ["latin"] });

export default function IntakePage() {
  return (
    <div className={inter.className}>
      <IntakeForm />
    </div>
  );
}