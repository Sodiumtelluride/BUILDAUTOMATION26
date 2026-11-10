import Link from "next/link"
import { redirect } from "next/navigation"
import { auth } from "@/src/auth"
import { CARD, NoAccess, StatusPill } from "@/src/components/dashboard-panels"
import { listIntakes, REVIEW_ROLES } from "@/src/lib/intake-data"

// Intakes page: every project request submitted through the public intake form
export default async function IntakesPage() {
  const session = await auth()
  if (!session?.user) redirect("/login")
  if (!REVIEW_ROLES.includes(session.user.role)) return <NoAccess message="Only admins and reviewers can view intake forms." />

  const intakes = await listIntakes()

  return (
    <main className="space-y-6 p-6 md:p-10">
      <div>
        <h1 className="text-lg font-semibold">Intakes</h1>
        <p className="mt-1 text-sm text-zinc-400">Project requests from the intake form · {intakes.length} total</p>
      </div>

      {intakes.length === 0 ? (
        <div className={CARD}>
          <p className="text-sm text-zinc-500">No intake forms yet. Submissions from the /intake page show up here.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-white/10 bg-white/[0.02]">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-white/10 text-xs text-zinc-500">
              <tr>
                <th className="px-5 py-3 font-medium">Organization</th>
                <th className="px-5 py-3 font-medium">Contact</th>
                <th className="px-5 py-3 font-medium">Reference</th>
                <th className="px-5 py-3 font-medium">Submitted</th>
                <th className="px-5 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {intakes.map((intake) => (
                <tr key={intake.id} className="transition-colors hover:bg-white/[0.03]">
                  <td className="px-5 py-3">
                    <Link href={`/intakes/${intake.id}`} className="font-medium text-zinc-100 hover:underline">
                      {intake.organization ?? intake.projectName ?? "Untitled"}
                    </Link>
                  </td>
                  <td className="px-5 py-3">
                    <p className="text-zinc-300">{intake.clientName ?? "—"}</p>
                    <p className="text-xs text-zinc-500">{intake.clientEmail}</p>
                  </td>
                  <td className="px-5 py-3 font-mono text-xs text-zinc-400">{intake.referenceNo}</td>
                  <td className="whitespace-nowrap px-5 py-3 text-zinc-400">
                    {intake.createdAt?.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) ?? "—"}
                  </td>
                  <td className="px-5 py-3">{intake.status && <StatusPill status={intake.status} />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  )
}
