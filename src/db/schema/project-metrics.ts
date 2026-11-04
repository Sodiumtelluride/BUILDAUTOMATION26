import { sql } from 'drizzle-orm';
import { integer, numeric, pgView, text, timestamp, uuid } from 'drizzle-orm/pg-core';
import { intakeJobStatusEnum } from './intake-jobs';
import { pipelineStageEnum } from './job-stages';

// One row per intake job, for the App Factory dashboard cards.
// Only job_stages rows that have started count. Percent done counts completed stages
// up to the current one, so stages that will be redone after a revision don't count.
export const projectMetrics = pgView('project_metrics', {
  jobId: uuid('job_id').notNull(),
  orgId: uuid('org_id').notNull(),
  orgName: text('org_name').notNull(),
  status: intakeJobStatusEnum('status'),
  currentStage: pipelineStageEnum('current_stage'),
  stagesCompleted: integer('stages_completed').notNull(),
  percentDone: integer('percent_done').notNull(),
  agentsUsed: integer('agents_used').notNull(),
  rerunCount: integer('rerun_count').notNull(),
  maxIterationCount: integer('max_iteration_count'),
  inputTokens: integer('input_tokens').notNull(),
  outputTokens: integer('output_tokens').notNull(),
  totalTokens: integer('total_tokens').notNull(),
  costUsd: numeric('cost_usd').notNull(),
  createdAt: timestamp('created_at').notNull(),
  updatedAt: timestamp('updated_at').notNull(),
}).as(sql`
  WITH started AS (
    SELECT * FROM job_stages WHERE started_at IS NOT NULL
  ),
  latest AS (
    SELECT DISTINCT ON (job_id, stage) job_id, stage, status, attempt, iteration_count
    FROM started ORDER BY job_id, stage, attempt DESC
  ),
  cur AS (
    SELECT DISTINCT ON (job_id) job_id, stage
    FROM started ORDER BY job_id, started_at DESC, attempt DESC
  ),
  progress AS (
    SELECT l.job_id,
      count(*) FILTER (WHERE l.status = 'completed' AND l.stage <= c.stage)::int AS stages_completed,
      count(*)::int AS agents_used,
      sum(l.attempt - 1)::int AS rerun_count,
      max(l.iteration_count) AS max_iteration_count
    FROM latest l JOIN cur c USING (job_id)
    GROUP BY l.job_id
  ),
  costs AS (
    SELECT job_id,
      coalesce(sum(input_tokens), 0)::int AS input_tokens,
      coalesce(sum(output_tokens), 0)::int AS output_tokens,
      coalesce(sum(estimated_cost), 0) AS cost_usd
    FROM cost_logs GROUP BY job_id
  )
  SELECT
    j.id AS job_id,
    j.org_id,
    o.name AS org_name,
    j.status,
    c.stage AS current_stage,
    coalesce(p.stages_completed, 0) AS stages_completed,
    round(100.0 * coalesce(p.stages_completed, 0) / cardinality(enum_range(NULL::pipeline_stage)))::int AS percent_done,
    coalesce(p.agents_used, 0) AS agents_used,
    coalesce(p.rerun_count, 0) AS rerun_count,
    p.max_iteration_count,
    coalesce(k.input_tokens, 0) AS input_tokens,
    coalesce(k.output_tokens, 0) AS output_tokens,
    coalesce(k.input_tokens, 0) + coalesce(k.output_tokens, 0) AS total_tokens,
    coalesce(k.cost_usd, 0) AS cost_usd,
    j.created_at,
    j.updated_at
  FROM intake_jobs j
  JOIN organizations o ON o.id = j.org_id
  LEFT JOIN cur c ON c.job_id = j.id
  LEFT JOIN progress p ON p.job_id = j.id
  LEFT JOIN costs k ON k.job_id = j.id
`);
