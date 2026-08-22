# Completion Manifest

- task_id: `hermes-session-note-fix-20260822`
- objective: 排除会话总结串扰，并恢复 Hermes sandbox 的真实联网工具能力。
- status: `PUSHED`

## Diagnosis

- `scripts/hermes_bridge.py` 原先在每个进程内流式请求中无条件按隔离 `user_id` 恢复旧 Hermes session。即使 iOS 携带了权威快照，旧 session 仍可能把历史“土耳其”研究带入模型上下文。
- 生产 Hermes `/opt/hermes/venv` 的 platform tools 包含 `web`，但 `web_search`/`web_extract` 的 availability check 返回 false；DDGS 未安装，且未配置其他 web provider。因此模型收到的工具列表中没有联网工具。

## Changes

- `scripts/hermes_bridge.py`
  - 快照请求使用一次性 Hermes turn，不恢复旧映射 session。
  - 快照请求禁用 `memory` 与 `session_search` toolset，阻断历史内容回流。
  - 快照请求不覆盖用户的持久 Hermes session 映射。
  - Agent 声明已授权联网但 sandbox 无 `web` provider 时，返回明确 `web_toolset_unavailable`，不让模型伪装成普通能力限制。
  - fallback 路径同样禁止快照请求恢复旧 Hermes session。
- `scripts/update.sh`
  - 部署时检查 Hermes 专用 venv 的 `ddgs` provider，缺失则从阿里云 PyPI 镜像安装 `ddgs>=9.0`。
- `tests/test_client_session_notes.py`
  - 增加快照请求不恢复旧 Hermes session 的回归测试。

## Verification

- 本地 Python/Bridge 定向回归：87 passed，0 failed。
- Python 语法检查及 `git diff --check`：passed。
- 生产只读诊断证据：`platform_has_web=True`，但 `web_defs=[]`；`ddgs=False`，`backend=` 空；因此联网 provider 缺失结论可复现。
- 运行时代码 commit：`91c940f57d020ed917d9d99b5544b1e20ea2cb94`。
- GitHub remote/ref/SHA：`https://github.com/Johnie198946/ai-lab-platform.git` / `refs/heads/codex/hermes-session-note-draft` / `91c940f57d020ed917d9d99b5544b1e20ea2cb94`，已使用 `git ls-remote` 核对。

## Delivery

- server_before: `/opt/releases/ai-lab-platform-1d06cd3`，`.deployed-sha=53a99cdc82ef927529c77b581cbd0b02019492e2`；API healthy，Bridge active，但仍为修复前运行时代码。
- server_after: 未执行；本轮生产部署需要当前用户对该新修复再次明确授权，安全策略已阻止部署命令。
- health_check: 既有服务器健康状态此前为内外 `/health` 200；本轮未改变服务器，未重新宣称修复后健康。
- functional_check: 本地通过；生产修复后的 session 隔离及真实联网搜索尚未验收。
- rollback_point: `/opt/releases/ai-lab-platform-cd004cad`，之前建立的 main 版本回滚副本仍保留。
- remaining_risks: 修复尚未部署；生产仍可能复现旧 Hermes session 串扰，且当前 Bridge 仍缺少 DDGS provider。

## Deployment Gate

请明确授权部署本次新修复后，执行：

```text
bash scripts/update.sh 91c940f57d020ed917d9d99b5544b1e20ea2cb94
```

该命令会安装 Hermes venv 的 DDGS provider、重建服务、运行契约审计，并重启 Hermes Bridge；完成后再进行真实双账号/快照与联网功能验收。
