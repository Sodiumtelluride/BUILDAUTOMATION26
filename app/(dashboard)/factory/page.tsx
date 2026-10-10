import { redirect } from "next/navigation"
import { auth } from "@/src/auth"
import { db } from "@/src/db"
import { projectMetrics } from "@/src/db/schema/project-metrics"

const CLUB_ROLES = ["admin", "reviewer", "member"]

export default async function FactoryPage() {
  const session = await auth()
  if (!session?.user || !CLUB_ROLES.includes(session.user.role)) redirect("/login")

  const projects = await db.select().from(projectMetrics)

  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-10">
      <h1 className="mb-6 text-2xl font-semibold">App Factory</h1>
      {projects.length === 0 && <p className="text-zinc-500">No projects yet.</p>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {projects.map((p) => (
          <div key={p.jobId} className="rounded-lg border p-4">
            <div className="flex items-baseline justify-between">
              <h2 className="font-medium">{p.orgName}</h2>
              <span className="text-xs text-zinc-500">{p.status}</span>
            </div>
            <p className="mt-1 text-sm text-zinc-600">Stage: {p.currentStage ?? "Not started"}</p>
            <div className="mt-3 h-2 rounded bg-zinc-200">
              <div className="h-2 rounded bg-black" style={{ width: `${p.percentDone}%` }} />
            </div>
            <p className="mt-1 text-xs text-zinc-500">{p.percentDone}% done</p>
            <dl className="mt-3 grid grid-cols-2 gap-1 text-sm">
              <dt className="text-zinc-500">Tokens</dt>
              <dd>{p.totalTokens.toLocaleString()}</dd>
              <dt className="text-zinc-500">Cost</dt>
              <dd>${Number(p.costUsd).toFixed(2)}</dd>
              <dt className="text-zinc-500">Agents used</dt>
              <dd>{p.agentsUsed} / 7</dd>
              <dt className="text-zinc-500">Reruns</dt>
              <dd>{p.rerunCount}</dd>
              <dt className="text-zinc-500">Max iterations</dt>
              <dd>{p.maxIterationCount ?? "—"}</dd>
            </dl>
          </div>
        ))}
      </div>
    </main>
  )
}
