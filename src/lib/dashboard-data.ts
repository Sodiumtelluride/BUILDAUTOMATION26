import { count, countDistinct, desc, eq, gte, inArray, notInArray, sql, sum } from "drizzle-orm"
import { getDb } from "@/src/db"
import { costLogs, deployments, intakeJobs, jobStages, organizations, pipelineStageEnum, reviewerActions, users } from "@/src/db/schema"
import { projectMetrics } from "@/src/db/schema/project-metrics"
import type { ChartPoint } from "@/src/components/area-chart"

// Short display names for the 7 agent stages
export const STAGE_NAMES: Record<(typeof pipelineStageEnum.enumValues)[number], string> = {
  INTAKE: "Intake",
  DESIGN: "Design",
  CODE_GENERATION: "Code",
  CONTENT: "Content",
  SEO: "SEO",
  APPROVAL_GATE: "Approval",
  DEPLOYMENT: "Deploy",
}

export type Activity = {
  kind: "nonprofit" | "finished" | "failed" | "approved" | "rejected" | "live"
  subject: string // shown in bold, e.g. "Design agent"
  action: string // the rest of the sentence, e.g. "finished for Food Bank"
  at: Date
}

/** The last 7 days (oldest first) with how many projects started on each day. */
export async function projectsPerDay(): Promise<ChartPoint[]> {
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  start.setDate(start.getDate() - 6)

  const jobs = await getDb().select({ createdAt: intakeJobs.createdAt }).from(intakeJobs).where(gte(intakeJobs.createdAt, start))

  return Array.from({ length: 7 }, (_, i) => {
    const day = new Date(start)
    day.setDate(start.getDate() + i)
    return {
      label: day.toLocaleDateString("en-US", { weekday: "short" }),
      title: day.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }),
      value: jobs.filter((job) => job.createdAt.toDateString() === day.toDateString()).length,
    }
  })
}

/** Numbers for the stat tiles: projects by status, plus AI spend this month. */
export async function getStats() {
  const monthStart = new Date()
  monthStart.setDate(1)
  monthStart.setHours(0, 0, 0, 0)

  const [byStatus, [spend]] = await Promise.all([
    getDb().select({ status: intakeJobs.status, jobs: count() }).from(intakeJobs).groupBy(intakeJobs.status),
    getDb()
      .select({ total: sum(costLogs.estimatedCost), projects: countDistinct(costLogs.jobId) })
      .from(costLogs)
      .where(gte(costLogs.createdAt, monthStart)),
  ])

  // how many projects have this status (0 if none)
  const jobsWith = (status: string) => byStatus.find((row) => row.status === status)?.jobs ?? 0
  const spent = Number(spend?.total ?? 0)

  return {
    inProgress: jobsWith("in_progress"),
    queued: jobsWith("queued"),
    awaitingReview: jobsWith("awaiting_review"),
    failed: jobsWith("failed"),
    spentThisMonth: spent,
    costPerProject: spend?.projects ? spent / spend.projects : 0,
  }
}

/** How many unfinished projects are at each agent stage right now, in pipeline order. */
export async function getPipeline() {
  const jobs = await getDb()
    .select({ stage: projectMetrics.currentStage })
    .from(projectMetrics)
    .where(notInArray(projectMetrics.status, ["deployed", "failed"]))

  return pipelineStageEnum.enumValues.map((stage) => ({
    stage: STAGE_NAMES[stage],
    projects: jobs.filter((job) => (job.stage ?? "INTAKE") === stage).length, // not started yet = still at Intake
  }))
}

/** The latest events across the app, newest first: nonprofits added, agents finishing or failing, reviews, and launches. */
export async function getRecentActivity(limit = 6): Promise<Activity[]> {
  const [orgs, stages, reviews, launches] = await Promise.all([
    getDb().select({ name: organizations.name, at: organizations.createdAt }).from(organizations).orderBy(desc(organizations.createdAt)).limit(limit),
    getDb()
      .select({
        org: organizations.name,
        stage: jobStages.stage,
        status: jobStages.status,
        attempt: jobStages.attempt,
        completedAt: jobStages.completedAt,
        startedAt: jobStages.startedAt,
      })
      .from(jobStages)
      .innerJoin(intakeJobs, eq(jobStages.jobId, intakeJobs.id))
      .innerJoin(organizations, eq(intakeJobs.orgId, organizations.id))
      .where(inArray(jobStages.status, ["completed", "failed"]))
      .orderBy(desc(sql`coalesce(${jobStages.completedAt}, ${jobStages.startedAt})`))
      .limit(limit),
    getDb()
      .select({ name: users.name, email: users.email, org: organizations.name, action: reviewerActions.action, at: reviewerActions.createdAt })
      .from(reviewerActions)
      .innerJoin(users, eq(reviewerActions.reviewerId, users.id))
      .innerJoin(intakeJobs, eq(reviewerActions.jobId, intakeJobs.id))
      .innerJoin(organizations, eq(intakeJobs.orgId, organizations.id))
      .orderBy(desc(reviewerActions.createdAt))
      .limit(limit),
    getDb()
      .select({ org: organizations.name, at: deployments.deployedAt })
      .from(deployments)
      .innerJoin(intakeJobs, eq(deployments.jobId, intakeJobs.id))
      .innerJoin(organizations, eq(intakeJobs.orgId, organizations.id))
      .orderBy(desc(deployments.deployedAt))
      .limit(limit),
  ])

  // Turn each kind of row into a sentence; some times can be missing, so they're filtered out below
  const events: (Omit<Activity, "at"> & { at: Date | null })[] = [
    ...orgs.map((o) => ({ kind: "nonprofit" as const, subject: o.name, action: "was added as a new nonprofit", at: o.at })),
    ...stages.map((s) => {
      const failed = s.status === "failed"
      return {
        kind: failed ? ("failed" as const) : ("finished" as const),
        subject: `${STAGE_NAMES[s.stage]} agent`,
        action: `${failed ? "failed" : "finished"} for ${s.org}${s.attempt > 1 ? ` (attempt ${s.attempt})` : ""}`,
        at: s.completedAt ?? s.startedAt,
      }
    }),
    ...reviews.map((r) => ({
      kind: r.action === "approved" ? ("approved" as const) : ("rejected" as const),
      subject: r.name ?? r.email,
      action: `${r.action === "approved" ? "approved" : "sent back"} the ${r.org} site`,
      at: r.at,
    })),
    ...launches.map((l) => ({ kind: "live" as const, subject: l.org, action: "site is live", at: l.at })),
  ]

  return events
    .filter((e): e is Activity => e.at !== null)
    .sort((a, b) => b.at.getTime() - a.at.getTime())
    .slice(0, limit)
}
