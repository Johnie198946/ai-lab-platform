# Completion Manifest — base-public-knowledge-v1-20260820

## Task

- task_id: `base-public-knowledge-v1-20260820`
- objective: 修复团队知识基础版“套餐已开通但知识为空”的产品与技术闭环；公共知识不足门槛时显示建设状态，达到门槛后自动授权绿色 K5，并将绿色公共知识与黄色知识包分开展示。
- current_status: `VERIFIED`

## Worktrees and branches

### Platform repository

- worktree: `/private/tmp/base-public-knowledge-v1`
- branch: `codex/base-public-knowledge-v1`
- base/head: `70aa5cb42eec9637c18ac24bfed00ed822d2c198`
- remote: `github=https://github.com/Johnie198946/ai-lab-platform.git`; `origin` 为本地仓库路径
- start status: 原工作区 `codex/showroom-visitor-session-v17` 含与本任务无关的重复 YAML、Showroom 音频和 HTML；未触碰、未混入本任务。

### Obsidian Vault repository

- worktree: `/private/tmp/base-public-knowledge-vault-v1`
- branch: `codex/base-public-knowledge-v1`
- base/head: `489429e00da05663d7254908259c204e074806f0`
- remote: 未配置
- start status: 原 Vault `main` 工作区有大量其他任务改动，且候选 Wiki 已被修改；本任务只在独立 Worktree 中新增外部来源卡，未覆盖原工作区。

## Changed files

### Platform

- `backend/services/knowledge_catalog.py`
- `backend/api/subscriptions.py`
- `backend/api/catalog.py`
- `ios/AIPlatformApp/Networking/APIClient.swift`
- `ios/AIPlatformApp/Views/Knowledge/KnowledgeView.swift`
- `ios/AIPlatformApp/Views/Settings/SettingsView.swift`
- `tests/test_subscription_center_api.py`
- `tests/test_base_knowledge_status.py`

### Vault source records

- `raw/sources/2026-08-20-postgresql-mvcc.md`
- `raw/sources/2026-08-20-cockroachdb-transaction-layer.md`
- `raw/sources/2026-08-20-json-schema.md`
- `raw/sources/2026-08-20-gvisor-security-model.md`
- `raw/sources/2026-08-20-deepseek-harness-repository.md`
- `raw/sources/2026-08-20-deepseek-harness-community-analysis.md`

## Implementation notes

- 后端从 Catalog 计算 `base_knowledge` 的 `building/ready`、文档数、分类数和编译时间；默认门槛 5 篇、2 个分类。
- Catalog 加载失败或出现不完整投影时保留上一份有效内存投影，不发布半成品。
- 基础版申请在公共知识未达到门槛时返回结构化 `base_knowledge_building`；已开通组织不被撤销。
- `/subscription-center` 与 `/me/knowledge-access` 分别返回基础公共知识和租户私有知识状态。
- iOS 将基础公共知识、黄色知识包和私有知识拆分展示；建设中有明确进度和自动开放说明。
- 公共知识发布仍 fail-closed。将条目标记为 `approved + green + K5` 会对全部正式租户开放，因方案要求人工安全审批，本任务未代替用户批准具体条目。

## Tests and validation

- focused Python regression: `21 passed`
  - `tests/test_base_knowledge_status.py`
  - `tests/test_subscription_center_api.py`
  - `tests/test_subscription_api.py`
  - `tests/test_knowledge_policy_v2.py`
- Swift build: `xcodebuild ... CODE_SIGNING_ALLOWED=NO build` → `BUILD SUCCEEDED`
- simulator install: bundle installed at `/Users/dengzhaoyu/Library/Developer/CoreSimulator/Devices/8386FBF2-321F-4F52-BF4C-337EF3780649/data/Containers/Bundle/Application/B4A0A7AB-6A7F-41C6-960E-3E73B59E7E42/AIPlatformApp.app`
- simulator launch: `com.ailab.AIPlatformApp: 45252`; launch/login screen screenshot captured successfully.
- `git diff --check`: passed for platform and Vault worktrees.
- full Python suite: collection blocked by existing dependency incompatibility in `tests/test_agents_api.py` (`starlette.TestClient` passes removed `httpx.Client(app=...)` argument). This failure occurs before task tests and is not introduced by changed files.

## Delivery evidence

- integration commit: `befef66`，已整合进平台 `main`；最终部署代码 SHA 为 `59755d1705dd3220fdad29401f844b78eac2774b`。
- GitHub remote/ref/SHA: `refs/heads/main` 已经 `git ls-remote` 核验到部署代码 SHA `59755d1705dd3220fdad29401f844b78eac2774b`；无 force push。
- server_before: `/opt/releases/ai-lab-platform-f6f8cfd`，`.deploy-commit=f6f8cfd3b10df100b3f5cde16b6a82fb35e651c9`。
- server_after: `/opt/releases/ai-lab-platform-59755d1`，`.deploy-commit=59755d1705dd3220fdad29401f844b78eac2774b`。
- health_check: 内外 `/health` 均为 `{"status":"ok","version":"0.8.0"}`，7 个服务运行，部署后 API error 为 0。
- functional_check: 生产容器内基础知识 `ready`，11 篇、2 分类，Catalog 2 项且均为绿色；本地受影响后端测试 26/26 通过。
- rollback_point: `/opt/releases/ai-lab-platform-04a688b`；原始回退点 `/opt/releases/ai-lab-platform-f6f8cfd` 仍保留。

## Remaining risks and blockers

- 尚需用户明确批准具体 Wiki 条目作为绿色公共知识。批准前 Catalog 继续为 0，基础版正确显示“建设中”。
- 当前候选中“Agent 协议签署功能”和“展厅输出物格式协议”包含内部产品实现；若公开，所有正式租户均可检索，建议不要作为基础公共知识。
- 首批 5 篇批准并编译后，仍需验证搜索、聊天、Agent 与工作流四条真实检索链路。
- 生产验证已经通过；公共知识后续内容更新仍须继续遵守人工安全审批。
