import { PIPELINE_STEPS, type PublicJobStatus, type PublicPhase } from "@/src/lib/intake/job-status";
import { getMockJourney, isIntakeMockEnabled } from "./mock-journey";

export type StatusResult =
  | { kind: "ok"; data: PublicJobStatus }
  | { kind: "not_found" }
  | { kind: "error" };

const PHASES: PublicPhase[] = ["queued", "generating", "choosing_design", "in_review", "publishing", "live", "failed"];
const STATES = ["pending", "active", "done", "failed"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function isPublicJobStatus(value: unknown): value is PublicJobStatus {
  if (!isRecord(value)) return false;
  if (typeof value.referenceNo !== "string" || !PHASES.includes(value.phase as PublicPhase)) return false;
  if (value.liveUrl !== null && typeof value.liveUrl !== "string") return false;
  if (!Array.isArray(value.steps) || value.steps.length !== PIPELINE_STEPS.length) return false;
  return value.steps.every((step) => isRecord(step) && typeof step.label === "string" && STATES.includes(step.state as string));
}

export async function fetchJobStatus(referenceNo: string, signal?: AbortSignal, fetcher: typeof fetch = fetch): Promise<StatusResult> {
  let response: Response;
  try {
    response = await fetcher(`/api/intake/status/${encodeURIComponent(referenceNo)}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    return { kind: "error" };
  }
  if (response.status === 404 || response.status === 400) return { kind: "not_found" };
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok || !isRecord(body) || body.success !== true || !isPublicJobStatus(body.data)) return { kind: "error" };
  return { kind: "ok", data: body.data };
}

export type StatusFetcher = (referenceNo: string, signal?: AbortSignal) => Promise<StatusResult>;

/** The real API, or the shared mock journey when NEXT_PUBLIC_INTAKE_MOCK=1. */
export function getStatusFetcher(): StatusFetcher {
  if (!isIntakeMockEnabled()) return (referenceNo, signal) => fetchJobStatus(referenceNo, signal);
  const journey = getMockJourney();
  return async (referenceNo) => {
    await new Promise((resolve) => setTimeout(resolve, 200));
    return { kind: "ok", data: journey.status(referenceNo) };
  };
}
