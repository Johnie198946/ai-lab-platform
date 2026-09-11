# Quantum 2.0：Hermes 托管运行时与可信模型后端方案

日期：2026-09-10

版本：2.0 架构基线 v1

适用产品：Quantum iOS 2.0、Quantum Web、服务端工作流

替代决策：《Hermes 本地运行时与可信模型后端：开源集成、安全深化完整方案》第七版中的“iPhone 内嵌 Hermes / 用户自有电脑 Host 为默认路线”

## 1. 最终产品决策

Quantum 2.0 延续 1.0.3 已验证的集中托管路线：

> 用户只安装 Quantum App。Hermes 由 Quantum 云端集中运行；每个用户拥有独立的 Hermes Profile 数据边界，但不拥有常驻进程或独立容器。多个低流量 Profile 由共享的 Hermes Multiplexer/Worker 承载，并按用户固定分片扩容。

明确不再把以下路径作为默认产品前提：

- 不要求用户在 Mac、PC、NAS 或 VPS 上安装 Hermes；
- 不把完整 Hermes Python/PTY/subprocess 运行时嵌入 App Store iOS；
- 不在 Swift 中重写 Hermes Agent loop；
- 不用“每用户一个容器或进程”换取隔离；
- 不把 Hermes 包装成可任意横向读写同一 Profile 的无状态服务。

这次调整不是对第七版换名字，而是对其核心部署前提的正式修订。第七版中仍然有效的知识同步、可信模型路由、配额结算、供应链安全和工具授权设计继续保留。

## 2. 现状与问题判定

### 2.1 1.0.3 已经具备的主链

```text
Quantum iOS
  -> AI Lab HTTPS/SSE API
  -> backend/api/chat.py
  -> 宿主机 hermes_bridge.py
  -> Hermes AIAgent
  -> 模型 Provider
```

现有可复用能力：

- iOS 已完整消费 `delta/thought/tool/clarify/done/error` 等事件；
- 服务端已有 durable run、断线恢复、取消、澄清与幂等 request id；
- 后端已从认证信息派生 tenant/user，不依赖客户端自报身份；
- SessionDB 已按 tenant/user 派生路径；
- 知识访问已有短期 capability、租户策略和 fail-closed 检查；
- Agent 缓存、worker 线程和用户锁已有上限。

因此 2.0 应扩展这条主路径，而不是再建设一套移动端 Runtime。

### 2.2 当前隔离并不完整

当前 `tenant_hermes_sandbox` 的结构近似：

```text
tenant/<tenant_hash>/
  hermes-home/                 # 租户共享
    skills/templates/
    skills/custom/
    agents/
  users/<user_hash>/state.db   # 用户独立
```

这意味着：

- 会话消息已经按用户隔离；
- Hermes Home、租户自定义 Skills 和部分 Agent 状态仍可能跨用户共享；
- `DEFAULT_TENANT_KEY` 非空时，新用户可能被统一映射到同一平台租户；
- 普通聊天显式禁用了 Host 的 context files/memory，但工作流节点尚未全部采用同一防线；
- 共享可写 Profile 一旦产生错误 memory/Skill，会把错误持续传播给其他用户。

结论：当前状态是“会话基本隔离、Profile 部分共享”，不能作为大规模消费者产品的最终安全边界。

### 2.3 代码仓库复用基线

Quantum 2.0 必须复用 [`Johnie198946/ai-lab-platform`](https://github.com/Johnie198946/ai-lab-platform)，不得另起一套应用、后端或部署脚手架。

仓库关系固定为：

```text
ai-lab-platform（1.0.3 代码与历史基线）
  -> 保留 Git 历史并持续吸收必要修复
  -> Quantum（2.0 产品与后续交付仓库）
```

截至 2026-09-10 的核对结果：

- `ai-lab-platform/main`：`b5ad115797d4edfa0e20d9c93afe64bdfb0659de`；
- 本任务最初的 Quantum 本地 HEAD：`5284db6f5090cde578b51656ad2d1ad9420a1748`；
- `5284db6` 是 `b5ad115` 的祖先，本地基线落后 7 个提交；
- 本任务 Worktree 已使用 fast-forward 对齐到 `b5ad115`；
- 新的 `Quantum` GitHub 远端当时尚无 `refs/heads/main`，首次交付前必须再次核对，不能把“远端为空”误报为已推送。

复用与改造边界：

| `ai-lab-platform` 既有模块 | 2.0 处理方式 |
|---|---|
| `ios/AIPlatformApp` | 原应用原位演进；保留 UI、网络层、聊天 reducer、本地历史和知识动作，不新建第二个 iOS App |
| `backend/api/auth.py` 与 Authen 集成 | 保留身份入口；统一 token/tenant/user 派生，Profile 身份只从可信服务端上下文产生 |
| `backend/api/chat.py` | 保留公网聊天、SSE 和旧客户端契约；逐步把 Profile 路由收敛到统一 Runtime Router |
| `scripts/hermes_bridge.py` | 保留 Hermes `AIAgent`、事件适配和工具治理；收敛重复创建入口，不重写 Agent loop |
| `scripts/chat_run_worker.py` 与 run store | 保留 durable run、断线恢复和有界 worker；增加 profile/shard 归属检查 |
| `tenant_hermes_sandbox.py` | 从 tenant 级可写 Hermes Home 演进为 user/profile 级可写目录；租户模板只读 |
| KnowledgePolicy、Wiki、书籍和笔记同步 | 原领域边界继续作为唯一真源；增加 Profile capability 绑定，不复制数据系统 |
| `docker-compose.yml`、`ops/systemd`、`scripts/update.sh` | 原部署链渐进扩展 Multiplexer/Shard；不同时引入 Kubernetes 或第二套部署系统 |
| 现有测试 | 扩展为 A/B 用户污染、Profile 生命周期、成本和迁移回归；不建立平行测试框架 |

工程规则：

1. Quantum 2.0 的首次代码基线必须包含 `ai-lab-platform` 的完整 Git 历史，禁止只复制源码快照。
2. `source` remote 固定指向 `ai-lab-platform`，`origin` 指向 `Quantum`；同步前后记录双方 SHA。
3. 上游修复优先 fast-forward 或按可审计提交吸收，禁止复制同一修复后改名提交。
4. 2.0 功能优先扩展上表中的既有主路径；证明现有抽象无法承载前，不新增平行 service/repository/runtime。
5. 旧接口保留只用于 1.0.3 兼容和可验证迁移，不将兼容层永久复制成第二套产品架构。

## 3. 官方兼容边界

Hermes 官方把 `HERMES_HOME` 作为 Profile 边界。Profile 管理以下状态：

- `config.yaml`、`.env`、`SOUL.md`；
- SessionDB、memory、Skills、插件数据；
- 日志、cron、gateway 状态；
- 工具子进程的可选独立 Home。

Quantum 2.0 遵守以下原则：

1. 一个用户默认对应一个可写 Profile；未来允许多个 Agent 时，边界升级为一个 user-agent 对应一个 Profile。
2. 两个用户不得同时读写同一个 Hermes Home。
3. 租户共享知识和模板不进入用户可写 Profile，而由显式授权的只读能力提供。
4. 所有自定义存储插件必须从请求绑定的 `hermes_home` 解析路径，禁止硬编码 `~/.hermes`。
5. Profile 可以共享进程，但不能共享可变状态。

Hermes 官方 Multiplexing Gateway 可以在一个进程中服务多个 Profile，适合大量低流量用户。但 Hermes 并不是完整的无状态多节点运行时，所以 Quantum 必须采用“有归属的状态分片”：同一时间只有一个 Runtime Shard 可以写某个 Profile。

## 4. 目标架构

```text
公网
  |
  v
Nginx / API Edge
  |
  v
AI Lab API
  |- Authen JWT / agreement / tenant context
  |- InferencePolicy / KnowledgePolicy / BookPolicy
  |- request idempotency / quota reserve / settlement
  |- SSE subscription / run status
  |
  v
Runtime Router
  |- profile_key = HMAC(server_secret, tenant_id + user_id [+ agent_id])
  |- profile_key -> shard_id 固定映射
  |- shard unavailable -> 排队、迁移或明确失败；禁止随机双写
  |
  +--> Runtime Shard A
  |      |- Hermes Multiplexer / durable workers
  |      |- profiles/<profile_key>/
  |      |- bounded active Agent cache
  |      `- local persistent volume
  |
  `--> Runtime Shard B
         `- 其他 Profile

Hermes model call
  -> AI Lab Inference Gateway
  -> Bifrost（内网路由数据面）
  -> 可信模型 Provider
```

### 4.1 三类状态必须分开

| 边界 | 内容 | 写入规则 |
|---|---|---|
| 平台共享、不可变 | Hermes 固定版本、基础工具 schema、审核过的 Skill 模板、模型路由版本 | 只随发布更新 |
| 租户共享、受控 | 企业知识、书籍授权、管理员发布的 Agent/Skill 模板、业务策略 | 通过领域 API 和 capability 访问 |
| 用户私有、可变 | SessionDB、memory、USER/SOUL、个人 Skills、插件状态、审计回执 | 仅对应用户 Profile 可写 |

租户管理员发布 Skill 时，发布的是有版本和 hash 的只读模板。用户需要修改时创建个人副本，不能原地修改租户模板。

### 4.2 Profile 磁盘结构

```text
/var/lib/quantumn-hermes/
  runtime/                         # 固定 Hermes 安装，只读
  profiles/
    <profile_key>/
      config.yaml                  # 服务端生成；用户不可提交 provider/base_url/key
      profile.yaml
      state.db
      MEMORY.md
      USER.md
      SOUL.md
      skills/
        personal/
      plugin-data/
      audit/
      home/                        # terminal.home_mode=profile 时使用
  template-releases/
    <version>/                     # 只读平台/租户模板
```

要求：

- `profile_key` 只由服务端 HMAC 派生，不包含可猜测的原始账号信息；
- Profile 根目录权限为 `0700`，文件默认 `0600`；
- 禁止路径穿越、symlink 逃逸和客户端提交绝对路径；
- 删除账号进入可恢复隔离期，随后按政策清理 Profile、备份和索引；
- 备份与恢复以完整 Profile 为单位，恢复时不能与旧写节点同时启动。

## 5. 隔离与污染防线

### 5.1 普通消费者默认工具面

默认允许：

- Hermes 会话、澄清、有限 memory；
- 受控的租户知识搜索/读取；
- 用户笔记搜索、读取和经确认写入；
- 受控远程 Web 搜索；
- 平台签名并审核过的 Skills。

默认禁止：

- 任意 shell、PTY 和代码执行；
- 任意宿主机文件读写；
- 动态安装 Python/Node 包；
- 用户自定义 stdio MCP；
- 任意 URL、provider、API key 或请求 header 注入；
- 未确认的共享知识写入。

需要完整计算机能力的企业任务进入独立的高权限执行池，使用低权限容器、独立凭据、CPU/内存/进程/网络限制；它不是普通聊天默认路径。

### 5.2 Runtime 创建规则

每一个 `AIAgent` 创建入口必须满足同一组不变量：

- 请求身份已经绑定为可信的 tenant/user/profile；
- SessionDB 来自当前 Profile；
- Hermes Home 在当前线程/任务上下文中绑定，不能只修改进程全局环境变量；
- 不读取宿主机默认 `MEMORY.md`、`USER.md`、`SOUL.md` 或工作区 `AGENTS.md`；
- toolsets 由服务端 policy 计算，客户端只能请求更少，不能扩大；
- 关闭 Agent 时释放连接、回调、临时 capability 和敏感上下文。

普通聊天、预热、工作流、澄清判断、子 Agent 和后台复盘必须共用这些不变量，不能各写一套近似初始化逻辑。

### 5.3 跨用户回归测试

至少使用用户 A、用户 B 和管理员发布模板三组身份，证明：

1. A 的会话、memory、USER/SOUL、个人 Skill 不出现在 B 的 prompt、工具列表、检索结果或日志中；
2. A 与 B 使用相同 session id、request id、Skill 名称时仍不冲突；
3. A 正在执行时 B 并发进入，不会复用 A 的 Agent、SessionDB、callback 或 capability；
4. 工作流、子 Agent、预热和断线恢复与普通聊天保持相同隔离；
5. 伪造 tenant/user/profile header、路径穿越和 symlink 全部 fail closed；
6. Profile 迁移期间旧 Shard 失去写租约后才能启动新 Shard；
7. 日志、Trace、错误响应不包含其他用户正文、密钥或路径。

## 6. 低成本运行策略

### 6.1 不按注册用户分配进程

Profile 是持久化目录，不是常驻进程。容量由“同时活跃 Agent 数”决定：

```text
所需内存 ~= Shard 基础内存
          + 活跃 Agent 数 × 单 Agent P95 增量内存
          + durable queue / stream buffer
          + 安全余量
```

必须通过压测测量 P50/P95/P99，不能用注册用户数直接推导服务器数量。

### 6.2 有界资源

- 单个消费者账号默认一个活跃主 Run；
- Agent 缓存使用 LRU/TTL 和严格上限，驱逐时关闭 Agent 与数据库连接；
- worker 达到上限后进入有界队列，队列满返回明确的稍后重试状态；
- SSE 断开只分离订阅，后台 Run 仍受总时长和预算限制；
- 子 Agent、工具调用次数、输入字符、上下文 token 和输出 token 均有套餐上限；
- 预热只针对近期活跃用户，不因登录或打开首页给所有用户创建 Agent。

### 6.3 模型成本控制

模型费用通常会先于 Profile 磁盘成本成为主要成本。2.0 使用逻辑质量档，不让 App 指定真实模型：

| 逻辑档 | 典型任务 | 策略 |
|---|---|---|
| fast | 闲聊、改写、简单事实问答 | 低成本模型，无子 Agent，较低输出上限 |
| balanced | 知识问答、一般分析 | 默认工具循环和受控上下文 |
| reasoning | 复杂规划、跨资料研究 | 套餐准入、额度预占、严格并发 |

当前 `HERMES_FAST_CHAT_MODEL` 不能继续指向高成本主力模型。请求路由必须由后端的可信策略与真实复杂度决定；fallback 不能越过套餐、地区或成本上限。

### 6.4 配额状态机

```text
new(request_id)
  -> reserved
  -> settled(actual provider usage)
  -> failed_released
  -> pending_reconcile
```

- `(subject, request_id)` 唯一；重试不能重复扣费；
- 额度预占必须使用数据库原子事务；
- provider 没返回 usage 时不能按 0 结算；
- Redis 只做短窗口 RPM、并发和缓存，不做长期额度账本；
- 日志只保存必要 usage 与匿名化标识，不保存完整 prompt/response。

## 7. 可信模型后端

### 7.1 唯一公网入口

App 仍只连接 AI Lab，不直连 Hermes Shard、Bifrost 或模型厂商。AI Lab 必须重建请求，丢弃客户端提交的：

- provider、真实 model、API key、base URL；
- fallback/model list；
- 任意 Authorization/custom headers；
- callback/webhook/MCP server/file path。

### 7.2 Bifrost 边界

Bifrost 作为内网模型路由数据面，承担：

- provider 协议适配；
- 服务端 key pool；
- 复杂度/规则路由；
- retry/fallback；
- usage 和 provider 状态。

AI Lab 仍是产品身份、套餐、额度和审计权威。Bifrost Virtual Key 不等于 Quantum 用户账号，不能直接暴露给 App。

第一阶段不建设大型模型管理后台。逻辑模型和 deployment id 使用版本化配置；密钥使用 SOPS+age 或云 Secret Manager，配置中只保存 secret reference。

## 8. 知识与记忆边界

### 8.1 用户私有记忆

- SessionDB、MEMORY、USER、SOUL 和个人 Skills 全部进入用户 Profile；
- 模型推断出的长期记忆默认待用户确认；
- 密钥、证件、支付信息不得进入 prompt memory；
- 用户删除后，后台任务不得从旧会话重新生成已删除记忆。

### 8.2 租户共享知识

共享 Wiki、书籍和企业资料不复制进每个 Profile。Hermes 通过受限工具访问：

- `wiki_search`
- `wiki_read`
- `wiki_neighbors`
- `wiki_trace`

每次调用绑定当前 capability、tenant、user、policy version 和 request id。返回最少必要片段及引用，不向 Hermes 开放 Vault 根目录。

### 8.3 用户笔记

保留第七版的可靠同步要求：

- 本地保存 `last_synced_hash` 和单调 revision；
- 写回必须携带 base hash；
- `409` 生成冲突副本，不静默覆盖；
- 删除、归档、恢复使用 tombstone/revision；
- 笔记同步与“贡献到平台知识库”完全分流。

## 9. Profile 分片与扩容

### 9.1 固定归属

数据库维护：

```text
profile_key
shard_id
generation
lease_owner
lease_expires_at
state
```

路由规则：

- 新用户按容量权重选择 Shard，并持久化映射；
- 后续请求始终回到同一 Shard；
- Shard 不可用时可以排队或执行受控迁移，不能随机落到另一个节点创建空 Profile；
- generation/lease 防止迁移期间双写；
- 单 Shard 先垂直扩展，达到并发或故障域阈值后再新增 Shard。

### 9.2 Profile 迁移

```text
停止接收新 Run
  -> 等待/取消在途 Run
  -> 冻结旧 Shard 写租约
  -> SQLite checkpoint + 完整 Profile 快照
  -> 校验文件 hash
  -> 恢复到新 Shard
  -> generation + 1
  -> 新 Shard 获取写租约
  -> 功能检查
  -> 保留旧快照作为回滚点
```

不使用多个 Pod 直接挂载并发写同一个 SQLite Profile，也不以 sticky session 冒充故障恢复。

## 10. 从 1.0.3 迁移到 2.0

### 本地实施检查点（2026-09-10）

当前分支已完成第一批可独立验证的隔离改造：Hermes Home、SessionDB、个人 Skills 和 Agent 快照进入用户目录；平台模板保持租户内只读复用；来源不明的旧租户 custom Skills 原地隔离待审；普通聊天、工作流、预热和澄清四个 `AIAgent` 入口统一禁用宿主机 context、memory 与 SOUL identity。现有 API 未改变。

这不是 2.0 全部完成。生产 TenantMapping 审计、HMAC `profile_key`、官方 Multiplexer 对齐、分片租约、可信模型网关和 iOS 2.0 状态界面仍按下列阶段推进。

### 阶段 P0：立即止血

目标：不增加服务器，先关闭已知串扰入口。

- 审计生产 `DEFAULT_TENANT_KEY` 和现有 TenantMapping；
- 禁止普通用户修改共享租户 Skill；
- 工作流、子 Agent、预热与普通聊天使用同一 Profile 隔离构造函数；
- 所有非明确用户 Profile 的 Agent 默认 `skip_context_files/skip_memory`；
- 增加双用户并发隔离测试；
- 备份共享 Profile，但不把其中 memory/USER/SOUL 自动复制给用户。

验收：跨用户测试全部通过；生产普通聊天和工作流均无法读取宿主机默认 Profile。

### 阶段 P1：用户级 Profile

目标：把可写状态从 tenant 级迁到 user 级。

- 增加服务端 `profile_key`；
- `hermes_home`、state.db、memory、个人 Skills、plugin-data 全部用户级；
- 租户模板改成只读版本；
- 迁移现有用户 SessionDB；
- 对共享 custom Skills 分类：管理员模板可发布，来源不清的内容隔离待审；
- 不迁移共享 memory，避免把历史污染固化到每个用户。

验收：同租户用户之间没有任何可写 Profile 文件共享；回归功能与 1.0.3 一致。

### 阶段 P2：官方 Profiles/Multiplexer 对齐

目标：减少自定义 Bridge 对 Hermes 生命周期和 Profile 解析的接管。

- 固定支持 Profiles/multiplex 的 Hermes upstream commit；
- 对当前 Hermes 0.19.x 行为运行兼容测试；
- 使用官方 `HERMES_HOME`/profile context 与 Multiplexer；
- 保留 AI Lab 的 Auth、policy、durable run 和 SSE 产品契约；
- 不把 App 直接暴露给 Hermes API Server。

验收：官方 profile/memory/session/skills golden tests通过；同一进程并发 Profile 不串扰。

### 阶段 P3：可信模型网关与成本治理

目标：把 provider、fallback 和额度从单个 Host 配置升级成产品能力。

- 上线 InferencePolicy；
- 建立 request id 预占/结算账本；
- Bifrost PoC 通过后仅以内网方式接入；
- fast/balanced/reasoning 三档校准；
- 免费/普通套餐限制子 Agent、后台复盘和昂贵工具；
- 建立 token、延迟、失败率、队列时间和单活跃 Agent 内存看板。

验收：重试不重复扣费；fallback 不越权；高峰期有界排队而非 OOM。

### 阶段 P4：Runtime Shards

目标：服务器能力不足时平滑增加节点。

- 增加 profile placement 与租约；
- 实现 Profile 备份、恢复和迁移；
- 按真实并发增加 Shard；
- 演练 Shard 故障、恢复和回滚。

验收：迁移无双写、无会话丢失、无跨用户状态；故障时状态和用户提示明确。

## 11. 本地验证计划

2.0 在任何 push 或服务器部署前，先完成本地验证。

### 11.1 单元与契约测试

- Profile key HMAC 稳定且不可由客户端覆盖；
- tenant/user/session/request 四级身份绑定；
- A/B 用户 memory、Skill、SessionDB、callback、capability 隔离；
- 工作流与普通聊天隔离行为一致；
- tool schema 白名单、路径和 symlink 拒绝；
- request id 幂等与 usage 状态机；
- Profile lease/generation 防双写。

### 11.2 本地集成测试

使用两个测试账号、一个共享租户模板、一个模拟恶意 Skill：

1. 并发发起普通聊天、工作流和取消；
2. A 写 memory/个人 Skill，B 询问同一关键词；
3. 重启 Bridge/Worker，恢复各自会话；
4. 模拟 SSE 断线和重复 request id；
5. 模拟 Profile 从 Shard A 迁到 Shard B；
6. 检查日志、SQLite、文件树和模型请求载荷。

### 11.3 容量基线

必须记录：

- Shard 空载 RSS；
- 每增加一个活跃 Agent 的 P50/P95 RSS；
- 1/4/8/16 并发下的首 token、总延迟、CPU 和队列时间；
- Agent 缓存命中/驱逐后的资源释放；
- 每类请求的输入、输出、reasoning、cache token；
- 单用户并发和恶意长任务下的资源上限。

没有这些数据前，不承诺一台服务器能支持多少注册用户或并发用户。

### 11.4 iOS 回归

- 1.0.3 的登录、聊天、流式、澄清、取消、恢复和知识动作保持可用；
- App 不感知 Shard、Profile 路径和真实模型；
- 服务器排队、限额、迁移和维护状态有明确 UI；
- 锁屏/断网后恢复不产生重复回答、工具写入或扣费。

## 12. 安全与运维基线

- Hermes、Bifrost、扫描器和镜像全部固定版本/commit/digest；
- SOPS+age 起步，达到多主机动态凭据需求后再评估 OpenBao/云 KMS；
- OTel 使用属性白名单，不采集 prompt、response、memory、笔记正文或 Authorization；
- Syft 生成 SBOM，Grype 检查漏洞，Gitleaks 检查凭据；
- Promptfoo 只在隔离测试环境运行跨租户、越权工具和提示注入回归；
- restic 执行加密异地备份并定期恢复演练；
- 生产变更必须先固定 GitHub SHA，再部署同一 SHA，记录回滚点。

## 13. 明确不做

- 不做 iOS 内嵌 CPython/Hermes Spike 作为 2.0 主线；
- 不保留“要求用户电脑安装 Hermes”的回退路线；
- 不新增 Swift `MobileAgentRuntime` 或第二套 Agent loop；
- 不给每个普通用户启动独立容器、端口或 systemd unit；
- 不允许用户 Profile 直接持有平台 provider key；
- 不把租户共享资料复制到用户 memory；
- 不在没有数据前引入 Kubernetes、CRDT、向量数据库或完整计费平台；
- 不以模型内容过滤器代替权限、工具白名单和系统隔离。

## 14. 首个开发切片

第一个代码切片只做隔离止血，不同时引入 Multiplexer、Bifrost 和多 Shard：

1. 建立唯一的 tenant/user ProfileContext；
2. 将用户可写 Hermes Home 与 state.db 迁到用户级目录；
3. 让所有 `AIAgent` 创建入口复用同一安全构造路径；
4. 将租户 Skill 模板只读化，个人 Skill 用户级化；
5. 增加跨用户普通聊天/工作流/预热/恢复测试；
6. 保持 iOS API 与 UI 契约不变。

这个切片通过后，才进入官方 Multiplexer 兼容验证。这样可以最少改动先关闭真实风险，并避免在隔离尚未正确时扩大并发。

## 15. 2.0 验收门槛

只有同时满足以下条件，托管式 Hermes 2.0 才可进入生产灰度：

- 用户级 Profile 边界覆盖所有 Agent 入口；
- 双用户并发污染测试通过；
- 普通消费者没有宿主机 shell/文件/stdio MCP 权限；
- 额度预占、幂等结算与断线恢复通过；
- Profile 备份恢复经过实测；
- 容量压测得出明确并发上限和排队策略；
- iOS 1.0.3 核心行为回归通过；
- 生产发布具备远端 SHA、健康检查、功能检查和回滚点。

在以上条件未满足前，只能标记为本地验证或灰度准备，不能宣称 Quantum 2.0 已上线。

## 16. 证据与参考

### 当前 Quantum 代码

- iOS 生产 API 与 SSE：[`ios/AIPlatformApp/Networking/APIClient.swift`](../ios/AIPlatformApp/Networking/APIClient.swift)
- 服务端聊天入口：[`backend/api/chat.py`](../backend/api/chat.py)
- Hermes Bridge 与 Agent 创建入口：[`scripts/hermes_bridge.py`](../scripts/hermes_bridge.py)
- durable worker 并发边界：[`scripts/chat_run_worker.py`](../scripts/chat_run_worker.py)
- 当前 tenant/user sandbox：[`backend/services/tenant_hermes_sandbox.py`](../backend/services/tenant_hermes_sandbox.py)
- 默认租户映射：[`backend/api/register.py`](../backend/api/register.py)
- 生产 Hermes systemd 配置：[`ops/systemd/hermes-bridge.service`](../ops/systemd/hermes-bridge.service)
- 1.0.3 复用基线：[Johnie198946/ai-lab-platform](https://github.com/Johnie198946/ai-lab-platform)
- 2.0 交付仓库：[Johnie198946/Quantum](https://github.com/Johnie198946/Quantum)

### Hermes 官方资料

- [Profiles：`HERMES_HOME` 与 Profile 状态边界](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/profiles.md)
- [FAQ：Profile 的 memory/session/skills 隔离要求](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/reference/faq.md)
- [Multi-profile gateways：共享 Multiplexer 与独立 Profile](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/multi-profile-gateways.md)
- [Memory provider：插件存储必须使用 profile-scoped `hermes_home`](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/developer-guide/memory-provider-plugin.md)
- [无状态多用户部署提案及当前边界](https://github.com/NousResearch/hermes-agent/issues/10107)
