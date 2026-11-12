// Checks that admin console pages stay behind sign-in, public pages stay public,
// and signed-out users are sent to our own /login page.
import assert from "node:assert/strict";
import { register } from "node:module";
import { test } from "node:test";

// Fake next-auth and database, so importing the app's code never touches a real service
register("./helpers/typescript-loader.mjs", import.meta.url, { data: { mocks: {
  "next-auth": `data:text/javascript,${encodeURIComponent("export default function NextAuth(config) { globalThis.__authConfig = config; return { handlers: {}, auth() {}, signIn() {}, signOut() {} }; }")}`,
  "@/src/db": `data:text/javascript,${encodeURIComponent("export function getDb() { throw new Error('tests must not use the real database'); }")}`,
} } });

const { isPublicRequest } = await import("../src/lib/auth/access.ts");
await import("../src/auth.ts");
const { REVIEW_ROLES } = await import("../src/lib/intake-data.ts");

const SUBMISSION_ID = "3f2b8c1e-7a4d-4e5f-9b6a-1c2d3e4f5a6b";

test("admin console pages require sign-in", () => {
  for (const path of ["/dashboard", "/factory", "/intakes", `/intakes/${SUBMISSION_ID}`]) {
    assert.equal(isPublicRequest(path, "GET"), false, `${path} should require sign-in`);
  }
});

test("the public /intake form does not make the private /intakes pages public", () => {
  // "/intake" (public form) is one letter away from "/intakes" (private submissions)
  assert.equal(isPublicRequest("/intake", "GET"), true);
  assert.equal(isPublicRequest("/intakes", "GET"), false);
  assert.equal(isPublicRequest(`/intakes/${SUBMISSION_ID}`, "GET"), false);
});

test("homepage, sign-in page, and intake form stay public", () => {
  for (const path of ["/", "/login", "/intake"]) {
    assert.equal(isPublicRequest(path, "GET"), true, `${path} should be public`);
  }
});

test("anyone can submit an intake form, but reading submissions requires sign-in", () => {
  assert.equal(isPublicRequest("/api/intake", "POST"), true);
  assert.equal(isPublicRequest("/api/intake", "GET"), false);
  assert.equal(isPublicRequest(`/api/intake/${SUBMISSION_ID}`, "GET"), false);
});

test("signed-out users are sent to our /login page, not the built-in Auth.js page", () => {
  assert.equal(globalThis.__authConfig.pages?.signIn, "/login");
});

test("only admins and reviewers can view intake forms", () => {
  assert.deepEqual([...REVIEW_ROLES].sort(), ["admin", "reviewer"]);
  assert.equal(REVIEW_ROLES.includes("member"), false);
});
