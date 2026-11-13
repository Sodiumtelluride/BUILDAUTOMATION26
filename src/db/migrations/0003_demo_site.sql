ALTER TABLE "intake_submissions" ADD COLUMN "demo_url" text;--> statement-breakpoint
ALTER TABLE "intake_submissions" ADD COLUMN "demo_status" text;--> statement-breakpoint
ALTER TABLE "intake_submissions" ADD COLUMN "demo_error" text;--> statement-breakpoint
ALTER TABLE "intake_submissions" ADD COLUMN "demo_started_at" timestamp with time zone;