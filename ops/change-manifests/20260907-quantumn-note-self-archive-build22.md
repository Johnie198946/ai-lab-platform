# Quantumn Chat 笔记自归档修复与 Build 22 验收

- 状态：VERIFIED
- 日期：2026-09-07（CST）
- 影响范围：iOS Chat 笔记草稿确认、知识笔记云同步、服务端归档门禁

## 根因

真机与生产数据确认，Chat 卡片的“已更新并同步”不是虚假网络成功，而是完成了一个错误事务：

1. `note_draft` 的 `merge_candidates` 包含目标笔记自身 `03c6079a-b04d-4abb-b4dc-04715f41d632`。
2. 旧 iOS 客户端在更新目标后归档所有候选，没有排除目标 ID。
3. 服务端归档接口允许 `note_id == merged_into_note_id`，最终将《九州旅行纲要》标记为归档并 `merged_into` 自己，因此知识首页查询不到。
4. 同一事件的 `merged_markdown` 只有标题、标签和占位语，但 `markdown` 有完整 3,024 字符内容；旧客户端错误优先使用了不完整的 `merged_markdown`。
5. 本地 reload 使用 `.skipsHiddenFiles`，导致隐藏目录 `.archive` 实际无法被稳定加载，削弱了归档恢复与重复记录清理。

## 修复

- Hermes bridge：
  - 更新操作从 merge candidates 中排除目标自身、归档记录和重复 ID。
  - 更新操作强制使用完整 `markdown` 作为最终正文，不再信任模型生成的兼容 `merged_markdown` 占位稿。
- 后端：拒绝自归档请求，返回 `422 invalid_merged_note_id`。
- iOS：
  - legacy note draft 更新始终使用完整更新正文。
  - 归档候选再次排除 primary note ID 并去重。
  - 云恢复时清理同一 note ID 在 active/archive 两侧的重复副本。
  - reload 纳入 `.archive`，仍排除 `.trash`。
- Build number：`1.0.3 (22)`。

## 生产数据恢复

- 目标账号路径：`accounts/6c6bcc5a9a331bf7ea36/344c8055e972fe202198`
- 恢复笔记：`03c6079a-b04d-4abb-b4dc-04715f41d632` / 《九州旅行纲要》
- 恢复来源：同一 Chat `note_draft` 确认事件中的完整 `markdown`
- 修复前备份：`/opt/ai-lab-shared/backups/knowledge-self-archive-20260907T000003Z`
- 服务端修复后：active 存在、archive 不存在、自归档字段不存在。
- 真机 App 重启并自动云恢复后：active 文件存在，正文包含 `## 10.7`，字节数 `6254`；知识首页数据源可见。

## 验收

- Python：`tests/test_client_session_notes.py tests/test_knowledge_sync_api.py`：`38 passed`。
- iOS 非 Keychain 回归：`138 passed, 0 failed`。
- `KnowledgeNoteStoreTests`（含 active/archive 重复清理）：`20 passed, 0 failed`。
- 全量测试命令中仅 `SignedInKeychainAcceptanceTests` 因 `CODE_SIGNING_ALLOWED=NO` 无可执行宿主失败；功能测试均通过。
- Release Simulator：`BUILD SUCCEEDED`。
- 真机 Release Archive：`ARCHIVE SUCCEEDED`。
- Archive：`/Users/dengzhaoyu/Library/Developer/Xcode/Archives/2026-09-06/Quantumn-1.0.3-22.xcarchive`
- Archive 版本：`1.0.3 (22)`。
- Archive App 二进制 SHA-256：`33add64a8f0e9b96f16df006ac4f457a923c99dfca31f93ca4495b0030795747`
- Xcode Organizer：`Uploaded to Apple`；Submission Status 显示 `Uploaded Today at 12:05 AM`，Build Number `22`。
- 服务端部署代码：`483ceea1763c9457ff905f793a31750089004508`，`/ready` 与部署自检通过。

## RYG / 权限 / 回滚

- RYG：Green（代码、生产恢复、真机回读、Archive、上传均有实证；Apple TestFlight processing/测试组可见性尚需平台处理完成）。
- 权限：仅修复已认证个人租户下违反不变量的自归档目标；未放宽 tenant/account 查询过滤。
- 回滚：服务端按 update manifest 回滚；用户笔记修复前原件和 sidecar 已独立备份。iOS Build 22 未替换既有 Build 21。
