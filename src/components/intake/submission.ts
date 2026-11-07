import { CONTENT_PARTIAL, CONTENT_YES, DOMAIN_OWNED, LOGO_UPLOAD, type FormErrors, type IntakeFormData } from "./validation";

export class IntakeSubmissionError extends Error {
  constructor(message: string, readonly fields: FormErrors = {}) {
    super(message);
    this.name = "IntakeSubmissionError";
  }
}

export function createIntakeRequest(data: IntakeFormData): FormData {
  const { logoFile, contentFiles, ...answers } = data;
  const hasContent = data.hasContent === CONTENT_YES || data.hasContent === CONTENT_PARTIAL;
  const body = new FormData();
  body.set("payload", JSON.stringify({
    ...answers,
    existingContent: hasContent ? data.existingContent : "",
    domainName: data.hasDomain === DOMAIN_OWNED ? data.domainName : "",
  }));
  if (data.hasLogo === LOGO_UPLOAD && logoFile) body.set("logoFile", logoFile);
  if (hasContent) contentFiles.forEach((file) => body.append("contentFiles", file));
  return body;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

export async function submitIntake(data: IntakeFormData, fetcher: typeof fetch = fetch): Promise<string> {
  let response: Response;
  try {
    response = await fetcher("/api/intake", {
      method: "POST",
      headers: { Accept: "application/json" },
      body: createIntakeRequest(data),
      redirect: "error",
    });
  } catch {
    throw new IntakeSubmissionError("We couldn't reach BUILD. Check your connection and try again. Your answers are still here.");
  }

  const result: unknown = await response.json().catch(() => null);
  if (!response.ok || !isRecord(result) || result.success !== true) {
    const fields: FormErrors = {};
    if (isRecord(result) && Array.isArray(result.details)) {
      for (const detail of result.details) {
        if (isRecord(detail) && typeof detail.field === "string" && typeof detail.message === "string") {
          fields[detail.field] = detail.message;
        }
      }
    }
    const message = Object.keys(fields).length
      ? "Please check the highlighted fields and submit again."
      : response.status === 413
        ? "Your upload is too large for this server. Choose smaller files and try again."
        : "We couldn't save your project. Your answers are still here; please try again shortly.";
    throw new IntakeSubmissionError(message, fields);
  }

  const submission = isRecord(result.data) ? result.data.submission : null;
  if (!isRecord(submission) || typeof submission.referenceNo !== "string" || !submission.referenceNo.trim()) {
    throw new IntakeSubmissionError("We couldn't confirm your submission. Please try again shortly.");
  }
  return submission.referenceNo;
}
