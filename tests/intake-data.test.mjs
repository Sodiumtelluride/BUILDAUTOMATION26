// Checks how the admin console reads saved intake forms: parsing the saved JSON,
// laying answers out by form section, and the list/detail reads (using a fake database).
import assert from "node:assert/strict";
import { register } from "node:module";
import { beforeEach, test } from "node:test";

// Swap the real database for a fake one that each test controls through globalThis.__fakeDb
register("./helpers/typescript-loader.mjs", import.meta.url, { data: { mocks: {
  "@/src/db": `data:text/javascript,${encodeURIComponent("export function getDb() { globalThis.__dbCalls++; return globalThis.__fakeDb; }")}`,
} } });

const { intakeAnswers } = await import("./helpers/intake-fixture.mjs");
const { answerGroups, getIntake, listIntakes, parseIntakeNotes } = await import("../src/lib/intake-data.ts");

const SUBMISSION_ID = "3f2b8c1e-7a4d-4e5f-9b6a-1c2d3e4f5a6b";
const LOGO = { category: "logo", originalName: "logo.png", size: 2048, contentType: "image/png", bucket: "intake-uploads", path: "jobs/1/logo.png" };

/** The notes JSON exactly as the intake API saves it (see app/api/intake/route.ts). */
function savedNotes(overrides = {}) {
  return JSON.stringify({ version: 1, answers: intakeAnswers(), attachments: [LOGO], organizationId: "org-1", jobId: "job-1", ...overrides });
}

/** A stand-in database: any chain of query calls (select, from, where, ...) resolves to `rows`. */
function fakeDb(rows) {
  const query = {
    select: () => query,
    from: () => query,
    where: () => query,
    orderBy: () => query,
    limit: () => query,
    then: (resolve, reject) => Promise.resolve(rows).then(resolve, reject),
  };
  return query;
}

beforeEach(() => {
  globalThis.__dbCalls = 0;
  globalThis.__fakeDb = fakeDb([]);
});

// ---------- Reading the saved JSON ----------

test("reads the answers and attachments the intake API saves", () => {
  const parsed = parseIntakeNotes(savedNotes());
  assert.deepEqual(parsed.answers, intakeAnswers());
  assert.deepEqual(parsed.attachments, [LOGO]);
});

test("a submission without an attachments list gets an empty list", () => {
  assert.deepEqual(parseIntakeNotes(savedNotes({ attachments: undefined })).attachments, []);
});

test("older, empty, or broken notes return null instead of crashing the page", () => {
  const notJson = ["{not json", "plain text notes from the old form"];
  const wrongShape = [JSON.stringify({ version: 2, answers: {} }), JSON.stringify({ version: 1 }), JSON.stringify({ version: 1, answers: null })];
  for (const notes of [null, "", ...notJson, ...wrongShape]) {
    assert.equal(parseIntakeNotes(notes), null, `expected null for ${JSON.stringify(notes)}`);
  }
});

// ---------- Laying answers out on the detail page ----------

test("answers are grouped in the same order as the intake form", () => {
  assert.deepEqual(
    answerGroups(intakeAnswers()).map((group) => group.title),
    ["Organization & Contact", "Project Goals", "Design & Branding", "Content", "Technical Details", "Additional Information"],
  );
});

test("list answers are joined into one line and blank entries are dropped", () => {
  const rows = Object.fromEntries(answerGroups(intakeAnswers()).flatMap((group) => group.rows));
  assert.equal(rows.Pages, "Home, About, Contact");
  assert.equal(rows.References, "example.org"); // the fixture has ["example.org", "", ""]
});

test("every question on the intake form is shown on the detail page", () => {
  // Give each answer a unique marker, then make sure every marker appears on the page.
  // If someone adds a question to the form (and the fixture), this fails until the console shows it too.
  const marked = Object.fromEntries(
    Object.entries(intakeAnswers())
      .filter(([key]) => key !== "sensitiveDataAcknowledged") // a required checkbox, not an answer
      .map(([key, value]) => [key, Array.isArray(value) ? [`<${key}>`] : `<${key}>`]),
  );
  const shown = answerGroups(marked).flatMap((group) => group.rows.map(([, value]) => value));
  for (const key of Object.keys(marked)) {
    assert.ok(shown.includes(`<${key}>`), `"${key}" is saved by the form but not shown on the intake page`);
  }
});

// ---------- Database reads (fake database) ----------

test("the intakes list adds the organization name and never returns the raw saved JSON", async () => {
  globalThis.__fakeDb = fakeDb([
    { id: "a", referenceNo: "INT-1", clientName: "Maria Santos", notes: savedNotes() },
    { id: "b", referenceNo: "TEST-001", clientName: null, notes: null }, // older submission without JSON
  ]);
  const intakes = await listIntakes();
  assert.equal(intakes[0].organization, "Pioneer Community");
  assert.equal(intakes[1].organization, null);
  assert.ok(intakes.every((intake) => !("notes" in intake)));
});

test("a malformed submission id is rejected without querying the database", async () => {
  assert.equal(await getIntake("not-a-real-id"), null);
  assert.equal(globalThis.__dbCalls, 0);
});

test("a missing submission returns null, and a found one includes its parsed answers", async () => {
  assert.equal(await getIntake(SUBMISSION_ID), null);

  globalThis.__fakeDb = fakeDb([{ id: SUBMISSION_ID, referenceNo: "INT-1", notes: savedNotes() }]);
  const intake = await getIntake(SUBMISSION_ID);
  assert.equal(intake.details.answers.organizationName, "Pioneer Community");
  assert.deepEqual(intake.details.attachments, [LOGO]);
});
