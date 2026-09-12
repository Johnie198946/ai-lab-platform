# Completion Manifest

- task_id: `20260913-document-upload-ppt-note-preview`
- 目标: 补齐 PDF/DOCX 上传后的聊天卡片封面、知识入库和处理状态，并将文档转 PPT 重设计为“演示需求单—文档分析—逐页大纲—真实内容代表页—全稿逐页验收—下载分享”。
- 判定: 部分实现。原件存储/解析、知识贡献队列、版本化审批、修订重跑和 PPTX/PDF 输出均已存在；缺少上传文档落用户笔记、实时编译状态、演示专用需求问题、独立分析阶段与清晰的五段式 UI。

## 变更文件

- `backend/api/documents.py`
- `backend/api/workflows.py`
- `backend/services/document_sources.py`
- `backend/services/presentation_scenario.py`
- `backend/services/workflow_executor.py`
- `ios/AIPlatformApp/Models/UIModels.swift`
- `ios/AIPlatformApp/Networking/APIClient.swift`
- `ios/AIPlatformApp/Services/InboxFileManager.swift`
- `ios/AIPlatformApp/Views/Chat/Cards/AttachmentCard.swift`
- `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`
- `ios/AIPlatformApp/Views/Workflows/WorkflowDashboardView.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
- `scripts/hermes_bridge.py`
- `tests/test_document_presentation.py`
- `ops/change-manifests/20260913-document-upload-ppt-note-preview-completion.md`

## 开工前 Git 盘点

- status: 独立克隆初始为 `## main...origin/main`，无本地改动；原工作目录存在用户未跟踪 manifest，因此未在原目录修改。
- branch: `main`（遵循项目内 AGENTS.md 的仅 main 规则）
- HEAD: `6c50ae187443a33c0ae43e0b10d9f72b335c7fd8`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/quantum-document-ppt-e2e-20260913`

## 测试与校验

- `python3 -m pytest tests/test_document_presentation.py tests/test_workflows_api.py tests/test_knowledge_sync_api.py tests/test_v4_all_source_enqueue_hooks.py -q`: `81 passed, 1 skipped`。
- iOS `WorkflowLifecycleDTOTests`: 通过，进程退出码 0。
- iPhone 17 Pro 模拟器 Debug build（关闭签名）: 通过。
- 用户截图复核发现上传消息仍显示为紫色正文气泡且大小为 `0 KB`。根因是用户消息渲染分支未分发已存在的 `.attachment` block，同时文件大小在 security-scoped 访问开始前读取。已复用 `AttachmentCard` 修复两处断点；新增用户附件消息布局回归测试通过，修复后真机 Build 35 构建、覆盖安装、版本回读和启动通过。
- `python3 -m compileall -q backend scripts/hermes_bridge.py`: 通过。
- `git diff --check`: 通过。
- 模拟器启动截图仅到启动页，未形成 PPT 工作流页面的有效视觉验收证据；未将其计为通过。
- 修订闭环: 大纲、版式和逐页反馈通过现有 retry 接口传入对应 Hermes 节点；回归测试确认修改意见进入下一版节点提示。
- 真机复查: iPhone“囧尼部落”（CoreDevice `CFE79F35-1270-527D-8BD7-9AB60449B6DF` / Xcode `00008150-000C50980244401C`）已连接。Debug 真机构建退出码 0。首次安装误选旧 DerivedData，手机回读为 `1.0.3 (20)`；经用户指出后定位正确产物 `AIPlatformApp-fdywafccmdyztcgguzlhahizprfd`，构建时间 `2026-09-13 01:51:40`，覆盖安装后真机回读为 `1.0.3 (35)`，并成功启动。旧包安装不计验收证据。
- 真机联网验收: 当前 Debug 包固定连接 `https://120.24.248.58`；新后端已部署，但尚未完成修复后卡片视觉回读、知识编译、PPT 下载和系统转发闭环，不得标记为 VERIFIED。
- TestFlight Build 36: 以 `9f15880100828b71ab1de8a9901bd6449c38cb66` 归档，祖先包含文档卡片修复 `37838f87c0f4f6ded3502248595db35c60828318`、Token 卡片简化 `f29583f` 与用量修复 `6d4e5ba`。8 个文档/Token 定向 iOS 测试通过；Release archive 为 `/Users/dengzhaoyu/Library/Developer/Xcode/Archives/2026-09-13/Quantumn-1.0.3-36.xcarchive`，包内版本 `1.0.3 (36)`，Team `AALA948YY5`，arm64，二进制 SHA-256 `638f59147ed5691c9c8ed5f72de25ae1af7177fa3568eca26c1d3a94fd85105f`。App Store Connect 返回 `Uploaded package is processing`、`Upload succeeded` 与 `EXPORT SUCCEEDED`。

## 交付状态

- status: `DEPLOYED`
- commit SHA: 后端/工作流实现 `49444561a5f9d24c75877ece62d9b6bca901401f`；文档卡片渲染修复 `37838f87c0f4f6ded3502248595db35c60828318`；Build 36 归档提交 `9f15880100828b71ab1de8a9901bd6449c38cb66`。
- GitHub remote/ref/SHA: Build 36 归档提交已推送至 `Johnie198946/ai-lab-platform/main` 并经 `git ls-remote` 核验；生产部署源 `Johnie198946/Quantum` 包含等价文档卡片修复提交 `f19d877dce95d1c22a358a1c40d38b7791a66476`。
- server_before: `.deployed-sha=97d3990385cb74886785ec37d4cb30f951c0f555`；release `/opt/releases/ai-lab-platform-97d3990385cb.A30r2r`；API 与主要 Compose 服务 healthy。
- server_after: `.deployed-sha=49444561a5f9d24c75877ece62d9b6bca901401f`；release `/opt/releases/ai-lab-platform-49444561a5f9.SAz0Ib`；API 与 workflow worker 镜像 revision 均为目标 SHA。
- health_check: exact-SHA 部署完成 6/6；API `/ready` 返回 `{"status":"ready","version":"0.8.0"}`，公网 HTTPS `/health` 返回 HTTP 200，Hermes Bridge v6 经容器实际路径返回 healthy，API 和两个 Hermes systemd 单元 active。
- functional_check: 后端回归、iOS 单测、附件卡片与 Token 卡片定向回归、模拟器编译、正确 Build 35 真机构建/安装/启动、Build 36 Release archive 与 TestFlight 上传通过；生产运行契约审计通过。真机卡片视觉回读及后续联网端到端仍待完成。
- rollback_point: `/opt/releases/ai-lab-platform-97d3990385cb.A30r2r`；附加 root-only 镜像/证明检查点 `/opt/ai-lab-shared/deployment-checkpoints/20260913-document-ppt-49444561`。

## 风险与未完成项

- 真机已回读确认安装并启动正确 Build 35；尚缺新版本后端上的真实 iPhone 端到端操作证据。
- 生产已部署新后端；必须在解锁真机上完成真实文件上传、笔记出现、多轮大纲/版式确认、PPT 下载和系统分享，才可升级为 `VERIFIED`。
- Apple 已接收 Build 36，但仍在处理；TestFlight 测试组可见性尚未独立回读，不把“上传成功”扩大表述为“测试员已可安装”。
- 扫描版 PDF OCR 仍不在本任务范围，继续返回“无可提取文本”的明确错误。
