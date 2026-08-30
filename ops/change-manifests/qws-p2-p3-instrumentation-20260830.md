---
title: QWS P2 与 P3 校准基础交付回执
date: 2026-08-30
status: IMPLEMENTED_VERIFIED_NOT_DEPLOYED
tags:
  - qws
  - change-manifest
  - p2
  - p3
---

# QWS P2 与 P3 校准基础交付回执

> [!success] 结论
> P2 六项已实现并通过本地完整门禁；P3 已实现指标采集、校准提案、按项目 L1/L2/L3 门禁、Final Project Distillation 与候选知识生命周期治理，但真实校准结论必须等待生产样本。本回执不表示已部署。

## 真源与边界

- 设计真源：[[qws-task-operating-loop-v1]]。
- 编译计划：`docs/qws-task-operating-loop-v1.compiled.json`。
- 执行状态覆盖：`docs/qws-task-operating-loop-v1.status.json`。
- QWS process snapshot 仍是任务关系唯一可写真源；项目文档只是 Obsidian-compatible 可读投影。
- Automation 只生成 `WAITING_CLAIM` 推荐；不会执行推荐，也不会绕过 `TODO → IN_PROGRESS + lease` 原子 claim。
- Telemetry 仅接受带专用 scope 的 service principal、已验证 `source_ref`、固定 measurement contract 和类型/时间白名单。
- L2/L3 仅能由交互式人类按项目配置，并同时受 capability allowlist、scope allowlist、样本量和质量门禁约束。

## 实现范围

### P2 文档与项目资产

- 文档 revision、content hash、YAML frontmatter、wikilink/backlink/broken-link 图。
- `source_ref` 校验；Task、Intake、Artifact、Decision 等可变事实必须带 revision/version。
- 项目资产只读聚合；不会复制或反向覆盖 Intake、Decision、Task、Artifact 真源。
- Project Distiller 使用确定性 cursor、预算和候选去重；只产出 `CANDIDATE`，准入/拒绝必须由交互式人类完成。
- Project Documents UI 支持 Draft/Published、tags、source refs、wikilink 与 backlink 可见性。

### P2 Automation 与 Cron

- 版本化 rule、immutable run identity、payload-drift fail-closed、recommendation 报告和采纳/拒绝反馈。
- IANA timezone、Cron 表达式与实际 slot 校验、DST fold identity、misfire/backfill、并发和幂等合同。
- novelty cluster、扫描/推荐预算和 circuit breaker。
- 新 run 必须使用最新且 enabled 的 rule；旧 rule version 只允许重放已经存在的 run。
- Automation/Telemetry API 仅允许具备专用 scope 的 service principal 调用。

### P3 校准与自治基础

- 指标：重复判断、handoff 首次行动与重复工作、ETA P50/P80、推荐采纳、Cron 噪声、一次验收、附件读取、知识准入、Challenge 避险、token 与人工打断。
- 样本量不足时明确返回 `INSUFFICIENT_REAL_DATA`，不会伪造或自动应用阈值。
- 校准只生成 proposal，阈值应用和 L2/L3 升级均需交互式人类决定。
- L3 明确禁止 production/deploy/publish/delete/credential 等 scope/capability。
- 项目关闭要求任务终态，且每个 DONE 任务的**最新** Delivery Manifest 必须为 `ACCEPTED` 并匹配当前 `task_revision`；关闭后普通 process write 由 revision + project status 双重 CAS 拦截。
- 关闭时生成项目级 Manifest、Final Project Distillation 与 Published 指针投影；正文只存在 governed payload，不复制进 immutable process revision。
- 知识候选 payload 与 immutable process metadata 分离；支持过期、纠正、权限收紧和合规删除。`RESTRICTED`/`DELETED` 不返回 payload；合规删除清除主治理表 payload、保留哈希审计收据，并明确备份受基础设施保留策略约束。

## 验证收据

| 门禁 | 结果 |
|---|---:|
| Backend pytest | `882 passed, 2 skipped, 10 warnings` |
| QWS frontend tests | `11 passed` |
| Frontend production build | 通过 |
| Ruff | 通过 |
| Python compileall | 通过 |
| Plan compiler | `READY`, 4 phases / 37 tasks / 6 decisions |
| Git diff check | 通过 |

## RYG

- **Green**：P2 六项本地实现与测试；P0/P1 既有生产状态未被降级。
- **Amber**：P3 九项事件采集/指标合同已实现但等待真实生产样本；不宣称已校准。备份物理清理由基础设施保留策略执行，不伪称即时擦除。
- **Red / TODO**：尚未部署本变更；L2/L3 不会在真实样本门禁通过前启用。

## 费用 A/B 轨

- **A 轨（本次）**：沿用现有 API、PostgreSQL process snapshot 与 Hermes Runtime；无新增固定基础设施费用，主要成本为开发、复核与生产观察。
- **B 轨（未启动）**：独立 Edge Worker/新调度基础设施；会增加运行、监控和运维成本，当前无真实负载依据，暂不投入。

## 回滚

- 代码回滚：切回部署前精确 Git SHA 与不可变 Release。
- 数据边界：本次无破坏性 schema 删除；新增 `workspace_knowledge_candidates` 与 process snapshot 字段均为 additive。
- 自治回滚：项目 policy 可由交互式人类降回 `L1`；Automation rule 可通过新版本 disabled 停止新 run，既有 run 仍可审计重放。
