-- Migration: 0001_intake_submissions
-- Generated for: buildautomation26
-- Run with: npx drizzle-kit migrate

-- ─── Enums ────────────────────────────────────────────────────────────────────

CREATE TYPE job_status AS ENUM (
  'pending',
  'in_review',
  'approved',
  'in_progress',
  'needs_revision',
  'completed',
  'cancelled'
);

CREATE TYPE page_type AS ENUM (
  'landing',
  'about',
  'services',
  'portfolio',
  'blog',
  'contact',
  'faq',
  'pricing',
  'custom'
);

CREATE TYPE brand_asset_type AS ENUM (
  'logo_primary',
  'logo_secondary',
  'logo_icon',
  'font',
  'color_palette',
  'style_guide',
  'photography',
  'illustration',
  'other'
);

-- ─── Organizations ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS organizations (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name         VARCHAR(255) NOT NULL,
  industry     VARCHAR(100),
  website      VARCHAR(500),
  size         VARCHAR(50),
  notes        TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Contacts ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS contacts (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  first_name       VARCHAR(100) NOT NULL,
  last_name        VARCHAR(100) NOT NULL,
  email            VARCHAR(255) NOT NULL,
  phone            VARCHAR(30),
  role             VARCHAR(100),
  is_primary       BOOLEAN NOT NULL DEFAULT FALSE,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_contacts_org ON contacts(organization_id);

-- ─── Intake Submissions ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS intake_submissions (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      UUID NOT NULL REFERENCES organizations(id),
  primary_contact_id   UUID REFERENCES contacts(id),
  preferred_domain     VARCHAR(255),
  preferred_subdomain  VARCHAR(255),
  domain_notes         TEXT,
  project_summary      TEXT NOT NULL,
  target_audience      TEXT,
  competitors          TEXT,
  budget_range         VARCHAR(100),
  desired_launch_date  TIMESTAMPTZ,
  status               job_status NOT NULL DEFAULT 'pending',
  internal_notes       TEXT,
  submitted_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  reviewed_at          TIMESTAMPTZ
);

CREATE INDEX idx_intake_submissions_org    ON intake_submissions(organization_id);
CREATE INDEX idx_intake_submissions_status ON intake_submissions(status);

-- ─── Branding Assets ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS branding_assets (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  intake_submission_id  UUID NOT NULL REFERENCES intake_submissions(id) ON DELETE CASCADE,
  asset_type            brand_asset_type NOT NULL,
  label                 VARCHAR(255) NOT NULL,
  file_url              VARCHAR(2048),
  value                 TEXT,
  metadata              JSONB,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_branding_assets_submission ON branding_assets(intake_submission_id);

-- ─── Page Requirements ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS page_requirements (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  intake_submission_id  UUID NOT NULL REFERENCES intake_submissions(id) ON DELETE CASCADE,
  page_type             page_type NOT NULL,
  custom_name           VARCHAR(255),
  description           TEXT,
  content_notes         TEXT,
  client_provides_copy  BOOLEAN NOT NULL DEFAULT FALSE,
  sort_order            TEXT NOT NULL DEFAULT '0',
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_page_requirements_submission ON page_requirements(intake_submission_id);

-- ─── Jobs ─────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS jobs (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  intake_submission_id  UUID NOT NULL REFERENCES intake_submissions(id),
  organization_id       UUID NOT NULL REFERENCES organizations(id),
  title                 VARCHAR(255) NOT NULL,
  status                job_status NOT NULL DEFAULT 'pending',
  priority              VARCHAR(20) NOT NULL DEFAULT 'normal',
  assigned_to           UUID,
  due_date              TIMESTAMPTZ,
  completed_at          TIMESTAMPTZ,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_jobs_intake    ON jobs(intake_submission_id);
CREATE INDEX idx_jobs_org       ON jobs(organization_id);
CREATE INDEX idx_jobs_status    ON jobs(status);
CREATE INDEX idx_jobs_assigned  ON jobs(assigned_to);
