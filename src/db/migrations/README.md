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

The first migration creates the core tables. The next migration completes the
auth and intake tables and aligns the `users` columns with the current schema.
The old unregistered drafts are archived in `legacy/` and must not be applied.

The `users.email_verified` timestamp conversion interprets historical timestamp
values as UTC so the result does not depend on the migrating session's timezone.
Existing users with a null role receive the default `member` role before the
not-null constraint is added.
