---
title: 本地 Main 抱怨日报投递
task_id: local-main-feedback-digest-20260829
status: SIGNED_PENDING_DEPLOYMENT
date: 2026-08-29
tags:
  - ops/change-manifest
  - feedback
  - hermes
protocol: cloud-user-complaint-feedback-v1@2
---

# 本地 Main 抱怨日报投递

> [!summary]
> 云端只冻结聚合摘要，不再配置或调用飞书 webhook。本地 Mac Main 使用 Hermes 原生 `send` 命令投递到已连接的飞书 Home Chat，成功后回写 ACK。

## 实现边界

- 云端 `prepare_feedback_digest`：生成并冻结稳定 Digest ID、聚合正文和 payload hash。
- 云端 `acknowledge_feedback_digest`：仅接受匹配 Digest ID 与 payload hash 的确认。
- 云端 FastAPI scheduler：移除抱怨日报外发任务。
- 本地 `scripts/local_feedback_digest.py`：SSH 拉取摘要 → `hermes send --to feishu` → 成功后 SSH ACK。
- 失败语义：发送失败不 ACK；ACK 失败会重发同一冻结摘要，保持 at-least-once。
- 数据库：为 `feedback_digest_runs.payload_content` 增加幂等启动迁移。
- 隐私边界：飞书正文仅含聚合计数与分类，不含用户原文或脱敏摘录。
- 成本：确定性脚本链路，单次运行 0 次 LLM 调用。

## 文件

- `backend/db.py`
- `backend/models/feedback.py`
- `backend/services/agent_scheduler.py`
- `backend/services/feedback.py`
- `backend/services/feedback_cli.py`
- `scripts/local_feedback_digest.py`
- `tests/test_feedback.py`
- `tests/test_local_feedback_digest.py`
- `ops/protocols/cloud-user-complaint-feedback-v1.yaml`

## 当前验收

- [x] 本地 Hermes Gateway 飞书适配器状态为 `connected`
- [x] 本地飞书 Home Chat 已设置
- [x] 定向反馈/本地投递门禁：`36 passed`
- [x] 后端全量门禁：`820 passed, 2 skipped, 10 warnings`
- [x] QWS 回归：`1 passed`
- [x] Python 编译与 `git diff --check` 通过
- [x] `hermes send --help` 确认 `--to`、`--subject`、`--file -`、`--json` 参数
- [x] v2 增量三轮复签：`main_agent / supervision / coder = APPROVE`
- [x] 功能提交 `6ca549ad2305280bf04e706828ab21f24d30a697` 已进入 GitHub `main`
- [ ] 统一 SHA 生产部署
- [ ] 本地 Cron 建立
- [x] 本地 `hermes send` 飞书实发并按 message ID 回读：目标与正文完全匹配
- [x] `~/.hermes/scripts/local_feedback_digest.py` 与提交脚本 SHA-256 一致

## 交付状态

- 分支：`main`
- 基线：`71cde6d99a32bd7836fff62e1626c92687642d66`
- GitHub 推送：`6ca549ad2305280bf04e706828ab21f24d30a697` 已推送
- 云端部署：待完成
- 本地计划：待部署和真实飞书收件验收
- 回滚点：部署前创建

## 权限与风险

- 云端不新增飞书凭据。
- 本地复用现有 Hermes 飞书连接，不复制或输出 Token。
- 服务器使用专用 `feedback-digest` 强制命令账户，不授予通用生产 Shell；本地脚本固定目标、显式绑定专用 Ed25519 私钥并启用严格 Host Key 检查。
- 本地发送前重新计算并常量时间比较 payload SHA-256；不匹配时禁止发送和 ACK。
- Cron 可独立暂停或删除，不影响聊天与反馈采集。
- 不宣称物理 exactly-once：若飞书已接收但进程在 ACK 前崩溃，可能以相同 Digest ID 重复投递。
