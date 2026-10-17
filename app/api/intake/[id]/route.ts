import { NextRequest, NextResponse } from "next/server"
import { and, eq } from "drizzle-orm"
import { getDb } from "@/src/db"
import { organizations } from "@/src/db/schema/organizations"
import { intakeJobs } from "@/src/db/schema/intake-jobs"
import { intakeSubmissions } from "@/src/db/schema/intake-submissions"
import { auth } from "@/src/auth"

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function submissionLinks(notes: string | null) {
  if (!notes) return null
  try {
    const value: unknown = JSON.parse(notes)
    if (!value || typeof value !== "object" || !("version" in value) || value.version !== 1 ||
      !("organizationId" in value) || typeof value.organizationId !== "string" || !UUID_RE.test(value.organizationId) ||
      !("jobId" in value) || typeof value.jobId !== "string" || !UUID_RE.test(value.jobId)) return null
    return { organizationId: value.organizationId, jobId: value.jobId }
  } catch {
    return null
  }
}

async function authorizeReviewer() {
  const session = await auth()
  if (!session?.user) return NextResponse.json({ success: false, error: "Authentication required" }, { status: 401 })
  if (!["admin", "reviewer"].includes(session.user.role)) return NextResponse.json({ success: false, error: "Reviewer access required" }, { status: 403 })
  return null
}

interface RouteContext {
  params: Promise<{ id: string }>
}

export async function GET(_req: NextRequest, ctx: RouteContext) {
  const unauthorized = await authorizeReviewer()
  if (unauthorized) return unauthorized
  const { id } = await ctx.params

  if (!UUID_RE.test(id)) {
    return NextResponse.json(
      { success: false, error: "Invalid submission ID" },
      { status: 400 }
    )
  }

  try {
    const db = getDb()
    const [submission] = await db
      .select()
      .from(intakeSubmissions)
      .where(eq(intakeSubmissions.id, id))
      .limit(1)

    if (!submission) {
      return NextResponse.json(
        { success: false, error: "Submission not found" },
        { status: 404 }
      )
    }

    const links = submissionLinks(submission.notes)
    const [organization] = submission.clientEmail
      ? await db
          .select()
          .from(organizations)
          .where(links
            ? and(eq(organizations.id, links.organizationId), eq(organizations.contactEmail, submission.clientEmail))
            : eq(organizations.contactEmail, submission.clientEmail))
          .limit(1)
      : []

    const jobs = organization
      ? await db
          .select()
          .from(intakeJobs)
          .where(links
            ? and(eq(intakeJobs.orgId, organization.id), eq(intakeJobs.id, links.jobId))
            : eq(intakeJobs.orgId, organization.id))
      : []

    return NextResponse.json({
      success: true,
      data: {
        submission,
        organization: organization ?? null,
        jobs,
      },
    })
  } catch (err) {
    console.error(`[GET /api/intake/${id}] Database error:`, err)
    return NextResponse.json(
      { success: false, error: "Failed to fetch submission." },
      { status: 500 }
    )
  }
}

export async function PATCH(req: NextRequest, ctx: RouteContext) {
  const unauthorized = await authorizeReviewer()
  if (unauthorized) return unauthorized
  const { id } = await ctx.params
  if (!UUID_RE.test(id)) return NextResponse.json({ success: false, error: "Invalid submission ID" }, { status: 400 })

  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json(
      { success: false, error: "Invalid JSON" },
      { status: 400 }
    )
  }

  const VALID_STATUSES = new Set([
    "pending",
    "queued",
    "in_progress",
    "awaiting_review",
    "approved",
    "deployed",
    "failed",
    "cancelled",
  ])

  if (
    !body ||
    typeof body !== "object" ||
    Array.isArray(body) ||
    !("status" in (body as object)) ||
    typeof (body as Record<string, unknown>).status !== "string" ||
    !VALID_STATUSES.has((body as Record<string, unknown>).status as string)
  ) {
    return NextResponse.json(
      {
        success: false,
        error: `status must be one of: ${[...VALID_STATUSES].join(", ")}`,
      },
      { status: 422 }
    )
  }

  const nextStatus = (body as { status: string }).status
  try {
    const db = getDb()
    const [updated] = await db
      .update(intakeSubmissions)
      .set({
        status: nextStatus,
      })
      .where(eq(intakeSubmissions.id, id))
      .returning({
        id: intakeSubmissions.id,
        status: intakeSubmissions.status,
      })

    if (!updated) {
      return NextResponse.json(
        { success: false, error: "Submission not found" },
        { status: 404 }
      )
    }

    return NextResponse.json({ success: true, data: updated })
  } catch (err) {
    console.error(`[PATCH /api/intake/${id}] Database error:`, err)
    return NextResponse.json(
      { success: false, error: "Failed to update status." },
      { status: 500 }
    )
  }
}
