import assert from "node:assert/strict";
import test from "node:test";
import { createIntakeRequest, submitIntake, IntakeSubmissionError } from "../src/components/intake/submission.ts";
import { CONTENT_OPTIONS, CONTENT_YES, DOMAIN_OPTIONS, LOGO_OPTIONS, LOGO_UPLOAD } from "../src/components/intake/validation.ts";
import { isPublicRequest } from "../src/lib/auth/access.ts";

const answers = {
  organizationName: "BUILD UMass", primaryContactEmail: "hello@example.org",
  hasLogo: LOGO_OPTIONS[1], logoFile: null,
  hasContent: CONTENT_OPTIONS[2], existingContent: "Old hidden text", contentFiles: [],
  hasDomain: DOMAIN_OPTIONS[1], domainName: "old.example.org",
};

test("anonymous access permits submission without exposing individual intake records", () => {
  assert.equal(isPublicRequest("/intake", "GET"), true);
  assert.equal(isPublicRequest("/api/intake", "POST"), true);
  for (const method of ["GET", "PATCH", "DELETE"]) {
    assert.equal(isPublicRequest("/api/intake", method), false);
  }
  assert.equal(isPublicRequest("/api/intake/abc", "GET"), false);
  assert.equal(isPublicRequest("/api/intake/abc", "POST"), false);
  assert.equal(isPublicRequest("/intake-admin", "GET"), false);
  assert.equal(isPublicRequest("/dashboard", "GET"), false);
});

test("multipart payload retains active attachments and omits hidden content and domain answers", () => {
  const logo = new File(["<svg/>"], "logo.svg", { type: "image/svg+xml" });
  const doc = new File(["Content"], "copy.txt", { type: "text/plain" });
  const inactive = createIntakeRequest({ ...answers, logoFile: logo, contentFiles: [doc] });
  const payload = JSON.parse(inactive.get("payload"));
  assert.equal(payload.organizationName, "BUILD UMass");
  assert.equal(payload.existingContent, "");
  assert.equal(payload.domainName, "");
  assert.equal("logoFile" in payload, false);
  assert.equal(inactive.has("logoFile"), false);
  assert.equal(inactive.has("contentFiles"), false);
  const active = createIntakeRequest({ ...answers, hasLogo: LOGO_UPLOAD, logoFile: logo, hasContent: CONTENT_YES, contentFiles: [doc] });
  assert.equal(active.get("logoFile").name, "logo.svg");
  assert.equal(active.getAll("contentFiles")[0].name, "copy.txt");
});

test("only a persisted server receipt produces success", async () => {
  const reference = await submitIntake(answers, async (url, request) => {
    assert.equal(url, "/api/intake");
    assert.equal(request.method, "POST");
    assert.ok(request.body instanceof FormData);
    assert.equal(request.headers["Content-Type"], undefined);
    return Response.json({ success: true, data: { submission: { referenceNo: "INT-20261017-ABC123" } } }, { status: 201 });
  });
  assert.equal(reference, "INT-20261017-ABC123");
  for (const response of [
    Response.json({ success: true, data: {} }),
    new Response("<html>Login</html>"),
    Response.json({ success: false }, { status: 500 }),
  ]) {
    await assert.rejects(submitIntake(answers, async () => response), IntakeSubmissionError);
  }
});

test("server field errors and network failures remain recoverable", async () => {
  await assert.rejects(submitIntake(answers, async () => Response.json({
    success: false, details: [{ field: "contentFiles", message: "Unsupported file contents." }],
  }, { status: 422 })), (error) => {
    assert.equal(error.fields.contentFiles, "Unsupported file contents.");
    return true;
  });
  await assert.rejects(submitIntake(answers, async () => { throw new Error("Offline"); }), /connection/);
  await assert.rejects(submitIntake(answers, async () => new Response(null, { status: 413 })), /too large/);
});
