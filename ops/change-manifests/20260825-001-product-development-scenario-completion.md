---
task_id: 20260825-001-product-development-scenario
status: VERIFIED
branch: main
scope: frontend/src/app/App.jsx; frontend/src/pages/ArchitectWorkbenchPage.jsx; frontend/src/pages/ScenarioEntryPage.jsx; frontend/src/pages/ScenarioEntryPage.css; frontend/src/auth/entryRoute.js; frontend/tests/showroom-routing.test.mjs
change_type: CODE_RELEASE
---

# 001 产品开发预制场景工作台发布收据

## 交付内容

- 增加 `/scenarios` 预制场景入口。
- 首个场景为“001 产品开发”。
- 展示 IPD 阶段、Agent 分工、预期交付物和执行边界。
- 点击场景后创建服务端 Workflow，并跳转到现有 Architect 工作台。
- Architect 工作台支持通过 `workflow` 查询参数加载刚创建的任务。
- 展示账号默认入口从 `/architect` 调整为 `/scenarios`。
- 不新增 Agent Runtime；执行仍由现有 AI Lab/Hermes API 负责。

## 验证

- 本地 `npm run build`: passed。
- 本地 `npm run test`: passed, 84/84。
- GitHub main SHA: `ad4d0a7a974a8aba34e28717fd8fc257252506a7`。
- server_before: `f47f29d10a32f8cbdf3a947b95204c2bf56f6fa1`。
- server_after: `ad4d0a7a974a8aba34e28717fd8fc257252506a7`。
- API health: passed, `{"status":"ok","version":"0.8.0"}`。
- `/scenarios`: HTTP 200。
- 登录验收：`showroom_demo` 登录 HTTP 200，浏览器进入 `/scenarios`。
- Workflow API：同一认证会话创建“001 产品开发”返回 HTTP 201。

## 回滚

将服务器部署到 `f47f29d10a32f8cbdf3a947b95204c2bf56f6fa1`，执行：

```bash
cd /opt/ai-lab-platform && bash scripts/update.sh f47f29d10a32f8cbdf3a947b95204c2bf56f6fa1
```

## 剩余风险

- 当前只有一个预制场景，其他场景后续按同一数据/页面结构增加。
- 展示账号密码为临时弱密码，后续应通过 Authen 密码修改流程轮换。
- 尚未在本次验收中启动 Hermes 真实模型执行，避免替用户消耗额度；已验证工作台对现有 Workflow API 的创建对接。
