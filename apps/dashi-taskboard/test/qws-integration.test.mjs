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
  const previousInternalToken = process.env.HERMES_BRIDGE_INTERNAL_TOKEN;
  process.env.HERMES_BRIDGE_INTERNAL_TOKEN = "qws-test-internal-token";
  let canonicalRevision = 1;
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
          status: "BACKLOG", assignee_role: "需求经理", deliverables: ["Evidence"],
          start_date: canonicalRevision > 1 ? "2026-08-31" : null,
          due_date: canonicalRevision > 1 ? "2026-08-31" : null,
          development_context: { platform: "independent web", devices: ["mobile", "desktop"] },
        }, {
          id: "task-2", stage_id: "stage-1", title: "Runtime task", summary: "Use a branch",
          status: "WAITING_CLAIM", assignee_role: "需求经理", deliverables: [],
          start_date: canonicalRevision > 1 ? "2026-09-01" : null,
          due_date: canonicalRevision > 1 ? "2026-09-01" : null,
          development_context: { type: "branch", branch: "codex/runtime-task" },
          relations: canonicalRevision < 3 ? [
            { type: "parent", target_task_id: "task-1" },
            { type: "blocked_by", target_task_id: "task-1" },
          ] : [],
        }],
        dependencies: canonicalRevision === 2
          ? [{ from_task_id: "task-1", to_task_id: "task-2" }]
          : [],
      }));
      return;
    }
    if (request.url === "/api/v1/projects/prj-sync/ai-employees/ensure") {
      response.end(JSON.stringify({ ai_employees: [
        { employee_id: "a".repeat(32), agent_id: "a".repeat(32), display_name: "林知远", job_title: "需求经理", base_agent_id: "knowledge", project_id: "prj-sync", is_ai: true },
        { employee_id: "b".repeat(32), agent_id: "b".repeat(32), display_name: "周砚", job_title: "产品经理", base_agent_id: "main_agent", project_id: "prj-sync", is_ai: true },
        { employee_id: "c".repeat(32), agent_id: "c".repeat(32), display_name: "许澄", job_title: "技术负责人", base_agent_id: "coder", project_id: "prj-sync", is_ai: true },
        { employee_id: "d".repeat(32), agent_id: "d".repeat(32), display_name: "程野", job_title: "测试经理", base_agent_id: "supervision", project_id: "prj-sync", is_ai: true },
        { employee_id: "e".repeat(32), agent_id: "e".repeat(32), display_name: "沈星", job_title: "交付经理", base_agent_id: "main_agent", project_id: "prj-sync", is_ai: true },
        { employee_id: "f".repeat(32), agent_id: "f".repeat(32), display_name: "陆川", job_title: "评审人", base_agent_id: "supervision", project_id: "prj-sync", is_ai: true },
      ] }));
      return;
    }
    if (request.url === "/api/v1/projects/prj-invalid") {
      response.end(JSON.stringify({ id: "prj-invalid", name: "Invalid project" }));
      return;
    }
    if (request.url === "/api/v1/projects/prj-invalid/process") {
      response.end(JSON.stringify({
        stages: [{ id: "stage-1", name: "需求" }],
        tasks: [{
          id: "valid-first", stage_id: "stage-1", title: "Would be partial", status: "TODO",
          start_date: null, due_date: null,
        }, {
          id: "invalid-second", stage_id: "stage-1", title: "Invalid date", status: "TODO",
          start_date: null, due_date: "tomorrow",
        }],
      }));
      return;
    }
    if (request.url === "/api/v1/projects/prj-invalid/ai-employees/ensure") {
      response.end(JSON.stringify({ ai_employees: [] }));
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
    assert.equal(tasksA.tasks.length, 2);
    const canonicalTask = tasksA.tasks.find((task) => task.title === "Canonical task");
    const runtimeTask = tasksA.tasks.find((task) => task.title === "Runtime task");
    assert.deepEqual(canonicalTask.labels, ["qws-task-1"]);
    assert.deepEqual(canonicalTask.assignee, {
      type: "agent",
      id: "a".repeat(32),
      name: "林知远 · AI 员工 · 需求经理",
      avatarUrl: null,
    });
    assert.match(canonicalTask.description, /开发上下文（业务）/);
    assert.match(canonicalTask.description, /independent web/);
    assert.equal(canonicalTask.developmentContext, null);
    assert.equal(canonicalTask.participants.filter((actor) => actor.type === "agent").length, 6);
    assert.deepEqual(
      canonicalTask.participants.filter((actor) => actor.type === "agent").map((actor) => actor.name),
      [
        "林知远 · AI 员工 · 需求经理", "周砚 · AI 员工 · 产品经理", "许澄 · AI 员工 · 技术负责人",
        "程野 · AI 员工 · 测试经理", "沈星 · AI 员工 · 交付经理", "陆川 · AI 员工 · 评审人",
      ],
    );
    assert.equal(canonicalTask.status, "backlog", "QWS backlog tasks belong in the executable todo lane");
    assert.equal(runtimeTask.status, "todo", "WAITING_CLAIM remains separate and is not executable todo");
    assert.deepEqual(runtimeTask.developmentContext, {
      type: "branch",
      branch: "codex/runtime-task",
    });
    assert.equal(runtimeTask.relations.blockedBy.length, 1);
    assert.equal(runtimeTask.relations.parent?.id, canonicalTask.id);

    const aiCommentResponse = await fetch(`${origin}/api/tasks/${canonicalTask.id}/comments`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        cookie: cookieA,
        "x-qws-ai-employee-token": "qws-test-internal-token",
        "x-qws-ai-employee-id": "a".repeat(32),
        "x-qws-ai-employee-name": encodeURIComponent("林知远"),
      },
      body: JSON.stringify({ body: "AI 自动执行\n\n已完成需求核验。" }),
    });
    assert.equal(aiCommentResponse.status, 201);
    const aiComment = (await aiCommentResponse.json()).comment;
    assert.equal(aiComment.authorType, "agent");
    assert.equal(aiComment.authorId, "a".repeat(32));
    assert.equal(aiComment.authorName, "林知远");

    const blockedCard = await fetch(`${origin}/api/tasks/${canonicalTask.id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json", cookie: cookieA },
      body: JSON.stringify({ version: canonicalTask.version, status: "blocked" }),
    });
    assert.equal(blockedCard.status, 200);
    canonicalRevision = 2;
    const [resyncedSession, concurrentReplay] = await Promise.all([
      fetch(`${origin}/api/qws/session`, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: "Bearer tenant-a" },
        body: JSON.stringify({ project_id: "prj-sync" }),
      }),
      fetch(`${origin}/api/qws/session`, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: "Bearer tenant-a" },
        body: JSON.stringify({ project_id: "prj-sync" }),
      }),
    ]);
    assert.equal(resyncedSession.status, 200);
    assert.equal(concurrentReplay.status, 200, "concurrent QWS session sync is an idempotent replay");
    const tasksAfterResync = await fetch(`${origin}/api/tasks?projectId=qws-tenant-a-prj-sync&archived=false`, {
      headers: { cookie: cookieA },
    }).then((response) => response.json());
    assert.equal(
      tasksAfterResync.tasks.find((task) => task.id === canonicalTask.id).status,
      "blocked",
      "a runtime blocker must not return to waiting-for-claim after QWS refresh",
    );
    const canonicalAfterResync = tasksAfterResync.tasks.find((task) => task.id === canonicalTask.id);
    const runtimeAfterResync = tasksAfterResync.tasks.find((task) => task.id === runtimeTask.id);
    assert.equal(canonicalAfterResync.startDate, "2026-08-31");
    assert.equal(runtimeAfterResync.dueDate, "2026-09-01");
    assert.equal(runtimeAfterResync.relations.blockedBy.some((task) => task.id === canonicalTask.id), true);
    const forbiddenRelationWrite = await fetch(
      `${origin}/api/tasks/${canonicalTask.id}/relations/related/${runtimeTask.id}`,
      {
        method: "POST",
        headers: { "content-type": "application/json", cookie: cookieA },
        body: JSON.stringify({ version: canonicalAfterResync.version, origin: "manual" }),
      },
    );
    assert.equal(forbiddenRelationWrite.status, 409);
    assert.equal((await forbiddenRelationWrite.json()).error.code, "QWS_RELATION_READ_ONLY");

    canonicalRevision = 3;
    const driftRepair = await fetch(`${origin}/api/qws/session`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: "Bearer tenant-a" },
      body: JSON.stringify({ project_id: "prj-sync" }),
    });
    assert.equal(driftRepair.status, 200);
    const repairedTasks = await fetch(`${origin}/api/tasks?projectId=qws-tenant-a-prj-sync&archived=false`, {
      headers: { cookie: cookieA },
    }).then((response) => response.json());
    assert.equal(
      repairedTasks.tasks.find((task) => task.id === runtimeTask.id).relations.blockedBy.length,
      0,
      "QWS resync removes Taskboard relation drift when canonical relation disappears",
    );

    const invalidSession = await fetch(`${origin}/api/qws/session`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: "Bearer tenant-a" },
      body: JSON.stringify({ project_id: "prj-invalid" }),
    });
    assert.equal(invalidSession.status, 400);
    const projectsAfterInvalidSync = await fetch(`${origin}/api/projects`, {
      headers: { cookie: cookieA },
    }).then((response) => response.json());
    assert.equal(
      projectsAfterInvalidSync.projects.some((project) => project.id === "qws-tenant-a-prj-invalid"),
      false,
      "all task payloads must be validated before the project or its first task is written",
    );

    const sessionB = await fetch(`${origin}/api/qws/session`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: "Bearer tenant-b" },
      body: "{}",
    });
    const cookieB = sessionB.headers.get("set-cookie").split(";", 1)[0];
    const projectsB = await fetch(`${origin}/api/projects`, { headers: { cookie: cookieB } }).then((response) => response.json());
    assert.equal(projectsB.projects.some((project) => project.id === "qws-tenant-a-prj-sync"), false);
  } finally {
    if (previousInternalToken === undefined) delete process.env.HERMES_BRIDGE_INTERNAL_TOKEN;
    else process.env.HERMES_BRIDGE_INTERNAL_TOKEN = previousInternalToken;
    await app.close();
    await close(identityServer);
    await rm(dataDirectory, { recursive: true, force: true });
  }
});
