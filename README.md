# BUILD Automation

Next.js application for collecting website project briefs for BUILD UMass. The public intake form is at `/intake`; the home page links to it.

Inter is bundled locally under `app/fonts` with its SIL Open Font License, so builds do not download fonts from Google.

## Local setup

Use Node.js 20.9 or newer and npm. On Windows PowerShell, use `npm.cmd` if your execution policy blocks `npm.ps1`.

```sh
npm ci
```

Copy `.env.example` to `.env.local`, set `DATABASE_URL` to a development PostgreSQL database, and generate a unique `AUTH_SECRET`. Next.js and Drizzle load `.env.local` automatically.

```sh
npm run db:migrate
npm run dev
```

Open <http://localhost:3000>. Public pages render without database credentials, but saving a submission requires the configured, migrated database. Authentication uses existing users with bcrypt password hashes and JWT sessions; signup/account provisioning is outside this intake feature.

## File uploads

To accept attachments, configure `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `INTAKE_UPLOAD_BUCKET` on the server. Create the bucket in Supabase Storage in advance and leave it **private**. The service key must never use a `NEXT_PUBLIC_` variable or appear in frontend code.

Allow a per-file size of at least 10 MiB and these MIME types in the bucket:

- Logos: `image/png`, `image/jpeg`, `image/svg+xml` (one file).
- Content: `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `text/plain` (up to five files).

The app enforces 10 MiB per file and 61 MiB per multipart request. Configure hosting/reverse-proxy body limits accordingly; a host with a lower limit will reject larger uploads. Text and SVG must use UTF-8. File extensions, sizes, counts, and format signatures are validated on the server. Originals remain private; reviewers/downstream services must use authenticated downloads or short-lived signed URLs, and must never inline untrusted SVG. Public file URLs are not created.

Without storage settings, submissions without attachments work normally. A submission with attachments fails clearly if storage is unavailable. Failed uploads and failed database transactions trigger object cleanup; cleanup failures are logged for operator recovery.

## Submission behavior

`POST /api/intake` accepts multipart data containing one `payload` JSON field, an optional `logoFile`, and repeated optional `contentFiles`. The browser and server share the detailed intake validation contract. The API also accepts the earlier JSON payload (`projectName`, `clientName`, `clientEmail`, and optional legacy fields).

Successful requests atomically create the submission and queued job, associate the organization, and save all detailed answers as a versioned JSON brief in `intake_submissions.notes`. Attachment metadata is included in that brief and linked to the job in `assets` using private `supabase://bucket/path` references. The API returns a saved reference number; the UI displays success only after receiving it. Failed requests preserve the user's current answers for correction/retry. Answers stay in memory until submission; drafts are not saved across reloads.

Anonymous access is limited to submission. Reading or updating `/api/intake/[id]` requires a signed-in `admin` or `reviewer`; other members receive 403. Receipt responses omit organization/contact records. Confirmation emails and execution of the queued automation pipeline are not implemented by this feature; the Python pipeline contracts are under `agent/`.

## Verification and migrations

```sh
npm run check
npm run db:check
```

`check` runs lint, TypeScript, Node tests, and a production build. Tests cover validation, request size limits, multipart parsing, submission receipts/errors, authorization, private uploads/cleanup, route persistence, and database migrations. Migration tests use an isolated in-memory PostgreSQL-compatible PGlite database; tests do not need real database or storage credentials. CI installs the lockfile with `npm ci` and runs these checks.

```sh
npm run db:generate   # Generate a migration after changing the TypeScript schema
npm run db:migrate    # Apply registered migrations to DATABASE_URL
```

The authoritative schema is `src/db/schema`; the registered migration journal is `src/db/migrations/meta/_journal.json`. Historical unregistered drafts are preserved in `src/db/migrations/legacy` for context and must not be applied. The complete intake/auth migration repairs the registered baseline, preserves existing organization records, and normalizes legacy null roles to `member`. A database previously created from an unregistered draft needs reconciliation before using the registered migration chain.

Before deployment, configure runtime database/auth/storage values and apply the registered migrations to the intended database. `npm run build` only builds the application; the existing Deploy workflow does not provision hosting, apply migrations, send emails, or start the Python pipeline.
