import type { ReactNode } from "react"
import Icon from "@/src/components/icon"
import type { Activity } from "@/src/lib/dashboard-data"

// Shared look for every dashboard card
export const CARD = "rounded-2xl border border-white/10 bg-white/[0.02] p-5"

// Reserved status colors: only used when the color means good or bad
const STATUS = { good: "#0ca30c", warning: "#fab219", serious: "#ec835a", critical: "#d03b3b" }
const BLUE = "#3987e5"
const NEUTRAL = "#a1a1aa"

/** "Just now", "5 minutes ago", "3 hours ago", "2 days ago". */
function timeAgo(date: Date, now: Date) {
  const minutes = Math.floor((now.getTime() - date.getTime()) / 60_000)
  if (minutes < 1) return "Just now"
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`
  const days = Math.floor(hours / 24)
  return `${days} day${days === 1 ? "" : "s"} ago`
}

/**
 * One headline number, e.g. "Awaiting review: 3".
 * note: small line underneath. status: adds a colored dot when the note is a warning.
 */
export function StatTile({ label, value, note, status }: { label: string; value: string; note: string; status?: "warning" | "critical" }) {
  return (
    <div className={CARD}>
      <p className="text-sm text-zinc-400">{label}</p>
      <p className="mt-2 text-3xl font-semibold tracking-tight">{value}</p>
      <p className="mt-1 flex items-center gap-1.5 text-xs text-zinc-500">
        {status && <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: STATUS[status] }} />}
        {note}
      </p>
    </div>
  )
}

// Label and dot color for each project status (status colors only where they mean good or bad)
const PROJECT_STATUS: Record<string, { label: string; color: string }> = {
  queued: { label: "Queued", color: NEUTRAL },
  in_progress: { label: "In progress", color: BLUE },
  awaiting_review: { label: "Awaiting review", color: STATUS.warning },
  approved: { label: "Approved", color: STATUS.good },
  deployed: { label: "Live", color: STATUS.good },
  failed: { label: "Failed", color: STATUS.critical },
}

/** Small rounded label showing a project's status, e.g. "● Awaiting review". */
export function StatusPill({ status }: { status: string }) {
  const { label, color } = PROJECT_STATUS[status] ?? { label: status, color: NEUTRAL }
  return (
    <span className="flex shrink-0 items-center gap-1.5 rounded-full border border-white/10 px-2 py-0.5 text-xs text-zinc-300">
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  )
}

// Icon and color for each kind of event
const EVENT_STYLE: Record<Activity["kind"], { color: string; icon: ReactNode }> = {
  nonprofit: {
    color: BLUE,
    icon: (
      <>
        <path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z" />
        <path d="M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2" />
        <path d="M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2" />
        <path d="M10 6h4" />
        <path d="M10 10h4" />
        <path d="M10 14h4" />
        <path d="M10 18h4" />
      </>
    ),
  },
  finished: { color: NEUTRAL, icon: <path d="M20 6 9 17l-5-5" /> },
  failed: {
    color: STATUS.critical,
    icon: (
      <>
        <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" />
        <path d="M12 9v4" />
        <path d="M12 17h.01" />
      </>
    ),
  },
  approved: {
    color: STATUS.good,
    icon: (
      <>
        <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <polyline points="16 11 18 13 22 9" />
      </>
    ),
  },
  rejected: {
    color: STATUS.serious,
    icon: (
      <>
        <path d="M18 6 6 18" />
        <path d="m6 6 12 12" />
      </>
    ),
  },
  live: {
    color: STATUS.good,
    icon: (
      <>
        <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z" />
        <path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z" />
        <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0" />
        <path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5" />
      </>
    ),
  },
}

/** List of the latest events, newest first, each with an icon and how long ago it happened. */
export function ActivityFeed({ events, now }: { events: Activity[]; now: Date }) {
  return (
    <section className={CARD}>
      <h2 className="font-semibold">Recent activity</h2>
      {events.length === 0 ? (
        <p className="mt-4 text-sm text-zinc-500">No activity yet. Events show up here as nonprofits are added and agents run.</p>
      ) : (
        <ul className="mt-2 divide-y divide-white/5">
          {events.map((event, i) => {
            const { color, icon } = EVENT_STYLE[event.kind]
            return (
              <li key={i} className="flex gap-3 py-3">
                <span
                  className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
                  style={{ backgroundColor: `${color}26`, color }}
                >
                  <Icon>{icon}</Icon>
                </span>
                <div className="min-w-0">
                  <p className="text-sm text-zinc-300">
                    <span className="font-semibold text-zinc-100">{event.subject}</span> {event.action}
                  </p>
                  <p className="mt-0.5 text-xs text-zinc-500">{timeAgo(event.at, now)}</p>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

/** The 7 agent stages in order, with how many projects are at each one right now. */
export function PipelineStrip({ stages }: { stages: { stage: string; projects: number }[] }) {
  const total = stages.reduce((sum, s) => sum + s.projects, 0)

  return (
    <section className={CARD}>
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="font-semibold">Pipeline</h2>
        <p className="text-xs text-zinc-500">
          {total === 0 ? "No projects in progress" : `${total} project${total === 1 ? "" : "s"} in progress`}
        </p>
      </div>
      <ol className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
        {stages.map((s, i) => {
          const busy = s.projects > 0
          return (
            <li
              key={s.stage}
              className="rounded-xl border px-3 py-3"
              style={busy ? { borderColor: `${BLUE}66`, backgroundColor: `${BLUE}1a` } : { borderColor: "rgba(255,255,255,0.05)" }}
            >
              <p className="text-[11px] text-zinc-500">
                {i + 1}. {s.stage}
              </p>
              <p className={`mt-1 text-2xl font-semibold ${busy ? "text-zinc-100" : "text-zinc-600"}`}>{s.projects}</p>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
