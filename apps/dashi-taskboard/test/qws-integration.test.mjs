import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { createServer } from "node:http";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { createTaskboardServer } from "../server/app.mjs";

const listen = (server) => new Promise((resolve, reject) => {
  server.once("error", reject);
  server.listen(0, "127.0.0.1", () => resolve(server.address()));
});

const close = (server) => new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));

test("QWS mode authenticates through AI Lab and isolates tenant taskboard data", async () => {
  const dataDirectory = await mkdtemp(path.join(os.tmpdir(), "qws-taskboard-test-"));
  const identityServer = createServer((request, response) => {
    const tenant = request.headers.authorization === "Bearer tenant-b" ? "tenant-b" : "tenant-a";
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ tenant_key: tenant, user_id: `${tenant}-user`, username: tenant }));
  });
  const identityAddress = await listen(identityServer);
  const app = createTaskboardServer({
    dataDirectory,
    qwsMode: true,
    aiLabBaseUrl: `http://127.0.0.1:${identityAddress.port}`,
  });
  const address = await app.listen({ port: 0 });
  const origin = `http://127.0.0.1:${address.port}`;
  try {
    const unauthorized = await fetch(`${origin}/api/projects`);
    assert.equal(unauthorized.status, 401);

    const sessionA = await fetch(`${origin}/api/qws/session`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: "Bearer tenant-a" },
      body: "{}",
    });
    assert.equal(sessionA.status, 200);
    const cookieA = sessionA.headers.get("set-cookie").split(";", 1)[0];
    const created = await fetch(`${origin}/api/projects`, {
      method: "POST",
      headers: { "content-type": "application/json", cookie: cookieA },
      body: JSON.stringify({ id: "qws-tenant-a-project", name: "Tenant A", workspacePath: "/workspace" }),
    });
    assert.equal(created.status, 201);

    const sessionB = await fetch(`${origin}/api/qws/session`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: "Bearer tenant-b" },
      body: "{}",
    });
    const cookieB = sessionB.headers.get("set-cookie").split(";", 1)[0];
    const projectsB = await fetch(`${origin}/api/projects`, { headers: { cookie: cookieB } }).then((response) => response.json());
    assert.equal(projectsB.projects.some((project) => project.id === "qws-tenant-a-project"), false);
  } finally {
    await app.close();
    await close(identityServer);
    await rm(dataDirectory, { recursive: true, force: true });
  }
});
