import { spawn } from "node:child_process"
import { closeSync, mkdirSync, openSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import path from "node:path"
import { and, eq, isNull, ne, or } from "drizzle-orm"
import { getDb } from "@/src/db"
import { intakeSubmissions } from "@/src/db/schema/intake-submissions"
import { parseIntakeNotes } from "@/src/lib/intake-data"

/**
 * Local demo builds: the "Generate demo site" button runs agent/pipeline/run.py on this machine.
 *
 * Only works where the console and the agent share a laptop, so it is off unless DEMO_SITES_DIR is set.
 * Each intake gets DEMO_SITES_DIR/<submission id>/ holding intake.json, run.log, run.pid and, when the
 * run ends, result.json. Nothing waits on the process: the next page load reads result.json and
 * finishes the row (settleDemo), so a restarted dev server never leaves a row stuck at "running".
 */

/** A run younger than this is never declared dead: its files may not exist yet. */
export const START_GRACE_MS = 60_000

export type DemoFields = {
  demoStatus: string | null
  demoUrl: string | null
  demoError: string | null
  demoStartedAt: Date | null
}

type RunResult = { status?: unknown; url?: unknown; error?: unknown; finished_at?: unknown }

export function demoSitesDir(): string | null {
  return process.env.DEMO_SITES_DIR || null
}

function jobDir(root: string, submissionId: string) {
  return path.join(root, submissionId)
}

/**
 * What a "running" row should become, or null while it is still running.
 * A result.json that finished before this run started belongs to an earlier run and is ignored.
 */
export function settlement(
  startedAt: Date | null,
  result: RunResult | null,
  processAlive: boolean,
  now: Date,
): Pick<DemoFields, "demoStatus" | "demoUrl" | "demoError"> | null {
  const finishedAt = typeof result?.finished_at === "string" ? new Date(result.finished_at) : null
  if (result && finishedAt && (!startedAt || finishedAt >= startedAt)) {
    if (result.status === "succeeded" && typeof result.url === "string") {
      return { demoStatus: "succeeded", demoUrl: result.url, demoError: null }
    }
    return { demoStatus: "failed", demoUrl: null, demoError: typeof result.error === "string" ? result.error : "The build failed." }
  }
  if (startedAt && now.getTime() - startedAt.getTime() < START_GRACE_MS) return null
  if (processAlive) return null
  return { demoStatus: "failed", demoUrl: null, demoError: "The build process stopped without writing a result. See run.log in the job folder." }
}

function readResult(dir: string): RunResult | null {
  try {
    return JSON.parse(readFileSync(path.join(dir, "result.json"), "utf8"))
  } catch {
    return null
  }
}

function runIsAlive(dir: string): boolean {
  let pid: number
  try {
    pid = Number.parseInt(readFileSync(path.join(dir, "run.pid"), "utf8"), 10)
  } catch {
    return false
  }
  if (!Number.isInteger(pid) || pid <= 0) return false
  try {
    process.kill(pid, 0) // signal 0: existence check only
    return true
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "EPERM"
  }
}

/** If the row's build is "running", finish it from result.json or a dead process. Returns the row as it now stands. */
export async function settleDemo<T extends DemoFields & { id: string }>(row: T): Promise<T> {
  const root = demoSitesDir()
  if (row.demoStatus !== "running" || !root) return row
  const dir = jobDir(root, row.id)
  const next = settlement(row.demoStartedAt, readResult(dir), runIsAlive(dir), new Date())
  if (!next) return row
  const startedMatches = row.demoStartedAt ? eq(intakeSubmissions.demoStartedAt, row.demoStartedAt) : isNull(intakeSubmissions.demoStartedAt)
  await getDb()
    .update(intakeSubmissions)
    .set(next)
    // only the run this row was read with; a newer click has its own start time
    .where(and(eq(intakeSubmissions.id, row.id), eq(intakeSubmissions.demoStatus, "running"), startedMatches))
  return { ...row, ...next }
}

/** Only what the agent needs (including the model key for AGENT_PROVIDER=anthropic): never the console's DATABASE_URL, AUTH_SECRET or Supabase keys. */
function agentEnv(): NodeJS.ProcessEnv {
  const keep = /^(PATH|HOME|OLLAMA_\w+|AGENT_\w+|BUILD_TEMPLATE_SOURCE|ANTHROPIC_API_KEY)$/
  // cast: Next types NODE_ENV as always present, and the agent must not inherit it either
  return Object.fromEntries(Object.entries(process.env).filter(([key]) => keep.test(key))) as NodeJS.ProcessEnv
}

export type StartOutcome = "started" | "busy" | "unavailable" | "failed"

/**
 * Claim the row (refused while a build is already running) and start the agent fully detached:
 * stdin from intake.json, output to run.log, its own process group, no pipes back to this server.
 */
export async function startDemoBuild(submissionId: string): Promise<StartOutcome> {
  const root = demoSitesDir()
  if (!root) return "unavailable"
  const db = getDb()
  const startedAt = new Date()
  const [claimed] = await db
    .update(intakeSubmissions)
    .set({ demoStatus: "running", demoUrl: null, demoError: null, demoStartedAt: startedAt })
    .where(and(
      eq(intakeSubmissions.id, submissionId),
      or(isNull(intakeSubmissions.demoStatus), ne(intakeSubmissions.demoStatus, "running")),
    ))
    .returning({ notes: intakeSubmissions.notes })
  if (!claimed) return "busy"

  const fail = async (demoError: string): Promise<StartOutcome> => {
    await db.update(intakeSubmissions).set({ demoStatus: "failed", demoError }).where(eq(intakeSubmissions.id, submissionId))
    return "failed"
  }
  if (!claimed.notes || !parseIntakeNotes(claimed.notes)) return fail("This intake has no saved form answers to build from.")

  // turbopackIgnore: this is a directory to run Python in, not files to bundle (tracing it trips on venv symlinks)
  const agentDir = path.join(/* turbopackIgnore: true */ process.cwd(), "agent")
  const python = process.env.AGENT_PYTHON || path.join(agentDir, ".venv", "bin", "python")
  const dir = jobDir(root, submissionId)
  let pid: number | undefined
  try {
    mkdirSync(dir, { recursive: true })
    rmSync(path.join(dir, "result.json"), { force: true })
    writeFileSync(path.join(dir, "intake.json"), claimed.notes)
    const input = openSync(path.join(dir, "intake.json"), "r")
    const log = openSync(path.join(dir, "run.log"), "w")
    try {
      const child = spawn(/* turbopackIgnore: true */ python, ["-m", "pipeline.run", "--job-dir", dir], {
        cwd: agentDir,
        env: agentEnv(),
        detached: true,
        stdio: [input, log, log],
      })
      child.on("error", () => {}) // a missing interpreter is reported below through the absent pid
      pid = child.pid
      child.unref()
    } finally {
      closeSync(input)
      closeSync(log)
    }
    if (pid) writeFileSync(path.join(dir, "run.pid"), `${pid}\n`)
  } catch (error) {
    return fail(`Could not start the build: ${error instanceof Error ? error.message : String(error)}`)
  }
  if (!pid) return fail(`Could not start ${python}. Set AGENT_PYTHON or create agent/.venv.`)
  return "started"
}
