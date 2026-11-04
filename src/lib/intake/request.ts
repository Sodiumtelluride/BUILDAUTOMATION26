import { MAX_INTAKE_REQUEST_BYTES } from "./uploads"
import type { IntakeFiles } from "../validation/intake"

export const MAX_INTAKE_JSON_BYTES = 64 * 1024

export class IntakeRequestError extends Error {
  constructor(message: string, public status: number = 400) {
    super(message)
    this.name = "IntakeRequestError"
  }
}

async function readLimitedBody(req: Request, limit: number) {
  const declaredLength = Number(req.headers.get("content-length"))
  if (declaredLength > limit) throw new IntakeRequestError("The intake request is too large.", 413)
  const reader = req.body?.getReader()
  if (!reader) throw new IntakeRequestError("Request body is required.")
  const chunks: Uint8Array[] = []
  let size = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      size += value.byteLength
      if (size > limit) {
        await reader.cancel()
        throw new IntakeRequestError("The intake request is too large.", 413)
      }
      chunks.push(value)
    }
  } finally {
    reader.releaseLock()
  }
  const body = new Uint8Array(size)
  let offset = 0
  for (const chunk of chunks) {
    body.set(chunk, offset)
    offset += chunk.byteLength
  }
  return body
}

function parseJson(value: string): unknown {
  if (new TextEncoder().encode(value).byteLength > MAX_INTAKE_JSON_BYTES) {
    throw new IntakeRequestError("The intake answers are too large.", 413)
  }
  try {
    return JSON.parse(value)
  } catch {
    throw new IntakeRequestError("Invalid JSON")
  }
}

export async function parseIntakeRequest(req: Request): Promise<{ body: unknown; files: IntakeFiles }> {
  const contentType = req.headers.get("content-type") ?? "application/json"
  const mediaType = contentType.split(";")[0].trim().toLowerCase()
  if (mediaType === "application/json") {
    const bytes = await readLimitedBody(req, MAX_INTAKE_JSON_BYTES)
    return { body: parseJson(new TextDecoder().decode(bytes)), files: { logo: [], content: [] } }
  }
  if (mediaType !== "multipart/form-data") throw new IntakeRequestError("Use JSON or multipart form data.", 415)

  const bytes = await readLimitedBody(req, MAX_INTAKE_REQUEST_BYTES)
  let form: FormData
  try {
    form = await new Response(bytes, { headers: { "content-type": contentType } }).formData()
  } catch {
    throw new IntakeRequestError("Invalid multipart form data.")
  }
  for (const key of form.keys()) {
    if (!["payload", "logoFile", "contentFiles"].includes(key)) throw new IntakeRequestError("Unexpected multipart form field.")
  }
  const payloads = form.getAll("payload")
  if (payloads.length !== 1 || typeof payloads[0] !== "string") throw new IntakeRequestError("Provide one JSON payload field.")
  function getFiles(field: string): File[] {
    const values = form.getAll(field)
    if (values.some((value) => typeof value === "string")) throw new IntakeRequestError(`${field} must contain uploaded files.`)
    return values as File[]
  }
  return { body: parseJson(payloads[0]), files: { logo: getFiles("logoFile"), content: getFiles("contentFiles") } }
}
