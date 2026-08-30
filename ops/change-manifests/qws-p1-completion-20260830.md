# QWS × Hermes P1 阶段完成回执

- Task ID: `qws-p1-completion-20260830`
- 阶段代码状态: `PUSHED`
- 部署状态: `NOT_DEPLOYED`
- 线上验证状态: `NOT_VERIFIED`
- 分支: `main`
- 远端阶段节点: `fc663a3ad8330510d7ec690147e9ad003610bd8f`

## 结论

P1 后端纵切已经全部实现、经过专项测试与全仓测试并推送：重复检测、字段级可逆合并、`MERGED` 重定向、权限边界内的 Relation Digest、Challenge Review 和 Decision Brief。

这不等于上线完成。当前没有部署授权，且正式生产数据库 migration 仍未补齐，因此不能标记为 `DEPLOYED` 或线上 `VERIFIED`。

## P1 纵切与真源节点

| 纵切 | 状态 | 提交 |
| --- | --- | --- |
| 创建/认领前重复检测 | PUSHED | `3b1f9f54e030c33b2638f36e6119d4935580300a` |
| 字段级 Merge Preview、apply/revert | PUSHED | `3098f9e9da966c1a0520caa3b522352baf3f1fbd` |
| 合并反方审查安全收口 | PUSHED | `dbd5a54dea5032a8dde3e0965488feaf3694792d` |
| Relation Digest 与关系确认 | PUSHED | `fd83b23` |
| Challenge Review 与 Decision Brief | PUSHED | `fc663a3ad8330510d7ec690147e9ad003610bd8f` |

## 验收矩阵

### 重复检测

- 六维字段联合评分，不只比较标题。
- 创建前与执行认领前均检查。
- 强重复暂停自动认领，但不自动合并。
- 阈值继续标记为 `PENDING_REAL_DATA`，等待真实任务校准。

### 合并

- 字段级冲突预览与显式选择。
- Preview / Apply / Revert 使用 request ID 幂等并防 payload drift。
- 来源任务保留为只读 `MERGED` 并重定向主任务。
- Feedback、附件、Artifact、Decision、Handoff 与验收记录保留原身份，不扁平复制。
- 撤销校验 Project CAS、双 Task revision、内容哈希与执行租约。
- Artifact / Manifest 可从主任务聚合发现，记录不迁移、不删除。

### Relation Digest

- 聚合 canonical relations、项目 dependencies 和 `CONFIRMED` Relation Proposal。
- 只输出字段白名单、精炼摘要、确认决策与结构化 Artifact 身份引用。
- 外项目或不可定位目标仅返回固定“受限依赖”占位，不泄漏目标 ID、标题、状态或原因。
- Context Pack 只嵌入最多 3 条权限过滤后的 Relation Digest，不读取关联 Session 全聊天。
- 当前权限边界是项目 RBAC；尚未宣称实现独立的 Task/Artifact ACL。

### Challenge Review / Decision Brief

- 证据明确分类为 `FACT / INFERENCE / TO_VERIFY`。
- 服务端硬风险集覆盖安全、权限、不可逆删除、法律、泄露、生产发布、预算超限与跨任务影响。
- 确定性关键词检测为明显风险漏报提供 P1 安全网，但不冒充语义风险模型。
- HARD / SOFT 生成 Decision Brief 并进入 `DECISION_REQUIRED`；低风险可逆 NOTICE 不阻塞。
- 开放 Challenge 无法通过普通状态接口绕过；已有租约会暂停并立即过期。
- 每个选项绑定 cost 与 resolution，决策动作必须与选项一致。
- CAS 冲突后按 request ID 重新读取并收敛相同请求。

## 最终验证

```text
全仓 pytest: 854 passed, 2 skipped, 10 warnings
QWS API + Task Operating Loop 专项: 55 passed, 5 warnings
Ruff backend + tests: passed
compileall backend + tests: passed
git diff --check: passed
QWS 设计编译: READY
compiled phases: 4
compiled tasks: 37
compiled decisions: 6
source_sha256: c824eebb244c6764a05756404499624b82d19718979eb567eeaebba90c05316d
```

10 条 warning 均为已有依赖弃用提示，包括 FastAPI `on_event`、Pydantic class-based config、Starlette TestClient/httpx 和 `pkg_resources`；未出现测试失败。

2 个 skipped 测试沿用仓库原有跳过条件，本阶段没有将失败改为 skip。

## RYG

- Green:
  - P1 五个后端纵切已实现、测试、提交、推送；
  - 三轮合并反方审查与三轮 Relation Digest / Challenge Review 反方审查的 P0/P1 风险已收口；
  - 本地 HEAD 与远端 `main` 已核验一致。
- Yellow:
  - 重复阈值仍需真实任务校准；
  - Challenge 自动触发规则仍需真实复杂度/风险样本校准；
  - 确定性关键词只能作安全网；
  - 当前权限粒度是 Project RBAC，不是独立 Task/Artifact ACL。
- Red（部署门禁）：
  - `WorkspaceBusinessIntake` revision 字段及唯一约束、`WorkspaceArtifact`、`WorkspaceArtifactVersion`、`WorkspaceDeliveryManifest` 尚缺正式生产 migration；
  - 未获生产部署授权；
  - 未执行生产 migration、部署、健康检查或线上 UI 验收。

## 费用 A/B 轨

- A 轨（开发与验证）：本次使用本地仓库 `.venv`、SQLite 测试库和 GitHub 推送；未发生可单独核验的第三方基础设施付费。模型调用费用在当前运行环境中不可见，不作零费用声明。
- B 轨（部署与运营）：未部署、未执行生产 migration，因此没有可归属于本阶段的部署验证费用或线上运行费用。

## 回滚

- 代码真源为 GitHub `main`。
- 各纵切均有独立提交与完成回执；如需回退，使用常规 `git revert` 生成反向提交，不 force push、不改写历史。
- 当前未部署，因此不存在生产运行态回滚动作。
