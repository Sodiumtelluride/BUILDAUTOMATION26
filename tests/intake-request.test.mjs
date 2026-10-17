import assert from "node:assert/strict";
import { test } from "node:test";
import { IntakeRequestError, MAX_INTAKE_JSON_BYTES, parseIntakeRequest } from "../src/lib/intake/request.ts";
import { MAX_INTAKE_REQUEST_BYTES } from "../src/lib/intake/uploads.ts";

function request(body, headers = {}) {
  return new Request("http://localhost/api/intake", { method: "POST", body, headers });
}

test("parses legacy JSON and rejects malformed JSON or unsupported types", async () => {
  assert.deepEqual((await parseIntakeRequest(request('{"name":"value"}', { "content-type": "application/json" }))).body, { name: "value" });
  await assert.rejects(() => parseIntakeRequest(request("{", { "content-type": "application/json" })), /Invalid JSON/);
  await assert.rejects(() => parseIntakeRequest(request("text", { "content-type": "text/plain" })), (error) => error instanceof IntakeRequestError && error.status === 415);
});

test("parses real multipart files separately from the JSON payload", async () => {
  const form = new FormData();
  form.append("payload", JSON.stringify({ organizationName: "BUILD" }));
  form.append("contentFiles", new File(["hello"], "copy.txt", { type: "text/plain" }));
  const parsed = await parseIntakeRequest(request(form));
  assert.deepEqual(parsed.body, { organizationName: "BUILD" });
  assert.equal(parsed.files.content[0].name, "copy.txt");
  assert.equal(await parsed.files.content[0].text(), "hello");
});

test("rejects repeated payload, text pretending to be files, and unknown multipart fields", async () => {
  for (const [field, value] of [["payload", "{}"], ["logoFile", "fake-file"], ["unknown", "value"]]) {
    const form = new FormData();
    form.append("payload", "{}");
    form.append(field, value);
    await assert.rejects(() => parseIntakeRequest(request(form)), IntakeRequestError);
  }
});

test("limits JSON by actual stream length even with a missing or false Content-Length", async () => {
  for (const headers of [{}, { "content-length": "1" }]) {
    await assert.rejects(() => parseIntakeRequest(request("x".repeat(MAX_INTAKE_JSON_BYTES + 1), { "content-type": "application/json", ...headers })), (error) => error.status === 413);
  }
});

test("rejects declared oversized multipart data before allocating file bytes", async () => {
  await assert.rejects(() => parseIntakeRequest(request("small", { "content-type": "multipart/form-data; boundary=test", "content-length": String(MAX_INTAKE_REQUEST_BYTES + 1) })), (error) => error.status === 413);
});
