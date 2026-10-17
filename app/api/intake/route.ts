import { NextRequest, NextResponse } from "next/server"
import { and, eq } from "drizzle-orm"
import { getDb } from "@/src/db"
import { validateIntakeBody } from "@/src/lib/validation/intake"
import { organizations } from "@/src/db/schema/organizations"
import { intakeJobs } from "@/src/db/schema/intake-jobs"
import { intakeSubmissions } from "@/src/db/schema/intake-submissions"
import { assets } from "@/src/db/schema/assets"
import { IntakeRequestError, parseIntakeRequest } from "@/src/lib/intake/request"
import { rollbackIntakeUploads, uploadIntakeFiles, UploadStorageError, UploadValidationError, type UploadedIntakeFile } from "@/src/lib/intake/uploads"

export const runtime = "nodejs"

function generateReferenceNo() {
  const now = new Date()
  const y = now.getUTCFullYear()
  const m = String(now.getUTCMonth() + 1).padStart(2, "0")
  const d = String(now.getUTCDate()).padStart(2, "0")
  const suffix = crypto.randomUUID().replace(/-/g, "").slice(0, 6).toUpperCase()

  return `INT-${y}${m}${d}-${suffix}`
}

export async function POST(req: NextRequest) {
  let parsed: Awaited<ReturnType<typeof parseIntakeRequest>>
  try {
    parsed = await parseIntakeRequest(req)
  } catch (error) {
    return NextResponse.json(
      { success: false, error: error instanceof IntakeRequestError ? error.message : "Could not read the intake request." },
      { status: error instanceof IntakeRequestError ? error.status : 400 }
    )
  }

  const { data, errors, files } = validateIntakeBody(parsed.body, parsed.files)

  if (!data) {
    return NextResponse.json(
      { success: false, error: "Validation failed", details: errors },
      { status: 422 }
    )
  }

  let uploaded: UploadedIntakeFile[] = []
  try {
    const db = getDb()
    const jobId = crypto.randomUUID()
    uploaded = await uploadIntakeFiles(files, jobId)
    const result = await db.transaction(async (tx) => {
      const [existingOrganization] = await tx
        .select({
          id: organizations.id,
          name: organizations.name,
          contactEmail: organizations.contactEmail,
          contactName: organizations.contactName,
        })
        .from(organizations)
        .where(and(
          eq(organizations.contactEmail, data.clientEmail),
          eq(organizations.name, data.organizationName ?? data.clientName)
        ))
        .limit(1)

      const organization =
        existingOrganization ??
        (
          await tx
            .insert(organizations)
            .values({
              name: data.organizationName ?? data.clientName,
              contactEmail: data.clientEmail,
              contactName: data.clientName,
              mission: data.answers?.organizationDescription,
              status: "prospect",
            })
            .returning({
              id: organizations.id,
              name: organizations.name,
              contactEmail: organizations.contactEmail,
              contactName: organizations.contactName,
            })
        )[0]

      const referenceNo = generateReferenceNo()

      const [submission] = await tx
        .insert(intakeSubmissions)
        .values({
          referenceNo,
          projectName: data.projectName,
          clientName: data.clientName,
          clientEmail: data.clientEmail,
          budget: data.budget ?? null,
          features: data.features ?? null,
          teamSize: data.teamSize ?? null,
          startDate: data.startDate ?? null,
          notes: data.answers ? JSON.stringify({ version: 1, answers: data.answers, attachments: uploaded, organizationId: organization.id, jobId }) : data.notes ?? null,
          status: "pending",
          emailSent: false,
        })
        .returning({
          id: intakeSubmissions.id,
          referenceNo: intakeSubmissions.referenceNo,
          status: intakeSubmissions.status,
          createdAt: intakeSubmissions.createdAt,
        })

      const [job] = await tx
        .insert(intakeJobs)
        .values({
          id: jobId,
          orgId: organization.id,
          status: "queued",
          currentStage: "intake_received",
        })
        .returning({
          id: intakeJobs.id,
          status: intakeJobs.status,
          currentStage: intakeJobs.currentStage,
          createdAt: intakeJobs.createdAt,
        })

      if (uploaded.length) {
        await tx.insert(assets).values(uploaded.map((file) => ({
          jobId,
          fileName: file.originalName,
          fileType: file.contentType,
          fileUrl: `supabase://${file.bucket}/${file.path}`,
        })))
      }

      return {
        submission,
        job,
      }
    })

    return NextResponse.json(
      {
        success: true,
        data: result,
      },
      { status: 201 }
    )
  } catch (err) {
    if (uploaded.length) {
      try {
        await rollbackIntakeUploads(uploaded)
      } catch (cleanupError) {
        console.error("[POST /api/intake] Upload cleanup error:", cleanupError)
      }
    }
    if (err instanceof UploadValidationError) {
      return NextResponse.json(
        { success: false, error: "Validation failed", details: [{ field: err.field, message: err.message }] },
        { status: 422 }
      )
    }
    if (err instanceof UploadStorageError) {
      console.error("[POST /api/intake] Upload storage error:", err)
      return NextResponse.json(
        { success: false, error: "File uploads are temporarily unavailable. Please try again later." },
        { status: 503 }
      )
    }
    console.error("[POST /api/intake] Database error:", err)
    return NextResponse.json(
      { success: false, error: "Failed to create intake submission." },
      { status: 500 }
    )
  }
}
