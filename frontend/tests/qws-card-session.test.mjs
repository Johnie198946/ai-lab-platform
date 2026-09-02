import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { composeClarificationResponse, isOtherClarificationChoice, normalizedClarificationChoice } from "../src/features/quantum-workspace/hermesClarification.js";
import { extractProjectBlueprint, extractProjectBlueprintProtocol, projectPlanningNaturalReply, projectPlanningVisibleAnswer } from "../src/features/quantum-workspace/projectBlueprintPresentation.js";

const hostSource = await readFile(
  new URL("../src/features/quantum-workspace/DashiTaskboardHost.jsx", import.meta.url),
  "utf8",
);
const drawerSource = await readFile(
  new URL("../src/features/quantum-workspace/TaskChatDrawer.jsx", import.meta.url),
  "utf8",
);
const clarificationSource = await readFile(
  new URL("../src/features/quantum-workspace/HermesClarificationCard.jsx", import.meta.url),
  "utf8",
);
const planningSource = await readFile(
  new URL("../src/features/quantum-workspace/ProjectPlanningDialog.jsx", import.meta.url),
  "utf8",
);
const blueprintReviewSource = await readFile(
  new URL("../src/features/quantum-workspace/ProjectBlueprintReview.jsx", import.meta.url),
  "utf8",
);
const executionTraceSource = await readFile(
  new URL("../src/features/quantum-workspace/HermesExecutionTrace.jsx", import.meta.url),
  "utf8",
);
const homeSource = await readFile(
  new URL("../src/features/quantum-workspace/WorkspaceHomePage.jsx", import.meta.url),
  "utf8",
);
const frontendDockerfile = await readFile(
  new URL("../Dockerfile", import.meta.url),
  "utf8",
);
const backendSource = await readFile(
  new URL("../../backend/api/quantum_workspace.py", import.meta.url),
  "utf8",
);

test("opening a card session never creates a canonical task in the web host", () => {
  const openHandler = hostSource.slice(hostSource.indexOf('event.data.type !== "taskboard:create-thread"'));
  assert.doesNotMatch(openHandler, /createProjectTask/);
  assert.match(hostSource, /resolveCanonicalTask/);
  assert.match(hostSource, /binding_kind: "taskboard_card"/);
  assert.match(openHandler, /onOpenTaskChat\?\.\(\{/);
  assert.doesNotMatch(hostSource, /dashiRequest\("\/api\/tasks",\s*\{\s*method: "POST"/);
  assert.match(hostSource, /body: JSON\.stringify\(\{ project_id: project\.id \}\)/);
});

test("single-card execution opens the live progress drawer instead of starting invisibly", () => {
  const start = hostSource.indexOf('event.data.type === "taskboard:run-task"');
  const end = hostSource.indexOf('event.data.type === "taskboard:run-project-todos"');
  const singleRunHandler = hostSource.slice(start, end);
  assert.match(singleRunHandler, /onOpenTaskChat\?\.\(\{/);
  assert.match(singleRunHandler, /autoInstruction: batchAutoInstruction/);
  assert.match(singleRunHandler, /refreshCardContext/);
  assert.match(singleRunHandler, /可实时查看进度与失败日志/);
  assert.doesNotMatch(singleRunHandler, /startTaskAutoExecution/);
});

test("card session sends versionable full card context to the backend", () => {
  for (const field of [
    "business_goal",
    "parent_issue",
    "descriptions",
    "sub_issues",
    "comments",
    "status",
    "priority",
    "assignee",
    "labels",
    "development_context",
    "start_date",
    "due_date",
    "recurrence",
    "attachments",
    "related_issues",
  ]) assert.match(hostSource, new RegExp(field));
  assert.match(drawerSource, /card_context: cardContext/);
  assert.match(drawerSource, /contextSync\.mode === "incremental"/);
  assert.match(hostSource, /项目概览、项目纲领文档、相关任务档案与规划历史已作为本次只读上下文直接提供/);
  assert.match(hostSource, /非关键或可后补的信息不得作为阻塞理由/);
});

test("card backfill requires confirmation and routes overflow through session inbox", () => {
  assert.match(hostSource, /session_registry/);
  assert.doesNotMatch(hostSource, /method: "PATCH"/);
  assert.match(backendSource, /async def _apply_taskboard_backfill/);
  assert.match(backendSource, /"createIssues"/);
  assert.match(backendSource, /"addAttachments"/);
  assert.match(backendSource, /"relationChanges"/);
  assert.match(backendSource, /relations\/parent/);
  assert.match(drawerSource, /materializeTaskBackfillProposal/);
  assert.match(drawerSource, /window\.confirm/);
  assert.match(drawerSource, /completeTaskBackfillProposal/);
  assert.match(drawerSource, /applyTaskBackfillProposal/);
  assert.match(drawerSource, /确认回填/);
  assert.match(drawerSource, /BackfillChangeList/);
  assert.match(backendSource, /"Host": "127\.0\.0\.1"/);
  assert.match(drawerSource, /再次点击“确认回填”重试/);
});

test("card session presents and routes through the project AI employee", () => {
  assert.match(backendSource, /_ensure_project_ai_employees/);
  assert.match(backendSource, /"qws_employee"/);
  assert.match(backendSource, /agent_id=\(None if planning_session else str\(\(conversation\.binding/);
  assert.match(drawerSource, /AI Lab · AI 员工 Session/);
  assert.match(drawerSource, /aiEmployee\.display_name/);
  assert.match(drawerSource, /AI Lab AI 员工/);
});

test("card session renders and submits Hermes clarification instead of waiting silently", () => {
  assert.match(drawerSource, /streamEvent\.type === "clarify"/);
  assert.match(clarificationSource, /AI 需要补充信息/);
  assert.match(drawerSource, /submitTaskClarification/);
  assert.match(drawerSource, /clarify_id: clarification\.clarify_id/);
  assert.match(drawerSource, /等待你补充信息/);
  assert.equal(isOtherClarificationChoice("Other"), true);
  assert.equal(isOtherClarificationChoice({ label: "其他（请填写）", value: "other" }), true);
  const choices = ["部署到内网", "Other"].map(normalizedClarificationChoice);
  assert.equal(composeClarificationResponse(choices, ["部署到内网", "Other"], "需要离线部署"), "部署到内网；其他：需要离线部署");
  assert.match(clarificationSource, /isOtherClarificationChoice/);
  assert.match(clarificationSource, /请补充具体信息/);
  assert.match(clarificationSource, /这段内容会原样交给 Hermes/);
  assert.match(clarificationSource, /composedResponse/);
});

test("same-origin Taskboard iframe is not blocked by the production proxy", () => {
  const taskboardBlocks = frontendDockerfile.match(/location \/taskboard\/ \{[\s\S]*?    \}\\n\\/g) || [];
  assert.equal(taskboardBlocks.length, 2);
  for (const block of taskboardBlocks) {
    assert.match(block, /proxy_hide_header X-Frame-Options/);
    assert.match(block, /add_header X-Frame-Options "SAMEORIGIN" always/);
    assert.match(block, /Content-Security-Policy "frame-ancestors \$scheme:\/\/\$host"/);
  }
});

test("planning stream follows new output but completed review keeps user scroll position", () => {
  assert.match(planningSource, /messages\.some\(\(item\) => item\.role === "assistant" && item\.pending\)/);
  assert.match(planningSource, /scrollTo\(\{ top: messagesRef\.current\.scrollHeight \}\)/);
  assert.doesNotMatch(planningSource, /useEffect\(\(\) => \{ messagesRef\.current\?\.scrollTo/);
});

test("new projects automatically enter the shared Hermes clarification protocol", () => {
  assert.match(planningSource, /trigger: "project_created"/);
  assert.match(planningSource, /project-intake-\$\{project\.id\}/);
  assert.match(planningSource, /HermesClarificationCard/);
  assert.match(planningSource, /submitTaskClarification/);
  assert.match(planningSource, /activeConversation\.binding\?\.session_id/);
  assert.match(backendSource, /"system" if body\.trigger == "project_created"/);
  assert.match(backendSource, /use the same Hermes clarify capability as the iOS main session/);
  assert.match(backendSource, /持续询问用户至需求收敛/);
});

test("unfinished project planning can be resumed and deletion has explicit progress", () => {
  assert.match(homeSource, /继续 AI 生成/);
  assert.match(homeSource, /planning_state === "dispatched"/);
  assert.match(homeSource, /deletingProjectId/);
  assert.match(homeSource, /删除中…/);
  assert.match(planningSource, /resumeNeeded/);
  assert.match(planningSource, /上次 AI 生成尚未完成/);
});

test("dispatch persists a structured task contract for every card session", () => {
  assert.match(backendSource, /_seed_project_session_registry/);
  assert.match(backendSource, /_task_registry_profile/);
  for (const field of ["goal", "current_state", "progress", "acceptance_criteria", "deliverables", "handoff"]) {
    assert.match(backendSource, new RegExp(`"${field}"`));
  }
  assert.match(backendSource, /"task_profile": row\.task_profile/);
});

test("card session exposes safe skill execution progress without chain-of-thought", () => {
  const executionSources = `${drawerSource}\n${executionTraceSource}`;
  for (const eventType of [
    "status",
    "triage_route",
    "capability_route",
    "tool_start",
    "tool_complete",
  ]) assert.match(executionSources, new RegExp(eventType));
  assert.match(executionTraceSource, /候选技能/);
  assert.match(executionTraceSource, /模型响应较慢/);
  assert.match(executionTraceSource, /最近活动距今/);
  assert.match(executionTraceSource, /总耗时不受 60 秒首活动时限限制/);
  assert.doesNotMatch(executionSources, /chain.of.thought|思维链/i);
});

test("project planning reuses the safe Hermes execution trace", () => {
  assert.match(planningSource, /HermesExecutionTrace/);
  assert.match(planningSource, /updateHermesExecution/);
  assert.match(planningSource, /variant="planning"/);
  assert.match(executionTraceSource, /planning_context/);
  assert.match(executionTraceSource, /候选技能/);
  assert.match(executionTraceSource, /不是页面卡死/);
  assert.match(executionTraceSource, /当前阶段已持续/);
  assert.match(executionTraceSource, /总耗时不受 60 秒首活动时限限制/);
  assert.doesNotMatch(executionTraceSource, /chain.of.thought|思维链/i);
});

test("project planning exposes blueprint protocol beside the natural summary", () => {
  const partial = "方案已收敛。\n```project_blueprint\n{\"project_goal\":\"建设人脸识别门禁\",\"stages\":[";
  assert.equal(projectPlanningVisibleAnswer(partial, { pending: true }), "方案已收敛。");
  assert.doesNotMatch(projectPlanningVisibleAnswer(partial, { pending: true }), /project_goal|stages|```/);
  assert.deepEqual(extractProjectBlueprintProtocol(partial), {
    payload: '{"project_goal":"建设人脸识别门禁","stages":[',
    complete: false,
  });

  const blueprint = {
    project_goal: "建设人脸识别门禁",
    stages: [{ key: "plan", name: "方案设计", acceptance_criteria: ["需求已确认"] }, { key: "delivery", name: "开发交付" }],
    tasks: [
      { key: "T1", stage_key: "plan", title: "确认业务需求", role: "产品经理", deliverables: ["需求说明书"] },
      { key: "T2", stage_key: "delivery", title: "设计系统架构", role: "架构师", deliverables: ["架构图"] },
    ],
    documents: [{ id: "D1", title: "项目实施方案" }],
  };
  const completed = `蓝图可供确认。\n\`\`\`project_blueprint\n${JSON.stringify(blueprint)}\n\`\`\``;
  assert.deepEqual(extractProjectBlueprint(completed), blueprint);
  assert.equal(extractProjectBlueprintProtocol(completed).complete, true);
  assert.match(extractProjectBlueprintProtocol(completed).payload, /"project_goal": "建设人脸识别门禁"/);
  const visible = projectPlanningVisibleAnswer(completed);
  assert.match(visible, /项目蓝图已经整理完成，共 2 个阶段、2 项任务和 1 份项目文档/);
  assert.match(visible, /项目目标：建设人脸识别门禁/);
  assert.match(visible, /执行流程：方案设计 → 开发交付/);
  assert.match(visible, /1\. 方案设计：确认业务需求/);
  assert.match(visible, /关键验收：需求已确认/);
  assert.match(visible, /产品经理、架构师/);
  assert.doesNotMatch(visible, /project_goal|stages|tasks|```|\{|\}/);

  const generic = `蓝图已合并。\n\`\`\`json\n${JSON.stringify(blueprint)}\n\`\`\``;
  assert.deepEqual(extractProjectBlueprint(generic), blueprint);
  assert.equal(projectPlanningNaturalReply(generic), "蓝图已合并。");
  assert.doesNotMatch(projectPlanningVisibleAnswer(generic), /project_goal|```json|\{/);

  const bare = `更新后的完整方案：\n${JSON.stringify(blueprint)}`;
  assert.deepEqual(extractProjectBlueprint(bare), blueprint);
  assert.equal(projectPlanningNaturalReply(bare), "更新后的完整方案：");
  assert.equal(projectPlanningVisibleAnswer('正在整理。\n{"project_goal":"门禁","stages":[', { pending: true }), "正在整理。");
});

test("project planning rejects false done terminals and exposes one controlled repair", () => {
  assert.match(backendSource, /phase": "blueprint_repair"/);
  assert.match(backendSource, /missing_project_blueprint/);
  assert.match(backendSource, /terminal_type == "planning_incomplete"/);
  assert.match(backendSource, /Do not ask another clarification in this repair pass/);
  assert.match(backendSource, /Hermes SessionDB is the sole dialogue-history source/);
  assert.match(backendSource, /qws_business_context=qws_business_context/);
  assert.match(backendSource, /client_session_context=None/);
  assert.match(planningSource, /eventValue\.type === "planning_incomplete"/);
  assert.match(planningSource, /setPlanningNotice\(detail\)/);
  assert.match(planningSource, /蓝图未通过完整性校验/);
  assert.match(executionTraceSource, /blueprint_repair/);
});

test("project planning treats new user input as a merged convergence revision", () => {
  assert.match(planningSource, /latestBlueprintVersion/);
  assert.match(planningSource, /继续补充或修订收敛单/);
  assert.match(planningSource, /ProjectBlueprintReview/);
  assert.match(planningSource, /setBlueprintRequestId\(""\)/);
  assert.match(backendSource, /current_convergence_sheet_version/);
  assert.match(backendSource, /preserve every unaffected confirmed fact/);
  assert.match(backendSource, /Never start a parallel or unrelated planning flow/);
});

test("confirmed blueprint is fully human-editable and dispatches the saved revision", () => {
  assert.match(blueprintReviewSource, /人工修订需求确认单/);
  assert.match(blueprintReviewSource, /新增阶段/);
  assert.match(blueprintReviewSource, /新增任务/);
  assert.match(blueprintReviewSource, /新增文档/);
  assert.match(blueprintReviewSource, /验收标准（每行一条）/);
  assert.match(blueprintReviewSource, /交付物（每行一项）/);
  assert.match(blueprintReviewSource, /const draftLines = \(value\) => String\(value \|\| ""\)\.split\("\\n"\)/);
  assert.match(blueprintReviewSource, /onSave\(normalizedBlueprint\(draft\)\)/);
  assert.match(planningSource, /reviewBlueprint/);
  assert.match(planningSource, /blueprint: reviewBlueprint/);
  assert.match(planningSource, /project_blueprint_revision/);
  assert.match(planningSource, /检查人工修改/);
  assert.match(planningSource, /保留用户改动，修复受影响字段/);
  assert.match(planningSource, /严格按你在当前页面保存后的需求确认单/);
});
