---
title: Quantumn 知识问答与长回答双线交付记录
status: tested-local-partial
tags:
  - quantumn
  - knowledge
  - acceptance
---

# Quantumn 知识问答与长回答双线交付记录

> [!warning] 未完成、未发布
> 本记录覆盖本地实现与设备无关验证，不代表生产交付门禁通过。Mac Hermes 运行态、真实账号/真机、服务器、PostgreSQL 与 TestFlight 均未验证或应用本次改动。

## 基线与修改归属

- task_id: `quantumn-knowledge-delivery-20260906`
- status: `TESTED`（本地 Python 回归与 Swift app/test 编译通过；Swift 真执行和生产验收未完成）
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-knowledge-delivery-20260906`
- head/local_commit: `ef06450ad80acc511ff27e7cf5540ee8cba6c0a3`；本次改动尚未提交。
- remote_sha: 父会话于本轮开工前完成原生 fetch 并核验 `HEAD == origin/main == ef06450ad80acc511ff27e7cf5540ee8cba6c0a3`；收据 `/tmp/quantumn-parent-main-verification.json`，SHA-256 `32769a026ddbb770b7ca38cf1b3ccc8a84b21891fddac4557ba9718fb37927d5`。本轮按要求未重复 fetch。
- server_before / server_after: 本任务未读取部署版本或执行部署。
- rollback_point: 未部署，无本任务生产回滚点。
- 用户明确批准独立 main 克隆；保留旧工作区，发布时串行协调。原工作区仍有其他会话执行提交和部署。
- 用户更正当前客户端为 Build 14，目标 Build 15。Build 11 仅作历史事故记录；本地未上传的同号 archive 不能冒充用户成品。

## 原始门禁

| 门禁 | 当前状态 |
|---|---|
| 自然问题综合个人与可用平台正文 | 本地实现并通过夹具测试；真实账号/Gateway 联调未通过 |
| 长回答真实按需读取、完整展开、恢复、无重复模型调用 | 本地协议、存储、客户端编译通过；真实 SSE/重连/设备性能未验收 |
| 合并保留主 note_id、不创建替代笔记 | 本地文件权威事务与并发回归通过；跨设备真实同步/PostgreSQL 不适用且未证明 |

## 已修改

- `scripts/hermes_bridge.py`：缺目标、畸形标识、缺版本、已归档目标/来源、自归档及重复来源合并不得生成提案；普通问答可保留既有授权 Gateway，不因零关键词丢工具；不启用专家、终端或额外文件权限。
- `backend/api/chat.py`：API 签名前独立拒绝无明确目标/版本的合并，避免绕过 Bridge 校验。
- `backend/services/chat_triage.py`：明确的单一翻译指令不因待翻译正文含“今天”等词而强制外搜。
- `KnowledgeNoteStore.swift`：本地 Codex CLI 实现显式主目标、版本验证及移除合并新建降级；同步恢复不再缺 base 自动创建云端目标。
- 新增 Python 回归；更新 Swift 合并测试。Swift 实际执行曾失败，已通过隔离 store 和同步依赖修复测试，主会话独立重跑 16 个 XCTest 全部通过；这些是单元测试，不是生产账号验收。

## 已执行证据

- 最新合并 Python 回归：`155 passed, 6 warnings`；`/tmp/quantumn-knowledge-backend-final.xml`。
- Swift 修复后主会话重跑：`/tmp/quantumn-knowledge-merge-tests-rerun.xcresult`，`16 tests, 0 failures`，`TEST SUCCEEDED`。真实网络同步通过接口注入的测试替身隔离；生产默认仍为 APIClient。

- Python 相关八组回归：`114 passed, 6 warnings`；JUnit `/tmp/quantumn-knowledge-backend-regression.xml`，回读 `errors=0, failures=0, skipped=0, tests=114`。
- Agency 路由回归独立执行：`39 passed, 2 warnings`。
- `git diff --check`：通过。
- 本任务独立模拟器：`0BA31412-9B75-4B69-9380-BED812A71C21`，iPhone 17 Pro / iOS 26.1；不覆盖其他会话模拟器。
- 首次 Swift 真执行：`/tmp/quantumn-knowledge-merge-tests.xcresult`，16 个测试，14 通过、2 失败，共 3 个失败断言。失败为成功路径 await 后目标笔记不可见；已隔离真实网络/单例账户生命周期并重跑通过，保留该失败回执用于复盘。
- Codex 长回答只读审计：`/tmp/quantumn-knowledge-p0-codex.txt`；结论为现有视觉折叠不等于网络分页。
- iPhone 真机仍 `unavailable/Offline`；配对记录 `developerModeStatus=disabled`，未测量当前 Build 14。用户已表示连接，需实时复查，不以配对缓存视为在线。

## 接口与迁移边界

### 2026-09-06 剩余实现检查点

1. **授权正文**：`knowledge_search` 继续走同一签名 capability、实时 policy/version 和 `document_index` 撤回屏障；平台命中现在返回最多 20,000 字/文档、60,000 字/回合的正文，并携带 `knowledge_id/version/citation/source_kind/conditions/effective_at/content_status`。正文不写入搜索缓存；个人笔记继续由同一 Gateway 的 tenant+user capability 返回全文。零命中、scope denied、Gateway unavailable、正文 revoked/unavailable/budget_exhausted/truncated 分开表达。
2. **合并事务**：新增 `POST /api/v1/me/knowledge-notes/merge`，固定请求为 `operation_id,target_note_id,target_base_hash,source_versions,revised_content`。同账号文件锁内写 durable journal，逐项 CAS，原位更新 target，只归档显式 source；payload digest 绑定幂等键；崩溃后同 payload 可续做，异 payload 拒绝。个人结果先完成，贡献/撤回投影以 journal outbox 独立重试。
3. **长回答**：复用 `chat_runs/chat_run_events`，新增 `chat_message_blocks` 投影；每个 delta 到达时即持久化已闭合 Markdown block，`done` 只对账并刷新尾块。`answer_blocks_v1` 不接收 delta、done.answer、status/history 全文；首次只收有界 page，后续用 tenant/user/message/revision 绑定 HMAC cursor 拉取。单块最大 32 KiB，单页最大 20 块/128 KiB，默认 10 块/64 KiB；超大内容 UTF-8 安全分段并可精确重组。
4. **iOS**：API、SSE、durable replay、status、消息模型、持久历史、coordinator 和 LongAnswerSheet 均接入 block page。客户端只解析已取块并保存 revision/cursor/hasMore；“加载下一批”只读取存储，不发模型请求；旧 Codable 字段保持可选兼容。复制与导出会显式逐页读取全部已存储块，不调用模型，且不改变当前阅读窗口。
5. **Wiki/撤回与外部补证**：未建第二条编译链，继续复用 contribution → candidate ingest → durable knowledge run → sanitize/privacy/re-identification → publication gate。已验证现有链能 fail-closed 撤回单源/多源投影，但它**没有**实现“按实体/概念/专题更新既有 Wiki、无增量不重写、冲突注释”的新编译契约，也不存在动态“授权概括版本 resolver”；当前只能把事先独立审批并编入 catalog 的文档当作普通授权文档。相关旧测试不能作为这些新契约的完成证据，发布门禁仍阻塞。

### 精确验证结果

- Python 组合回归：`214 passed, 7 warnings in 3.01s`；JUnit `/tmp/quantumn-remaining-python.xml`（`failures=0, errors=0, skipped=0`）。
- 合并事务追加并发回归：`5 passed, 4 warnings in 1.10s`；同一 base 的两个线程只有一个 CAS winner，outbox 故障后同 operation retry 完成。
- Python `py_compile`：`scripts/chat_run_store.py scripts/hermes_bridge.py backend/api/chat.py backend/api/knowledge.py backend/api/knowledge_policy.py backend/api/knowledge_sync.py` 通过。
- Swift app 编译：generic iOS Simulator、隔离 DerivedData `/tmp/quantumn-derived`，`BUILD SUCCEEDED`。
- Swift app + tests 编译：同一 DerivedData，`TEST BUILD SUCCEEDED`；新增 `answer_page` DTO 测试已编译。
- Swift XCTest 真执行：**本轮未执行**。CoreSimulatorService 在沙箱中 `connection invalid`；未连接或修改任何模拟器。此前 16 个合并 XCTest 结果不能替代本轮 block UI 真执行。
- `git diff --check`：通过。

### 2026-09-06 独立复核修正

- iOS 合并生产主路径已从逐条 `syncKnowledgeNote/archiveKnowledgeNote` 改为单次 `POST /api/v1/me/knowledge-notes/merge`；注入同步器回归精确断言 `operation_id,target_note_id,target_base_hash,source_versions,revised_content`，并断言未调用旧合并写路径。服务端事务后仍执行账号指纹复核、云端 target/source read-back，再归档本地 source；不再补建缺失云端 source。
- `done` 与增量投影不一致时先递增 `answer_revision` 再重建块；旧 cursor 返回 stale，客户端收到 409 后从首屏显式重载。cursor 增加一小时过期，durable production 未配置 `CHAT_BLOCK_CURSOR_SECRET` 时拒绝启动。
- `answer_blocks_v1` 的 delta 不再逐次重写增长中的 `partial_answer`；已闭合块继续增量持久化，error/cancel 会终态 flush 尾块。legacy run 仍保持原 `partial_answer` 合同。
- 超大 code/table 按行/行片段持久化，UTF-8 精确可重组；LongAnswerSheet 按服务端稳定 block id、40 block 阅读窗口和 120 行 code/table 子页渲染，避免全文 hash cache 和每页追加后重解析旧全文。
- 新增 catalog 路径逃逸反例：manifest/matrix 候选只有在 resolve 后仍位于 vault 且为文件时才可进入索引或正文读取。
- Python 回归：`218 passed, 7 warnings in 2.95s`；JUnit `/tmp/quantumn-independent-corrections-python.xml`。
- Swift build-for-testing：`TEST BUILD SUCCEEDED`；DerivedData `/tmp/quantumn-corrections-derived`。
- Swift 真执行：修正主路径的 `95 tests, 0 failures`，`TEST EXECUTE SUCCEEDED`；结果 `/tmp/quantumn-independent-corrections-swift.xcresult`。随后新增的 AnswerBlock 历史 round-trip 测试已进入最终 `TEST BUILD SUCCEEDED`，但复跑时 CoreSimulatorService 失联，故该 1 项只有编译证据、无执行证据。先前执行日志出现既有 SQLite 文件仍打开时清理夹具的系统警告，但未造成测试失败；应单独治理，不能解释为生产验收通过。

### 安全与兼容限制

- cursor 不含正文，只含 owner hash、message、revision、next index、协议版本并签名；每页重新校验 owner。生产必须设置非默认 `CHAT_BLOCK_CURSOR_SECRET` 并在 Bridge 实例间一致配置。
- 受限正文只在 capability/policy/live-document 三重检查后进入模型请求；搜索缓存只保留索引/片段。概括版本仍须作为独立批准文档进入既有 catalog，不自动降级或自动红删受限原文。
- 公开专利文档不产生实施许可；预期收益/企业实践仍需 evidence metadata 与编译审查，真实内容抽样尚未完成。
- SQLite populated schema 重开两次回归通过；没有 PostgreSQL 发布证据。当前 chat run store 本来就是 SQLite，生产共享卷、备份、密钥轮换与 cursor 失效仍需运维验证。

合并是单账号共享文件权威下的 recoverable transaction，不宣称跨本地设备与云端的分布式原子性。源-only 旧请求仍明确拒绝并提示重新选择主笔记。

## 余下工作与发布禁区

1. 真机可达性、Build 14 成品映射与性能基线；固定数值门槛。
2. Swift 全部回归、真实登录和核心功能/视觉验收。
3. 真实账号联合正文阅读、授权概括版本、wikilink 多轮边界与外部补证失败分类验收。
4. 合并事务真实多设备断网/云成功本地读失败恢复，以及生产文件卷锁/备份演练。
5. 长回答真实 SSE/断线/重启/历史恢复、scroll anchor、峰值内存/主线程停顿/首屏及翻页延迟验收。
6. Wiki 实际内容 update/no-increment/conflict/withdraw/multi-source 抽样；本地夹具通过不能替代生产语料审查。
7. Mac 单用户直连与服务器 Gateway 两端应用；精确 GitHub SHA、回滚点、部署回读。
8. 模拟器及真机验收通过后核对 Build 15 占用，最后上传 TestFlight。

## 2026-09-06 授权概括与增量编译子任务（本地部分实现）

- 实际新增：`document_index → durable contribution path binding → authorized version resolver` 读屏障。签名 Gateway 搜索在任何正文读取前安装获准路径集合；普通用户只获得独立发布 summary，拥有 detail 权限时优先 detail。Wiki HTTP 路由使用同一 durable dependency；摘要正文与缓存结果不包含私有 lineage。删除 summary/来源绑定标签不能降级成普通 green 文档。
- 概括发布复用既有 compile/sanitize/privacy 三个 Hermes durable run，保留三个独立 session/receipt、派生许可、public 受众、summary 粒度、精确 source_revision/hash/fingerprint、发布正文 hash；每次读取重新校验源版本、授权 epoch、撤回及正文 hash。未新增 AI Runtime、未调用真实模型或发布真实语料。
- 源版本更新在 Outbox 事务内使旧版本及依赖退出可读态；多源保持 `recompile_required`，不保留含撤回证据的旧正文。旧授权 epoch 下同 hash/revision 可重新进入独立候选，不恢复旧投影。
- 既有 `CompilerService` 增加确定性 apply，并由 `knowledge_pipeline → write_red_projection` 实际调用；支持 tenant namespace 内 entity/concept/topic target、SHA-256 CAS、跨进程文件锁、no_increment 不改 Wiki 字节/mtime、不启动下一 sanitize run、显式未解决冲突与 fingerprint 去重。缺失来源绑定拒绝更新。
- 新增 `tests/test_knowledge_disclosure_incremental.py`，覆盖真实业务 pipeline + 签名 Gateway 函数调用、detail→summary、正文篡改、去标签攻击、撤回/版本更新、生产 no_increment 路径和并发 CAS。Hermes 结果仍为本地夹具，不是线上模型验收。
- 发现并修复 `knowledge_access_audits.id` 的 SQLite BigInteger 自增故障：只为 SQLite 使用 Integer variant，PostgreSQL 类型不变。既有 SQLite 数据库迁移未实现/应用；新建测试库验证通过。
- 运行指定 venv：`PYTHONPATH=. python -m pytest tests/test_knowledge*.py -q --disable-warnings --junitxml=/tmp/quantumn-governance-all.xml`，**92 passed, 7 warnings**；`git diff --check` 通过。

### 仍阻塞，不应据测试宣称完成

1. 当前 compiler 输入尚无完整“授权既有实体/概念/专题候选发现 + 版本正文”装配，只有经 Hermes verified result 显式提交 target/base_hash 的 apply 合同；不能宣称已自动完成既有 Wiki 语义增量成长。
2. Green 平台 Wiki 仍按既有 event 投影发布，尚未完成稳定 canonical identity 的跨来源 CAS 合并与全来源 run 注册/重编译；不同旧 source fingerprint 缺绑定时明确拒绝，不能由模型自称多源补齐。
3. 本地 file CAS 与 contribution SQL acceptance 不是跨介质原子事务；增量写成功后 acceptance 失败/服务重启的完整恢复对账尚待补齐，生产共享卷锁和 PostgreSQL 并发未验证。
4. 当前安全策略取消了 Gateway lexical snippet 缓存复用，并对所有候选查 durable path binding；数据库不可用时 fail closed。大语料/故障分类/性能门槛尚未测量。
5. 既有三项非替代性交付门禁仍由主会话验收；本子任务没有 commit/push/deploy/TestFlight 或生产数据修改。

## 费用

- A 轨：本地源码审计、Codex 修改、pytest 与 Xcode 测试已实际执行；未取得供应商费用回执，不填金额。
- B 轨：尚未完成真实联合问答、编译、外搜及分页传输成本测量，不宣称降低总成本。

## 2026-09-06 Full-suite regression closure（本地 TESTED，未发布）

- 根因修复：Bridge 的 `answer_blocks_v1` 端点默认值由直接调用时为真的 `Query(False)` 改为普通 `False`；legacy durable status 继续返回 `answer`，只有客户端显式协商 blocks v1 才隐藏全文。
- 兼容测试：Hermes bootstrap probe 不再向 Python 3.12 注入 Python 3.11 `site-packages`；使用当前 Bridge 解释器依赖集合加 Hermes 源码根，实际导入并断言 `tools.registry` 来自 Hermes。Gateway mocks 明确断言 `include_content=True` 及授权正文返回字段。
- 治理夹具：base knowledge readiness 创建与 catalog 对应的真实文件；损坏 catalog 明确断言 fail closed，不恢复可能失效的 `_LAST_VALID_MANIFEST`。两项 Agency 单测将 telemetry 写入 `tmp_path`，不触碰真实 `~/.hermes/state`。
- 原 PostgreSQL 证据保持不变：17 项 disclosure/incremental 测试使用真实 PostgreSQL 16、fresh database、pytest-only `NullPool` 全部通过；JUnit `/tmp/quantumn-parent-postgres-clean.xml`，SHA-256 `e566a49c99808cb06a8f88e22cca571bb1b73303b3e6133ef90e5e64ffa35f01`。本轮未启动或修改 Docker。
- Targeted：`21 passed`，JUnit `/tmp/quantumn-full-regression-targeted.xml`，SHA-256 `4ab8856a28da1b79337f775bf64fa0a1288cc81b9f4a7b047a55a17979067699`。
- Differential：`149 passed`，JUnit `/tmp/quantumn-full-regression-differential.xml`，SHA-256 `cacc3bbca3733e70eda77d81cd0af0cfec5ff4e26ebeb96127190e84be3f8950`。
- Full suite：`1295 tests = 1293 passed + 2 skipped`，`0 failures / 0 errors`，34 warnings，31.03s；JUnit `/tmp/quantumn-full-regression-final.xml`，SHA-256 `3a219c5eee3e6780cd1f9320b66f65cbd875449ad659d8a205a910c83d0a6bd0`。
- 两项 skip 均为既有 `tests/test_showroom_api.py` V1 夹具：staffing browser orchestration 已由服务端持久化 Insight V2 取代；browser backfill 已由 Artifact V2 projection 测试取代。本轮没有新增 skip。
- `git diff --check` 通过。没有 commit、push、deploy、生产写入、真实 Hermes 模型调用或 TestFlight 操作。

```text
task_id: quantumn-knowledge-delivery-20260906
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-knowledge-delivery-20260906
head/local_commit: ef06450ad80acc511ff27e7cf5540ee8cba6c0a3 (working tree changes uncommitted)
remote_sha: ef06450ad80acc511ff27e7cf5540ee8cba6c0a3 (parent native-fetch receipt)
server_before: NOT_READ
server_after: NOT_DEPLOYED
health_check: NOT_RUN
functional_check: LOCAL_FULL_SUITE_GREEN; PRODUCTION_NOT_RUN
rollback_point: NONE (no deployment)
manifest: ops/change-manifests/quantumn-knowledge-delivery-20260906-completion.md
remaining_risks: real Hermes/semantic/account gates; production PostgreSQL/shared-volume/process-kill gates; server/device/TestFlight gates
```

## 2026-09-06 Canonical Wiki 独立复核修正（本地 TESTED，未发布）

- 开工收据：父会话已在沙箱外执行 `git fetch origin main`；`HEAD == origin/main == ef06450ad80acc511ff27e7cf5540ee8cba6c0a3`，无远端差异。收据 `/tmp/quantumn-parent-main-verification.json`。本轮未重复 fetch。
- 公共 canonical 输入：候选发现不再依赖当前租户私有目录存在；先读取至多 64 KiB frontmatter 并做相关性/DB 投影绑定，再在文件大小预算内读取正文。Hermes compile payload 现在包含已批准公共正文、正文 hash、文件版本、投影版本及公共 review receipt hash；不包含外租户 raw/Red 正文或私有事件 lineage。
- 生成期 CAS：Green 的文件/投影 expected base 固定取自 compile dispatch 的公共输入，不在 acceptance 时采样当前版本。未声明 incremental target 的既有同名 canonical、生成期间更新或撤回均拒绝旧结果并置为 `recompile_pending`。
- 证据绑定：只在实际公共输入引用仍精确匹配当前投影、评审收据、正文 hash、active bindings 和各来源当前授权时复用旧证据；其余历史外租户 binding 不再自动保留。source count 由当前与获准复用事件的 root fingerprint 去重，复制 Wiki 不新增独立根。
- supervisor：重编译仅复用 event ID、tenant/user、authorization epoch、source revision、candidate hash 与实际正文 SHA-256 全部精确匹配的 Hermes compile 内容；选择最新匹配项。缺精确源时标记 stale，不静默跳过；创建 fresh compile 后 supersede 旧 registered 阶段，避免旧完成结果反复抢回事件状态。
- 新增反例：两租户唯一事实进入真实 compile/sanitize payload 并保留到最终公共正文；B dispatch 后 A 更新导致 B stale/recompile；无私有根仍可发现公共 canonical；大体积未绑定候选在完整正文读取前被拒绝；同名但无 incremental target 不覆盖。
- 验证：最终组合执行 `tests/test_knowledge*.py`、agency/ordinary discovery/merge integration 共 `206 passed, 7 warnings in 4.76s`；相关服务 `py_compile` 与 `git diff --check` 均通过。
- 边界：未调用真实 Hermes 模型、真实账号、生产 Vault/PostgreSQL、服务器或 TestFlight；未 commit、push、deploy。共享卷锁语义、真实并发数据库与生产语料质量仍须父会话发布前验证。

## 2026-09-06 Wiki 三项生产路径闭环（本地 TESTED，未发布）

- 输入闭环：`submit_compile` 在既有 durable Hermes run 创建前，从当前租户 canonical Red Wiki 目录按 title/aliases/entity 做非空关键词、确定性、最多 1 篇/400,000 bytes 的候选解析；候选必须同时通过 owner/status/frontmatter、当前 policy epoch、Projection/Binding/Event 数据库绑定。实际 Hermes `knowledge_stage.existing_wiki` 携带完整正文、canonical ID、路径、原始字节 SHA-256 `base_version` 和精确事件 provenance。模型返回的 increment target/base 不在该次 dispatch 中即拒绝；sanitize/privacy 后继 run 清空 Red Wiki 正文。
- canonical 闭环：Red ID 按 private audience + tenant namespace + kind + normalized identity 稳定生成；Green ID 按 public audience + platform namespace + kind + identity 稳定生成。相同实体/概念/专题的同租户与跨租户来源复用同一平台 Green projection；跨租户只在各自独立 compile/sanitize/privacy 后合并数据库 source binding，不混合原始 Red 正文。更新使用文件 SHA-256 CAS、Projection 行锁/版本 CAS、唯一约束；旧 accepted run 标为 superseded。撤回立即禁用读取，单源 withdrawn，多源 recompile_required，并由现有 supervisor 从既有 durable compile receipt 恢复剩余来源内容、创建新的 Hermes run。
- 恢复闭环：新增 `knowledge_contribution_projection_operations`，在任何 Red/Green 文件修改前持久化 operation ID、payload/base/result digest、artifact/projection 引用与最小 acceptance intent；阶段为 prepared → file_published → sql_accepted → completed/quarantined。文件写入使用 fsync+atomic rename 和目标锁；重入只接受同 operation 同 payload。既有 supervisor 同时恢复未完成 operation；SQL 不可用、rename 后崩溃、commit 后丢 ACK、Green publication/index 失败均可重放。文件 CAS 发现无关更新时不覆盖，旧 operation 隔离并重新排队；恢复期间授权撤回则 quarantine，读取端继续 fail closed。
- Schema/旧数据：SQLite/PostgreSQL 兼容 ORM 表由既有 `init_db/create_all` 创建，显式 migration hook 也 `checkfirst` 建表。`migrate_legacy_event_projections(..., apply=False)` 默认只 dry-run 列出缺少 canonical identity 的旧 Green 页；`apply=True` 只把它们标成 `recompile_required`，不改 ID、正文或现有 note ID。SQLite dry-run/apply 和 V1 outbox 保留测试通过；本机没有 `pg_isready`，没有伪造 PostgreSQL 运行证据。
- 故障/攻防测试：覆盖真实 durable dispatch 输入、跨租户/符号链接隔离、未下发 target/version 拒绝、no_increment 字节与 mtime 不变、两个来源同 canonical 页面和完整 binding、并发 CAS、before-write、after-rename-before-SQL、after-commit-before-ACK、SQL unavailable、index failure、restart、异 payload idempotency conflict、无关新编辑不覆盖、恢复中 revoke quarantine，以及 legacy migration dry-run/apply。
- 验证：最终 `tests/test_knowledge*.py` 为 **101 passed, 7 warnings in 4.25s**，JUnit `/tmp/quantumn-wiki-closure-all.xml`；durable store/worker/agency integration 为 **56 passed, 2 warnings in 1.78s**，JUnit `/tmp/quantumn-wiki-closure-integration.xml`；相关 Python `py_compile` 和 `git diff --check` 通过。
- 边界：Hermes 输出全部为显式测试替身，没有调用真实模型、真实 Vault、`.hermes`、生产数据库或服务器。没有 commit/push/deploy。NFS/共享卷 `flock` 语义、真实 PostgreSQL 并发、进程 kill/fsync/磁盘故障、生产语料事实质量与真实 Gateway 负载仍是发布前门禁；实现不宣称跨主机文件+SQL 分布式原子性。
