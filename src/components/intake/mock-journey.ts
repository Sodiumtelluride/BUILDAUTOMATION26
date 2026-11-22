import { toPublicJobStatus, type PublicJobStatus, type StageRow } from "@/src/lib/intake/job-status";
import type { DesignOptionsState } from "@/src/lib/intake/design-options";

// A fake, time-based walk through the whole post-submission journey, used when
// NEXT_PUBLIC_INTAKE_MOCK=1 until the backend exists. One store drives both the
// status page and the design picker, so they always agree. State lives in
// sessionStorage, so it survives page changes and reloads in the demo tab.
//
//   0 ............ designsMs        building design options (INTAKE → DESIGN → CODE_GENERATION)
//   designsMs ...  (until picked)    waiting for the submitter's choice
//   picked + 0 ... + contentMs       CONTENT, then SEO
//   picked + contentMs               BUILD review (stops here; a person would take over)
//
// Special reference endings for trying error states:
//   ...-000000  building the design options fails
//   ...-EEEEEE  the first attempt to save a choice fails

export const isIntakeMockEnabled = (): boolean => process.env.NEXT_PUBLIC_INTAKE_MOCK === "1";

interface Record_ { startedAt: number; selectedId: string | null; selectedAt: number | null; failedSelect: boolean }

export interface JourneyStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export interface MockJourneyOptions {
  designsMs?: number;
  contentMs?: number;
  now?: () => number;
  storage?: JourneyStorage;
}

function memoryStorage(): JourneyStorage {
  const map = new Map<string, string>();
  return { getItem: (k) => map.get(k) ?? null, setItem: (k, v) => { map.set(k, v); } };
}

function defaultStorage(): JourneyStorage {
  try {
    if (typeof window !== "undefined" && window.sessionStorage) return window.sessionStorage;
  } catch { /* storage can be blocked */ }
  return memoryStorage();
}

const MOCK_FAMILIES = [
  { family: "bold", bg: "#111111", fg: "#ffffff", accent: "#ff5a36", radius: "999px", font: "800 64px/1 Inter, system-ui, sans-serif" },
  { family: "classic", bg: "#f7f3ec", fg: "#1f2a37", accent: "#2f6f5e", radius: "6px", font: "600 56px/1.1 Georgia, serif" },
  { family: "civic", bg: "#ffffff", fg: "#0b2545", accent: "#13315c", radius: "4px", font: "700 54px/1.1 'Source Sans 3', system-ui, sans-serif" },
] as const;

function mockSiteHtml(f: (typeof MOCK_FAMILIES)[number]): string {
  const card = (title: string) =>
    `<div style="flex:1;padding:28px;border-radius:${f.radius === "999px" ? "20px" : f.radius};background:${f.fg}10;border:1px solid ${f.fg}22"><div style="font-weight:700;font-size:22px;margin-bottom:10px">${title}</div><div style="opacity:.7;font-size:16px;line-height:1.5">[PLACEHOLDER] A short description of this program goes here.</div></div>`;
  return `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
    *{box-sizing:border-box}body{margin:0;font-family:system-ui,sans-serif;background:${f.bg};color:${f.fg}}
    nav{display:flex;justify-content:space-between;align-items:center;padding:24px 6vw;font-weight:700}
    nav span{opacity:.75;font-weight:500;margin-left:24px}
    .hero{padding:10vh 6vw 12vh}.hero h1{font:${f.font};margin:0 0 20px;max-width:14ch}
    .hero p{font-size:20px;opacity:.75;max-width:42ch;line-height:1.5}
    .btn{display:inline-block;margin-top:24px;padding:16px 28px;border-radius:${f.radius};background:${f.accent};color:#fff;font-weight:700}
    .row{display:flex;gap:24px;padding:0 6vw 10vh;flex-wrap:wrap}
    @media (max-width:600px){nav span{display:none}.hero h1{font-size:40px}.row{flex-direction:column}}
  </style></head><body>
    <nav><div>Your Organization</div><div><span>About</span><span>Programs</span><span>Get involved</span></div></nav>
    <section class="hero"><h1>[PLACEHOLDER] Your mission, in one line</h1><p>[PLACEHOLDER] A sentence about who you serve and why it matters. We'll write this from your answers.</p><a class="btn">Get involved</a></section>
    <section class="row">${card("Program one")}${card("Program two")}${card("Program three")}</section>
  </body></html>`;
}

const OPTIONS = MOCK_FAMILIES.map((f, i) => ({
  id: `opt-${f.family}`,
  family: f.family,
  previewUrl: `data:text/html;charset=utf-8,${encodeURIComponent(mockSiteHtml(f))}`,
  recommended: i === 0,
}));

export type MockSelect =
  | { kind: "ok"; data: DesignOptionsState }
  | { kind: "conflict"; data: DesignOptionsState }
  | { kind: "rejected" }
  | { kind: "error" };

export function createMockJourney({ designsMs = 10_000, contentMs = 7_000, now = Date.now, storage = defaultStorage() }: MockJourneyOptions = {}) {
  const key = (ref: string) => `build:mock-journey:${ref}`;

  const read = (ref: string): Record_ => {
    try {
      const raw = storage.getItem(key(ref));
      if (raw) return JSON.parse(raw) as Record_;
    } catch { /* corrupt or blocked: start over */ }
    const fresh: Record_ = { startedAt: now(), selectedId: null, selectedAt: null, failedSelect: false };
    write(ref, fresh);
    return fresh;
  };
  const write = (ref: string, record: Record_) => {
    try { storage.setItem(key(ref), JSON.stringify(record)); } catch { /* ignore */ }
  };

  const fails = (ref: string) => ref.endsWith("-000000");

  function designs(ref: string): DesignOptionsState {
    const r = read(ref);
    const elapsed = now() - r.startedAt;
    if (fails(ref) && elapsed >= designsMs * 0.7) return { referenceNo: ref, status: "failed", options: [], selectedOptionId: null };
    if (elapsed < designsMs) return { referenceNo: ref, status: "generating", options: [], selectedOptionId: null };
    return { referenceNo: ref, status: r.selectedId ? "submitted" : "ready", options: OPTIONS, selectedOptionId: r.selectedId };
  }

  function status(ref: string): PublicJobStatus {
    const r = read(ref);
    const t = now();
    const elapsed = t - r.startedAt;
    const rows: StageRow[] = [];
    const mark = (stage: string, state: "completed" | "running" | "failed") => rows.push({ stage, status: state, attempt: 1 });
    const job = (status: string, currentStage: string) => toPublicJobStatus(ref, { status, currentStage, liveUrl: null, updatedAt: new Date(t) }, rows);

    if (elapsed < designsMs * 0.15) return job("queued", "intake_received");

    // Building the design options.
    const buildStages: [string, number][] = [["INTAKE", 0.4], ["DESIGN", 0.7], ["CODE_GENERATION", 1]];
    for (const [stage, until] of buildStages) {
      if (elapsed < designsMs * until) {
        if (fails(ref) && stage === "CODE_GENERATION") { mark(stage, "failed"); return job("failed", stage); }
        mark(stage, "running");
        return job("in_progress", stage);
      }
      mark(stage, "completed");
    }
    if (fails(ref)) return job("failed", "CODE_GENERATION");
    if (!r.selectedAt) return job("awaiting_selection", "CODE_GENERATION");

    // After the pick: content, SEO, then review.
    const since = t - r.selectedAt;
    if (since < contentMs * 0.6) { mark("CONTENT", "running"); return job("in_progress", "CONTENT"); }
    mark("CONTENT", "completed");
    if (since < contentMs) { mark("SEO", "running"); return job("in_progress", "SEO"); }
    mark("SEO", "completed");
    return job("awaiting_review", "APPROVAL_GATE");
  }

  function select(ref: string, optionId: string): MockSelect {
    const state = designs(ref);
    if (state.status === "submitted") return { kind: "conflict", data: state };
    if (state.status !== "ready" || !OPTIONS.some((o) => o.id === optionId)) return { kind: "rejected" };
    const r = read(ref);
    if (ref.endsWith("-EEEEEE") && !r.failedSelect) {
      write(ref, { ...r, failedSelect: true });
      return { kind: "error" };
    }
    write(ref, { ...r, selectedId: optionId, selectedAt: now() });
    return { kind: "ok", data: designs(ref) };
  }

  return { designs, status, select };
}

export type MockJourney = ReturnType<typeof createMockJourney>;

let shared: MockJourney | null = null;
export function getMockJourney(): MockJourney {
  shared ??= createMockJourney();
  return shared;
}
