import assert from "node:assert/strict";
import { register } from "node:module";
import { after, before, beforeEach, test } from "node:test";
import { fileURLToPath } from "node:url";
import { PGlite } from "@electric-sql/pglite";
import { drizzle } from "drizzle-orm/pglite";
import { migrate } from "drizzle-orm/pglite/migrator";
import { CONTENT_YES } from "../src/lib/intake/contract.ts";
import { intakeAnswers } from "./helpers/intake-fixture.mjs";

function moduleUrl(source) { return `data:text/javascript,${encodeURIComponent(source)}`; }

register("./helpers/typescript-loader.mjs", import.meta.url, { data: { mocks: {
  "@/src/db": moduleUrl("export function getDb() { if (globalThis.__intakeDbError) throw globalThis.__intakeDbError; return globalThis.__intakeDb; }"),
  "@/src/auth": moduleUrl("export async function auth() { return globalThis.__intakeSession; }"),
  "@/src/lib/intake/uploads": moduleUrl(`
    export const MAX_INTAKE_REQUEST_BYTES = 61 * 1024 * 1024;
    export class UploadStorageError extends Error {}
    export class UploadValidationError extends Error { constructor(field, message) { super(message); this.field = field; } }
    export async function uploadIntakeFiles(files, jobId) {
      globalThis.__intakeUploadCalls++;
      if (globalThis.__intakeUploadError) throw globalThis.__intakeUploadError;
      return [...files.logo.map(file => ({ file, category: 'logo' })), ...files.content.map(file => ({ file, category: 'content' }))].map(({file,category}) => ({ category, originalName: file.name, size: file.size, contentType: file.type || 'text/plain', bucket: 'intake-private', path: jobId + '/' + file.name }));
    }
    export async function rollbackIntakeUploads(files) { globalThis.__intakeRolledBack.push(...files); }
  `),
} } });

const { POST } = await import("../app/api/intake/route.ts");
const { GET, PATCH } = await import("../app/api/intake/[id]/route.ts");
const { UploadStorageError } = await import("@/src/lib/intake/uploads");
const database = new PGlite();
const db = drizzle(database);

before(async () => {
  await migrate(db, { migrationsFolder: fileURLToPath(new URL("../src/db/migrations/", import.meta.url)) });
});
after(async () => { await database.close(); });
beforeEach(async () => {
  await database.exec("TRUNCATE assets, intake_jobs, intake_submissions, organizations CASCADE");
  globalThis.__intakeDb = db;
  globalThis.__intakeDbError = null;
  globalThis.__intakeSession = null;
  globalThis.__intakeUploadError = null;
  globalThis.__intakeUploadCalls = 0;
  globalThis.__intakeRolledBack = [];
});

function jsonRequest(body, method = "POST") {
  return new Request("http://localhost/api/intake", { method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
}

test("real POST transaction stores legacy intake and returns a receipt without organization PII", async () => {
  const response = await POST(jsonRequest({ projectName: "Website", clientName: "Maria", clientEmail: "maria@example.org" }));
  assert.equal(response.status, 201);
  const result = await response.json();
  assert.match(result.data.submission.referenceNo, /^INT-\d{8}-[A-F0-9]{6}$/);
  assert.equal(result.data.organization, undefined);
  assert.equal(result.data.job.orgId, undefined);
  assert.equal((await database.query("SELECT * FROM intake_jobs")).rows.length, 1);
  assert.equal((await database.query("SELECT * FROM intake_submissions")).rows[0].client_name, "Maria");
});

test("detailed POST persists every answer and distinguishes organization from contact", async () => {
  const response = await POST(jsonRequest(intakeAnswers()));
  assert.equal(response.status, 201);
  const organization = (await database.query("SELECT * FROM organizations")).rows[0];
  assert.equal(organization.name, "Pioneer Community");
  assert.equal(organization.contact_name, "Maria Santos");
  assert.equal(organization.cause_area, null);
  const submission = (await database.query("SELECT * FROM intake_submissions")).rows[0];
  const saved = JSON.parse(submission.notes);
  assert.equal(saved.answers.visualStyle, intakeAnswers().visualStyle);
  assert.equal(saved.answers.organizationDescription, organization.mission);
  assert.equal(saved.organizationId, organization.id);
  assert.equal(saved.jobId, (await response.json()).data.job.id);
});

test("multipart POST records private attachments in both notes and job assets", async () => {
  const form = new FormData();
  form.append("payload", JSON.stringify(intakeAnswers({ hasContent: CONTENT_YES })));
  form.append("contentFiles", new File(["Approved homepage copy"], "homepage.txt", { type: "text/plain" }));
  const response = await POST(new Request("http://localhost/api/intake", { method: "POST", body: form }));
  assert.equal(response.status, 201);
  const { data } = await response.json();
  const asset = (await database.query("SELECT * FROM assets")).rows[0];
  assert.equal(asset.job_id, data.job.id);
  assert.equal(asset.file_url, `supabase://intake-private/${data.job.id}/homepage.txt`);
  const saved = JSON.parse((await database.query("SELECT notes FROM intake_submissions")).rows[0].notes);
  assert.equal(saved.attachments[0].originalName, "homepage.txt");
});

test("server validation fails before uploads or database writes", async () => {
  const response = await POST(jsonRequest(intakeAnswers({ sensitiveDataAcknowledged: false })));
  assert.equal(response.status, 422);
  assert.ok((await response.json()).details.some(error => error.field === "sensitiveDataAcknowledged"));
  assert.equal(globalThis.__intakeUploadCalls, 0);
  assert.equal((await database.query("SELECT * FROM organizations")).rows.length, 0);
});

test("failed database transaction rolls back inserted records and uploaded files", async (t) => {
  t.mock.method(console, "error", () => {});
  globalThis.__intakeDb = { transaction: callback => db.transaction(async tx => { await callback(tx); throw new Error("simulated transaction failure"); }) };
  const form = new FormData();
  form.append("payload", JSON.stringify(intakeAnswers({ hasContent: CONTENT_YES })));
  form.append("contentFiles", new File(["copy"], "copy.txt"));
  const response = await POST(new Request("http://localhost/api/intake", { method: "POST", body: form }));
  assert.equal(response.status, 500);
  assert.equal((await database.query("SELECT * FROM intake_submissions")).rows.length, 0);
  assert.equal((await database.query("SELECT * FROM organizations")).rows.length, 0);
  assert.equal((await database.query("SELECT * FROM assets")).rows.length, 0);
  assert.equal(globalThis.__intakeRolledBack.length, 1);
});

test("missing database configuration and unavailable storage return safe errors", async (t) => {
  t.mock.method(console, "error", () => {});
  globalThis.__intakeDbError = new Error("sensitive connection configuration");
  const failedDb = await POST(jsonRequest(intakeAnswers()));
  assert.equal(failedDb.status, 500);
  assert.doesNotMatch(JSON.stringify(await failedDb.json()), /sensitive/);
  globalThis.__intakeDbError = null;
  globalThis.__intakeUploadError = new UploadStorageError("private storage configuration");
  assert.equal((await POST(jsonRequest(intakeAnswers()))).status, 503);
  assert.equal((await database.query("SELECT * FROM intake_submissions")).rows.length, 0);
});

test("GET and PATCH require reviewer/admin authorization even without proxy", async () => {
  const context = { params: Promise.resolve({ id: "bad-id" }) };
  assert.equal((await GET(new Request("http://localhost"), context)).status, 401);
  assert.equal((await PATCH(jsonRequest({ status: "approved" }, "PATCH"), context)).status, 401);
  globalThis.__intakeSession = { user: { role: "member" } };
  assert.equal((await GET(new Request("http://localhost"), context)).status, 403);
  assert.equal((await PATCH(jsonRequest({ status: "approved" }, "PATCH"), context)).status, 403);
  globalThis.__intakeSession = { user: { role: "reviewer" } };
  assert.equal((await GET(new Request("http://localhost"), context)).status, 400);
  assert.equal((await PATCH(jsonRequest({ status: "approved" }, "PATCH"), context)).status, 400);
});

test("authorized reviewers can fetch and update saved submissions", async () => {
  const created = await POST(jsonRequest(intakeAnswers()));
  const id = (await created.json()).data.submission.id;
  const context = { params: Promise.resolve({ id }) };
  globalThis.__intakeSession = { user: { role: "reviewer" } };
  assert.equal((await GET(new Request("http://localhost"), context)).status, 200);
  assert.equal((await PATCH(jsonRequest({ status: "not-a-status" }, "PATCH"), context)).status, 422);
  const updated = await PATCH(jsonRequest({ status: "approved" }, "PATCH"), context);
  assert.equal(updated.status, 200);
  assert.equal((await updated.json()).data.status, "approved");
});

test("submission lookup keeps organizations and repeated projects separate when contacts share an email", async () => {
  await POST(jsonRequest(intakeAnswers({ organizationName: "First Organization" })));
  const second = await POST(jsonRequest(intakeAnswers({ organizationName: "Second Organization" })));
  const secondData = (await second.json()).data;
  await POST(jsonRequest(intakeAnswers({ organizationName: "Second Organization" })));
  globalThis.__intakeSession = { user: { role: "reviewer" } };
  const fetched = await GET(new Request("http://localhost"), { params: Promise.resolve({ id: secondData.submission.id }) });
  const result = (await fetched.json()).data;
  assert.equal(result.organization.name, "Second Organization");
  assert.equal(result.jobs.length, 1);
  assert.equal(result.jobs[0].id, secondData.job.id);
});
