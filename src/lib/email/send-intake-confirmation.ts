// Sends the intake confirmation through Resend and records the result.
// Never throws: a failed email must not turn a saved submission into an error
// (see the decision record, Decision 2).

import { eq } from "drizzle-orm";
import { Resend } from "resend";
import { getDb } from "@/src/db";
import { intakeSubmissions } from "@/src/db/schema/intake-submissions";
import { buildIntakeConfirmationEmail, type IntakeConfirmationInput } from "./intake-confirmation";

export interface IntakeConfirmationJob extends Omit<IntakeConfirmationInput, "supportEmail"> {
  submissionId: string;
  to: string;
}

export type SendResult =
  | { status: "sent"; emailId: string }
  | { status: "skipped"; reason: string }
  | { status: "failed"; reason: string };

/** The part of the Resend client this module uses, so tests can pass a fake. */
export interface EmailClient {
  emails: {
    send: Resend["emails"]["send"];
  };
}

export interface SendDependencies {
  client?: EmailClient | null;
  env?: Record<string, string | undefined>;
  markSent?: (submissionId: string) => Promise<void>;
}

async function markEmailSent(submissionId: string) {
  await getDb()
    .update(intakeSubmissions)
    .set({ emailSent: true })
    .where(eq(intakeSubmissions.id, submissionId));
}

export async function sendIntakeConfirmation(
  job: IntakeConfirmationJob,
  deps: SendDependencies = {},
): Promise<SendResult> {
  const env = deps.env ?? process.env;
  const apiKey = env.RESEND_API_KEY;
  const from = env.INTAKE_EMAIL_FROM;
  const supportEmail = env.INTAKE_SUPPORT_EMAIL;

  if (!apiKey || !from || !supportEmail) {
    // Local development without email settings: same pattern as optional Supabase uploads.
    console.warn(`[intake-email] Skipped ${job.referenceNo}: RESEND_API_KEY, INTAKE_EMAIL_FROM and INTAKE_SUPPORT_EMAIL must all be set.`);
    return { status: "skipped", reason: "email not configured" };
  }

  const content = buildIntakeConfirmationEmail({ ...job, supportEmail });
  const client = deps.client ?? new Resend(apiKey);

  try {
    const { data, error } = await client.emails.send(
      { from, to: job.to, replyTo: supportEmail, subject: content.subject, text: content.text, html: content.html },
      // Same reference number = same email; a retry can never send a second copy.
      { idempotencyKey: `intake-confirmation/${job.referenceNo}` },
    );
    if (error) {
      // daily_quota_exceeded = the free plan's 100 emails/day cap (Decision 1).
      console.error(`[intake-email] Resend rejected ${job.referenceNo}: ${error.name} — ${error.message}`);
      return { status: "failed", reason: error.name };
    }
    try {
      await (deps.markSent ?? markEmailSent)(job.submissionId);
    } catch (err) {
      // The email did go out; only the bookkeeping failed. Do not report a send failure.
      console.error(`[intake-email] Sent ${job.referenceNo} but could not set email_sent:`, err);
    }
    return { status: "sent", emailId: data.id };
  } catch (err) {
    console.error(`[intake-email] Could not send ${job.referenceNo}:`, err);
    return { status: "failed", reason: "exception" };
  }
}
