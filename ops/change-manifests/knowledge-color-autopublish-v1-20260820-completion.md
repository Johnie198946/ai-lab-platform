# Knowledge Color Autopublish V1 Completion Manifest

- `task_id`: `knowledge-color-autopublish-v1-20260820`
- `status`: `TESTED`
- `branch`: `codex/knowledge-color-autopublish-v1`
- `worktree`: `/private/tmp/knowledge-color-autopublish-v1`
- `head/local_commit`: `70aa5cb42eec9637c18ac24bfed00ed822d2c198`（未创建本地 commit）

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

## 外部系统与发布状态

- `commit SHA`: 未授权提交，未执行。
- `GitHub remote/ref/SHA`: 未授权 push，未执行；未声明 `PUSHED`。
- `server_before`: 未授权部署，未检查。
- `server_after`: 未授权部署，未执行。
- `health_check`: 本地测试通过；服务器健康检查未执行。
- `functional_check`: 本地后端测试与 iOS 编译通过；未覆盖安装模拟器，也未做生产联调。
- `rollback_point`: Git 基线 `70aa5cb42eec9637c18ac24bfed00ed822d2c198`；本任务未部署服务器。

## 风险与未完成项

- 本仓库没有 Authen 服务源码。本任务已实现 Platform 侧 Yellow 签名事件发送、幂等事件标识和失败回滚，但 Authen 必须实现并部署 `POST /api/v1/internal/knowledge-pack-approvals` 的验签、知识包注册与权益版本递增，Yellow 链路才能端到端生效。
- Green 和 Red 的 Platform 投影已实现并通过本地测试，但当前代码尚未提交、推送、部署或安装到模拟器，所以现有 App 截图不会自动变化。
- 管理员审批操作会修改 Vault Wiki Frontmatter；本轮为避免污染当前脏 Vault，没有对真实知识条目执行批准。
- 生产启用前仍需验证缓存失效、Catalog 重编译、Authen 乱序/重复事件、跨租户 Yellow/Red 隔离以及 iOS 真机/模拟器交互。

## 回滚说明

本任务尚未提交或部署。若需放弃本地实现，可删除独立 Worktree 和任务分支；不得对源工作区或其他任务 Worktree 执行重置或清理。
