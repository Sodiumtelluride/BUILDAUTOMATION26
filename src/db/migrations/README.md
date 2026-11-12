# Database migrations

`src/db/schema` is the authoritative schema. Drizzle applies only migrations
listed in `meta/_journal.json`, in order. Keep existing registered migrations and
their snapshots unchanged after they have been applied.

From the repository root, configure `DATABASE_URL` for the intended PostgreSQL
database, then run:

```sh
npm run db:migrate
```

After changing a schema, generate and review the next migration before applying
it:

```sh
npm run db:generate
```

The baseline migration (`0000_init`) creates the core, auth and intake tables.
Later migrations are layered on top of it. The old unregistered drafts are
archived in `legacy/` and must not be applied.

Every migration must have a unique `idx` in `meta/_journal.json`, with a
matching `meta/<idx>_snapshot.json`.
