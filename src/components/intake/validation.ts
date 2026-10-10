// Client-side validation for the intake form.
// Every rule here comes from the Intake Form PRD, Section 3 (field tables).
// The server will re-validate on submit; this file only gives the submitter
// fast, specific feedback before they move to the next section.

export type IntakeFormData = {
  // Section 1: Organization & Contact
  sensitiveDataAcknowledged: boolean;
  organizationName: string;
  primaryContactName: string;
  primaryContactEmail: string;
  organizationType: string;

  // Section 2: Project Goals
  primaryGoal: string;
  organizationDescription: string;
  targetAudience: string;
  pages: string[];
  features: string[];
  featureDetails: string;

  // Section 3: Design & Branding
  hasLogo: string;
  logoFile: File | null;
  brandColors: string;
  brandFonts: string;
  visualStyle: string;
  referenceWebsites: string[];

  // Section 4: Content
  hasContent: string;
  existingContent: string;
  contentFiles: File[];
  toneAndVoice: string[];
  contentRestrictions: string;

  // Section 5: Technical Details
  hasDomain: string;
  domainName: string;
  integrations: string[];
  integrationDetails: string;

  // Section 6: Additional Information
  additionalInfo: string;
};

// Field key -> error message. Reference websites use "referenceWebsites.0" etc.
export type FormErrors = Record<string, string>;

// ---------- Dropdown / multi-select options (PRD Section 3) ----------

export const ORGANIZATION_TYPES = [
  "Student Organization",
  "Campus Department",
  "Small Business",
  "Nonprofit",
  "Personal / Portfolio",
  "Other",
];

export const PRIMARY_GOALS = [
  "Attract new members",
  "Sell products or services",
  "Share information or resources",
  "Accept donations",
  "Build a professional presence",
  "Promote events",
  "Other",
];

export const PAGE_OPTIONS = [
  "Home",
  "About",
  "Team",
  "Services",
  "Events",
  "Blog",
  "Contact",
  "Gallery",
  "Donate",
  "Join/Apply",
  "FAQ",
  "Other",
];

export const FEATURE_OPTIONS = [
  "Contact form",
  "Event calendar",
  "Photo gallery",
  "Newsletter signup",
  "Social media feed",
  "Member application form",
  "Donation button",
  "Password-protected page",
  "Other",
];

export const LOGO_UPLOAD = "Yes — I will upload it";
export const LOGO_OPTIONS = [
  LOGO_UPLOAD,
  "No — please create a simple text-based logo",
  "No — I will provide one later",
];

export const CONTENT_YES = "Yes — I will upload or paste it";
export const CONTENT_PARTIAL = "Partially — I have some but not all";
export const CONTENT_OPTIONS = [
  CONTENT_YES,
  CONTENT_PARTIAL,
  "No — please generate it from my description",
];

export const TONE_OPTIONS = [
  "Professional",
  "Friendly",
  "Casual",
  "Inspiring",
  "Authoritative",
  "Playful",
  "Minimalist",
];
export const MAX_TONES = 3;

export const DOMAIN_OWNED = "Yes — I own one already";
export const DOMAIN_OPTIONS = [
  DOMAIN_OWNED,
  "No — I need one",
  "No — a BUILD subdomain is fine for now",
];

export const INTEGRATION_OPTIONS = [
  "Google Analytics",
  "Mailchimp",
  "HubSpot",
  "Stripe",
  "PayPal",
  "Calendly",
  "Instagram feed",
  "Facebook page",
  "LinkedIn",
  "Other",
];

// ---------- Upload rules (PRD Section 4.1) ----------

export const LOGO_UPLOAD_RULES = {
  extensions: [".png", ".svg", ".jpg", ".jpeg"],
  maxSizeMB: 10,
  maxFiles: 1,
};

export const CONTENT_UPLOAD_RULES = {
  extensions: [".pdf", ".docx", ".txt"],
  maxSizeMB: 10,
  maxFiles: 5,
};

// Returns an error message for the first bad file, or null if all are fine.
export function checkFiles(
  files: File[],
  rules: { extensions: string[]; maxSizeMB: number; maxFiles: number },
): string | null {
  if (files.length > rules.maxFiles) {
    return `You can upload at most ${rules.maxFiles} file${rules.maxFiles === 1 ? "" : "s"}.`;
  }
  for (const file of files) {
    const name = file.name.toLowerCase();
    if (!rules.extensions.some((ext) => name.endsWith(ext))) {
      return `"${file.name}" isn't an accepted file type. Please upload ${rules.extensions.join(", ")}.`;
    }
    if (file.size > rules.maxSizeMB * 1024 * 1024) {
      return `"${file.name}" exceeds the ${rules.maxSizeMB}MB maximum. Please upload a smaller file.`;
    }
  }
  return null;
}

// ---------- Small helpers ----------

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
// example.com, sub.example.org: no protocol, no "www."
const DOMAIN_RE = /^(?!-)[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$/i;
// Forgiving URL check: protocol and trailing slash are optional (PRD 3.3).
const URL_RE = /^(https?:\/\/)?([a-z0-9-]+\.)+[a-z]{2,}(:\d+)?(\/\S*)?$/i;

function checkLength(
  value: string,
  min: number,
  max: number,
  label: string,
): string | null {
  const len = value.trim().length;
  if (len === 0 && min > 0) return `${label} is required.`;
  if (len < min) return `${label} needs at least ${min} characters (currently ${len}).`;
  if (len > max) return `${label} must be ${max} characters or fewer.`;
  return null;
}

function add(errors: FormErrors, key: string, message: string | null) {
  if (message) errors[key] = message;
}

// ---------- Per-section validation ----------

export function validateSection(index: number, d: IntakeFormData): FormErrors {
  const e: FormErrors = {};

  switch (index) {
    case 0: {
      if (!d.sensitiveDataAcknowledged) {
        e.sensitiveDataAcknowledged =
          "Please confirm you won't upload confidential or legally protected material.";
      }
      add(e, "organizationName", checkLength(d.organizationName, 2, 100, "Organization name"));
      add(e, "primaryContactName", checkLength(d.primaryContactName, 2, 100, "Contact name"));
      if (!d.primaryContactEmail.trim()) {
        e.primaryContactEmail = "Contact email is required.";
      } else if (!EMAIL_RE.test(d.primaryContactEmail.trim())) {
        e.primaryContactEmail = "Enter a valid email address, like name@example.org.";
      }
      if (!d.organizationType) e.organizationType = "Select your organization type.";
      break;
    }

    case 1: {
      if (!d.primaryGoal) e.primaryGoal = "Select the primary goal of your website.";
      add(
        e,
        "organizationDescription",
        checkLength(d.organizationDescription, 50, 1000, "Organization description"),
      );
      add(e, "targetAudience", checkLength(d.targetAudience, 30, 500, "Target audience"));
      if (d.pages.length === 0) e.pages = "Select at least one page.";
      if (d.features.includes("Other") && !d.featureDetails.trim()) {
        e.featureDetails = "You selected \"Other\": please describe the feature you need.";
      } else {
        add(e, "featureDetails", checkLength(d.featureDetails, 0, 500, "Feature details"));
      }
      break;
    }

    case 2: {
      if (!d.hasLogo) e.hasLogo = "Let us know whether you have a logo.";
      if (d.hasLogo === LOGO_UPLOAD && !d.logoFile) {
        e.logoFile = "Upload your logo, or choose a different option above.";
      }
      add(e, "brandFonts", checkLength(d.brandFonts, 0, 200, "Brand fonts"));
      add(e, "visualStyle", checkLength(d.visualStyle, 30, 500, "Visual style description"));
      d.referenceWebsites.forEach((url, i) => {
        if (url.trim() && !URL_RE.test(url.trim())) {
          e[`referenceWebsites.${i}`] = "That doesn't look like a website address, like example.com.";
        }
      });
      break;
    }

    case 3: {
      if (!d.hasContent) e.hasContent = "Let us know whether you have existing content.";
      if (d.hasContent === CONTENT_YES || d.hasContent === CONTENT_PARTIAL) {
        add(e, "existingContent", checkLength(d.existingContent, 1, 5000, "Existing content"));
      }
      if (d.toneAndVoice.length === 0) e.toneAndVoice = "Select at least one tone.";
      if (d.toneAndVoice.length > MAX_TONES) e.toneAndVoice = `Select at most ${MAX_TONES} tones.`;
      add(e, "contentRestrictions", checkLength(d.contentRestrictions, 0, 500, "Content exclusions"));
      break;
    }

    case 4: {
      if (!d.hasDomain) e.hasDomain = "Let us know your domain situation.";
      if (d.hasDomain === DOMAIN_OWNED) {
        const domain = d.domainName.trim();
        if (!domain) {
          e.domainName = "Enter the domain you own.";
        } else if (/^https?:\/\//i.test(domain) || /^www\./i.test(domain) || !DOMAIN_RE.test(domain)) {
          e.domainName = "Enter just the domain, like example.org, without http:// or www.";
        }
      }
      add(e, "integrationDetails", checkLength(d.integrationDetails, 0, 500, "Integration details"));
      break;
    }

    case 5: {
      add(e, "additionalInfo", checkLength(d.additionalInfo, 0, 1000, "Additional details"));
      break;
    }
  }

  return e;
}
