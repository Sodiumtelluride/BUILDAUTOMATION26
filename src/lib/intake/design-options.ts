// Design selection: the nonprofit compares the generated design alternatives
// and picks one before content generation starts.
//
// PROPOSED CONTRACT — the frontend is built against this, but no backend
// implements it yet (the UI runs on a mock; see design-source.ts). Agree it with
// the agent owner before wiring the real routes.
//
//   GET  /api/intake/designs/{referenceNo}
//     200 { success: true, data: DesignOptionsState }
//     404 unknown reference · 400 malformed reference
//
//   POST /api/intake/designs/{referenceNo}/selection   body { optionId }
//     200 { success: true, data: DesignOptionsState }   status becomes "submitted"
//     409 { success: false, data: DesignOptionsState }  a design was already chosen
//     400 unknown optionId or designs not ready · 404 unknown reference
//
// Like the status API, both are public (the submitter has no account), so they
// return nothing personal. The number of options is the backend's call: the
// pipeline currently builds every theme family (5); the ticket asks for 3. The
// UI handles 1 to MAX_DESIGN_OPTIONS.

export const MAX_DESIGN_OPTIONS = 5;

export type DesignOptionsStatus = "generating" | "ready" | "submitted" | "failed";

export interface DesignOption {
  /** Stable id the selection POST sends back. */
  id: string;
  /** Theme family from the template (bold, classic, civic, collage, transit). */
  family: string;
  /** Live preview of this design with placeholder copy. */
  previewUrl: string;
  /** The agent's own pick for this intake. */
  recommended: boolean;
}

export interface DesignOptionsState {
  referenceNo: string;
  status: DesignOptionsStatus;
  options: DesignOption[];
  selectedOptionId: string | null;
}

// Plain-language names for the template's theme families (from the DESIGN prompt).
const FAMILY_INFO: Record<string, { name: string; description: string }> = {
  bold: { name: "Bold", description: "High-contrast and energetic, made to grab attention." },
  classic: { name: "Classic", description: "Balanced and familiar, with a conventional layout." },
  civic: { name: "Civic", description: "Institutional and trustworthy, calm and clear." },
  collage: { name: "Collage", description: "Playful, with layered cut-paper shapes." },
  transit: { name: "Transit", description: "Signage-inspired, with flat color and sharp corners." },
};

export function describeFamily(family: string): { name: string; description: string } {
  const known = FAMILY_INFO[family.toLowerCase()];
  if (known) return known;
  const name = family.replace(/[-_]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()).trim() || "Design";
  return { name, description: "A distinct visual style for your site." };
}

/** Only http(s) previews are framed. data: is allowed solely for the local mock. */
export function safePreviewUrl(url: unknown, { allowData = false } = {}): string | null {
  if (typeof url !== "string" || !url) return null;
  if (allowData && url.startsWith("data:text/html")) return url;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch {
    return null;
  }
}

const STATUSES: DesignOptionsStatus[] = ["generating", "ready", "submitted", "failed"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

/** Validates an API payload. Drops options with unusable previews; returns null if the shape is wrong. */
export function parseDesignOptions(value: unknown, { allowData = false } = {}): DesignOptionsState | null {
  if (!isRecord(value) || typeof value.referenceNo !== "string") return null;
  if (!STATUSES.includes(value.status as DesignOptionsStatus) || !Array.isArray(value.options)) return null;
  if (value.selectedOptionId !== null && typeof value.selectedOptionId !== "string") return null;

  const seen = new Set<string>();
  const options: DesignOption[] = [];
  for (const raw of value.options) {
    if (options.length === MAX_DESIGN_OPTIONS) break;
    if (!isRecord(raw) || typeof raw.id !== "string" || !raw.id || seen.has(raw.id) || typeof raw.family !== "string") continue;
    const previewUrl = safePreviewUrl(raw.previewUrl, { allowData });
    if (!previewUrl) continue;
    seen.add(raw.id);
    options.push({ id: raw.id, family: raw.family, previewUrl, recommended: raw.recommended === true });
  }

  const status = value.status as DesignOptionsStatus;
  // "ready" with nothing usable to show is a failure from the submitter's point of view.
  if (status === "ready" && options.length === 0) return { referenceNo: value.referenceNo, status: "failed", options, selectedOptionId: null };
  const selectedOptionId = value.selectedOptionId && seen.has(value.selectedOptionId) ? value.selectedOptionId : null;
  return { referenceNo: value.referenceNo, status, options, selectedOptionId };
}

/** Recommended first, then the order the backend sent. */
export function orderOptions(options: DesignOption[]): DesignOption[] {
  return [...options].sort((a, b) => Number(b.recommended) - Number(a.recommended));
}

export function designPollDelayMs(status: DesignOptionsStatus | null): number | null {
  return status === "generating" || status === null ? 5_000 : null;
}

export function designsPagePath(referenceNo: string): string {
  return `/intake/designs/${encodeURIComponent(referenceNo)}`;
}
