import Link from "next/link"
import { notFound, redirect } from "next/navigation"
import { auth } from "@/src/auth"
import { CARD, NoAccess, StatusPill } from "@/src/components/dashboard-panels"
import { answerGroups, getIntake, REVIEW_ROLES } from "@/src/lib/intake-data"

/** A titled card of label/value rows; empty answers show as "—". */
function AnswerCard({ title, rows }: { title: string; rows: [string, string | null | undefined][] }) {
  return (
    <section className={CARD}>
      <h2 className="font-semibold">{title}</h2>
      <dl className="mt-4 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-[160px_1fr]">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-zinc-500">{label}</dt>
            <dd className="whitespace-pre-wrap break-words text-zinc-200">{value || "—"}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

// One intake form: every answer grouped by form section, the attached files, and the raw saved JSON
export default async function IntakeDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const session = await auth()
  if (!session?.user) redirect("/login")
  if (!REVIEW_ROLES.includes(session.user.role)) return <NoAccess message="Only admins and reviewers can view intake forms." />

  const { id } = await params
  const intake = await getIntake(id)
  if (!intake) notFound()

  const answers = intake.details?.answers
  const attachments = intake.details?.attachments ?? []

  return (
    <main className="space-y-6 p-6 md:p-10">
      <div>
        <Link href="/intakes" className="text-sm text-zinc-500 hover:text-zinc-300">
          ← All intakes
        </Link>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <h1 className="text-lg font-semibold">{answers?.organizationName ?? intake.projectName ?? "Untitled intake"}</h1>
          {intake.status && <StatusPill status={intake.status} />}
        </div>
        <p className="mt-1 text-sm text-zinc-400">
          <span className="font-mono">{intake.referenceNo}</span>
          {intake.createdAt && ` · Submitted ${intake.createdAt.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}`}
        </p>
      </div>

      {answers ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {answerGroups(answers).map((group) => (
            <AnswerCard key={group.title} title={group.title} rows={group.rows} />
          ))}
        </div>
      ) : (
        // older submissions saved only these basic fields
        <AnswerCard
          title="Submission"
          rows={[
            ["Project", intake.projectName],
            ["Contact", intake.clientName],
            ["Email", intake.clientEmail],
            ["Budget", intake.budget],
            ["Features", intake.features],
            ["Team size", intake.teamSize],
            ["Start date", intake.startDate],
            ["Notes", intake.notes],
          ]}
        />
      )}

      {attachments.length > 0 && (
        <section className={CARD}>
          <h2 className="font-semibold">Attachments</h2>
          <ul className="mt-3 divide-y divide-white/5 text-sm">
            {attachments.map((file) => (
              <li key={file.path} className="flex items-center justify-between gap-4 py-2">
                <span className="truncate text-zinc-200">{file.originalName}</span>
                <span className="shrink-0 text-xs text-zinc-500">
                  {file.category} · {Math.max(1, Math.round(file.size / 1024))} KB
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-zinc-500">Files are stored privately in Supabase; downloading them from here isn&apos;t built yet.</p>
        </section>
      )}

      {intake.details && (
        <details className={CARD}>
          <summary className="cursor-pointer text-sm font-semibold">Raw JSON</summary>
          <pre className="mt-4 overflow-x-auto rounded-lg bg-black/40 p-4 text-xs text-zinc-300">
            {JSON.stringify(intake.details, null, 2)}
          </pre>
        </details>
      )}
    </main>
  )
}
