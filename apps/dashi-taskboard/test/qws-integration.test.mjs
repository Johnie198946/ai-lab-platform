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
    if (request.url === "/api/v1/projects/prj-sync") {
      response.end(JSON.stringify({ id: "prj-sync", name: "Synced project", goal: "Ship safely" }));
      return;
    }
    if (request.url === "/api/v1/projects/prj-sync/process") {
      response.end(JSON.stringify({
        stages: [{ id: "stage-1", name: "需求" }],
        tasks: [{
          id: "task-1", stage_id: "stage-1", title: "Canonical task", summary: "Server owned",
          status: "TODO", assignee_role: "需求经理", deliverables: ["Evidence"], start_date: null, due_date: null,
        }],
      }));
      return;
    }
    if (request.url === "/api/v1/projects/prj-sync/ai-employees/ensure") {
      response.end(JSON.stringify({ ai_employees: [{
        employee_id: "a".repeat(32), agent_id: "a".repeat(32), display_name: "林知远",
        job_title: "需求经理", base_agent_id: "knowledge", project_id: "prj-sync", is_ai: true,
      }] }));
      return;
    }
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
      body: JSON.stringify({ project_id: "prj-sync" }),
    });
    assert.equal(sessionA.status, 200);
    const sessionPayload = await sessionA.json();
    assert.equal(sessionPayload.taskboard_project_id, "qws-tenant-a-prj-sync");
    const cookieA = sessionA.headers.get("set-cookie").split(";", 1)[0];
    const tasksA = await fetch(`${origin}/api/tasks?projectId=qws-tenant-a-prj-sync&archived=false`, { headers: { cookie: cookieA } }).then((response) => response.json());
    assert.equal(tasksA.tasks.length, 1);
    assert.equal(tasksA.tasks[0].title, "Canonical task");
    assert.deepEqual(tasksA.tasks[0].labels, ["qws-task-1"]);
    assert.deepEqual(tasksA.tasks[0].assignee, {
      type: "agent",
      id: "a".repeat(32),
      name: "林知远 · AI 员工 · 需求经理",
      avatarUrl: null,
    });

    const sessionB = await fetch(`${origin}/api/qws/session`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: "Bearer tenant-b" },
      body: "{}",
    });
    const cookieB = sessionB.headers.get("set-cookie").split(";", 1)[0];
    const projectsB = await fetch(`${origin}/api/projects`, { headers: { cookie: cookieB } }).then((response) => response.json());
    assert.equal(projectsB.projects.some((project) => project.id === "qws-tenant-a-prj-sync"), false);
  } finally {
    await app.close();
    await close(identityServer);
    await rm(dataDirectory, { recursive: true, force: true });
  }
});
