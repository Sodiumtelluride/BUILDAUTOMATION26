import { pgTable, text, timestamp, uuid, boolean } from "drizzle-orm/pg-core"

export const intakeSubmissions = pgTable("intake_submissions", {
  id: uuid("id").defaultRandom().primaryKey(),
  referenceNo: text("reference_no").notNull(),
  projectName: text("project_name"),
  clientName: text("client_name"),
  clientEmail: text("client_email"),
  budget: text("budget"),
  features: text("features"),
  teamSize: text("team_size"),
  startDate: text("start_date"),
  notes: text("notes"),
  status: text("status"),
  emailSent: boolean("email_sent"),
  // Local demo build (agent/pipeline/run.py), kept apart from the intake's review status.
  // demoStatus: null (never built) | "running" | "succeeded" | "failed"
  demoUrl: text("demo_url"),
  demoStatus: text("demo_status"),
  demoError: text("demo_error"),
  demoStartedAt: timestamp("demo_started_at", { withTimezone: true }),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
})
