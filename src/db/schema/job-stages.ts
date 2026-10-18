import { integer, pgEnum, pgTable, text, timestamp, unique, uuid } from 'drizzle-orm/pg-core';
import { intakeJobs } from './intake-jobs';

// Matches agent/pipeline/state.py StageEnum, in pipeline order (project_metrics relies on this order).
export const pipelineStageEnum = pgEnum('pipeline_stage', [
  'INTAKE',
  'DESIGN',
  'CODE_GENERATION',
  'CONTENT',
  'SEO',
  'APPROVAL_GATE',
  'DEPLOYMENT',
]);

export const jobStageStatusEnum = pgEnum('job_stage_status', [
  'pending',
  'running',
  'completed',
  'failed',
]);

export const jobStages = pgTable(
  'job_stages',
  {
    id: uuid('id').defaultRandom().primaryKey(),
    jobId: uuid('job_id').references(() => intakeJobs.id).notNull(),
    stage: pipelineStageEnum('stage').notNull(),
    status: jobStageStatusEnum('status'),
    attempt: integer('attempt').notNull().default(1),
    iterationCount: integer('iteration_count'),
    startedAt: timestamp('started_at'),
    completedAt: timestamp('completed_at'),
    errorMessage: text('error_message'),
  },
  (t) => [unique().on(t.jobId, t.stage, t.attempt)],
);
