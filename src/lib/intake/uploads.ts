import { randomUUID } from "node:crypto"
import { createClient } from "@supabase/supabase-js"

export const MAX_INTAKE_FILE_BYTES = 10 * 1024 * 1024
export const MAX_INTAKE_REQUEST_BYTES = 61 * 1024 * 1024

type UploadCategory = "logo" | "content"
type UploadField = "logoFile" | "contentFiles"

export interface UploadedIntakeFile {
  category: UploadCategory
  originalName: string
  size: number
  contentType: string
  bucket: string
  path: string
}

export class UploadValidationError extends Error {
  constructor(public readonly field: UploadField, message: string) {
    super(message)
    this.name = "UploadValidationError"
  }
}

export class UploadStorageError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options)
    this.name = "UploadStorageError"
  }
}

const CONTENT_TYPES: Record<string, string> = {
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  svg: "image/svg+xml",
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  txt: "text/plain",
}

function storageConfig() {
  const url = process.env.SUPABASE_URL?.trim()
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY?.trim()
  const bucket = process.env.INTAKE_UPLOAD_BUCKET?.trim()

  if (!url || !serviceKey || !bucket) {
    throw new UploadStorageError(
      "File uploads require SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, and INTAKE_UPLOAD_BUCKET on the server.",
    )
  }

  try {
    const storage = createClient(url, serviceKey, {
      auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
    }).storage
    return { storage, bucket }
  } catch (cause) {
    throw new UploadStorageError("The file upload service is not configured correctly.", { cause })
  }
}

function hasBytes(bytes: Uint8Array, signature: number[]) {
  return signature.every((value, index) => bytes[index] === value)
}

// DOCX is a ZIP container. Inspect its directory without extracting or executing
// uploaded data, and require the standard Word document parts.
function isDocx(bytes: Uint8Array) {
  if (!hasBytes(bytes, [0x50, 0x4b, 0x03, 0x04]) || bytes.length < 22) return false
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  const minimum = Math.max(0, bytes.length - 22 - 65535)
  let end = bytes.length - 22
  for (; end >= minimum; end--) {
    if (view.getUint32(end, true) === 0x06054b50 &&
        end + 22 + view.getUint16(end + 20, true) === bytes.length) break
  }
  if (end < minimum) return false
  if (view.getUint16(end + 4, true) !== 0 || view.getUint16(end + 6, true) !== 0) return false
  const entries = view.getUint16(end + 10, true)
  const directorySize = view.getUint32(end + 12, true)
  let offset = view.getUint32(end + 16, true)
  const directoryEnd = offset + directorySize
  if (directoryEnd > end || entries === 0 || entries > 10000) return false
  const names = new Set<string>()

  for (let index = 0; index < entries; index++) {
    if (offset + 46 > directoryEnd || view.getUint32(offset, true) !== 0x02014b50) return false
    const nameLength = view.getUint16(offset + 28, true)
    const extraLength = view.getUint16(offset + 30, true)
    const commentLength = view.getUint16(offset + 32, true)
    const nextOffset = offset + 46 + nameLength + extraLength + commentLength
    if (nextOffset > directoryEnd) return false
    names.add(new TextDecoder().decode(bytes.subarray(offset + 46, offset + 46 + nameLength)))
    offset = nextOffset
  }

  return offset === directoryEnd && names.has("[Content_Types].xml") &&
    names.has("_rels/.rels") && names.has("word/document.xml")
}

function matchesFormat(bytes: Uint8Array, extension: string) {
  switch (extension) {
    case "png": return hasBytes(bytes, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
    case "jpg":
    case "jpeg": return hasBytes(bytes, [0xff, 0xd8, 0xff])
    case "pdf": return hasBytes(bytes, [0x25, 0x50, 0x44, 0x46, 0x2d])
    case "docx": return isDocx(bytes)
    case "svg":
    case "txt": {
      let value: string
      try {
        value = new TextDecoder("utf-8", { fatal: true }).decode(bytes)
      } catch {
        return false
      }
      if (value.includes("\0")) return false
      if (extension === "txt") return true
      // This identifies an SVG file; it is not an HTML/SVG sanitizer. Keep the
      // original private and do not inline untrusted SVG in downstream pages.
      const withoutPreamble = value.replace(/^\s*<\?xml\b[^?]*\?>/i, "")
        .replace(/<!--[^]*?-->/g, "").trimStart()
        // Illustrator and other editors emit an external SVG doctype. Skip
        // the declaration for format identification; never resolve its URL.
        .replace(/^<!DOCTYPE\s+svg(?:\s+(?:PUBLIC\s+(?:"[^"]*"|'[^']*')\s+(?:"[^"]*"|'[^']*')|SYSTEM\s+(?:"[^"]*"|'[^']*')))?\s*>/i, "")
        .trimStart()
      return /^<svg(?:\s|\/?>)/i.test(withoutPreamble) &&
        (/<\/svg\s*>\s*$/i.test(value) || /^<svg\b[^]*\/\s*>\s*$/i.test(withoutPreamble))
    }
    default: return false
  }
}

interface PreparedFile {
  file: File
  category: UploadCategory
  field: UploadField
  extension: string
  contentType: string
}

function prepareFiles(files: { logo: File[]; content: File[] }): PreparedFile[] {
  const prepared: PreparedFile[] = []
  const groups = [
    { category: "logo", field: "logoFile", files: files.logo, max: 1, extensions: ["png", "svg", "jpg", "jpeg"] },
    { category: "content", field: "contentFiles", files: files.content, max: 5, extensions: ["pdf", "docx", "txt"] },
  ] as const

  for (const group of groups) {
    if (!Array.isArray(group.files) || group.files.length > group.max) {
      throw new UploadValidationError(group.field, `Upload at most ${group.max} ${group.category} file${group.max === 1 ? "" : "s"}.`)
    }
    for (const file of group.files) {
      if (!(file instanceof File)) {
        throw new UploadValidationError(group.field, "Select a valid file to upload.")
      }
      const dot = file.name.lastIndexOf(".")
      const extension = dot > 0 ? file.name.slice(dot + 1).toLowerCase() : ""
      if (!file.name || file.name.length > 255 || /[\x00-\x1f\x7f]/.test(file.name) ||
          !(group.extensions as readonly string[]).includes(extension)) {
        throw new UploadValidationError(group.field, `Accepted ${group.category} file types: ${group.extensions.join(", ")}.`)
      }
      if (file.size === 0 || file.size > MAX_INTAKE_FILE_BYTES) {
        throw new UploadValidationError(group.field, "Each uploaded file must contain data and be 10 MB or smaller.")
      }
      prepared.push({ file, category: group.category, field: group.field, extension, contentType: CONTENT_TYPES[extension] })
    }
  }
  return prepared
}

async function removeUploads(
  storage: ReturnType<typeof storageConfig>["storage"],
  files: UploadedIntakeFile[],
) {
  const pathsByBucket = new Map<string, string[]>()
  for (const file of files) {
    const paths = pathsByBucket.get(file.bucket) ?? []
    paths.push(file.path)
    pathsByBucket.set(file.bucket, paths)
  }
  for (const [bucket, paths] of pathsByBucket) {
    const { error } = await storage.from(bucket).remove(paths)
    if (error) throw error
  }
}

/** Store files in a pre-created private bucket; returned paths are never public URLs. */
export async function uploadIntakeFiles(
  files: { logo: File[]; content: File[] },
  jobId: string = randomUUID(),
): Promise<UploadedIntakeFile[]> {
  const prepared = prepareFiles(files)
  if (prepared.length === 0) return []
  if (!/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}$/.test(jobId)) {
    throw new UploadStorageError("A valid intake job identifier is required for file uploads.")
  }

  const { storage, bucket } = storageConfig()
  const attempted: UploadedIntakeFile[] = []
  try {
    const { data: bucketInfo, error: bucketError } = await storage.getBucket(bucket)
    if (bucketError || !bucketInfo) {
      throw new UploadStorageError("The configured intake upload bucket is unavailable.", { cause: bucketError })
    }
    if (bucketInfo.public !== false) {
      throw new UploadStorageError("The intake upload bucket must be private.")
    }

    for (const item of prepared) {
      const bytes = new Uint8Array(await item.file.arrayBuffer())
      if (bytes.byteLength !== item.file.size || !matchesFormat(bytes, item.extension)) {
        throw new UploadValidationError(item.field, `The contents of "${item.file.name}" do not match its file type. Text and SVG files must use UTF-8.`)
      }
      const metadata: UploadedIntakeFile = {
        category: item.category,
        originalName: item.file.name,
        size: item.file.size,
        contentType: item.contentType,
        bucket,
        path: `intake/${jobId}/${item.category}/${randomUUID()}.${item.extension}`,
      }
      // Track attempts before the network call: an interrupted response can
      // follow a successful write, so that path must also be cleaned up.
      attempted.push(metadata)
      const { error } = await storage.from(bucket).upload(metadata.path, bytes, {
        contentType: item.contentType,
        cacheControl: "0",
        upsert: false,
      })
      if (error) throw error
    }
    return attempted
  } catch (cause) {
    if (attempted.length) {
      try {
        await removeUploads(storage, attempted)
      } catch (cleanupCause) {
        throw new UploadStorageError("File upload failed and uploaded files could not be fully removed. Server cleanup is required.", {
          cause: { uploadError: cause, cleanupError: cleanupCause, paths: attempted.map(({ bucket, path }) => ({ bucket, path })) },
        })
      }
    }
    if (cause instanceof UploadValidationError || cause instanceof UploadStorageError) throw cause
    throw new UploadStorageError("Files could not be saved. Please try again later.", { cause })
  }
}

/** Call when the database transaction fails after uploadIntakeFiles succeeds. */
export async function rollbackIntakeUploads(files: UploadedIntakeFile[]): Promise<void> {
  if (files.length === 0) return
  try {
    await removeUploads(storageConfig().storage, files)
  } catch (cause) {
    throw new UploadStorageError("Uploaded files could not be removed after the submission failed. Server cleanup is required.", {
      cause: { cleanupError: cause, paths: files.map(({ bucket, path }) => ({ bucket, path })) },
    })
  }
}
