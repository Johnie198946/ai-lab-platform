# AI Project Office Phase 1 Completion Manifest

- task_id: `20260823-project-office-phase1`
- objective: 在现有 `/architect` React应用中加入共享同一workflow、plan、execution、events与artifacts状态的只读Office View，同时保持Workbench及全部受控操作不变。
- status: `VERIFIED / DEPLOYED`
- branch: `main`
- isolated_checkout: `/Users/dengzhaoyu/Desktop/AI Lab/wt-project-office-phase1`
- base: `0cb89e5275771f2df6e3e4a192ebd51601e2dc02`
- delivery_scope: Phase 0 + Phase 1 单屏只读投影；不含澄清提交、审批、执行启动、九屏或第二工作流引擎。

## Implemented

1. `OfficeProjection v1`纯函数合同：
   - `workflowId / planId / executionId`
   - `snapshotVersion / cursor / latestSeq / updatedAt`
   - `truthMode / connectionState`
   - `approvalState / governanceState`
   - 动态`seats / events / artifacts`
2. 真实Plan节点动态生成席位；固定六角色未进入运行模型。
3. 业务角色与`runtimeAgentId`明确分离。
4. 事件必须具真实`event_id/id`且显式绑定`node_id`才进入席位气泡；无回执不显示活动。
5. 工件只按显式节点来源或唯一明确`agent_id`映射；歧义工件仅留在全局工件带。
6. `LIVE`严格门禁：后端即使返回`truth=LIVE`，仍必须存在`started_at/hermes_session_id`且状态不能是`queued/pending`；否则降级`PLAN`。
7. `REPLAY / SIMULATION / UNCONNECTED`按对象显示；状态源断线后所有席位降级`UNCONNECTED`并停止运行中动效。
8. `view=office|workbench`路由保留全部其他query参数；Showroom默认Office，普通账号默认Workbench。
9. 带`customer_demand_id/showroom_session_id`时只加载`requirements_snapshot`中与上下文绑定的workflow；无匹配不回退到无关首任务。
10. 后端需求确认时保留已授权的`customer_demand/showroom_context`来源快照，避免确认动作覆盖任务绑定关系；不新增API字段或数据库状态机。
11. Office组件无任何API调用或写操作；所有创建、澄清、批准、启动能力仍仅在Workbench。
12. 1280×633单屏布局：六席位、工件带、员工详情均首屏可见；事件气泡与对象真相标签遮挡已实测修复。
13. 需求仍处于`clarifying`或`awaiting_requirement_confirmation`时不请求尚未生成的Plan；仅在规划及其后状态或已有`active_plan_id`时读取Plan，消除误导性的404轮询。
14. 澄清回复生命周期事件的展示消息限制为500字符，完整需求详情保留在JSON payload；提交事务异常时恢复`clarifying_pending`，避免500后workflow永久卡住；前端对重复提交409给出明确处理中提示。

## Main Verification

- `node --test tests/project-office.test.mjs`: `10 passed / 0 failed`
- `npm test`: `78 passed / 0 failed`
- `npm run build`: PASS
- backend full suite: `572 passed / 2 skipped / 0 failed`
- `git diff --check`: PASS
- production bundle: PASS；仅保留仓库既有`>500 kB` chunk warning。

## Browser Verification

实际React应用经原有登录与API链路运行，临时fixture明确声明`SIMULATION`：

1. 1280×633：六个动态席位、工件交接带、右侧员工详情全部可见，无上下排裁切。
2. Office/Workbench双向切换通过，Workbench原有操作区保留。
3. 点击席位可切换只读员工详情。
4. 顶栏只声明`已登录`，不再把认证冒充连接状态。
5. 事件气泡不再遮挡对象级`SIMULATION`标签。
6. 主动切断状态源后：页面、全部席位及员工详情统一降级`UNCONNECTED`；既有事件回执保留但不冒充在线LIVE。
7. 携带不存在的`customer_demand_id`时不加载无关历史任务，Office显示0个服务端节点。

## Governance

- no second workflow engine
- no backend/API schema mutation
- no server/Vault synchronization
- follow-up frontend-only deployment completed
- no credential persisted
- temporary fixture located outside repository and stopped after verification

## Independent Review

- Round 1：发现`queued`伪LIVE与Showroom错任务风险，已修复。
- Round 2：`P0=0 / P1=3`；发现确认后来源上下文覆盖、capability wire shape错配、清单未同步，已全部修复。
- Round 3：`PASS / P0=0 / P1=0`。

## Remaining

- Plan 404修复已部署并完成健康检查；生产LIVE开放仍需真实生产execution验收与连续演示彩排。

## Follow-up Delivery

- fix_commit: `592355ca5657eb06ffea9688e8953c8666a5333a`
- server_before: `dca7e318f3af57c35cefa1db3e2445df5a3d0a79`
- server_after: `592355ca5657eb06ffea9688e8953c8666a5333a`
- data_recovery: workflow `wf_35e4fec1f08e4e6bb54f5925ea4f9ec0` restored from `clarifying_pending` to `clarifying` after the failed 500 transaction.
- plan_polling_follow_up: retry a transient 404 when the server already exposes `active_plan_id`, including `awaiting_approval` workflows.
- deployment: `scripts/update.sh <full SHA>` completed; frontend rebuilt; runtime contract audit passed.
- health_check: API returned `{"status":"ok","version":"0.8.0"}`.
