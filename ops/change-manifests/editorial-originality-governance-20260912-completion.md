# Completion Manifest

- `task_id`: `editorial-originality-governance-20260912`
- 目标：在既有 Quantumn 作者—独立审稿—确定性发行链中加入 AI 主编选题与原创论点合同，并治理本机已有稿件。
- 当前状态：`COMMITTED`（部署验证完成后继续更新）

## 开工前 Git 盘点

- `status`: `## main...source/main [behind 31]`，工作区无本地改动。
- `branch`: `main`
- `HEAD`: `5284db6f5090cde578b51656ad2d1ad9420a1748`
- `remote`: `origin=https://github.com/Johnie198946/Quantum.git`；`source=https://github.com/Johnie198946/ai-lab-platform.git`
- `worktree`: 当前 `/Users/dengzhaoyu/Documents/AI Lab/Quantum-2.0` 使用 `main`；另有历史 worktree `/private/tmp/quantum-2.0-managed-hermes` 使用 `codex/quantum-2.0-managed-hermes`，未触碰。
- 同步：按仓库规则从 `source/main` fast-forward 到 `23cc7c397ee9d897674f62a21d7f8bb7dd224cc2` 后开始修改，无 merge/rebase。

## 变更文件

- `backend/services/publication_editorial.py`：`editorial-v2` 合同、五种体裁、原创论点 brief 机械门禁及新增独立审稿项。
- `backend/services/knowledge_publication_store.py`：复用既有 prepare/stage/release 主路径；brief 与来源共同绑定，证据 URL 必须来自 bundle references；公共投影增加体裁。
- `backend/services/knowledge_catalog.py`、`backend/api/subscriptions.py`：沿既有书架 DTO 透传 `editorial_genre`。
- `ios/AIPlatformApp/Networking/APIClient.swift`：显示“教程 / 研究报告 / 科普 / 趣味文章 / 观点文章”与书籍格式组合标签。
- `config/quantumn-daily-publication.json`、`docs/prompts/quantumn-editorial-v2.md`：主编选题、允许无稿、观点/反方/不确定性、存量治理和独立审稿要求。
- `ops/manuscript-governance-20260912.md`：8 份既有稿件的治理决定和首批重编选题。
- 相关 Python/Swift 测试 fixture 与断言。

## 存量治理结论

- 6 篇 2026-09-09/10 短稿有效汉字为 873–1,247，均无 `editorial-v2` brief：新上架一律 `rewrite_required`；若生产已发布则只保留冻结历史版本。
- `personal-knowledge-handbook/manuscript-v2.md`：37,552 有效汉字、10 章，revision 1 已拒稿，保持 `research_blocked`。
- `personal-knowledge-handbook-r2/manuscript-v3.md`：与 v2 文本相似度 99.32%，仍为 `editorial-v1` 待审，判定 `duplicate + rewrite_required`，不得沿用旧批准路径。
- 原文件、审稿记录与证据均未删除或覆盖。

## 测试与校验

- `git diff --check`：通过。
- `python3 -m json.tool config/quantumn-daily-publication.json`：通过。
- `ruff check`（本任务 Python 文件）：通过。
- `PYTHONPATH=. python3 -m pytest -q tests/test_*publication*.py`：`173 passed`；仅 4 条既有 Pydantic v2 deprecation warning。
- `xcodebuild ... -destination generic/platform=iOS CODE_SIGNING_ALLOWED=NO build`：`BUILD SUCCEEDED`。
- iOS Simulator 测试：CoreSimulatorService 在本机不可用，未执行；DTO 解码断言已更新，设备构建通过。

## 交付状态

- `status`: `COMMITTED`
- `head/local_commit`: 实现与治理提交 `d70f6d5f`；本 manifest 随后单独提交。
- `remote_sha`: 未授权 push，未执行。
- `server_before`: 状态只读连接因本机缺少安全 identity file 返回 `unknown`。
- `server_after`: 未授权部署，未执行。
- `health_check`: 不适用；未部署。
- `functional_check`: 本地出版相关后端 173 项通过，iOS device build 通过；生产与真机未验证。
- `rollback_point`: 本地改动前基线 `23cc7c397ee9d897674f62a21d7f8bb7dd224cc2`；未创建生产回滚点。

## 剩余风险

- Hermes 的书级作者、独立审稿和发行任务当前仍为 disabled；未获 push/部署授权前不能启用，否则会继续运行旧生产代码。
- 本机存量稿件已完成分类，但尚未由真实作者会话生成 `editorial-v2` 新 revision，也未经过新的独立审稿。
- 未取得生产出版库状态，不能确认两篇 2026-09-10 短稿是否已发布；治理策略因此采用“已发布则冻结，未发布则重写”的失败关闭处理。
