import assert from "node:assert/strict"
import { register } from "node:module"
import { beforeEach, test } from "node:test"

// Replace the SDK before importing the module: these tests never create a real
// storage client, read real credentials, or make network requests.
register("./helpers/typescript-loader.mjs", import.meta.url, {
  data: {
    mocks: {
      "@supabase/supabase-js": `data:text/javascript,${encodeURIComponent(
        "export function createClient() { return { storage: globalThis.__intakeStorageMock }; }",
      )}`,
    },
  },
})

const {
  MAX_INTAKE_FILE_BYTES,
  UploadStorageError,
  UploadValidationError,
  uploadIntakeFiles,
  rollbackIntakeUploads,
} = await import("../src/lib/intake/uploads.ts")

let state

beforeEach(() => {
  process.env.SUPABASE_URL = "https://example.invalid"
  process.env.SUPABASE_SERVICE_ROLE_KEY = "test-only-service-key"
  process.env.INTAKE_UPLOAD_BUCKET = "private-intake"
  state = { uploads: [], removals: [], bucketChecks: [], publicBucket: false }
  globalThis.__intakeStorageMock = {
    async getBucket(bucket) {
      state.bucketChecks.push(bucket)
      return { data: { public: state.publicBucket }, error: state.bucketError ?? null }
    },
    from(bucket) {
      return {
        async upload(path, bytes, options) {
          state.uploads.push({ bucket, path, bytes, options })
          return { error: state.failUpload === state.uploads.length ? new Error("Test upload failure") : null }
        },
        async remove(paths) {
          state.removals.push({ bucket, paths })
          return { error: state.failCleanup ? new Error("Test cleanup failure") : null }
        },
      }
    },
  }
})

const png = () => new File([Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10])], "logo.png", { type: "text/html" })
const text = () => new File(["Project content"], "content.txt", { type: "image/jpeg" })
const selected = () => ({ logo: [png()], content: [text()] })

test("no files require no storage configuration or requests", async () => {
  delete process.env.SUPABASE_URL
  assert.deepEqual(await uploadIntakeFiles({ logo: [], content: [] }), [])
  await rollbackIntakeUploads([])
  assert.equal(state.bucketChecks.length, 0)
})

test("selected files report missing server storage configuration", async () => {
  delete process.env.SUPABASE_SERVICE_ROLE_KEY
  await assert.rejects(uploadIntakeFiles(selected()), (error) =>
    error instanceof UploadStorageError && error.message.includes("SUPABASE_SERVICE_ROLE_KEY"),
  )
  assert.equal(state.bucketChecks.length, 0)
})

test("upload counts are checked independently on the server", async () => {
  await assert.rejects(uploadIntakeFiles({ logo: [png(), png()], content: [] }), (error) =>
    error instanceof UploadValidationError && error.field === "logoFile",
  )
  await assert.rejects(uploadIntakeFiles({ logo: [], content: Array.from({ length: 6 }, text) }), (error) =>
    error instanceof UploadValidationError && error.field === "contentFiles",
  )
  assert.equal(state.bucketChecks.length, 0)
})

test("empty, oversized, and unsupported files fail before storage requests", async () => {
  for (const file of [
    new File([], "empty.txt"),
    new File([new Uint8Array(MAX_INTAKE_FILE_BYTES + 1)], "large.txt"),
    new File(["text"], "txt"),
    new File(["text"], "document.exe"),
  ]) {
    await assert.rejects(uploadIntakeFiles({ logo: [], content: [file] }), UploadValidationError)
  }
  assert.equal(state.bucketChecks.length, 0)
})

test("public and unavailable storage buckets cannot receive uploaded files", async () => {
  state.publicBucket = true
  await assert.rejects(uploadIntakeFiles(selected()), /must be private/)
  state.publicBucket = false
  state.bucketError = new Error("Test unavailable bucket")
  await assert.rejects(uploadIntakeFiles(selected()), /bucket is unavailable/)
  assert.equal(state.uploads.length, 0)
})

test("server derives MIME types and returns serializable private storage references", async () => {
  const files = await uploadIntakeFiles(selected(), "test-job")
  assert.equal(files.length, 2)
  assert.equal(files[0].contentType, "image/png")
  assert.equal(files[1].contentType, "text/plain")
  assert.equal(state.uploads[0].options.contentType, "image/png")
  assert.equal(state.uploads[0].options.upsert, false)
  assert.match(files[0].path, /^intake\/test-job\/logo\/[a-f0-9-]+\.png$/)
  assert.match(files[1].path, /^intake\/test-job\/content\/[a-f0-9-]+\.txt$/)
  assert.deepEqual(JSON.parse(JSON.stringify(files)), files)
  assert.equal(files[0].bucket, "private-intake")
  assert.equal(Object.hasOwn(files[0], "url"), false)
})

test("a failed second upload removes successful and possibly written paths", async () => {
  state.failUpload = 2
  await assert.rejects(uploadIntakeFiles(selected()), UploadStorageError)
  assert.equal(state.uploads.length, 2)
  assert.deepEqual(state.removals[0].paths, state.uploads.map(({ path }) => path))
})

test("content mismatch after a successful upload also removes stored files", async () => {
  await assert.rejects(uploadIntakeFiles({
    logo: [png()],
    content: [new File(["This is not a PDF"], "document.pdf", { type: "application/pdf" })],
  }), (error) => error instanceof UploadValidationError && error.field === "contentFiles")
  assert.equal(state.uploads.length, 1)
  assert.deepEqual(state.removals[0].paths, [state.uploads[0].path])
})

test("database rollback removes every returned storage reference", async () => {
  const files = await uploadIntakeFiles(selected())
  await rollbackIntakeUploads(files)
  assert.deepEqual(state.removals, [{ bucket: "private-intake", paths: files.map(({ path }) => path) }])
})

test("cleanup errors remain visible and include paths for server recovery", async () => {
  state.failUpload = 1
  state.failCleanup = true
  await assert.rejects(uploadIntakeFiles(selected()), (error) =>
    error instanceof UploadStorageError && error.message.includes("cleanup") && error.cause.paths.length === 1,
  )
  await assert.rejects(rollbackIntakeUploads([{
    category: "content", originalName: "content.txt", size: 1,
    contentType: "text/plain", bucket: "private-intake", path: "intake/test/content/test.txt",
  }]), UploadStorageError)
})

test("UTF-8 SVG logos accept full and self-closing roots", async () => {
  for (const svg of [
    '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>',
    '<?xml version="1.0"?><!-- logo --><svg xmlns="http://www.w3.org/2000/svg"/>',
  ]) {
    const files = await uploadIntakeFiles({ logo: [new File([svg], "logo.svg")], content: [] })
    assert.equal(files[0].contentType, "image/svg+xml")
  }
})

test("SVG logos support common editor doctype declarations without resolving them", async () => {
  for (const declaration of [
    '<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">',
    "<!DOCTYPE svg SYSTEM 'http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd'>",
    "<!DOCTYPE svg>",
  ]) {
    const svg = `<?xml version="1.0" encoding="utf-8"?>\n${declaration}\n<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>`
    const files = await uploadIntakeFiles({ logo: [new File([svg], "editor-logo.svg")], content: [] })
    assert.equal(files[0].contentType, "image/svg+xml")
  }
})

test("binary text, generic ZIP files renamed DOCX, and invalid SVG are rejected", async () => {
  for (const file of [
    new File([Uint8Array.from([0xff, 0xfe])], "binary.txt"),
    new File(["text\0binary"], "binary.txt"),
    new File([Uint8Array.from([0x50, 0x4b, 0x03, 0x04])], "document.docx"),
  ]) {
    await assert.rejects(uploadIntakeFiles({ logo: [], content: [file] }), UploadValidationError)
  }
  await assert.rejects(uploadIntakeFiles({ logo: [new File(["<html>no SVG</html>"], "logo.svg")], content: [] }), UploadValidationError)
  assert.equal(state.uploads.length, 0)
})

test("storage paths cannot contain a caller-supplied path traversal", async () => {
  await assert.rejects(uploadIntakeFiles(selected(), "../another-job"), UploadStorageError)
  assert.equal(state.uploads.length, 0)
})
