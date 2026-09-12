# Completion Manifest

- `task_id`: `editorial-originality-governance-20260912`
- 目标：在既有 Quantumn 作者—独立审稿—确定性发行链中加入 AI 主编选题与原创论点合同，并治理本机已有稿件。
- 当前状态：`TESTED`（等待精确 SHA 部署验证）

## 开工前 Git 盘点

- `status`: `## main...source/main [behind 31]`，工作区无本地改动。
- `branch`: `main`
- `HEAD`: `5284db6f5090cde578b51656ad2d1ad9420a1748`
- `remote`: `origin=https://github.com/Johnie198946/Quantum.git`；`source=https://github.com/Johnie198946/ai-lab-platform.git`
- `worktree`: 当前 `/Users/dengzhaoyu/Documents/AI Lab/Quantum-2.0` 使用 `main`；另有历史 worktree `/private/tmp/quantum-2.0-managed-hermes` 使用 `codex/quantum-2.0-managed-hermes`，未触碰。
- 同步：按仓库规则从 `source/main` fast-forward 到 `23cc7c397ee9d897674f62a21d7f8bb7dd224cc2` 后开始修改，无 merge/rebase。
- 上线前发现生产仍在 `origin/main` 的 `977e07776e1a8c1e68cfa69c74cb1ffbe82767a8`，与 `source/main` 分叉；直接部署会删除生产 Hermes 多租户运行架构。因此先将该生产分支合回获授权的 `source/main`；Git 只同时合并 `backend/api/register.py`，并保留了碰撞安全租户解析与短信登录两侧修复。

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
- 合并生产架构后，出版、鉴权、推理策略、运行放置、租户沙箱和部署合同聚焦测试：`328 passed`；仅 4 条既有 Pydantic v2 deprecation warning。
- `bash -n scripts/update.sh scripts/deploy_exact_sha.sh`：通过。
- `xcodebuild ... -destination generic/platform=iOS CODE_SIGNING_ALLOWED=NO build`：`BUILD SUCCEEDED`。
- iOS Simulator 测试：CoreSimulatorService 在本机不可用，未执行；DTO 解码断言已更新，设备构建通过。

## 交付状态

- `status`: `TESTED`
- `head/local_commit`: 实现与治理提交 `d70f6d5f`；首份 manifest 提交 `e5fc2907`；生产架构汇合提交 `10df5c7a`。
- `remote_sha`: `e5fc290702730814a10eb2bd2ed6cdc949be7a33` 已经 `git ls-remote source refs/heads/main` 核对；当前待部署汇合提交尚未推送。
- `server_before`: `/opt/releases/ai-lab-platform-977e07776e1a.ruR4f8`，`.deployed-sha=977e07776e1a8c1e68cfa69c74cb1ffbe82767a8`；无 `scripts/update.sh` 进程；API `/health` 与 `/ready` 正常。
- `server_after`: 待部署。
- `health_check`: 不适用；未部署。
- `functional_check`: 本地出版相关后端 173 项通过，iOS device build 通过；生产与真机未验证。
- `rollback_point`: 本地改动前基线 `23cc7c397ee9d897674f62a21d7f8bb7dd224cc2`；生产当前 release `/opt/releases/ai-lab-platform-977e07776e1a.ruR4f8` 将由标准发布脚本保留为回滚点。

## 剩余风险

- Hermes 的书级作者、独立审稿和发行任务当前仍为 disabled；应先用真实作者会话生成并通过一份 `editorial-v2` 样稿，再启用自动发行。
- 本机存量稿件已完成分类，但尚未由真实作者会话生成 `editorial-v2` 新 revision，也未经过新的独立审稿。
- 未取得生产出版库状态，不能确认两篇 2026-09-10 短稿是否已发布；治理策略因此采用“已发布则冻结，未发布则重写”的失败关闭处理。
