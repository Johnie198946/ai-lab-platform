# TestFlight Build 33 Completion

- `task_id`: `testflight-build33-20260912`
- 目标：人工合流 `Quantum/main` 与 `ai-lab-platform/main`，发布同时包含内容编辑治理、Quantum 2.0、多租户原生 Hermes 记忆、文档生成 PPT 与月度额度界面的 iOS `1.0.3 (33)`。
- `status`: `COMMITTED`

## 开工前盘点

- `branch`: `main`
- `worktree`: `/Users/dengzhaoyu/Documents/AI Lab/Quantum-2.0`
- `head`: `36200de04d7ac7eb630b177d0ae5f0dba24f1747`
- `status`: 工作区干净；相对 `source/main` ahead 4。
- `remote`: `origin=https://github.com/Johnie198946/Quantum.git`；`source=https://github.com/Johnie198946/ai-lab-platform.git`。
- `worktrees`: 当前 main worktree；两个历史 `codex/*` worktree 未修改。
- 刷新后 `origin/main=9278d981764952f39f5d1ac2b865b2a125e27316`，`source/main=50ee79f20adc56b717b761e57937ba7fd0bf86a5`，两者从 `677c9d8b983f76821f70d987a98c9f956138cf5c` 分叉。

## 合流与范围

- 用户明确授权人工合并两个 main，覆盖仓库“分叉即停止”门禁。
- 合流提交：`07d8eb8140e7a85db0b8d3e435a49db83dd23580`。
- 仅两个真实冲突：`scripts/hermes_bridge.py` 同时保留记忆 CRUD 和 PPT 审批端点；`tests/test_native_extract_dispatch.py` 保留 `keyless_rescue=false` 的严格隔离。
- 发布前 `source/main` 前进到 `9bacb5d947c146ea848ae4c5d5111677ae81a9a6`，已由 `04d876fe83bd7d9054ec30c6ab21e6638cb2eeae` 继续合入 1000 万月额度生产配置与 Hermes browser deadline patch；无冲突。
- Build 33 只使用已提交的两条 main 能力，不包含任何未提交工作区代码。

## 验证与交付

- 合流聚焦后端回归：显式绑定新版 Research Pipeline 与 Hermes 源，`330 passed, 1 skipped`。
- 全仓后端：锁定依赖环境 `2321 passed, 3 skipped`；唯一因该虚拟环境缺少 Hermes `snowballstemmer` 的用例，改用具备完整 Hermes 依赖的系统解释器单项复验为 `1 passed`。
- Ruff、Python 编译、`git diff --check`：通过。
- iOS：`164` 个单元测试全通过；`ReaderFixtureUITests` 的 `2` 个离线 UI 验收全通过。
- 两个生产 UI 验收未执行成功：分别缺少 `QUANTUMN_UI_DEV_PHONE/DEV_CODE` 与 `QUANTUMN_UI_BOOK_ID`，未从历史日志提取认证材料；这不是产品断言失败。
- 新增额度配置测试与 Hermes native dispatch 单项复验：各 `1 passed`。
- Release Archive、签名与 App Store Connect 上传：待执行。
- `head/local_commit`: Build 33 元数据提交 `6cf2530`；最终发布源提交待清单更新提交。
- `remote_sha`: 待推送和 `git ls-remote` 核对。
- `server_before`: 不适用，本任务不部署服务器。
- `server_after`: 不适用。
- `health_check`: 待 iOS 归档验证。
- `functional_check`: 待 TestFlight 上传回读。
- `rollback_point`: TestFlight Build 32；Git 合流前 `Quantum/main@9278d981764952f39f5d1ac2b865b2a125e27316` 和 `source/main@50ee79f20adc56b717b761e57937ba7fd0bf86a5`。
- `remaining_risks`: Apple 处理与测试组可见性需上传后回读；真机 PPT/记忆/额度视觉交互仍需用户验收。
