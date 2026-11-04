import {
  CONTENT_PARTIAL,
  CONTENT_YES,
  DOMAIN_OWNED,
  LOGO_UPLOAD,
  validateSection,
  type IntakeAnswers,
  type IntakeFormData,
} from "../intake/contract"

export interface IntakeSubmissionBody {
  projectName: string
  clientName: string
  clientEmail: string
  budget?: string
  features?: string
  teamSize?: string
  startDate?: string
  notes?: string
  organizationName?: string
  answers?: IntakeAnswers
}

export interface ValidationError {
  field: string
  message: string
}

export interface IntakeFiles {
  logo: File[]
  content: File[]
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const TEXT_FIELDS = [
  "organizationName", "primaryContactName", "primaryContactEmail", "organizationType",
  "primaryGoal", "organizationDescription", "targetAudience", "featureDetails", "hasLogo",
  "brandColors", "brandFonts", "visualStyle", "hasContent", "existingContent",
  "contentRestrictions", "hasDomain", "domainName", "integrationDetails", "additionalInfo",
] as const
const LIST_FIELDS = ["pages", "features", "referenceWebsites", "toneAndVoice", "integrations"] as const

function validateDetailedBody(body: Record<string, unknown>, files: IntakeFiles) {
  const errors: ValidationError[] = []
  const normalized: Record<string, unknown> = {}

  for (const field of TEXT_FIELDS) {
    if (typeof body[field] !== "string") {
      errors.push({ field, message: `${field} must be a string` })
    } else {
      normalized[field] = body[field].trim()
    }
  }
  for (const field of LIST_FIELDS) {
    const value = body[field]
    if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
      errors.push({ field, message: `${field} must be a list of strings` })
    } else if (value.length > (field === "referenceWebsites" ? 3 : 20)) {
      errors.push({ field, message: `${field} has too many selections` })
    } else {
      normalized[field] = [...new Set(value.map((item: string) => item.trim()))]
    }
  }
  if (body.sensitiveDataAcknowledged !== true) {
    errors.push({ field: "sensitiveDataAcknowledged", message: "Please confirm you won't upload confidential or legally protected material." })
  }
  // Files must be parsed from multipart data, never trusted from JSON objects.
  if ("logoFile" in body || "contentFiles" in body) {
    errors.push({ field: "body", message: "Send attachments as multipart files, separate from the JSON payload." })
  }
  if (errors.length) return { data: null, errors, files: { logo: [], content: [] } }

  const answers = { ...normalized, sensitiveDataAcknowledged: true } as IntakeAnswers
  answers.primaryContactEmail = answers.primaryContactEmail.toLowerCase()
  const activeFiles: IntakeFiles = {
    logo: answers.hasLogo === LOGO_UPLOAD ? files.logo : [],
    content: [CONTENT_YES, CONTENT_PARTIAL].includes(answers.hasContent) ? files.content : [],
  }
  if (answers.hasDomain !== DOMAIN_OWNED) answers.domainName = ""
  if (![CONTENT_YES, CONTENT_PARTIAL].includes(answers.hasContent)) answers.existingContent = ""

  if (activeFiles.logo.length > 1) errors.push({ field: "logoFile", message: "Upload at most one logo." })
  const form: IntakeFormData = { ...answers, logoFile: activeFiles.logo[0] ?? null, contentFiles: activeFiles.content }
  for (let section = 0; section < 6; section++) {
    for (const [field, message] of Object.entries(validateSection(section, form))) {
      errors.push({ field, message })
    }
  }
  if (errors.length) return { data: null, errors, files: activeFiles }

  const data: IntakeSubmissionBody = {
    projectName: answers.organizationName,
    organizationName: answers.organizationName,
    clientName: answers.primaryContactName,
    clientEmail: answers.primaryContactEmail,
    features: answers.features.join(", "),
    answers,
  }
  return { data, errors: [], files: activeFiles }
}

export function validateIntakeBody(body: unknown, files: IntakeFiles = { logo: [], content: [] }): {
  data: IntakeSubmissionBody | null
  errors: ValidationError[]
  files: IntakeFiles
} {
  const errors: ValidationError[] = []
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return { data: null, errors: [{ field: "body", message: "Request body must be a JSON object" }], files }
  }
  const b = body as Record<string, unknown>
  if ("organizationName" in b || "primaryContactEmail" in b || "sensitiveDataAcknowledged" in b) {
    return validateDetailedBody(b, files)
  }

  for (const field of ["projectName", "clientName", "clientEmail"] as const) {
    const value = b[field]
    if (typeof value !== "string" || !value.trim()) {
      errors.push({ field, message: `${field} is required` })
    } else if (value.trim().length > (field === "clientEmail" ? 254 : 200)) {
      errors.push({ field, message: `${field} is too long` })
    } else if (field === "clientEmail" && !EMAIL_RE.test(value.trim())) {
      errors.push({ field, message: "clientEmail must be a valid email" })
    }
  }
  const limits = { budget: 100, features: 10000, teamSize: 100, startDate: 100, notes: 20000 }
  for (const [field, limit] of Object.entries(limits)) {
    const value = b[field]
    if (value != null && typeof value !== "string") {
      errors.push({ field, message: `${field} must be a string` })
    } else if (typeof value === "string" && value.trim().length > limit) {
      errors.push({ field, message: `${field} must be ${limit} characters or fewer` })
    }
  }
  if (files.logo.length || files.content.length) errors.push({ field: "body", message: "Attachments require the detailed intake payload." })
  if (errors.length) return { data: null, errors, files }

  return {
    data: {
      projectName: (b.projectName as string).trim(),
      clientName: (b.clientName as string).trim(),
      clientEmail: (b.clientEmail as string).trim().toLowerCase(),
      ...Object.fromEntries(Object.keys(limits).map((field) => [field, typeof b[field] === "string" ? b[field].trim() : undefined])),
    },
    errors: [],
    files,
  }
}
