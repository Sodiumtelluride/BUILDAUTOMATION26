// Turns internal pipeline rows into the small, public status object the
// nonprofit sees on /intake/status/[referenceNo]. Nothing here touches the
// database, so it can be tested on its own.
//
// What the submitter is allowed to see (Intake PRD §2.1, §6):
//   - progress through the automated stages
//   - that BUILD is reviewing the draft (never the unreviewed preview URL)
//   - the live URL, only after the site is deployed

export const REFERENCE_NO_RE = /^INT-\d{8}-[A-F0-9]{6}$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// DESIGN_SELECTION is the submitter's own step (not a pipeline stage): the
// pipeline builds design options, waits for their pick, then writes content.
export const PIPELINE_STEPS = [
  { key: "INTAKE", label: "Reading your answers" },
  { key: "DESIGN", label: "Planning your design" },
  { key: "CODE_GENERATION", label: "Building your design options" },
  { key: "DESIGN_SELECTION", label: "Choosing your design" },
  { key: "CONTENT", label: "Writing your content" },
  { key: "SEO", label: "Preparing for search engines" },
  { key: "APPROVAL_GATE", label: "BUILD team review" },
  { key: "DEPLOYMENT", label: "Publishing your site" },
] as const;

export type StepKey = (typeof PIPELINE_STEPS)[number]["key"];
export type StepState = "pending" | "active" | "done" | "failed";
// choosing_design: the submitter must pick one of the generated designs (see design-options.ts).
export type PublicPhase = "queued" | "generating" | "choosing_design" | "in_review" | "publishing" | "live" | "failed";

export interface PublicJobStatus {
  referenceNo: string;
  phase: PublicPhase;
  steps: { key: StepKey; label: string; state: StepState }[];
  liveUrl: string | null;
  updatedAt: string;
}

export interface JobRow {
  status: string | null;
  currentStage: string | null;
  liveUrl: string | null;
  updatedAt: Date | string;
}

export interface StageRow {
  stage: string;
  status: string | null;
  attempt: number;
}

const REVIEW_INDEX = PIPELINE_STEPS.findIndex((s) => s.key === "APPROVAL_GATE");
export const SELECTION_INDEX = PIPELINE_STEPS.findIndex((s) => s.key === "DESIGN_SELECTION");
const DEPLOY_INDEX = PIPELINE_STEPS.findIndex((s) => s.key === "DEPLOYMENT");

/** Decodes and normalizes a reference number from a URL. Never throws. */
export function normalizeReferenceNo(raw: string): string {
  let value = raw;
  try { value = decodeURIComponent(raw); } catch { /* malformed %-escape: leave as-is, it won't match */ }
  return value.trim().toUpperCase();
}

/** Reads the jobId the intake API writes into intake_submissions.notes. */
export function submissionLinks(notes: string | null): { organizationId: string; jobId: string } | null {
  if (!notes) return null;
  try {
    const value: unknown = JSON.parse(notes);
    if (!value || typeof value !== "object" || !("version" in value) || value.version !== 1 ||
      !("organizationId" in value) || typeof value.organizationId !== "string" || !UUID_RE.test(value.organizationId) ||
      !("jobId" in value) || typeof value.jobId !== "string" || !UUID_RE.test(value.jobId)) return null;
    return { organizationId: value.organizationId, jobId: value.jobId };
  } catch {
    return null;
  }
}

/** Only http(s) URLs are ever rendered as a link (blocks javascript: and friends). */
export function safeSiteUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch {
    return null;
  }
}

function stepIndex(stage: string | null | undefined): number {
  if (!stage) return -1;
  const normalized = stage.toUpperCase();
  return PIPELINE_STEPS.findIndex((s) => s.key === normalized);
}

function phaseFor(status: string | null, liveUrl: string | null): PublicPhase {
  switch (status) {
    case "in_progress": return "generating";
    // Proposed, not yet in the intake_job_status enum: designs are built and
    // the pipeline is waiting for the submitter's choice.
    case "awaiting_selection": return "choosing_design";
    case "awaiting_review": return "in_review";
    case "approved": return "publishing";
    // A deployed job without a usable URL is still "publishing" to the submitter.
    case "deployed": return liveUrl ? "live" : "publishing";
    case "failed": return "failed";
    default: return "queued";
  }
}

export function toPublicJobStatus(referenceNo: string, job: JobRow, stageRows: StageRow[] = []): PublicJobStatus {
  const liveUrl = safeSiteUrl(job.liveUrl);
  const phase = phaseFor(job.status, liveUrl);

  // Latest attempt per stage wins (a retried stage can be failed then completed).
  const latest = new Map<string, StageRow>();
  for (const row of stageRows) {
    const prev = latest.get(row.stage);
    if (!prev || row.attempt > prev.attempt) latest.set(row.stage, row);
  }

  // Where is the pipeline? Prefer stage rows, fall back to job.currentStage.
  let activeIndex = -1;
  let failedIndex = -1;
  PIPELINE_STEPS.forEach((step, i) => {
    const row = latest.get(step.key);
    if (row?.status === "running") activeIndex = Math.max(activeIndex, i);
    if (row?.status === "failed") failedIndex = Math.max(failedIndex, i);
  });
  if (activeIndex < 0) activeIndex = stepIndex(job.currentStage);

  // The job status is the source of truth for the coarse position.
  if (phase === "queued") activeIndex = -1;
  if (phase === "generating") activeIndex = Math.min(Math.max(activeIndex, 0), REVIEW_INDEX - 1);
  if (phase === "choosing_design") activeIndex = SELECTION_INDEX;
  if (phase === "in_review") activeIndex = REVIEW_INDEX;
  if (phase === "publishing") activeIndex = DEPLOY_INDEX;
  if (phase === "live") activeIndex = PIPELINE_STEPS.length;
  if (phase === "failed") activeIndex = failedIndex >= 0 ? failedIndex : Math.max(activeIndex, 0);

  const steps = PIPELINE_STEPS.map((step, i) => {
    let state: StepState = "pending";
    if (i < activeIndex) state = "done";
    else if (i === activeIndex) state = phase === "failed" ? "failed" : "active";
    // Respect explicit completions the coarse status hasn't caught up with yet.
    if (state === "pending" && latest.get(step.key)?.status === "completed" && phase !== "failed") state = "done";
    return { key: step.key, label: step.label, state };
  });

  return {
    referenceNo,
    phase,
    steps,
    liveUrl: phase === "live" ? liveUrl : null,
    updatedAt: new Date(job.updatedAt).toISOString(),
  };
}

/** How long the status page waits before asking again. null = stop polling. */
export function pollDelayMs(phase: PublicPhase | null): number | null {
  switch (phase) {
    case "live":
    case "failed":
      return null;
    // A human is involved (the submitter choosing, or BUILD reviewing).
    case "choosing_design":
    case "in_review":
    case "publishing":
      return 30_000;
    default:
      return 5_000;
  }
}

export function statusPagePath(referenceNo: string): string {
  return `/intake/status/${encodeURIComponent(referenceNo)}`;
}
