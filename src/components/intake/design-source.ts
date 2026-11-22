import { parseDesignOptions, type DesignOptionsState } from "@/src/lib/intake/design-options";
import { createMockJourney, getMockJourney, isIntakeMockEnabled, type MockJourney } from "./mock-journey";

// Where the design selection page gets its data. The HTTP source speaks the
// proposed contract in src/lib/intake/design-options.ts; the mock (shared with
// the status page, see mock-journey.ts) stands in until a backend implements
// it. Turn the mock on with NEXT_PUBLIC_INTAKE_MOCK=1.

export type LoadResult =
  | { kind: "ok"; data: DesignOptionsState }
  | { kind: "not_found" }
  | { kind: "error" };

export type SelectResult =
  | { kind: "ok"; data: DesignOptionsState }
  /** Someone already chose (another tab, a double click). data is the current state. */
  | { kind: "conflict"; data: DesignOptionsState }
  | { kind: "rejected" }
  | { kind: "error" };

export interface DesignSource {
  load(referenceNo: string, signal?: AbortSignal): Promise<LoadResult>;
  select(referenceNo: string, optionId: string): Promise<SelectResult>;
}

// ---------- HTTP ----------

export function createHttpDesignSource(fetcher: typeof fetch = (...args) => fetch(...args)): DesignSource {
  const base = (referenceNo: string) => `/api/intake/designs/${encodeURIComponent(referenceNo)}`;
  const readState = async (response: Response) => {
    const body: unknown = await response.json().catch(() => null);
    return body && typeof body === "object" && "data" in body ? parseDesignOptions(body.data) : null;
  };

  return {
    async load(referenceNo, signal) {
      let response: Response;
      try {
        response = await fetcher(base(referenceNo), { headers: { Accept: "application/json" }, cache: "no-store", signal });
      } catch (error) {
        if (signal?.aborted) throw error;
        return { kind: "error" };
      }
      if (response.status === 404 || response.status === 400) return { kind: "not_found" };
      const data = response.ok ? await readState(response) : null;
      return data ? { kind: "ok", data } : { kind: "error" };
    },

    async select(referenceNo, optionId) {
      let response: Response;
      try {
        response = await fetcher(`${base(referenceNo)}/selection`, {
          method: "POST",
          headers: { Accept: "application/json", "Content-Type": "application/json" },
          body: JSON.stringify({ optionId }),
        });
      } catch {
        return { kind: "error" };
      }
      if (response.status === 409) {
        const data = await readState(response);
        return data ? { kind: "conflict", data } : { kind: "error" };
      }
      if (response.status === 400 || response.status === 404) return { kind: "rejected" };
      const data = response.ok ? await readState(response) : null;
      return data && data.status === "submitted" ? { kind: "ok", data } : { kind: "error" };
    },
  };
}

// ---------- Mock ----------

export function designSourceFromJourney(journey: MockJourney): DesignSource {
  const delay = () => new Promise((resolve) => setTimeout(resolve, 300));
  return {
    async load(referenceNo) {
      await delay();
      const data = parseDesignOptions(journey.designs(referenceNo), { allowData: true });
      return data ? { kind: "ok", data } : { kind: "error" };
    },
    async select(referenceNo, optionId) {
      await delay();
      return journey.select(referenceNo, optionId);
    },
  };
}

/** A standalone mock (its own in-memory journey), handy in tests. */
export function createMockDesignSource({ generationMs = 4_000, now = Date.now }: { generationMs?: number; now?: () => number } = {}): DesignSource {
  const map = new Map<string, string>();
  const storage = { getItem: (k: string) => map.get(k) ?? null, setItem: (k: string, v: string) => { map.set(k, v); } };
  return designSourceFromJourney(createMockJourney({ designsMs: generationMs, now, storage }));
}

let shared: DesignSource | null = null;

export function getDesignSource(): DesignSource {
  shared ??= isIntakeMockEnabled() ? designSourceFromJourney(getMockJourney()) : createHttpDesignSource();
  return shared;
}
