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

## Manual test: submit the intake form end to end

Use this to confirm that a submission made in the browser is saved to the database. It takes about 20 minutes the first time. Uploads are skipped; see [File uploads](#file-uploads) to test those.

### 1. Use your own test database

Do **not** point `DATABASE_URL` at a shared team or production database: step 3 applies migrations to whatever database it names.

Create a free personal project at [neon.tech](https://neon.tech) (any PostgreSQL 15+ database works) and copy its connection string. It starts with `postgresql://`.

### 2. Configure the app

From the repository root:

```sh
cp .env.example .env.local
openssl rand -base64 32
```

In `.env.local`:

- `DATABASE_URL`: your connection string from step 1.
- `AUTH_SECRET`: the random text printed by `openssl`.
- Leave the three `SUPABASE_*` values blank.

`.env.local` is git-ignored, so the database password is never committed.

### 3. Install, migrate and start

```sh
npm ci
npm run db:migrate
npm run dev
```

`npm run dev` keeps running; leave that terminal open.

### 4. Submit the form

Open <http://localhost:3000/intake>. Optionally open the browser's DevTools (F12), go to the **Network** tab, and keep it open while you submit.

Fill in each step. These answers pass validation and avoid any file upload:

| Step | Field | Value |
|---|---|---|
| 1 | Sensitive-data acknowledgement | Checked |
| 1 | Organization name / contact name | `Test Org` / `Test Person` |
| 1 | Contact email | `test@example.org` |
| 1 | Organization type | `Nonprofit` |
| 2 | Primary goal | `Attract new members` |
| 2 | Organization description (50+ characters) | `A test nonprofit used to check that intake submissions are saved correctly.` |
| 2 | Target audience (30+ characters) | `Local families and volunteers in our area.` |
| 2 | Pages | Select at least one |
| 3 | Logo | `No — please create a simple text-based logo` |
| 3 | Visual style (30+ characters) | `Clean, warm and friendly with plenty of white space.` |
| 4 | Existing content | `No — please generate it from my description` |
| 4 | Tone | Select one or two |
| 5 | Domain | `No — a BUILD subdomain is fine for now` |

Everything else can stay blank. Submit on the last step.

**Expected:** the page shows a success message with a **reference number**. The form only shows success after the API confirms the save, so a missing reference number means it was not saved. In the Network tab, `POST /api/intake` returns a success status with the same reference number.

### 5. Confirm the row in the database

In your database's SQL editor (Neon: **SQL Editor**), run:

```sql
select reference_no, project_name, client_email, status, created_at
from intake_submissions
order by created_at desc
limit 1;
```

**Expected:** one row with the reference number from step 4. The full set of answers is stored as versioned JSON in the `notes` column, and a matching job is created in `intake_jobs` with status `queued`:

```sql
select id, status, created_at
from intake_jobs
order by created_at desc
limit 1;
```

### Troubleshooting

| Symptom | Likely cause |
|---|---|
| `npm ci` fails or warns about the engine | Node is older than 20.9. Check with `node -v`. |
| `npm run db:migrate` fails to connect | `DATABASE_URL` is wrong or missing `?sslmode=require` (Neon needs it). |
| The form submits but shows an error instead of a reference number | The database isn't migrated, or `DATABASE_URL` points at a different database. Rerun `npm run db:migrate`. |
| A submission with an attached file fails | Expected without storage settings; see [File uploads](#file-uploads). |

Stop the app with `Ctrl + C` when you're done.

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
