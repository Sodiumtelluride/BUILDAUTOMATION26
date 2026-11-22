// Public status page: what a nonprofit can see about its job after submitting.
import assert from "node:assert/strict";
import { register } from "node:module";
import { after, before, beforeEach, test } from "node:test";
import { fileURLToPath } from "node:url";
import { PGlite } from "@electric-sql/pglite";
import { drizzle } from "drizzle-orm/pglite";
import { migrate } from "drizzle-orm/pglite/migrator";
import { intakeAnswers } from "./helpers/intake-fixture.mjs";

function moduleUrl(source) { return `data:text/javascript,${encodeURIComponent(source)}`; }

register("./helpers/typescript-loader.mjs", import.meta.url, { data: { mocks: {
  "@/src/db": moduleUrl("export function getDb() { if (globalThis.__statusDbError) throw globalThis.__statusDbError; return globalThis.__statusDb; }"),
  "@/src/auth": moduleUrl("export async function auth() { return null; }"),
  "@/src/lib/intake/uploads": moduleUrl(`
    export const MAX_INTAKE_REQUEST_BYTES = 61 * 1024 * 1024;
    export class UploadStorageError extends Error {}
    export class UploadValidationError extends Error {}
    export async function uploadIntakeFiles() { return []; }
    export async function rollbackIntakeUploads() {}
  `),
} } });

const { POST } = await import("../app/api/intake/route.ts");
const { GET } = await import("../app/api/intake/status/[referenceNo]/route.ts");
const { toPublicJobStatus, pollDelayMs, safeSiteUrl, statusPagePath } = await import("../src/lib/intake/job-status.ts");
const { fetchJobStatus } = await import("../src/components/intake/job-status-client.ts");
const { isPublicRequest } = await import("../src/lib/auth/access.ts");

const database = new PGlite();
const db = drizzle(database);

before(async () => {
  await migrate(db, { migrationsFolder: fileURLToPath(new URL("../src/db/migrations/", import.meta.url)) });
});
after(async () => { await database.close(); });
beforeEach(async () => {
  await database.exec("TRUNCATE deployments, job_stages, assets, intake_jobs, intake_submissions, organizations CASCADE");
  globalThis.__statusDb = db;
  globalThis.__statusDbError = null;
});

async function submit() {
  const response = await POST(new Request("http://localhost/api/intake", {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(intakeAnswers()),
  }));
  const { data } = await response.json();
  return { referenceNo: data.submission.referenceNo, jobId: data.job.id };
}

function getStatus(referenceNo) {
  return GET(new Request(`http://localhost/api/intake/status/${referenceNo}`), { params: Promise.resolve({ referenceNo }) });
}

const job = (overrides = {}) => ({ status: "queued", currentStage: "intake_received", liveUrl: null, updatedAt: new Date("2026-11-17T12:00:00Z"), ...overrides });
const states = (status) => status.steps.map((s) => s.state);

// ---------- mapping ----------

test("a freshly submitted job is queued with nothing started", () => {
  const status = toPublicJobStatus("INT-20261117-ABC123", job());
  assert.equal(status.phase, "queued");
  assert.ok(status.steps.every((s) => s.state === "pending"));
});

test("running stages show earlier steps done and the running one active", () => {
  const status = toPublicJobStatus("INT-20261117-ABC123", job({ status: "in_progress", currentStage: "DESIGN" }), [
    { stage: "INTAKE", status: "completed", attempt: 1 },
    { stage: "DESIGN", status: "completed", attempt: 1 },
    { stage: "CODE_GENERATION", status: "running", attempt: 1 },
  ]);
  assert.equal(status.phase, "generating");
  assert.deepEqual(states(status), ["done", "done", "active", "pending", "pending", "pending", "pending", "pending"]);
});

test("a retried stage uses its latest attempt", () => {
  const status = toPublicJobStatus("INT-20261117-ABC123", job({ status: "in_progress" }), [
    { stage: "INTAKE", status: "completed", attempt: 1 },
    { stage: "DESIGN", status: "failed", attempt: 1 },
    { stage: "DESIGN", status: "running", attempt: 2 },
  ]);
  assert.deepEqual(states(status).slice(0, 3), ["done", "active", "pending"]);
});

test("awaiting review never exposes a link, even if a preview exists", () => {
  const status = toPublicJobStatus("INT-20261117-ABC123", job({ status: "awaiting_review", liveUrl: "https://example.org" }));
  assert.equal(status.phase, "in_review");
  assert.equal(status.liveUrl, null);
  assert.deepEqual(states(status), ["done", "done", "done", "done", "done", "done", "active", "pending"]);
});

test("deployed jobs expose the live URL and finish every step", () => {
  const status = toPublicJobStatus("INT-20261117-ABC123", job({ status: "deployed", liveUrl: "https://pioneer.buildumass.org" }));
  assert.equal(status.phase, "live");
  assert.equal(status.liveUrl, "https://pioneer.buildumass.org/");
  assert.ok(status.steps.every((s) => s.state === "done"));
});

test("a deployed job without a safe URL keeps showing 'publishing'", () => {
  for (const liveUrl of [null, "javascript:alert(1)", "not a url"]) {
    const status = toPublicJobStatus("INT-20261117-ABC123", job({ status: "deployed", liveUrl }));
    assert.equal(status.phase, "publishing");
    assert.equal(status.liveUrl, null);
  }
});

test("failed jobs mark the stage that failed", () => {
  const status = toPublicJobStatus("INT-20261117-ABC123", job({ status: "failed" }), [
    { stage: "INTAKE", status: "completed", attempt: 1 },
    { stage: "DESIGN", status: "completed", attempt: 1 },
    { stage: "CODE_GENERATION", status: "failed", attempt: 3 },
  ]);
  assert.equal(status.phase, "failed");
  assert.deepEqual(states(status).slice(0, 4), ["done", "done", "failed", "pending"]);
});

test("polling is fast while building, slow during human review, and stops when finished", () => {
  assert.equal(pollDelayMs("generating"), 5_000);
  assert.equal(pollDelayMs("in_review"), 30_000);
  assert.equal(pollDelayMs("live"), null);
  assert.equal(pollDelayMs("failed"), null);
  assert.equal(safeSiteUrl("ftp://x.org"), null);
  assert.equal(statusPagePath("INT-20261117-ABC123"), "/intake/status/INT-20261117-ABC123");
});

// ---------- endpoint ----------

test("status endpoint returns progress for a real submission without personal data", async () => {
  const { referenceNo } = await submit();
  const response = await getStatus(referenceNo);
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "no-store");
  const text = await response.text();
  for (const secret of ["Maria", "Pioneer Community", "@", "preview"]) {
    assert.equal(text.includes(secret), false, `response must not contain ${secret}`);
  }
  assert.equal(JSON.parse(text).data.phase, "queued");
});

test("status endpoint follows the job through review to a live link", async () => {
  const { referenceNo, jobId } = await submit();
  await database.query("UPDATE intake_jobs SET status = 'awaiting_review', preview_url = 'https://preview.vercel.app/x' WHERE id = $1", [jobId]);
  let body = await (await getStatus(referenceNo)).json();
  assert.equal(body.data.phase, "in_review");
  assert.equal(body.data.liveUrl, null);

  await database.query("UPDATE intake_jobs SET status = 'deployed' WHERE id = $1", [jobId]);
  await database.query("INSERT INTO deployments (job_id, live_url) VALUES ($1, 'https://pioneer.buildumass.org')", [jobId]);
  body = await (await getStatus(referenceNo)).json();
  assert.equal(body.data.phase, "live");
  assert.equal(body.data.liveUrl, "https://pioneer.buildumass.org/");
});

test("status endpoint reads stage rows written by the pipeline", async () => {
  const { referenceNo, jobId } = await submit();
  await database.query("UPDATE intake_jobs SET status = 'in_progress' WHERE id = $1", [jobId]);
  await database.query("INSERT INTO job_stages (job_id, stage, status) VALUES ($1, 'INTAKE', 'completed'), ($1, 'DESIGN', 'running')", [jobId]);
  const body = await (await getStatus(referenceNo)).json();
  assert.deepEqual(states(body.data).slice(0, 3), ["done", "active", "pending"]);
});

test("unknown, malformed, and lowercase reference numbers are handled", async () => {
  assert.equal((await getStatus("INT-20261117-FFFFFF")).status, 404);
  assert.equal((await getStatus("../../etc")).status, 400);
  assert.equal((await getStatus("%E0%A4%A")).status, 400); // malformed escape must not crash
  const { referenceNo } = await submit();
  assert.equal((await getStatus(referenceNo.toLowerCase())).status, 200);
});

test("database outages return 503, not a crash", async () => {
  globalThis.__statusDbError = new Error("down");
  assert.equal((await getStatus("INT-20261117-ABC123")).status, 503);
});

// ---------- client + access ----------

test("client fetcher distinguishes ok, not found, and errors", async () => {
  const { referenceNo } = await submit();
  const viaRoute = async (url) => GET(new Request(`http://localhost${url}`), { params: Promise.resolve({ referenceNo: url.split("/").pop() }) });
  assert.equal((await fetchJobStatus(referenceNo, undefined, viaRoute)).kind, "ok");
  assert.equal((await fetchJobStatus("INT-20261117-FFFFFF", undefined, viaRoute)).kind, "not_found");
  assert.equal((await fetchJobStatus(referenceNo, undefined, async () => { throw new TypeError("offline"); })).kind, "error");
  assert.equal((await fetchJobStatus(referenceNo, undefined, async () => new Response("<html>", { status: 502 }))).kind, "error");
  assert.equal((await fetchJobStatus(referenceNo, undefined, async () => Response.json({ success: true, data: { phase: "hacked" } }))).kind, "error");
});

test("status page and status API are public; nothing else under /api/intake opens up", () => {
  assert.equal(isPublicRequest("/intake/status/INT-20261117-ABC123", "GET"), true);
  assert.equal(isPublicRequest("/api/intake/status/INT-20261117-ABC123", "GET"), true);
  assert.equal(isPublicRequest("/api/intake/status/INT-20261117-ABC123", "PATCH"), false);
  assert.equal(isPublicRequest("/api/intake/status/x/y", "GET"), false);
  assert.equal(isPublicRequest("/api/intake/3f2b8c1e-7a4d-4e5f-9b6a-1c2d3e4f5a6b", "GET"), false);
});
