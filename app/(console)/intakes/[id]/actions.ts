"use server"

import { revalidatePath } from "next/cache"
import { auth } from "@/src/auth"
import { startDemoBuild } from "@/src/lib/demo-site"
import { REVIEW_ROLES, UUID_RE } from "@/src/lib/intake-data"

// "Generate demo site" on an intake: starts the local agent run. The page shows progress from the row.
export async function generateDemoSite(submissionId: string) {
  const session = await auth()
  if (!session?.user || !REVIEW_ROLES.includes(session.user.role)) throw new Error("Reviewer access required")
  if (!UUID_RE.test(submissionId)) throw new Error("Invalid submission ID")
  await startDemoBuild(submissionId) // "busy" (already running) needs no message: the page shows the running build
  revalidatePath(`/intakes/${submissionId}`)
}
