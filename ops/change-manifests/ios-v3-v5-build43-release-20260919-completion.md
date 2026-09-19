# Completion Manifest

- task_id: `ios-v3-v5-build43-release-20260919`
- objective: 将 V3–V5 iOS 前端接入现有生产入口，推送发布分支，部署配套后端，并交付 TestFlight Build 43。
- status: `DEPLOYED`
- branch: `codex/ios-v3-v5-style-sandbox-20260917`
- worktree: `/Users/dengzhaoyu/Documents/AI Lab/.worktrees/quantum-ios-style-sandbox-20260917`
- started_from: `58d212f18ed1edd71d0a95d18b12fc0b820eb277`
- production_baseline_merged: `3a319d49973e1dafa4971b30096437bcb37f68b7`
- release_source_sha: `381d619b411bcfe66230407a144cbcae3f48c04e`
- remote: `source` / `https://github.com/Johnie198946/ai-lab-platform.git`
- remote_ref: `refs/heads/codex/ios-v3-v5-style-sandbox-20260917`
- remote_sha: `381d619b411bcfe66230407a144cbcae3f48c04e`（`git ls-remote` 已核验）

## Changed scope

- 生产 iOS 路由切换到 V3–V5 SwiftUI 体验；旧原型仅保留在 DEBUG 预览入口。
- 聊天、工作流、长文/公式富文本、书架与阅读批注/选词提问沿用现有数据结构和 API。
- 合并最新生产安全、会话、持久化与能力网关基线；修复选中书籍内容被通用知识门禁拦截及 PPT 原生确认提案路由。
- iOS 版本：`1.0.3 (43)`。
- 未提交约 400 MB 的页面切图与验收中间目录：`docs/ios-v3-v5-{extracted,pages,reference,validation}/`。

## Verification

- iOS `AIPlatformAppTests`: `231 passed, 0 failed`。
- 后端、知识门禁、iOS 能力矩阵与部署契约：`183 passed, 0 failed`。
- Release Simulator build: `BUILD SUCCEEDED`。
- Device archive: `ARCHIVE SUCCEEDED`；bundle `com.ailab.AIPlatformApp`，版本 `1.0.3 (43)`，arm64，Team `AALA948YY5`。
- Archive: `/Users/dengzhaoyu/Library/Developer/Xcode/Archives/2026-09-19/Quantumn-1.0.3-43-381d619.xcarchive`。
- TestFlight: 用户报告已手动完成上传；Codex 在 `2026-09-19T09:36:13+0800` 的最后只读界面回读仍显示 `Uploading to App Store Connect`，因此 Apple 处理完成状态未独立核验，不标记 `VERIFIED`。

## Deployment evidence

- server_before: SHA `3a319d49973e1dafa4971b30096437bcb37f68b7`；release `/opt/releases/ai-lab-platform-3a319d49973e.4klw02`。
- server_after: SHA `381d619b411bcfe66230407a144cbcae3f48c04e`；release `/opt/releases/ai-lab-platform-381d619b411b.dchorF`。
- backend_image: `sha256:b203c22cede7bd1900a344b32d50b39d43d34b7870bae355b6f0cc9a74b6185b`；四个后端服务标签均核验目标 revision。
- health_check: PASS；API `/ready`、Hermes Bridge `/health`、`https://t-react.com/health` 均通过，生产容器 `8/8 healthy`。
- functional_check: PASS；生产镜像内选词提问书籍上下文绕过错误通用门禁，PPT 请求路由到 `app_presentation_create_from_text` 且要求 one-time token。
- rollback_point: release `/opt/releases/ai-lab-platform-3a319d49973e.4klw02`；旧镜像标签 `rollback-3a319d49973e`；attestation 备份 `/opt/ai-lab-shared/deploy-backups/ios-v3-v5-before-381d619/offline-images.attested`。

## Remaining risks

- TestFlight 仍需在 App Store Connect/TestFlight 页面确认 Apple 已完成处理并可供测试；上传动作本身不等于可安装。
- 既有 `UITextItemInteraction` iOS 17 弃用警告未阻断构建，未在本发布中扩展范围处理。
