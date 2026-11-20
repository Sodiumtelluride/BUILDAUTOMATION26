import { desc, eq } from "drizzle-orm"
import { getDb } from "@/src/db"
import { intakeSubmissions } from "@/src/db/schema/intake-submissions"
import type { IntakeAnswers } from "@/src/lib/intake/contract"
import type { UploadedIntakeFile } from "@/src/lib/intake/uploads"

// Intake forms hold client contact details, so only these roles can see them (same rule as the intake API)
export const REVIEW_ROLES = ["admin", "reviewer"]

export const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * Reads the full form answers saved as JSON in the notes column. Returns null for older submissions without them.
 * `links` are the organization and job the submission created, or null if either id is missing or malformed.
 */
export function parseIntakeNotes(notes: string | null): {
  answers: Partial<IntakeAnswers>
  attachments: UploadedIntakeFile[]
  links: { organizationId: string; jobId: string } | null
} | null {
  if (!notes) return null
  try {
    const value = JSON.parse(notes)
    if (value?.version !== 1 || typeof value.answers !== "object" || value.answers === null) return null
    const hasLinks = [value.organizationId, value.jobId].every((id) => typeof id === "string" && UUID_RE.test(id))
    return {
      answers: value.answers,
      attachments: Array.isArray(value.attachments) ? value.attachments : [],
      links: hasLinks ? { organizationId: value.organizationId, jobId: value.jobId } : null,
    }
  } catch {
    return null
  }
}

/** Every intake submission, newest first, with the organization name taken from the saved answers. */
export async function listIntakes() {
  const rows = await getDb()
    .select({
      id: intakeSubmissions.id,
      referenceNo: intakeSubmissions.referenceNo,
      projectName: intakeSubmissions.projectName,
      clientName: intakeSubmissions.clientName,
      clientEmail: intakeSubmissions.clientEmail,
      status: intakeSubmissions.status,
      createdAt: intakeSubmissions.createdAt,
      notes: intakeSubmissions.notes,
      demoUrl: intakeSubmissions.demoUrl,
      demoStatus: intakeSubmissions.demoStatus,
      demoError: intakeSubmissions.demoError,
      demoStartedAt: intakeSubmissions.demoStartedAt,
    })
    .from(intakeSubmissions)
    .orderBy(desc(intakeSubmissions.createdAt))

  return rows.map(({ notes, ...row }) => ({ ...row, organization: parseIntakeNotes(notes)?.answers.organizationName ?? null }))
}

/** One submission by id with its parsed answers, or null if the id is malformed or not found. */
export async function getIntake(id: string) {
  if (!UUID_RE.test(id)) return null
  const [row] = await getDb().select().from(intakeSubmissions).where(eq(intakeSubmissions.id, id)).limit(1)
  if (!row) return null
  return { ...row, details: parseIntakeNotes(row.notes) }
}

/** Saved answers as titled groups of [label, value] rows, in the same order as the intake form. */
export function answerGroups(a: Partial<IntakeAnswers>): { title: string; rows: [string, string | undefined][] }[] {
  // join a list answer into one line, e.g. ["Home", "About"] -> "Home, About"
  const list = (values?: string[]) => values?.filter(Boolean).join(", ")

  return [
    {
      title: "Organization & Contact",
      rows: [["Organization", a.organizationName], ["Contact", a.primaryContactName], ["Email", a.primaryContactEmail], ["Type", a.organizationType]],
    },
    {
      title: "Project Goals",
      rows: [
        ["Goal", a.primaryGoal],
        ["About", a.organizationDescription],
        ["Audience", a.targetAudience],
        ["Pages", list(a.pages)],
        ["Features", list(a.features)],
        ["Feature details", a.featureDetails],
      ],
    },
    {
      title: "Design & Branding",
      rows: [["Logo", a.hasLogo], ["Colors", a.brandColors], ["Fonts", a.brandFonts], ["Style", a.visualStyle], ["References", list(a.referenceWebsites)]],
    },
    {
      title: "Content",
      rows: [["Has content", a.hasContent], ["Existing text", a.existingContent], ["Tone", list(a.toneAndVoice)], ["Avoid", a.contentRestrictions]],
    },
    {
      title: "Technical Details",
      rows: [["Domain", a.hasDomain], ["Domain name", a.domainName], ["Integrations", list(a.integrations)], ["Integration details", a.integrationDetails]],
    },
    { title: "Additional Information", rows: [["Anything else", a.additionalInfo]] },
  ]
}
