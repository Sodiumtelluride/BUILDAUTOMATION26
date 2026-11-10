import assert from "node:assert/strict";
import { test } from "node:test";
import { CONTENT_YES, LOGO_UPLOAD } from "../src/lib/intake/contract.ts";
import { buildIntakeConfirmationEmail } from "../src/lib/email/intake-confirmation.ts";
import { sendIntakeConfirmation } from "../src/lib/email/send-intake-confirmation.ts";
import { summarizeIntake } from "../src/lib/intake/summary.ts";
import { intakeAnswers } from "./helpers/intake-fixture.mjs";

const env = {
  RESEND_API_KEY: "re_test",
  INTAKE_EMAIL_FROM: "BUILD UMass <no-reply@buildumass.org>",
  INTAKE_SUPPORT_EMAIL: "support@buildumass.org",
};

function job(overrides = {}) {
  return {
    submissionId: "11111111-1111-4111-8111-111111111111",
    referenceNo: "INT-20261110-ABC123",
    to: "maria@example.org",
    contactName: "Maria Santos",
    answers: intakeAnswers(),
    files: { logo: null, content: [] },
    ...overrides,
  };
}

function fakeClient(result = { data: { id: "email_1" }, error: null }) {
  const calls = [];
  return {
    calls,
    emails: {
      async send(payload, options) {
        calls.push({ payload, options });
        if (result instanceof Error) throw result;
        return result;
      },
    },
  };
}

test("email contains the reference number and every answered section", () => {
  const email = buildIntakeConfirmationEmail({ ...job(), supportEmail: env.INTAKE_SUPPORT_EMAIL });
  assert.match(email.subject, /INT-20261110-ABC123/);
  for (const part of [email.text, email.html]) {
    assert.match(part, /INT-20261110-ABC123/);
    assert.match(part, /Pioneer Community/);
    assert.match(part, /Families and volunteers throughout Western Massachusetts\./);
    assert.match(part, /preview link/);
    assert.match(part, /support@buildumass\.org/);
  }
  for (const title of ["Organization &amp; Contact", "Project Goals", "Design &amp; Branding", "Content", "Technical Details"]) {
    assert.ok(email.html.includes(title), `missing section ${title}`);
  }
  // Empty optional answers are left out rather than printed as blank rows.
  assert.doesNotMatch(email.text, /Feature details:/);
});

test("submitter text is escaped in the HTML email", () => {
  const email = buildIntakeConfirmationEmail({
    ...job({ answers: intakeAnswers({ organizationName: "<script>alert(1)</script> & Co" }) }),
    supportEmail: env.INTAKE_SUPPORT_EMAIL,
  });
  assert.doesNotMatch(email.html, /<script>/);
  assert.match(email.html, /&lt;script&gt;alert\(1\)&lt;\/script&gt; &amp; Co/);
});

test("uploaded files appear by name only", () => {
  const email = buildIntakeConfirmationEmail({
    ...job({
      answers: intakeAnswers({ hasLogo: LOGO_UPLOAD, hasContent: CONTENT_YES, existingContent: "Our story" }),
      files: { logo: "logo.png", content: ["about.pdf"] },
    }),
    supportEmail: env.INTAKE_SUPPORT_EMAIL,
  });
  assert.match(email.text, /- logo\.png/);
  assert.match(email.text, /- about\.pdf/);
  assert.doesNotMatch(email.text, /supabase:|https?:\/\/[^ ]*\.pdf/);
});

test("older JSON submissions still get a confirmation", () => {
  const email = buildIntakeConfirmationEmail({
    referenceNo: "INT-20261110-OLD001",
    contactName: "Maria",
    projectName: "Website",
    files: { logo: null, content: [] },
    supportEmail: env.INTAKE_SUPPORT_EMAIL,
  });
  assert.match(email.text, /Project: Website/);
});

test("review step and email share one grouping", () => {
  const groups = summarizeIntake(intakeAnswers({ additionalInfo: "Launch before spring." }), { logo: null, content: [] });
  assert.deepEqual(groups.map((group) => group.section), [0, 1, 2, 3, 4, 5]);
  assert.deepEqual(groups.at(-1).rows, [["Additional details", "Launch before spring."]]);
});

test("a successful send uses the reference number as the idempotency key and records email_sent", async () => {
  const client = fakeClient();
  const marked = [];
  const result = await sendIntakeConfirmation(job(), { client, env, markSent: async (id) => { marked.push(id); } });
  assert.deepEqual(result, { status: "sent", emailId: "email_1" });
  assert.equal(client.calls.length, 1);
  assert.equal(client.calls[0].options.idempotencyKey, "intake-confirmation/INT-20261110-ABC123");
  assert.equal(client.calls[0].payload.to, "maria@example.org");
  assert.equal(client.calls[0].payload.from, env.INTAKE_EMAIL_FROM);
  assert.equal(client.calls[0].payload.replyTo, env.INTAKE_SUPPORT_EMAIL);
  assert.deepEqual(marked, [job().submissionId]);
});

test("a rejected send (for example the daily cap) is reported and email_sent stays false", async (t) => {
  t.mock.method(console, "error", () => {});
  const client = fakeClient({ data: null, error: { name: "daily_quota_exceeded", message: "Daily limit reached", statusCode: 429 } });
  const marked = [];
  const result = await sendIntakeConfirmation(job(), { client, env, markSent: async (id) => { marked.push(id); } });
  assert.deepEqual(result, { status: "failed", reason: "daily_quota_exceeded" });
  assert.deepEqual(marked, []);
});

test("network errors never throw out of the sender", async (t) => {
  t.mock.method(console, "error", () => {});
  const result = await sendIntakeConfirmation(job(), { client: fakeClient(new Error("socket hang up")), env, markSent: async () => {} });
  assert.deepEqual(result, { status: "failed", reason: "exception" });
});

test("a failed email_sent update still reports the email as sent", async (t) => {
  t.mock.method(console, "error", () => {});
  const result = await sendIntakeConfirmation(job(), { client: fakeClient(), env, markSent: async () => { throw new Error("db down"); } });
  assert.equal(result.status, "sent");
});

test("missing email settings skip sending without calling Resend", async (t) => {
  t.mock.method(console, "warn", () => {});
  const client = fakeClient();
  const result = await sendIntakeConfirmation(job(), { client, env: { ...env, RESEND_API_KEY: "" } });
  assert.equal(result.status, "skipped");
  assert.equal(client.calls.length, 0);
});
