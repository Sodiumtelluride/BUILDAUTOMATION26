import assert from "node:assert/strict";
import { mkdtemp, readFile, mkdir, copyFile, writeFile, realpath, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { PGlite } from "@electric-sql/pglite";
import { drizzle } from "drizzle-orm/pglite";
import { migrate } from "drizzle-orm/pglite/migrator";

const migrationsFolder = fileURLToPath(new URL("../src/db/migrations/", import.meta.url));
const journal = JSON.parse(await readFile(path.join(migrationsFolder, "meta/_journal.json"), "utf8"));
const lastIndex = String(journal.entries.at(-1).idx).padStart(4, "0");
const snapshot = JSON.parse(await readFile(path.join(migrationsFolder, `meta/${lastIndex}_snapshot.json`), "utf8"));

async function verifySchema(database) {
  const { rows: columns } = await database.query(
    "SELECT table_name, column_name, is_nullable, data_type FROM information_schema.columns WHERE table_schema = 'public'",
  );
  assert.deepEqual(
    [...new Set(columns.map((column) => column.table_name))].sort(),
    Object.values(snapshot.tables).map((table) => table.name).sort(),
  );
  for (const table of Object.values(snapshot.tables)) {
    const actualColumns = columns.filter((column) => column.table_name === table.name);
    assert.deepEqual(actualColumns.map((column) => column.column_name).sort(), Object.keys(table.columns).sort());
    for (const column of Object.values(table.columns)) {
      const actual = actualColumns.find((item) => item.column_name === column.name);
      assert.equal(actual.is_nullable, column.notNull ? "NO" : "YES", `${table.name}.${column.name} nullability`);
    }
  }
  const { rows: migrations } = await database.query("SELECT * FROM drizzle.__drizzle_migrations ORDER BY created_at");
  assert.equal(migrations.length, journal.entries.length);
}

test("registered migrations create a working intake/auth schema and can be rerun", async () => {
  const database = new PGlite();
  try {
    const db = drizzle(database);
    await migrate(db, { migrationsFolder });
    await verifySchema(database);

    const { rows: [organization] } = await database.query(
      "INSERT INTO organizations (name, contact_email) VALUES ('Example Nonprofit', 'lead@example.org') RETURNING id",
    );
    const { rows: [job] } = await database.query(
      "INSERT INTO intake_jobs (org_id) VALUES ($1) RETURNING id",
      [organization.id],
    );
    assert.ok(job.id);
    const notes = JSON.stringify({
      organizationName: "Example Nonprofit",
      pages: ["Home", "About"],
      additionalInfo: "Multilingual: español",
    });
    const { rows: [submission] } = await database.query(
      "INSERT INTO intake_submissions (reference_no, project_name, client_name, client_email, notes, status, email_sent) VALUES ('INT-TEST-ABCDEF', 'Example website', 'Project Lead', 'lead@example.org', $1, 'pending', false) RETURNING id, notes",
      [notes],
    );
    assert.ok(submission.id);
    assert.equal(submission.notes, notes);

    const { rows: [user] } = await database.query(
      "INSERT INTO users (email, password_hash) VALUES ('admin@example.org', 'test-hash') RETURNING id",
    );
    await database.query(
      "INSERT INTO accounts (user_id, type, provider, provider_account_id) VALUES ($1, 'oauth', 'test', 'account-1')",
      [user.id],
    );
    await database.query(
      "INSERT INTO sessions (session_token, user_id, expires) VALUES ('session-1', $1, NOW() + INTERVAL '1 hour')",
      [user.id],
    );
    await database.query("DELETE FROM users WHERE id = $1", [user.id]);
    assert.equal((await database.query("SELECT * FROM accounts")).rows.length, 0);
    assert.equal((await database.query("SELECT * FROM sessions")).rows.length, 0);

    await migrate(db, { migrationsFolder });
    await verifySchema(database);
    assert.equal((await database.query("SELECT * FROM intake_submissions")).rows.length, 1);
  } finally {
    await database.close();
  }
});

test("upgrading the registered baseline preserves data and safely normalizes users", async () => {
  const baselineFolder = await mkdtemp(path.join(tmpdir(), "build-intake-migration-"));
  const database = new PGlite();
  try {
    const baseline = journal.entries[0];
    await mkdir(path.join(baselineFolder, "meta"));
    await writeFile(path.join(baselineFolder, "meta/_journal.json"), JSON.stringify({ ...journal, entries: [baseline] }));
    await copyFile(path.join(migrationsFolder, `${baseline.tag}.sql`), path.join(baselineFolder, `${baseline.tag}.sql`));
    const db = drizzle(database);
    await migrate(db, { migrationsFolder: baselineFolder });
    await database.query(
      "INSERT INTO users (email, role, email_verified) VALUES ('existing@example.org', NULL, '2026-04-01 15:30:00')",
    );
    await database.query(
      "INSERT INTO organizations (name, contact_email) VALUES ('Existing organization', 'old@example.org')",
    );
    await database.query("SET TIME ZONE 'America/New_York'");

    await migrate(db, { migrationsFolder });
    await verifySchema(database);
    const { rows: [user] } = await database.query("SELECT role, email_verified FROM users");
    assert.equal(user.role, "member");
    assert.equal(user.email_verified.toISOString(), "2026-04-01T15:30:00.000Z");
    assert.equal((await database.query("SELECT name FROM organizations")).rows[0].name, "Existing organization");
  } finally {
    await database.close();
    const resolvedBaseline = await realpath(baselineFolder);
    assert.equal(path.dirname(resolvedBaseline), await realpath(tmpdir()));
    assert.ok(path.basename(resolvedBaseline).startsWith("build-intake-migration-"));
    await rm(resolvedBaseline, { recursive: true, force: true });
  }
});
