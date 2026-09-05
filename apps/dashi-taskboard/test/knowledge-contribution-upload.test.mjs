import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { afterEach, test } from "node:test";

const source = await readFile(new URL("../cloud/src/index.mjs", import.meta.url), "utf8");
const start = source.indexOf("async function sha256Hex");
const end = source.indexOf("async function uploadAttachment", start);
assert.ok(start >= 0 && end > start);
const adapterSource = source.slice(start, end).replace(
  "export async function enqueueUploadedFileContribution",
  "async function enqueueUploadedFileContribution",
);
const adapterModule = await import(`data:text/javascript,${encodeURIComponent(
  `${adapterSource}\nexport { enqueueUploadedFileContribution };`,
)}`);
const { enqueueUploadedFileContribution } = adapterModule;

const originalFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = originalFetch;
});

test("uploaded file bridge sends the persisted source and opt-out", async () => {
  let request;
  globalThis.fetch = async (url, init) => {
    request = { url, init };
    return new Response(JSON.stringify({ status: "excluded", contribution: null }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };

  const result = await enqueueUploadedFileContribution(
    {
      AI_LAB_INTERNAL_URL: "https://ai-lab.example.test/",
      AI_LAB_TENANT_KEY: "tenant-1",
      HERMES_BRIDGE_INTERNAL_TOKEN: "internal-token",
    },
    { id: "basic:alice" },
    {
      id: "attachment-1",
      change_revision: 12,
      created_at: "2026-09-05T12:00:00.000Z",
    },
    new TextEncoder().encode("uploaded source bytes").buffer,
    true,
  );

  assert.equal(result.status, "excluded");
  assert.equal(
    request.url,
    "https://ai-lab.example.test/api/v1/me/knowledge-notes/uploaded-files/attachment-1/contribution",
  );
  assert.equal(request.init.headers["x-hermes-internal-token"], "internal-token");
  const payload = JSON.parse(request.init.body);
  assert.deepEqual(
    {
      tenant_key: payload.tenant_key,
      user_id: payload.user_id,
      source_revision: payload.source_revision,
      source_changed_at: payload.source_changed_at,
      file_opt_out: payload.file_opt_out,
    },
    {
      tenant_key: "tenant-1",
      user_id: "basic:alice",
      source_revision: 12,
      source_changed_at: "2026-09-05T12:00:00.000Z",
      file_opt_out: true,
    },
  );
  assert.match(payload.content_hash, /^[a-f0-9]{64}$/);
});

test("eligible upload streams original bytes to the private extraction endpoint", async () => {
  let request;
  globalThis.fetch = async (url, init) => {
    request = { url, init };
    return new Response(JSON.stringify({ status: "processed" }), {
      status: 200, headers: { "content-type": "application/json" },
    });
  };
  const body = new TextEncoder().encode("private markdown").buffer;
  await enqueueUploadedFileContribution(
    {
      AI_LAB_INTERNAL_URL: "https://ai-lab.example.test",
      AI_LAB_TENANT_KEY: "tenant-1",
      HERMES_BRIDGE_INTERNAL_TOKEN: "internal-token",
    },
    { id: "basic:alice" },
    {
      id: "attachment-2", change_revision: 3,
      created_at: "2026-09-05T12:00:00.000Z",
      filename: "private.md", content_type: "text/markdown",
    },
    body, false,
  );
  assert.equal(request.url, "https://ai-lab.example.test/api/v1/me/knowledge-notes/uploaded-files/attachment-2/content");
  assert.equal(request.init.body, body);
  assert.equal(request.init.headers["x-file-name"], "private.md");
  assert.match(request.init.headers["x-content-hash"], /^[a-f0-9]{64}$/);
});

test("uploaded file bridge is inert unless the existing internal bridge is configured", async () => {
  let called = false;
  globalThis.fetch = async () => {
    called = true;
    throw new Error("must not call");
  };
  const result = await enqueueUploadedFileContribution(
    {}, { id: "basic:alice" },
    { id: "attachment-1", change_revision: 1, created_at: "2026-09-05T12:00:00Z" },
    new Uint8Array([1]).buffer, false,
  );
  assert.equal(result, null);
  assert.equal(called, false);
});
