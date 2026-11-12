// Builds the confirmation email a submitter receives after the intake form saves.
// Pure functions only: no network or database access, so this is easy to test.

import type { IntakeAnswers } from "../intake/contract";
import { summarizeIntake, type IntakeSummaryGroup } from "../intake/summary";

export interface IntakeConfirmationInput {
  referenceNo: string;
  contactName: string;
  /** Detailed answers. Absent for the older JSON payload (projectName/clientName/clientEmail). */
  answers?: IntakeAnswers;
  /** Used only when `answers` is absent. */
  projectName?: string;
  /** Original file names, never storage paths or URLs. */
  files: { logo: string | null; content: string[] };
  supportEmail: string;
}

export interface EmailContent {
  subject: string;
  text: string;
  html: string;
}

// PRD 6.2 asks for an estimated delivery timeline, but no figure has been agreed yet.
// Leave empty until the Tech Lead/PM confirms one; the line is omitted while empty.
export const ESTIMATED_DELIVERY = "";

const REVIEW_NOTE =
  "BUILD reviews every site before anything goes live. We will email you a preview link first — nothing is published without letting you know.";

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function groupsFor(input: IntakeConfirmationInput): IntakeSummaryGroup[] {
  if (input.answers) return summarizeIntake(input.answers, input.files);
  return input.projectName?.trim()
    ? [{ section: 0, title: "Project", rows: [["Project", input.projectName.trim()]] }]
    : [];
}

export function buildIntakeConfirmationEmail(input: IntakeConfirmationInput): EmailContent {
  const groups = groupsFor(input);
  const uploaded = [input.files.logo, ...input.files.content].filter((name): name is string => !!name);
  const subject = `We received your website request (${input.referenceNo})`;

  const text = [
    `Hi ${input.contactName},`,
    "",
    "Thank you for submitting your website request to BUILD UMass. Here is a copy of your responses for your records.",
    "",
    `Reference number: ${input.referenceNo}`,
    ...(ESTIMATED_DELIVERY ? [`Estimated delivery: ${ESTIMATED_DELIVERY}`] : []),
    "",
    REVIEW_NOTE,
    "",
    ...groups.flatMap((group) => [
      group.title.toUpperCase(),
      ...group.rows.map(([label, value]) => `${label}: ${value}`),
      "",
    ]),
    ...(uploaded.length ? ["FILES YOU UPLOADED", ...uploaded.map((name) => `- ${name}`), ""] : []),
    `Questions or need to change something? Email ${input.supportEmail} and include your reference number.`,
    "",
    "— BUILD UMass",
  ].join("\n");

  const row = ([label, value]: [string, string]) =>
    `<tr><td style="padding:6px 12px 6px 0;vertical-align:top;color:#555;white-space:nowrap">${escapeHtml(label)}</td>` +
    `<td style="padding:6px 0;white-space:pre-wrap">${escapeHtml(value)}</td></tr>`;

  const html = `<!doctype html>
<html><body style="margin:0;padding:24px;background:#f6f6f6;font-family:Arial,Helvetica,sans-serif;color:#111;line-height:1.5">
<div style="max-width:600px;margin:0 auto;background:#fff;border-radius:8px;padding:24px">
<p>Hi ${escapeHtml(input.contactName)},</p>
<p>Thank you for submitting your website request to BUILD UMass. Here is a copy of your responses for your records.</p>
<p style="margin:16px 0;padding:12px 16px;border:1px solid #ddd;border-radius:6px">
<strong>Reference number:</strong> <span style="font-family:monospace">${escapeHtml(input.referenceNo)}</span>${ESTIMATED_DELIVERY ? `<br>
<strong>Estimated delivery:</strong> ${escapeHtml(ESTIMATED_DELIVERY)}` : ""}</p>
<p>${escapeHtml(REVIEW_NOTE)}</p>
${groups.map((group) => `<h2 style="font-size:16px;margin:24px 0 8px">${escapeHtml(group.title)}</h2>
<table style="border-collapse:collapse;font-size:14px">${group.rows.map(row).join("")}</table>`).join("\n")}
${uploaded.length ? `<h2 style="font-size:16px;margin:24px 0 8px">Files you uploaded</h2>
<ul style="font-size:14px;padding-left:20px">${uploaded.map((name) => `<li>${escapeHtml(name)}</li>`).join("")}</ul>` : ""}
<p style="margin-top:24px">Questions or need to change something? Email <a href="mailto:${escapeHtml(input.supportEmail)}">${escapeHtml(input.supportEmail)}</a> and include your reference number.</p>
<p>— BUILD UMass</p>
</div></body></html>`;

  return { subject, text, html };
}
