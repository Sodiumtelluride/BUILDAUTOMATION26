import assert from "node:assert/strict";
import { test } from "node:test";
import { CONTENT_YES, DOMAIN_OWNED, LOGO_UPLOAD, validateSection } from "../src/lib/intake/contract.ts";
import { validateIntakeBody } from "../src/lib/validation/intake.ts";
import { intakeAnswers } from "./helpers/intake-fixture.mjs";

test("legacy JSON remains supported and normalizes contact details", () => {
  const { data, errors } = validateIntakeBody({ projectName: " Site ", clientName: " Person ", clientEmail: " PERSON@Example.org ", notes: " Details " });
  assert.equal(errors.length, 0);
  assert.equal(data.clientEmail, "person@example.org");
  assert.equal(data.notes, "Details");
});

test("invalid JSON shapes and unbounded legacy input are rejected", () => {
  for (const input of [null, [], "text", { projectName: "x", clientName: "x", clientEmail: "not-email", notes: "x".repeat(20001) }]) {
    assert.equal(validateIntakeBody(input).data, null);
  }
});

test("detailed answers preserve organization and contact as distinct fields", () => {
  const result = validateIntakeBody(intakeAnswers({ primaryContactEmail: " MARIA@Example.org " }));
  assert.deepEqual(result.errors, []);
  assert.equal(result.data.organizationName, "Pioneer Community");
  assert.equal(result.data.clientName, "Maria Santos");
  assert.equal(result.data.clientEmail, "maria@example.org");
  assert.equal(result.data.answers.targetAudience, intakeAnswers().targetAudience);
});

test("server enforces acknowledgement, value types, enum choices, lengths, and arrays", () => {
  for (const overrides of [
    { sensitiveDataAcknowledged: "true" }, { organizationType: "unknown" },
    { primaryGoal: "unknown" }, { features: ["malicious-option"] },
    { pages: [] }, { pages: {} }, { targetAudience: 100 },
    { brandColors: "x".repeat(201) }, { brandFonts: "x".repeat(201) },
    { toneAndVoice: ["Friendly", "Casual", "Playful", "Professional"] },
    { referenceWebsites: ["one.org", "two.org", "three.org", "four.org"] },
    { primaryContactEmail: `${"a".repeat(245)}@example.org` },
  ]) {
    assert.equal(validateIntakeBody(intakeAnswers(overrides)).data, null, JSON.stringify(overrides));
  }
});

test("active content accepts pasted text or uploaded files and bounds both", () => {
  const file = new File(["content"], "copy.txt", { type: "text/plain" });
  const body = intakeAnswers({ hasContent: CONTENT_YES });
  assert.equal(validateIntakeBody(body).data, null);
  assert.ok(validateIntakeBody({ ...body, existingContent: "Useful content" }).data);
  assert.ok(validateIntakeBody(body, { logo: [], content: [file] }).data);
  assert.equal(validateIntakeBody({ ...body, existingContent: "x".repeat(5001) }, { logo: [], content: [file] }).data, null);
  assert.equal(validateIntakeBody(body, { logo: [], content: Array(6).fill(file) }).data, null);
});

test("logo requirements and file types cannot be bypassed by JSON metadata", () => {
  assert.equal(validateIntakeBody(intakeAnswers({ hasLogo: LOGO_UPLOAD })).data, null);
  assert.equal(validateIntakeBody(intakeAnswers({ logoFile: { name: "fake.png", size: 1 } })).data, null);
  const invalid = new File(["binary"], "script.exe");
  const result = validateIntakeBody(intakeAnswers({ hasLogo: LOGO_UPLOAD }), { logo: [invalid], content: [] });
  assert.ok(result.errors.some((error) => error.field === "logoFile"));
});

test("inactive conditional values and files are removed before persistence", () => {
  const file = new File(["stale"], "copy.txt");
  const result = validateIntakeBody(intakeAnswers({ domainName: "old.example.org", existingContent: "old text" }), { logo: [file], content: [file] });
  assert.deepEqual(result.errors, []);
  assert.equal(result.data.answers.domainName, "");
  assert.equal(result.data.answers.existingContent, "");
  assert.deepEqual(result.files, { logo: [], content: [] });
});

test("domain and reference website validation handles bad labels and URL schemes", () => {
  for (const domain of ["-bad.example.org", "bad-.example.org", "www.example.org", "https://example.org", "example.org/path"]) {
    assert.equal(validateIntakeBody(intakeAnswers({ hasDomain: DOMAIN_OWNED, domainName: domain })).data, null, domain);
  }
  for (const website of ["javascript:alert(1)", "https://user:pass@example.org", "https://bad-.example.org", "https://example.org:99999"]) {
    assert.equal(validateIntakeBody(intakeAnswers({ referenceWebsites: [website] })).data, null, website);
  }
  assert.ok(validateIntakeBody(intakeAnswers({ referenceWebsites: ["https://example.org?project=build#about"] })).data);
});

test("shared client section validation catches empty uploads", () => {
  const empty = new File([], "copy.txt");
  const form = { ...intakeAnswers({ hasContent: CONTENT_YES }), logoFile: null, contentFiles: [empty] };
  assert.match(validateSection(3, form).contentFiles, /empty/);
});
