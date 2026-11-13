// Local demo builds: how a "running" row is finished from the job folder, and how a run is claimed and started.
import assert from "node:assert/strict";
import { chmod, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { register } from "node:module";
import { tmpdir } from "node:os";
import path from "node:path";
import { beforeEach, test } from "node:test";

register("./helpers/typescript-loader.mjs", import.meta.url, { data: { mocks: {
  "@/src/db": `data:text/javascript,${encodeURIComponent("export function getDb() { return globalThis.__fakeDb; }")}`,
} } });

const { START_GRACE_MS, settlement, settleDemo, startDemoBuild } = await import("../src/lib/demo-site.ts");

const ID = "3f2b8c1e-7a4d-4e5f-9b6a-1c2d3e4f5a6b";
const NOTES = JSON.stringify({ version: 1, answers: { organizationName: "Org" }, attachments: [], organizationId: "o", jobId: "j" });

/** Records every update's values; `returning` resolves to `rows`. */
function fakeDb(rows = []) {
  const updates = [];
  const chain = {
    update: () => chain,
    set: (values) => { updates.push(values); return chain; },
    where: () => chain,
    returning: () => Promise.resolve(rows),
    then: (resolve, reject) => Promise.resolve([]).then(resolve, reject),
  };
  return { db: chain, updates };
}

let root;
beforeEach(async () => {
  root = await mkdtemp(path.join(tmpdir(), "demo-sites-"));
  process.env.DEMO_SITES_DIR = root;
});

const started = new Date("2026-11-13T12:00:00Z");
const later = new Date(started.getTime() + START_GRACE_MS + 1);

test("a result written after the run started finishes the row", () => {
  const ok = { status: "succeeded", url: "http://localhost:5000", finished_at: later.toISOString() };
  assert.deepEqual(settlement(started, ok, false, later), { demoStatus: "succeeded", demoUrl: "http://localhost:5000", demoError: null });
  const bad = { status: "failed", error: "no valid design spec", finished_at: later.toISOString() };
  assert.deepEqual(settlement(started, bad, true, later), { demoStatus: "failed", demoUrl: null, demoError: "no valid design spec" });
});

test("a result from an earlier run is ignored", () => {
  const stale = { status: "succeeded", url: "http://localhost:1", finished_at: "2026-11-01T00:00:00Z" };
  assert.equal(settlement(started, stale, true, later), null);
});

test("a young run is never declared dead, an old one is once its process is gone", () => {
  assert.equal(settlement(started, null, false, new Date(started.getTime() + 5_000)), null);
  assert.equal(settlement(started, null, true, later), null);
  assert.equal(settlement(started, null, false, later).demoStatus, "failed");
});

test("settleDemo writes the outcome of a finished run and leaves other rows alone", async () => {
  const { db, updates } = fakeDb();
  globalThis.__fakeDb = db;
  const dir = path.join(root, ID);
  await mkdir(dir);
  await writeFile(path.join(dir, "result.json"), JSON.stringify({ status: "succeeded", url: "http://localhost:7", finished_at: new Date().toISOString() }));
  const row = { id: ID, demoStatus: "running", demoUrl: null, demoError: null, demoStartedAt: new Date(Date.now() - 1000) };
  assert.equal((await settleDemo(row)).demoUrl, "http://localhost:7");
  assert.equal(updates.length, 1);
  const done = { ...row, demoStatus: "succeeded" };
  assert.equal(await settleDemo(done), done);
  assert.equal(updates.length, 1);
});

test("a second click while a build is running is refused", async () => {
  globalThis.__fakeDb = fakeDb([]).db; // the conditional claim matched no row
  assert.equal(await startDemoBuild(ID), "busy");
});

test("without DEMO_SITES_DIR the button does nothing", async () => {
  delete process.env.DEMO_SITES_DIR;
  assert.equal(await startDemoBuild(ID), "unavailable");
});

test("a claimed run starts detached, reads intake.json, and never sees the console's secrets (only the model key)", async () => {
  const { db } = fakeDb([{ notes: NOTES }]);
  globalThis.__fakeDb = db;
  const seen = path.join(root, "seen.txt");
  const fake = path.join(root, "fake-python.sh");
  await writeFile(fake, `#!/bin/sh\n{ cat; echo; echo "DB=\${DATABASE_URL:-unset} OLLAMA=\${OLLAMA_HOST:-unset} KEY=\${ANTHROPIC_API_KEY:-unset}"; } > ${seen}\n`);
  await chmod(fake, 0o755);
  process.env.AGENT_PYTHON = fake;
  process.env.DATABASE_URL = "postgresql://platform-db";
  process.env.OLLAMA_HOST = "http://localhost:11434";
  process.env.ANTHROPIC_API_KEY = "test-key";
  try {
    assert.equal(await startDemoBuild(ID), "started");
  } finally {
    delete process.env.AGENT_PYTHON;
    delete process.env.DATABASE_URL;
    delete process.env.OLLAMA_HOST;
    delete process.env.ANTHROPIC_API_KEY;
  }
  assert.match(await readFile(path.join(root, ID, "run.pid"), "utf8"), /^\d+\n$/);
  let output = "";
  for (let i = 0; i < 200 && !output.includes("DB="); i++) { // up to 10s: the detached child may start slowly on a busy machine
    await new Promise((r) => setTimeout(r, 50));
    output = await readFile(seen, "utf8").catch(() => "");
  }
  assert.ok(output.startsWith(NOTES));
  assert.match(output, /DB=unset OLLAMA=http:\/\/localhost:11434 KEY=test-key/);
});

test("an intake without saved answers fails instead of starting", async () => {
  const { db, updates } = fakeDb([{ notes: "plain text notes" }]);
  globalThis.__fakeDb = db;
  assert.equal(await startDemoBuild(ID), "failed");
  assert.equal(updates.at(-1).demoStatus, "failed");
});
