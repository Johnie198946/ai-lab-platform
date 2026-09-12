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
- `python3 -m compileall -q backend scripts/hermes_bridge.py`: 通过。
- `git diff --check`: 通过。
- 模拟器启动截图仅到启动页，未形成 PPT 工作流页面的有效视觉验收证据；未将其计为通过。
- 修订闭环: 大纲、版式和逐页反馈通过现有 retry 接口传入对应 Hermes 节点；回归测试确认修改意见进入下一版节点提示。
- 真机复查: iPhone“囧尼部落”（CoreDevice `CFE79F35-1270-527D-8BD7-9AB60449B6DF` / Xcode `00008150-000C50980244401C`）已连接。Debug 真机构建退出码 0；`com.ailab.AIPlatformApp` 安装和启动均成功。Xcode 的通知代理曾报告设备受密码保护，但未阻断构建、安装或启动。
- 真机联网验收: 当前 Debug 包固定连接 `https://120.24.248.58`；本任务后端未获部署授权，因此尚未执行新版本的真实文件上传、知识编译、PPT 下载和系统转发闭环，不得标记为 VERIFIED。

## 交付状态

- status: `TESTED`
- commit SHA: 未授权/未执行本地提交。
- GitHub remote/ref/SHA: 未授权/未执行 push；未执行 `git ls-remote` 推送核验。
- server_before: 未授权/未执行部署，不适用。
- server_after: 未授权/未执行部署，不适用。
- health_check: 未部署，不适用。
- functional_check: 后端回归、iOS 单测、模拟器编译、真机构建/安装/启动通过；新后端未部署，真机联网端到端未完成。
- rollback_point: 未部署；回滚方式为丢弃本独立克隆中的未提交变更。

## 风险与未完成项

- 真机已可用且应用已安装启动；尚缺新版本后端上的真实 iPhone 端到端操作证据。
- 未获得 push 与部署授权，远端和服务器仍运行基线版本，真机当前只能连接旧后端，无法验证本任务新增链路。
- 扫描版 PDF OCR 仍不在本任务范围，继续返回“无可提取文本”的明确错误。
