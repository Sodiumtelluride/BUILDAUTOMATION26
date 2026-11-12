import { redirect } from "next/navigation"
import { auth } from "@/src/auth"
import AreaChart from "@/src/components/area-chart"
import { ActivityFeed, CARD, PipelineStrip, StatTile } from "@/src/components/dashboard-panels"
import { getPipeline, getRecentActivity, getStats, projectsPerDay } from "@/src/lib/dashboard-data"

const CLUB_ROLES = ["admin", "reviewer", "member"]
const TARGET_COST = 0.3 // PRD goal: about $0.30 of AI spend per project

// Admin console home: the page you land on after signing in (sidebar comes from ../layout.tsx)
export default async function DashboardPage() {
  const session = await auth()
  if (!session?.user || !CLUB_ROLES.includes(session.user.role)) redirect("/login")

  // all database reads at once, so the page loads faster
  const [stats, days, activity, pipeline] = await Promise.all([getStats(), projectsPerDay(), getRecentActivity(), getPipeline()])
  const startedThisWeek = days.reduce((sum, day) => sum + day.value, 0)

  return (
    <main className="space-y-6 p-6 md:p-10">
      <div>
        <h1 className="text-lg font-semibold">Overview</h1>
        <p className="mt-1 text-sm text-zinc-400">What the agents are doing and what needs you</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="In progress" value={String(stats.inProgress)} note={`${stats.queued} queued`} />
        <StatTile
          label="Awaiting review"
          value={String(stats.awaitingReview)}
          note={stats.awaitingReview > 0 ? "Waiting on a reviewer" : "All caught up"}
          status={stats.awaitingReview > 0 ? "warning" : undefined}
        />
        <StatTile
          label="Failed"
          value={String(stats.failed)}
          note={stats.failed > 0 ? "Needs a look" : "Nothing broken"}
          status={stats.failed > 0 ? "critical" : undefined}
        />
        <StatTile
          label="AI spend this month"
          value={`$${stats.spentThisMonth.toFixed(2)}`}
          note={
            stats.costPerProject > 0
              ? `$${stats.costPerProject.toFixed(2)} per project · target $${TARGET_COST.toFixed(2)}`
              : `Target $${TARGET_COST.toFixed(2)} per project`
          }
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <section className={`${CARD} lg:col-span-2`}>
          <h2 className="font-semibold">Projects started</h2>
          <p className="mt-1 text-sm text-zinc-400">Last 7 days · {startedThisWeek} total</p>
          <div className="mt-6">
            <AreaChart points={days} unit="Projects started" />
          </div>
        </section>
        <ActivityFeed events={activity} now={new Date()} />
      </div>

      <PipelineStrip stages={pipeline} />
    </main>
  )
}
