// Design selection: contract parsing, the HTTP and mock sources, and the status-page hand-off.
import assert from "node:assert/strict";
import { test } from "node:test";

const {
  parseDesignOptions, describeFamily, orderOptions, designPollDelayMs, designsPagePath, safePreviewUrl, MAX_DESIGN_OPTIONS,
} = await import("../src/lib/intake/design-options.ts");
const { createHttpDesignSource, createMockDesignSource } = await import("../src/components/intake/design-source.ts");
const { toPublicJobStatus, pollDelayMs } = await import("../src/lib/intake/job-status.ts");
const { fetchJobStatus } = await import("../src/components/intake/job-status-client.ts");

const REF = "INT-20261122-ABC123";
const option = (id, extra = {}) => ({ id, family: id, previewUrl: `https://${id}.demo.buildumass.org/`, recommended: false, ...extra });
const state = (extra = {}) => ({ referenceNo: REF, status: "ready", options: [option("bold", { recommended: true }), option("classic"), option("civic")], selectedOptionId: null, ...extra });

// ---------- contract ----------

test("a well-formed payload parses unchanged", () => {
  assert.deepEqual(parseDesignOptions(state()), state());
});

test("unsafe or duplicate options are dropped, and the list is capped", () => {
  const parsed = parseDesignOptions(state({
    options: [
      option("bold"),
      option("bold"), // duplicate id
      option("evil", { previewUrl: "javascript:alert(1)" }),
      option("data", { previewUrl: "data:text/html,<p>hi</p>" }), // only the mock may use data:
      ...["a", "b", "c", "d", "e", "f"].map((id) => option(id)),
    ],
  }));
  assert.deepEqual(parsed.options.map((o) => o.id), ["bold", "a", "b", "c", "d"]);
  assert.ok(parsed.options.length <= MAX_DESIGN_OPTIONS);
  assert.equal(safePreviewUrl("data:text/html,x", { allowData: true }), "data:text/html,x");
});

test("'ready' with nothing usable is shown as a failure", () => {
  assert.equal(parseDesignOptions(state({ options: [option("x", { previewUrl: "ftp://x" })] })).status, "failed");
});

test("a selection that isn't one of the options is ignored", () => {
  assert.equal(parseDesignOptions(state({ status: "submitted", selectedOptionId: "nope" })).selectedOptionId, null);
});

test("wrong shapes are rejected", () => {
  for (const bad of [null, [], { ...state(), status: "done" }, { ...state(), options: "x" }, { ...state(), selectedOptionId: 3 }, { ...state(), referenceNo: 1 }]) {
    assert.equal(parseDesignOptions(bad), null);
  }
});

test("family names are friendly, with a fallback for families the UI doesn't know", () => {
  assert.equal(describeFamily("CIVIC").name, "Civic");
  assert.equal(describeFamily("night_market").name, "Night Market");
  assert.equal(describeFamily("").name, "Design");
});

test("the recommended design comes first; polling only while generating", () => {
  assert.deepEqual(orderOptions([option("a"), option("b", { recommended: true })]).map((o) => o.id), ["b", "a"]);
  assert.equal(designPollDelayMs("generating"), 5_000);
  assert.equal(designPollDelayMs("ready"), null);
  assert.equal(designsPagePath(REF), `/intake/designs/${REF}`);
});

// ---------- HTTP source ----------

function fakeFetch(handler) {
  const calls = [];
  const fetcher = async (url, init = {}) => { calls.push({ url, init }); return handler(url, init); };
  return { fetcher, calls };
}

test("http load maps responses to ok, not found, and error", async () => {
  const ok = fakeFetch(() => Response.json({ success: true, data: state() }));
  assert.equal((await createHttpDesignSource(ok.fetcher).load(REF)).kind, "ok");
  assert.equal(ok.calls[0].url, `/api/intake/designs/${REF}`);

  for (const [response, kind] of [
    [new Response(null, { status: 404 }), "not_found"],
    [new Response(null, { status: 400 }), "not_found"],
    [new Response("<html>", { status: 502 }), "error"],
    [Response.json({ success: true, data: { nope: true } }), "error"],
  ]) {
    assert.equal((await createHttpDesignSource(async () => response).load(REF)).kind, kind);
  }
  assert.equal((await createHttpDesignSource(async () => { throw new TypeError("offline"); }).load(REF)).kind, "error");
});

test("http load lets an abort through instead of reporting an error", async () => {
  const controller = new AbortController();
  controller.abort();
  const source = createHttpDesignSource(async () => { throw new DOMException("aborted", "AbortError"); });
  await assert.rejects(source.load(REF, controller.signal));
});

test("http select posts the option id and handles every outcome", async () => {
  const ok = fakeFetch(() => Response.json({ success: true, data: state({ status: "submitted", selectedOptionId: "classic" }) }));
  const result = await createHttpDesignSource(ok.fetcher).select(REF, "classic");
  assert.equal(result.kind, "ok");
  assert.equal(ok.calls[0].url, `/api/intake/designs/${REF}/selection`);
  assert.equal(ok.calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(ok.calls[0].init.body), { optionId: "classic" });

  const conflict = await createHttpDesignSource(async () => Response.json({ success: false, data: state({ status: "submitted", selectedOptionId: "bold" }) }, { status: 409 })).select(REF, "classic");
  assert.equal(conflict.kind, "conflict");
  assert.equal(conflict.data.selectedOptionId, "bold");

  assert.equal((await createHttpDesignSource(async () => new Response(null, { status: 400 })).select(REF, "x")).kind, "rejected");
  assert.equal((await createHttpDesignSource(async () => new Response(null, { status: 500 })).select(REF, "x")).kind, "error");
  assert.equal((await createHttpDesignSource(async () => { throw new TypeError("offline"); }).select(REF, "x")).kind, "error");
  // A 200 that didn't actually record the choice must not look like success.
  assert.equal((await createHttpDesignSource(async () => Response.json({ success: true, data: state() })).select(REF, "bold")).kind, "error");
});

// ---------- mock source ----------

test("mock moves from generating to ready, accepts one choice, then reports a conflict", async () => {
  let clock = 0;
  const source = createMockDesignSource({ generationMs: 1_000, now: () => clock });
  assert.equal((await source.load(REF)).data.status, "generating");
  assert.equal((await source.select(REF, "opt-bold")).kind, "rejected");

  clock = 1_000;
  const ready = await source.load(REF);
  assert.equal(ready.data.status, "ready");
  assert.equal(ready.data.options.length, 3);
  assert.ok(ready.data.options[0].previewUrl.startsWith("data:text/html"));
  assert.equal(ready.data.options.filter((o) => o.recommended).length, 1);

  assert.equal((await source.select(REF, "opt-nope")).kind, "rejected");
  const chosen = await source.select(REF, "opt-classic");
  assert.equal(chosen.kind, "ok");
  assert.equal(chosen.data.status, "submitted");
  assert.equal(chosen.data.selectedOptionId, "opt-classic");
  assert.equal((await source.select(REF, "opt-bold")).kind, "conflict");
  assert.equal((await source.load(REF)).data.selectedOptionId, "opt-classic");
});

test("mock error references exercise the failure states", async () => {
  const source = createMockDesignSource({ generationMs: 0 });
  assert.equal((await source.load("INT-20261122-000000")).data.status, "failed");
  const flaky = "INT-20261122-EEEEEE";
  await source.load(flaky);
  assert.equal((await source.select(flaky, "opt-bold")).kind, "error");
  assert.equal((await source.select(flaky, "opt-bold")).kind, "ok");
});

// ---------- status page hand-off ----------

test("a job waiting for the submitter's choice maps to choosing_design", async () => {
  const status = toPublicJobStatus(REF, { status: "awaiting_selection", currentStage: "CODE_GENERATION", liveUrl: "https://x.org", updatedAt: new Date() });
  assert.equal(status.phase, "choosing_design");
  assert.equal(status.liveUrl, null);
  assert.equal(pollDelayMs("choosing_design"), 30_000);
  const client = await fetchJobStatus(REF, undefined, async () => Response.json({ success: true, data: status }));
  assert.equal(client.kind, "ok");
});

// ---------- the design step in the timeline ----------

test("the design choice is its own step: pending while building, active when it's their turn, done after", () => {
  const job = (status, currentStage) => ({ status, currentStage, liveUrl: null, updatedAt: new Date() });
  const at = (status) => status.steps.find((s) => s.key === "DESIGN_SELECTION").state;
  assert.equal(at(toPublicJobStatus(REF, job("in_progress", "CODE_GENERATION"))), "pending");
  assert.equal(at(toPublicJobStatus(REF, job("awaiting_selection", "CODE_GENERATION"))), "active");
  assert.equal(at(toPublicJobStatus(REF, job("in_progress", "CONTENT"))), "done");
  assert.equal(at(toPublicJobStatus(REF, job("awaiting_review", "APPROVAL_GATE"))), "done");
});

// ---------- mock journey (status page and picker share one store) ----------

const { createMockJourney } = await import("../src/components/intake/mock-journey.ts");
const { designSourceFromJourney } = await import("../src/components/intake/design-source.ts");

function memory() {
  const map = new Map();
  return { getItem: (k) => map.get(k) ?? null, setItem: (k, v) => map.set(k, v), map };
}

test("mock journey walks status and designs through the whole flow in step", async () => {
  let clock = 0;
  const journey = createMockJourney({ designsMs: 1_000, contentMs: 1_000, now: () => clock, storage: memory() });
  const phase = () => journey.status(REF).phase;

  assert.equal(phase(), "queued");
  clock = 500;
  assert.equal(phase(), "generating");
  assert.equal(journey.designs(REF).status, "generating");

  clock = 1_000;
  assert.equal(phase(), "choosing_design");
  assert.equal(journey.designs(REF).status, "ready");
  assert.equal((await designSourceFromJourney(journey).select(REF, "opt-civic")).kind, "ok");

  const writing = journey.status(REF);
  assert.equal(writing.phase, "generating");
  assert.equal(writing.steps.find((s) => s.key === "DESIGN_SELECTION").state, "done");
  assert.equal(writing.steps.find((s) => s.key === "CONTENT").state, "active");

  clock = 2_000;
  assert.equal(phase(), "in_review");
});

test("mock journey survives a reload (same storage, new instance)", () => {
  const storage = memory();
  let clock = 0;
  const first = createMockJourney({ designsMs: 1_000, now: () => clock, storage });
  first.status(REF);
  clock = 1_000;
  first.select(REF, "opt-bold");
  const again = createMockJourney({ designsMs: 1_000, now: () => clock, storage });
  assert.equal(again.designs(REF).selectedOptionId, "opt-bold");
});

test("mock journey failure reference stops at building the design options", () => {
  let clock = 0;
  const journey = createMockJourney({ designsMs: 1_000, now: () => clock, storage: memory() });
  const ref = "INT-20261122-000000";
  journey.status(ref);
  clock = 800;
  const status = journey.status(ref);
  assert.equal(status.phase, "failed");
  assert.equal(status.steps.find((s) => s.key === "CODE_GENERATION").state, "failed");
  assert.equal(journey.designs(ref).status, "failed");
});

test("corrupt mock storage starts a fresh journey instead of crashing", () => {
  const storage = memory();
  storage.setItem(`build:mock-journey:${REF}`, "{not json");
  assert.equal(createMockJourney({ storage }).status(REF).phase, "queued");
});
