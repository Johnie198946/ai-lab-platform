# Knowledge Color Autopublish V1 Completion Manifest

- `task_id`: `knowledge-color-autopublish-v1-20260820`
- `status`: `VERIFIED`
- `branch`: `codex/knowledge-color-autopublish-v1`
- `worktree`: `/private/tmp/knowledge-color-autopublish-v1`
- `head/local_commit`: `282e1191fd60f0b8987fa4050d1ecc22fca28c7d`（运行时代码提交；最终清单另有后续提交）

## 任务目标

将知识授权从“必须累计 5 篇 K5 才可发布”收敛为一次明确的管理员审批操作：

- Green：管理员批准后立即进入公共知识投影。
- Yellow：管理员批准后，通过签名事件注册精确 `entitlement_key`；Knowledge Gateway 仅向已订阅该知识包的租户放行。
- Red：管理员批准后，仅向 `owner_tenant` 放行。
- K5、来源数量和新鲜度继续作为质量指标，但不再作为权限发布开关。
- 缺失颜色、非法颜色或未批准内容继续 fail-closed。

## 开工前 Git 盘点

- `status`: 独立任务 Worktree 创建后为 clean；源工作区 `/Users/dengzhaoyu/Documents/AI Lab/ai-lab-platform-showroom` 存在大量其他任务和用户改动，未覆盖、暂存或混入本任务。
- `branch`: `codex/knowledge-color-autopublish-v1`
- `HEAD`: `70aa5cb42eec9637c18ac24bfed00ed822d2c198`
- `remote`:
  - `github`: `https://github.com/Johnie198946/ai-lab-platform.git`
  - `origin`: `/Users/dengzhaoyu/Desktop/AI Lab/ai-lab-platform`
- `worktree`: `/private/tmp/knowledge-color-autopublish-v1`

## 变更文件

- `backend/main.py`
- `backend/api/knowledge_publication.py`
- `backend/services/knowledge_catalog.py`
- `backend/services/knowledge_color_projection.py`
- `ios/AIPlatformApp/Networking/APIClient.swift`
- `ios/AIPlatformApp/Views/Settings/SettingsView.swift`
- `tests/test_knowledge_color_autopublish.py`
- `ops/change-manifests/knowledge-color-autopublish-v1-20260820-completion.md`
- `.env.example`
- `docker-compose.yml`

## 关键实现

1. 新增颜色审批与直接投影服务。只有显式颜色且 `classification_status=approved` 的条目才会进入知识投影。
2. 管理员可以在 iOS 订阅中心一次完成颜色、Yellow 精确权益 Key 或 Red 租户归属的审批。
3. Green 审批成功后刷新 Catalog 与搜索缓存；不再要求先凑齐 5 篇 K5。
4. Yellow 审批使用 HMAC 签名事件通知 Authen；Authen 失败时恢复原 Frontmatter，避免平台与权益真源产生半成功状态。
5. iOS 将“全部建设中/K5 发布门槛”改为“等待内容批准/已批准条目”，并提供清晰的审批、加载、错误和禁用状态。

## 测试与校验

- Python：`25 passed`
  - `tests/test_knowledge_color_autopublish.py`
  - `tests/test_subscription_api.py`
  - `tests/test_knowledge_policy_v2.py`
  - `tests/test_knowledge_api.py`
- Python 编译：`python3 -m compileall -q backend`，通过。
- Swift：使用 iPhone Simulator 通用目标执行 `xcodebuild`，结果 `BUILD SUCCEEDED`。
- Git whitespace：`git diff --check`，通过。
- UI/UX：按 `ui-ux-pro-max` 规则复核了加载反馈、防重复提交、44pt 触控区域、状态文案和原生控件使用。
- Authen 兼容端：`tests/test_knowledge_pack_subscriptions.py`，`2 passed`；Python compileall 通过。

## 外部系统与发布状态

- `commit SHA`: 平台运行时代码 `282e1191fd60f0b8987fa4050d1ecc22fca28c7d`；Authen 服务器兼容代码本地 commit `f369e8a`。
- `GitHub remote/ref/SHA`: `github/codex/knowledge-color-autopublish-v1` 已经 `git ls-remote` 核对为 `282e1191fd60f0b8987fa4050d1ecc22fca28c7d`（最终清单提交后再次核对远端 ref）。用户明确项目仓库仅为 `Johnie198946/ai-lab-platform`，因此未向独立 Authen 仓库推送。
- `server_before`: `/opt/ai-lab-platform` Git HEAD `f0119b980c144ffddca7ea7aaa813c4e26ec8bcd`；API image `sha256:91f1963290174bb5fb1394b0f072d7362bdbb1f14458ecd909a25af1063fc059`；Authen HEAD `1cb1a8cdcf745771aec2f76ffcbfe2a69b78dd7b`。
- `server_after`: `/opt/ai-lab-platform/.deploy-commit=282e1191fd60f0b8987fa4050d1ecc22fca28c7d`；API image `sha256:16f4603fc1f2e2e1801ab3104f7c86d39d2db5b78edd8c5b2b0ced286ca34e91`；`.authen-compat-version=f369e8a8-authen-local-compat`。
- `health_check`: Platform `/health` 返回 `{"status":"ok","version":"0.8.0"}`；API 容器 `healthy`；Authen systemd `active` 且根端点返回 `{"service":"订阅服务","status":"running"}`。
- `functional_check`: Platform 两个知识发布审批路由和 Authen 签名接收路由均出现在生产 OpenAPI；容器确认审批密钥已注入；正确签名的未登记知识包请求返回预期 `404 registered knowledge pack not found`，证明验签通过且未修改业务数据。iOS 在设备 `8386FBF2-321F-4F52-BF4C-337EF3780649` 构建成功、覆盖安装并启动，PID `4488`。
- `rollback_point`: `/opt/rollback-points/knowledge-color-autopublish-v1-20260820-170853`，包含平台/Authen 源码、部署前 Git 状态、Docker 镜像清单、`ai_lab.dump` 与 `auth.dump`。

## 风险与未完成项

- Authen 兼容端已经部署并验证，但按用户要求没有推送到独立 `Johnie198946/Authen` 仓库；其可追溯来源为本地 Worktree `/private/tmp/authen-knowledge-color-approval-v1` 的 commit `f369e8a` 和服务器回滚点。后续若独立维护 Authen，应将该提交纳入其正式发布链。
- 管理员审批会修改 Vault Wiki Frontmatter。本轮没有擅自挑选或批准真实知识条目，因此未执行会改变知识权限的正向生产审批；正向与幂等行为由本地自动化测试覆盖。
- 生产工作区在部署前已有其他任务留下的大量修改；本轮只在确认生产文件与任务基线 SHA-256 完全相等后定向覆盖 9 个文件，没有整仓清理或回退其他功能。
- 仍建议补充一次由用户选择真实 Green 与 Yellow 条目的端到端业务验收，以及 iOS 真机、VoiceOver 和 Dynamic Type 人工验收。

## 回滚说明

回滚时先停止 API/Authen 写入，使用 `/opt/rollback-points/knowledge-color-autopublish-v1-20260820-170853` 恢复两套源码；如产生业务写入，再分别使用 `ai_lab.dump` 和 `auth.dump` 恢复数据库，然后恢复部署前 Docker 镜像并执行健康检查。不得对其他任务 Worktree 执行重置或清理。
