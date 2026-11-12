import assert from "node:assert/strict";
import { register } from "node:module";
import { beforeEach, test } from "node:test";
import bcrypt from "bcryptjs";

register("./helpers/typescript-loader.mjs", import.meta.url, { data: { mocks: {
  "next-auth": `data:text/javascript,${encodeURIComponent("export default function NextAuth(config) { globalThis.__authConfig = config; return { handlers: {}, auth() {}, signIn() {}, signOut() {} }; }")}`,
  "@/src/db": `data:text/javascript,${encodeURIComponent("export function getDb() { globalThis.__authDbCalls++; return globalThis.__authDb; }")}`,
} } });

globalThis.__authDbCalls = 0;
await import("../src/auth.ts");
const callsOnImport = globalThis.__authDbCalls;
const config = globalThis.__authConfig;
const authorize = config.providers[0].options.authorize;
const user = { id: "reviewer-id", email: "reviewer@example.org", name: "Reviewer", role: "reviewer", passwordHash: bcrypt.hashSync("correct-password", 4) };

test("credentials JWT configuration imports without opening a database connection", () => {
  assert.equal(callsOnImport, 0);
  assert.equal(config.adapter, undefined);
  assert.equal(config.session.strategy, "jwt");
});

beforeEach(() => {
  globalThis.__authDbCalls = 0;
  globalThis.__authDb = { query: { users: { findFirst: async () => user } } };
});

test("invalid credential types are rejected before querying the database", async () => {
  for (const credentials of [{}, { email: 1, password: "secret" }, { email: "person@example.org", password: {} }, { email: " ", password: "secret" }]) {
    assert.equal(await authorize(credentials), null);
  }
  assert.equal(globalThis.__authDbCalls, 0);
});

test("password verification returns only the authenticated user's public session fields", async () => {
  assert.equal(await authorize({ email: user.email, password: "wrong-password" }), null);
  const authenticated = await authorize({ email: " REVIEWER@EXAMPLE.ORG ", password: "correct-password" });
  assert.deepEqual(authenticated, { id: user.id, email: user.email, name: user.name, role: "reviewer" });
  globalThis.__authDb.query.users.findFirst = async () => null;
  assert.equal(await authorize({ email: user.email, password: "correct-password" }), null);
});

test("JWT sessions carry recognized roles and default unrecognized roles to member", () => {
  const token = config.callbacks.jwt({ token: {}, user });
  assert.equal(token.role, "reviewer");
  assert.equal(config.callbacks.session({ session: { user: {} }, token }).user.role, "reviewer");
  for (const role of [undefined, "unknown", {}]) {
    assert.equal(config.callbacks.session({ session: { user: {} }, token: { role } }).user.role, "member");
  }
});
