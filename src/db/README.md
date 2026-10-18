# Database schema

> **Keep this up to date:** update this diagram whenever the schema in `src/db/schema/` changes.

Source of truth is the Drizzle schema in [`schema/`](./schema). Migrations live in [`migrations/`](./migrations).

## Entity relationship diagram

OAuth token columns on `accounts` (`refresh_token`, `access_token`, `expires_at`, `token_type`, `scope`, `id_token`, `session_state`) are left out to keep the diagram readable.

```mermaid
erDiagram
    organizations ||--o{ intake_jobs : "org_id"
    intake_jobs ||--o{ job_stages : "job_id"
    intake_jobs ||--o{ cost_logs : "job_id"
    intake_jobs ||--o{ assets : "job_id"
    intake_jobs ||--o{ reviewer_actions : "job_id"
    intake_jobs ||--o| deployments : "job_id (unique)"
    users ||--o{ reviewer_actions : "reviewer_id"
    users |o--o{ deployments : "deployed_by"
    users ||--o{ accounts : "user_id"
    users ||--o{ sessions : "user_id"

    organizations {
        uuid id PK
        text name
        text mission
        text contact_email
        text contact_name
        text cause_area
        organization_status status
        timestamp created_at
        timestamp updated_at
    }

    intake_jobs {
        uuid id PK
        uuid org_id FK
        intake_job_status status
        text current_stage
        text preview_url
        text live_url
        timestamp created_at
        timestamp updated_at
    }

    job_stages {
        uuid id PK
        uuid job_id FK "unique (job_id, stage, attempt)"
        pipeline_stage stage
        job_stage_status status
        int attempt "default 1"
        int iteration_count
        timestamp started_at
        timestamp completed_at
        text error_message
    }

    cost_logs {
        uuid id PK
        uuid job_id FK
        pipeline_stage stage
        text model
        int input_tokens
        int output_tokens
        numeric estimated_cost
        timestamp created_at
    }

    assets {
        uuid id PK
        uuid job_id FK
        text file_name
        text file_type
        text file_url
        timestamp created_at
    }

    reviewer_actions {
        uuid id PK
        uuid job_id FK
        uuid reviewer_id FK
        reviewer_action action
        text feedback
        timestamp created_at
    }

    deployments {
        uuid id PK
        uuid job_id FK, UK
        text live_url
        timestamp deployed_at
        uuid deployed_by FK "nullable"
        numeric total_cost
    }

    users {
        uuid id PK
        text name
        text email UK
        timestamp email_verified
        text image
        user_role role "default member"
        text password_hash
        timestamp created_at
        timestamp updated_at
    }

    accounts {
        text provider PK
        text provider_account_id PK
        uuid user_id FK
        text type
    }

    sessions {
        text session_token PK
        uuid user_id FK
        timestamp expires
    }

    verification_tokens {
        text identifier PK
        text token PK
        timestamp expires
    }

    intake_submissions {
        uuid id PK
        text reference_no
        text project_name
        text client_name
        text client_email
        text budget
        text features
        text team_size
        text start_date
        text notes
        text status
        boolean email_sent
        timestamp created_at
    }
```

`intake_submissions` and `verification_tokens` have no foreign keys.

## View: `project_metrics`

Mermaid ER diagrams can't draw views, so it's described here. Defined in [`schema/project-metrics.ts`](./schema/project-metrics.ts). One row per intake job, used by the App Factory dashboard cards.

**Reads from:**

| Table | Columns |
| --- | --- |
| `intake_jobs` | `id`, `org_id`, `status`, `created_at`, `updated_at` |
| `organizations` | `id`, `name` |
| `job_stages` | `job_id`, `stage`, `status`, `attempt`, `iteration_count`, `started_at` (only rows where `started_at` is set) |
| `cost_logs` | `job_id`, `input_tokens`, `output_tokens`, `estimated_cost` |
| `pipeline_stage` enum | value order (for stage comparison) and value count (denominator of `percent_done`) |

**Returns:** `job_id`, `org_id`, `org_name`, `status`, `current_stage`, `stages_completed`, `percent_done`, `agents_used`, `rerun_count`, `max_iteration_count`, `input_tokens`, `output_tokens`, `total_tokens`, `cost_usd`, `created_at`, `updated_at`.

Note that `current_stage` here comes from the most recently started `job_stages` row, not from `intake_jobs.current_stage`.

## Enums

**`pipeline_stage`** (in pipeline order; `project_metrics` relies on this order)
`INTAKE` → `DESIGN` → `CODE_GENERATION` → `CONTENT` → `SEO` → `APPROVAL_GATE` → `DEPLOYMENT`

**`intake_job_status`**
`queued`, `in_progress`, `awaiting_review`, `approved`, `deployed`, `failed`

**`job_stage_status`**
`pending`, `running`, `completed`, `failed`

**`reviewer_action`**
`approved`, `rejected`

**`organization_status`**
`prospect`, `applicant`, `active`, `alumni`

**`user_role`**
`admin`, `reviewer`, `member`
