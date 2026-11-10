// Runs the confirmation email after the HTTP response has been sent.
// Kept in its own module so route tests can replace it (after() needs a live
// Next.js request and throws when called outside one).

import { after } from "next/server";
import { sendIntakeConfirmation, type IntakeConfirmationJob } from "./send-intake-confirmation";

export function scheduleIntakeConfirmation(job: IntakeConfirmationJob) {
  after(async () => {
    await sendIntakeConfirmation(job);
  });
}
