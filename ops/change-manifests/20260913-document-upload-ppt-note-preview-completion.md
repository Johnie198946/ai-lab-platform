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
- 五项缺陷修订回归：`python3 -m pytest tests/test_document_presentation.py -q` 为 `25 passed, 1 skipped`；`WorkflowLifecycleDTOTests` 全套 `138 passed`；CAS 编码定向测试及审批门无损编码定向测试各 `1 passed`。
- 修订真机构建：基于 `f8d31ebbff3eb530fb0d86089e6bc139d3de3d75` 的 Debug Build 36 使用 iPhone 目标构建成功，并通过 Xcode Devices 覆盖安装到“囧尼部落”。
- 真机文件链路：上传 `收入证明.pdf` 成功；新卡片显示真实 PDF 封面、`701 KB`、原件预览与提取文本入口；Chat 同步显示 `收入证明.pdf 演示文稿` 工作流入口。
- 真机需求链路：首项澄清明确显示“已读取源文档”，内容线索来自实际文件；用途、页数、视觉方向均可逐项确认；方案页未展示执行边界、知识范围编辑器、总 Token 步进器或节点预算。
- 真机 422 回归：工作流 `wf_d33f03f5f05146f3a40b90d006eb8a28` 的 `PATCH /plan` 返回 `200 OK`，`POST /approve-plan` 返回 `201 Created`，随后进入 `agent_ready` 并实际执行。
- 首轮执行暴露并定位审批门丢失：iOS 保存方案时丢弃 `scenario_id`、`scenario_version`、`approval_gate`，导致大纲/版式不暂停且最终以 `approved presentation design is missing, stale, or tampered` 失败。提交 `425ee8c` 让 DTO 解码/编码无损保留这些服务端字段；对应测试通过。

## 交付状态

- status: `PUSHED`
- commit SHA: 五项缺陷实现与部署基线 `479b7ab7468f7d222b057dddd82791fa0ddda51e`；审批门 DTO 修复 `425ee8c`；当前合并提交 `f8d31ebbff3eb530fb0d86089e6bc139d3de3d75`。
- GitHub remote/ref/SHA: `Johnie198946/ai-lab-platform` 的 `codex/build36-device-acceptance-fixes` 已由 `git ls-remote` 核验为 `f8d31ebbff3eb530fb0d86089e6bc139d3de3d75`；`main` 仍为 `1922d1318b7f5a53a3edb30dbdb08ca815a7c2a7`，未绕过保护直接推送。
- server_before: `.deployed-sha=49444561a5f9d24c75877ece62d9b6bca901401f`；release `/opt/releases/ai-lab-platform-49444561a5f9.SAz0Ib`；API ready。
- server_after: `.deployed-sha=479b7ab7468f7d222b057dddd82791fa0ddda51e`；release `/opt/releases/ai-lab-platform-479b7ab7468f.4kqg68`；统一 API/workflow/planning/evaluation 运行镜像 revision 为该 SHA。
- health_check: 部署流程 `6/6`；API `/ready` 通过；运行契约审计通过；Hermes Bridge v6 healthy。
- functional_check: 新文档卡片、701 KB 大小、预览/提取文本、Chat 工作流同步、真实文档驱动澄清、精简方案页与 422 修复均已在物理 iPhone 验证。首轮 PPT 执行验证出审批门 DTO 根因；修复包已重新构建并安装，但 Mac 锁屏阻断了第二轮完整审批、PPTX 下载和系统分享页复测，因此不标记 `VERIFIED`。
- rollback_point: `/opt/releases/ai-lab-platform-49444561a5f9.SAz0Ib`；root-only 检查点 `/opt/ai-lab-shared/deployment-checkpoints/20260913-device-acceptance-479b7ab`；旧镜像标签 `rollback-49444561-before-479b7ab` 已保留。

## 风险与未完成项

- Mac 当前锁屏，Computer Use 无法继续；需解锁后在已重装的修复包上新建一次工作流，验证大纲审批、版式审批、最终 PPTX、下载以及仅打开不实际外传的 iOS 分享页。
- App Store Connect 已接收的公开 TestFlight Build 36 来自 `9f158801...`，不含后补的五项缺陷与审批门 DTO 修复。Apple 不允许重复上传相同 build number；公开测试需要另发 Build 37。
- 任务分支已推送，`main` 未包含 `f8d31eb`；在没有更明确的 main 目标授权/保护分支流程前不声称已合入主线。
- 扫描版 PDF OCR 仍不在本任务范围，继续返回“无可提取文本”的明确错误。
