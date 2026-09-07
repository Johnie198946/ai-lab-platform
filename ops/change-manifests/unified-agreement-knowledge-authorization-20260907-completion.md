---
title: 统一协议准入与知识贡献授权断链修复
date: 2026-09-07
tags:
  - ai-lab
  - authorization
status: VERIFIED
---

# Completion manifest

> [!warning] 授权修复已生产验收，不等于知识全闭环恢复
> 已提交、推送、部署并执行 authorization-only 迁移，精确回读与幂等通过。签约后有 3 个存量候选但 outbox 为 0，本次不重放；未验收真实模型推理或 iOS 登录。

## 交付状态

- task_id: unified-agreement-knowledge-authorization-20260907
- status: VERIFIED
- branch: main
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-qws-errors-20260903`
- head/local_commit / remote_sha（源码提交）: `d0335e5b99d18d7368c641871c52a9645de095b3`，git ls-remote 已读回一致。
- server_before: `8f2b61850bb521bb3176e92302c64c2de9ff9706`；`/opt/releases/ai-lab-platform-8f2b61850bb5.AnFVqc`。
- server_after（源码发布）: `d0335e5b99d18d7368c641871c52a9645de095b3`；`/opt/releases/ai-lab-platform-d0335e5b99d1.FcO0Tu`。
- health_check: API `/ready` ready 0.8.0；Hermes Bridge `/health` ok v6.0。
- functional_check: 生产 DB 45 位映射用户准入核验 3 allowed / 42 denied 428；真实 HTTP 无 marker 签约用户 3×200、无签约用户 428、匿名 401；详见生产回执。
- rollback_point: 旧 release、完整 PostgreSQL dump 与配置备份均存在，见下。
- 本 Markdown 回执将另作 doc-only 提交并部署；它自己的 SHA 不能写入自身。最终三方 SHA/release 以服务器备份目录 `final-release.json` 与会话收据为准，正文上述 SHA 始终指源码发布，不冒充文档提交 SHA。
- 保留原有两个 iOS completion 未跟踪文件及 `stash@{0}`，未触碰其他目录 Codex 进程。

## 盘点与授权证据边界

真实入口为 `backend/api/auth.py` 的认证/租户映射、`backend/api/agreement.py` 的统一签约与业务依赖，以及 `backend/main.py` 已注册业务路由依赖。旧实现允许 compatible mode 和缺少客户端 marker 的请求绕过，签约亦未投影两层贡献授权。

协议原文明确：**仅适用于接受本版本协议后新建或修改的内容，不回填或追溯处理此前历史内容**。版本 `2026-09-06` 显式映射既有贡献版本 `service-2026-09-06`；并未修改协议正文扩大范围。

- 唯一回填证据：真实持久化 `UserAgreementAcceptance` + 当前版本 + 非未来服务端 accepted_at + 持久化 TenantMapping。
- 登录、JWT、客户端 marker、legacy consent 均不是签约证据；不得由登录时间生成 acceptance。
- 真实 acceptance 原子投影缺失 tenant policy 与个人 consent；共享租户 policy 不代表其他成员同意。
- 已撤回/禁用和版本冲突行保守阻断，不由签约重试或迁移复活；晚于签约的个人 participation 生效时间保持，不向前扩大。
- 存量原文、sidecar 时间、private index 均不由迁移修改。签约前历史明确排除；签约后候选也仅报告、不入队。无 outbox 的存量候选仍需另行审核的安全重放工具。
- 委托只读生产盘点为 36 Markdown（28 active、3 archive、5 trash）、policy/outbox/runs/projections/operations 均零、enabled personal consent 一条。这些是父代理提供的证据，不是本脚本生产执行结果；实际真实 acceptance 数量仍待生产 dry-run。

## 修改清单与复用边界

- `backend/api/agreement.py`：无客户端/环境兼容豁免；真实 acceptance + 有效贡献授权准入；签约与授权同事务，冲突重试，DB 唯一约束幂等。
- `backend/services/agreement_authorization.py`（新）：API/迁移共用证据投影；PostgreSQL transaction advisory lock 处理不存在 policy 的并发竞争；不新增表。
- `backend/api/knowledge_contribution.py`：旧授权 enable 写接口转向统一签约（409），保留撤回，禁止历史回填。
- `backend/api/showroom.py`：WebSocket 握手和消息/心跳轮次重查协议，旧 token 不豁免。
- `backend/services/knowledge_contribution.py`、`knowledge_catalog.py`、`knowledge_publication_gate.py`、`backend/api/knowledge_publication.py`：贡献/公开复用读取亦校验真实 acceptance。
- `backend/api/knowledge_sync.py`：持久化原 source_changed_at；merge 重试使用已持久化时间而非重试当前时间。
- `backend/services/knowledge_pipeline.py`：note 精确 hash；终止事件不被迟到状态更新复活。
- `backend/services/knowledge_pipeline_supervisor.py` + 新 `knowledge_pending_sources.py`：只恢复已有 pending iOS note outbox 对应的精确 active source，校验 hash/revision/time，不扫库制造历史事件。
- 新 `knowledge_worker_authorization.py` + `scripts/chat_run_worker.py`：真实 worker 执行前 fail-closed DB 预检；继续使用 DurableChatRunStore、现有 Hermes bridge 与 compile/sanitize/privacy stage，不建立第二 runtime。
- 新 `scripts/migrate_agreement_authorization.py`：默认只读；显式 apply、新 0600 审计 JSONL、prepared/committed/verified、提交后精确回读、幂等；不创建 schema、不执行 Hermes、不重放笔记。
- 新 `tests/test_agreement_authorization.py`、`tests/agreement_fixtures.py`；更新 agreement API、贡献/pipeline/公开屏障测试。`tests/conftest.py` 对非 agreement 业务单测使用测试专用 dependency override；**非生产绕过**，完整准入安全由 agreement 命名测试独立验证，不能将其余业务单测当成授权覆盖。

官方运行时接口参考已读取： https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration 。此次只延伸已有生产 worker/bridge，不另引入 SDK runtime。

## 三轮对攻及真实执行

1. 授权/兼容：无 acceptance 但 legacy 表开启、所有 mode/marker、未来 acceptance、DB 故障、无 worker DB、WebSocket 旧 token 均 fail closed；签约原子创建 policy/consent 后可准入。
2. 幂等/并发：提交前注入故障全部回滚；同 key/不同 key 并发、同租户多成员仅一个 policy；迁移默认无写、apply 审计回读和重试 unchanged；签约重试与撤回竞争不复活。
3. 撤回/存量：撤回阻断 worker/业务、迟到 pipeline 状态不复活；签约前、archive/trash 排除；原文/mtime/private index 不变；晚生效时间不后退；已有 pending source 不替换 hash/time；实际 queue/worker/SQL → Red/Green 完成。

注意：以上为本代理实施的三组可执行反例测试，不声称有三个独立审查代理。端到端替换了模型推理与测试 sandbox，真实 SQL/queue/worker/receipt/编译流被执行；不是线上 LLM 质量验收。

### 最终通过结果

```sh
python3 -m pytest tests/test_agreement_api.py tests/test_agreement_authorization.py -q --tb=short
# 39 passed, 41 warnings in 4.76s

AGREEMENT_TEST_POSTGRES_PORT=49478 python3 -m pytest tests/test_agreement_authorization.py -q --tb=short --junitxml=/tmp/agreement-postgres.xml
# 13 passed, 2 warnings in 8.24s

docker run --rm --network none \
  -v "$PWD:/app:ro" \
  -v /Users/dengzhaoyu/.hermes/hermes-agent:/root/.hermes/hermes-agent:ro \
  -v /tmp/ai-lab-agreement-results:/results -w /app \
  qws-unified-agreement:arm64 python -m pytest tests -q --tb=short \
  -p no:cacheprovider --junitxml=/results/backend-final.xml
# 1463 passed, 3 skipped, 37 warnings in 60.69s
```

最终 JUnit：1466 collected、0 failures、0 errors、3 skipped。日志 `/tmp/agreement-backend-final.log`；XML `/tmp/ai-lab-agreement-results/backend-final.xml`；Postgres XML `/tmp/agreement-postgres.xml`。临时 PostgreSQL 为本机 disposable postgres:16-alpine，非生产。

早期非最终运行存在失败：本机依赖版本不一致；第一次完整容器运行未挂载 acceptance test 要求的 Hermes 源码路径，得到 1 failed / 1458 passed / 3 skipped。补齐只读 Hermes 挂载后该用例单跑通过并重跑全套，未修改断言或跳过失败。最终 whitespace-only 清理另以 `git diff --check` 校验。

## 授权发布执行记录（持续回读）

- 用户已明确授权 commit、push、生产部署和 authorization-only apply；不含历史重放、TestFlight 或 iOS 修改。
- 开工 GitHub fetch：本地 main 与 origin/main 同为 `8f2b61850bb521bb3176e92302c64c2de9ff9706`；无分叉，旧 iOS 两份未跟踪文档及 stash 保留。
- 发布前重新执行完整隔离容器测试：`/tmp/ai-lab-agreement-results/backend-release.xml`，1463 passed、3 skipped、0 failed/error，63.94 秒。原 final XML 早于最后源码 mtime，故未只依赖旧证据。
- PostgreSQL 重新验证：旧临时端口已不存在，首次连接失败；新建本地 disposable `agreement-release-pg` 后 `/tmp/agreement-postgres-release.xml` 为 13 passed、0 skipped/failure/error，11.78 秒。
- 已核验生产入口 `root@120.24.248.58`，真实 release `/opt/releases/ai-lab-platform-8f2b61850bb5.AnFVqc`，`.deployed-sha` 与基线相同；读过真实 update.sh、Compose、容器挂载和 systemd 工作目录。
- 生产备份：`/opt/ai-lab-shared/backups/agreement-authorization-20260907-211140/`；`database.dump` 2375327 字节，SHA-256 `091530970bd0a2e8fd988a4e9bca040efed9a9f2a8f19f9642349dd93505a32e`；pg_restore --list 回读 631 行。`config.tar.gz` 保存 env/compose/systemd，`before.json` 保存 rollback 元数据；文件 0600、目录 0700，不公开凭据。
- 回滚代码：`bash /opt/ai-lab-platform/scripts/update.sh 8f2b61850bb521bb3176e92302c64c2de9ff9706`。数据库备份仅灾难恢复使用，恢复前应停写并评估新数据；不能盲目整库覆盖。
- 发现真实 Hermes host worker 缺少 DATABASE_URL；其现有共享队列为 `/opt/ai-lab-platform/data/hermes_chat_runs.sqlite3`，SQLAlchemy/asyncpg 已安装。部署前将以独立 0600 EnvironmentFile 给现有 worker 配置同一 PostgreSQL 的 localhost URL，不新建 runtime；完成后须进程环境与 DB 只读回验。

## 迁移 dry-run 与 apply 用法

先安全设置 `DATABASE_URL`（不写到命令历史/回执），确认只读数据库角色与真实 raw root：

```sh
umask 077
python3 -m scripts.migrate_agreement_authorization \
  --sync-root /ABSOLUTE/raw/dialogues/tenants > /PRIVATE/agreement-dry-run.json
```

默认 PostgreSQL `SET TRANSACTION READ ONLY`，最终 rollback；不自动建表。报告含缺少真实 acceptance 的用户、缺少 mapping、冲突/撤回、建议创建/前向绑定动作和逐笔记排除原因。不应公开用户标识/路径的审计输出。

只有在另行获得生产写授权、备份、审阅 dry-run 后，才可由发布负责人运行：

```sh
python3 -m scripts.migrate_agreement_authorization \
  --sync-root /ABSOLUTE/raw/dialogues/tenants \
  --apply --audit /PRIVATE/new-unique-agreement-audit.jsonl
```

已存在审计文件拒绝覆盖。生产 apply 已在明确授权后执行，审计回读见下。DB commit 后进程故障可留下 prepared/committed 未 verified，须先只读复核，不以缺少末行断定未提交；重复 apply 本身幂等。

## 生产迁移与功能回执

> [!success] VERIFIED 的限定范围
> 统一协议准入、真实 acceptance 驱动的两层授权投影、迁移只改授权、幂等与 worker fail-closed 配置已验证。**不是全部知识生产闭环的 E2E 验收。**

### 真实数据与精确回读

| 对象 | apply 前 | apply 后 |
| --- | ---: | ---: |
| user_agreement_acceptances | 3 | 3 |
| tenant_mappings | 45 | 45 |
| knowledge_contribution_policies | 0 | 1 |
| knowledge_contribution_user_consents | 1 | 3 |
| knowledge_contribution_outbox | 0 | 0 |
| knowledge_contribution_runs | 0 | 0 |
| knowledge_contribution_projections | 0 | 0 |

- 当前 acceptance 3 条全部 ready；42 个映射用户没有当前 acceptance。缺 mapping / 冲突 / 撤回阻塞均 0。
- dry-run 是逐 acceptance 计划：3 条记录各显示 policy create，但属于同一租户；实际事务只创建 **1 个共享 policy**。个人 consent 新建 2、已有 1 条仅 forward-only 绑定真实签约证据；无新 acceptance、无扩权或历史回填。
- raw Markdown 实际 **37**：active 29、archive 3、trash 5；排除 inactive 8、无当前签约 14、签约前 12；签约后候选 **3** 仅报告，未 enqueue。旧上下文 36/28 已过时，不能当生产当前值。
- 81 个 raw 树文件（含 sidecar/private index）的内容 SHA-256 与 mtime_ns 在授权迁移前后完全相同。部署脚本自带权限修复不改内容；本次未重存历史笔记、未伪造新时间。
- apply 审计 `/opt/ai-lab-data/runtime/agreement-authorization-20260907-211140.jsonl`，0600；prepared → committed → verified 三阶段读回，精确验证 3 个 acceptance。随后 dry-run 三条记录 policy/consent 全 unchanged，幂等通过。

### 生产功能和 runtime

- 直接调用已部署准入依赖并读取生产 DB：45 个映射用户中签约 3 个 allowed、未签约 42 个 428；3 个签约用户的 policy/consent 版本、签约时间、participation 生效时间及 contribution gate 精确校验通过。
- 实际 HTTP `GET /api/screens`、不带 `X-Client-Contract`：未签约用户 428，3 个签约用户各 200，匿名 401。认证使用操作员通过已配置共享密钥生成的 60 秒诊断 JWT，不增加角色/管理员权限，不保存 token/响应内容；**这不是 Authen 登录/iOS 客户端 E2E**，也未创建签约。
- 原 Hermes worker 缺 DB 配置已真实修复：新增 `/opt/ai-lab-shared/agreement-worker.env`（0600）及 `/etc/systemd/system/hermes-chat-worker.service.d/50-agreement-authorization.conf`。值来自当前 API 的同库 URL，仅 hostname 改为本机已发布 127.0.0.1；没有新 runtime。
- 重启后的真实 worker 进程环境读取 DB 成功、outbox 0；不存在事件 denied、去掉 DB 后 denied，均 fail closed。worker active；与 API supervisor 共享 `/opt/ai-lab-data/hermes_chat_runs.sqlite3`，inode **824124** 完全一致；API 同环境 reconcile_once advanced 0，相关 supervisor 错误日志计数 0。此 probe 不等于实际模型执行验收。
- 配置回滚只移除以上两个本轮新文件，再 daemon-reload / restart worker；详见 `worker-config-change.json`，不修改已有 env/drop-in。

### 私有证据位置

服务器根目录（含用户标识的明细不公开）：`/opt/ai-lab-shared/backups/agreement-authorization-20260907-211140/`。

- `before.json`、`database.dump`、`config.tar.gz`：发布前回滚点。
- `dry-run-before.json`、`apply.json`、`dry-run-after.json`、`migration-summary.json`：授权迁移结果。
- `db-before.json`、`db-after.json`、`source-before.json`：精确 DB 与源文件证据。
- `functional.json`、`runtime-verification.json`：授权 HTTP 与运行环境证据。
- `deploy-code.log`：源码 release 部署日志。
- `final-release.json`、`deploy-receipt.log`：回执 doc-only 提交部署后的最终三方版本回读；本文件完成后由执行器写入，不循环修改自身 SHA。

## 剩余发布门禁与已知边界

- 生产真实 acceptance/dry-run 已审阅并完成授权迁移；不宣称全部历史来源都有授权。
- 撤回后重复同版本签约不自动恢复（409），符合不复活约束；若产品需要主动重新加入，需另行明确且可审计的授权语义，不通过第二配置开关偷偷恢复。
- 仅补齐已有 pending iOS note crash recovery；其他 source surface、无 outbox 的存量候选仍未补齐。历史不在授权范围，绝不能以新时间/新版本伪造事件。
- WebSocket 持续连接在消息/25 秒心跳边界重查，不是逐个广播检查；撤回到下次检查存在有界窗口。
- worker DATABASE_URL 缺失已修复并从实际运行进程环境验证 DB 连通；共享 store inode 与 supervisor 同环境 probe 通过。无合法 outbox，未触发真实生产 Hermes 模型推理或 Red/Green 生成，不能将环境就绪等同模型链验收。
- 3 个既有 skipped 测试不构成已验证功能；警告主要是弃用项。
- 本次外部授权与源码 commit/push/deploy、生产迁移及授权功能验收均已执行；最终 doc-only 部署回读见独立 final-release.json。
