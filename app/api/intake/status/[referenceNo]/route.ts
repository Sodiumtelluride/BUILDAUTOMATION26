import { NextRequest, NextResponse } from "next/server"
import { eq } from "drizzle-orm"
import { getDb } from "@/src/db"
import { intakeSubmissions } from "@/src/db/schema/intake-submissions"
import { intakeJobs } from "@/src/db/schema/intake-jobs"
import { jobStages } from "@/src/db/schema/job-stages"
import { deployments } from "@/src/db/schema/deployments"
import { REFERENCE_NO_RE, normalizeReferenceNo, submissionLinks, toPublicJobStatus } from "@/src/lib/intake/job-status"

export const runtime = "nodejs"

// Public on purpose: the submitter has no account. The reference number is the
// only key, so this returns nothing personal — no names, emails, internal error
// messages, or the unreviewed preview URL. See src/lib/intake/job-status.ts.

const NO_STORE = { "Cache-Control": "no-store" }

interface RouteContext {
  params: Promise<{ referenceNo: string }>
}

function notFound() {
  return NextResponse.json({ success: false, error: "We couldn't find a project with that reference number." }, { status: 404, headers: NO_STORE })
}

export async function GET(_req: NextRequest, ctx: RouteContext) {
  const { referenceNo: raw } = await ctx.params
  const referenceNo = normalizeReferenceNo(raw)

  if (!REFERENCE_NO_RE.test(referenceNo)) {
    return NextResponse.json({ success: false, error: "That doesn't look like a BUILD reference number." }, { status: 400, headers: NO_STORE })
  }

  try {
    const db = getDb()
    const [submission] = await db
      .select({ notes: intakeSubmissions.notes })
      .from(intakeSubmissions)
      .where(eq(intakeSubmissions.referenceNo, referenceNo))
      .limit(1)
    if (!submission) return notFound()

    // Older (legacy JSON) submissions were never linked to a pipeline job.
    const links = submissionLinks(submission.notes)
    if (!links) return notFound()

    // Independent lookups: run them together to keep each poll quick.
    const [[job], stages] = await Promise.all([
      db
        .select({
          status: intakeJobs.status,
          currentStage: intakeJobs.currentStage,
          liveUrl: intakeJobs.liveUrl,
          updatedAt: intakeJobs.updatedAt,
        })
        .from(intakeJobs)
        .where(eq(intakeJobs.id, links.jobId))
        .limit(1),
      db
        .select({ stage: jobStages.stage, status: jobStages.status, attempt: jobStages.attempt })
        .from(jobStages)
        .where(eq(jobStages.jobId, links.jobId)),
    ])
    if (!job) return notFound()

    let liveUrl = job.liveUrl
    if (job.status === "deployed" && !liveUrl) {
      const [deployment] = await db
        .select({ liveUrl: deployments.liveUrl })
        .from(deployments)
        .where(eq(deployments.jobId, links.jobId))
        .limit(1)
      liveUrl = deployment?.liveUrl ?? null
    }

    return NextResponse.json(
      { success: true, data: toPublicJobStatus(referenceNo, { ...job, liveUrl }, stages) },
      { headers: NO_STORE }
    )
  } catch (err) {
    console.error(`[GET /api/intake/status/${referenceNo}] Database error:`, err)
    return NextResponse.json({ success: false, error: "Status is temporarily unavailable." }, { status: 503, headers: NO_STORE })
  }
}
