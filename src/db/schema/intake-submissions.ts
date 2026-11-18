import { pgTable, text, timestamp, uuid, boolean, index } from "drizzle-orm/pg-core"

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
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
}, (t) => [
  // The public status page looks submissions up by reference number on every poll.
  index("intake_submissions_reference_no_idx").on(t.referenceNo),
])
