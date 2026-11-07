import { desc } from "drizzle-orm"
import { redirect } from "next/navigation"
import { auth } from "@/src/auth"
import { db } from "@/src/db"
import { projectMetrics } from "@/src/db/schema/project-metrics"
import { CARD, StatusPill } from "@/src/components/dashboard-panels"
import { STAGE_NAMES } from "@/src/lib/dashboard-data"

const CLUB_ROLES = ["admin", "reviewer", "member"]

// Projects page (App Factory): one card per project with its stage, progress, and AI usage
export default async function FactoryPage() {
  const session = await auth()
  if (!session?.user || !CLUB_ROLES.includes(session.user.role)) redirect("/login")

  const projects = await db.select().from(projectMetrics).orderBy(desc(projectMetrics.updatedAt))

  return (
    <main className="space-y-6 p-6 md:p-10">
      <div>
        <h1 className="text-lg font-semibold">Projects</h1>
        <p className="mt-1 text-sm text-zinc-400">App Factory · every nonprofit site the agents are building</p>
      </div>

      {projects.length === 0 ? (
        <div className={CARD}>
          <p className="text-sm text-zinc-500">No projects yet. They show up here once a nonprofit&apos;s intake starts the pipeline.</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {projects.map((p) => (
            <section key={p.jobId} className={CARD}>
              <div className="flex items-start justify-between gap-3">
                <h2 className="font-semibold">{p.orgName}</h2>
                {p.status && <StatusPill status={p.status} />}
              </div>
              <p className="mt-1 text-sm text-zinc-400">Stage: {p.currentStage ? STAGE_NAMES[p.currentStage] : "Not started"}</p>

              <div className="mt-4 h-1.5 rounded-full bg-white/5">
                <div className="h-1.5 rounded-full bg-[#3987e5]" style={{ width: `${p.percentDone}%` }} />
              </div>
              <p className="mt-1.5 text-xs text-zinc-500">{p.percentDone}% done</p>

              <dl className="mt-4 grid grid-cols-2 gap-y-1.5 text-sm">
                <dt className="text-zinc-500">Tokens</dt>
                <dd className="text-right tabular-nums">{p.totalTokens.toLocaleString()}</dd>
                <dt className="text-zinc-500">Cost</dt>
                <dd className="text-right tabular-nums">${Number(p.costUsd).toFixed(2)}</dd>
                <dt className="text-zinc-500">Agents used</dt>
                <dd className="text-right tabular-nums">{p.agentsUsed} / 7</dd>
                <dt className="text-zinc-500">Reruns</dt>
                <dd className="text-right tabular-nums">{p.rerunCount}</dd>
                <dt className="text-zinc-500">Max iterations</dt>
                <dd className="text-right tabular-nums">{p.maxIterationCount ?? "—"}</dd>
              </dl>
            </section>
          ))}
        </div>
      )}
    </main>
  )
}
