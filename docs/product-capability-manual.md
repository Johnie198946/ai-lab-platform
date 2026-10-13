# Product Capability Manual

> Generated view. Do not edit manually. Gateway/Bridge semantics are governed by `docs/product-specs/capability-gateway.md`; repository engineering workflow is governed by `AGENTS.md`.

QCP version: `1.0.0`
Catalog digest: `441637f924351eca81f1a7d30894eaaf4d535b443b2e72fa865db8e81090d104`

## Gateway 核心模块规范

### 1. 产品定位与目标

Capability Gateway（下称 Gateway）是 PCM/QCP 的统一能力入口，也是可独立演进、可替换实现的核心模块。它把 Hermes 原生工具、Web/iOS 操作、工作流节点和后台任务统一收敛到同一组版本化能力契约、策略校验、领域 Handler、事件和回执；它不是第二套 Agent Runtime，也不是业务逻辑或数据真相源。

目标：

- 同一业务动作无论来自自然语言、按钮、工作流还是后台任务，都执行同一 Capability Contract 和同一领域 Handler。
- 发现、授权、执行、渲染、验证和回执可独立审计，禁止“可发现即有权执行”。
- Gateway 可以进程内调用，也可以由受控 HTTP/MCP adapter 暴露；不同传输方式不得改变语义、安全和回执要求。
- 新增能力通过模块化契约和注册完成，不修改 Gateway 核心分发逻辑。

非目标：

- 不在 Gateway 内复制领域规则、持久化业务主数据或实现第二套工作流引擎。
- 不把纯视觉组件、页面跳转细节或 SwiftUI/React 类型名注册为产品能力。
- 不允许客户端、Prompt、Skill 或 adapter 绕过 Gateway 直接执行已纳管的副作用。
- 不以动态 search/describe 作为正常业务执行的必经链路；已实现且客户端支持的能力应在会话装配时编译为 Hermes 原生工具。search/describe 仅用于治理、调试和兼容性发现。

### 2. 模块边界与真相源

| 模块 | 职责 | 不得承担 |
|---|---|---|
| Capability Contract | 定义 capability ID、独立版本、输入/输出、effect、confirmation、idempotency、result event | 授权用户或直接修改领域数据 |
| Resource/Event Schema | 定义资源快照、事件 envelope、错误和 receipt schema | 推断业务权限 |
| Policy Resolver | 根据服务端身份、租户、客户端能力和资源状态计算允许调用的能力 | 信任客户端自报 tenant/user 或扩大工具权限 |
| Gateway Dispatcher | 校验 envelope、解析版本、执行策略门禁、路由 Handler、统一错误/遥测/回执 | 写业务分支或绕过 Handler |
| Domain Handler | 最终授权、资源版本检查、业务执行、事务/补偿、结果回读 | 信任 discovery 或 proposal 的历史判断 |
| Renderer Contract | 将语义事件映射到可版本协商的 UI，声明 action、最低客户端版本和 fallback | 持有执行权限或直接写 Store |
| Transport Adapter | HTTP、Hermes native tool、MCP、workflow node 等协议适配 | 改写 capability 语义或吞掉错误/回执 |

业务主数据以领域服务/Store 为真相源；PCM/QCP 契约目录是调用语义真相源；Gateway 只保留幂等、确认、审计和运行所需的最小状态。

#### 2.1 Gateway 分层

- **Capability Gateway** 是 PCM/QCP 的逻辑统一入口，负责契约、策略、确认、幂等、Handler 绑定和回执。
- **Domain Gateway** 是受 Capability Gateway 约束的领域模块，例如 Knowledge Gateway；它负责领域检索、读写屏障和结果验证，但不获得第二套身份、会话或能力注册表。
- **Transport Adapter** 只连接 Hermes native tool、HTTP、iOS/Web 或后台任务；它不得越过 Capability Gateway 直接取得领域执行权。

同一进程内可直接调用 Domain Gateway，跨进程可使用受控 HTTP/MCP adapter，但两者必须执行相同的 principal、scope、版本和回执契约。Domain Gateway 不能把“已发现资源”“已有索引记录”或“上游已授权”当作最终执行授权。

#### 2.2 Knowledge Gateway 专项合同

Knowledge Gateway 是知识读取、检索和披露的唯一领域边界。标准链路为：

```text
signed capability
-> current policy and entitlement validation
-> catalog admission
-> live file and durable consent/revocation barrier
-> request-scoped authorized snapshot
-> lexical/link/content processing
-> final file, durable-state and policy revalidation
-> bounded evidence result and audit receipt
```

开发约束：

- 请求级授权快照只能由可信边界在完成文件、数据库和模型披露检查后创建；只能收窄，不能扩权，不得跨请求缓存。
- 快照内的检索、排序和 WikiLink 解析复用已验证元数据，不得对同一路径、同一版本逐链接重复解析 frontmatter。
- 没有请求级授权快照的直接调用必须继续执行实时文件门禁；不得提供模型或调用方可设置的 `skip_auth`、`trusted`、`bypass` 参数。
- Gateway 返回前必须重新验证完整响应涉及的授权集合和当前 policy version；任何中途撤回、版本变化或授权读取失败均 fail closed，不返回部分证据。
- Hermes 发送答案前仍须对实际引用路径执行有界的 `path + version` 复核；该终检不能被 Gateway 内部快照替代。
- 索引、矩阵、搜索命中和缓存均不授予读取权限；授权真相来自当前策略、实时治理元数据和持久授权状态。
- 授权错误、系统错误、无命中和证据不足必须使用不同状态；超时不得伪装成无命中。

Bridge 消费裁决合同：

- Gateway 只裁决“当前请求可返回哪些知识证据”；Hermes Bridge 独占“最终答案是否消费了受控知识、能否发送”的裁决。Backend、Worker、Adapter 和客户端只能透传，不得再次解释或放宽状态。
- Bridge 必须分别记录权威布尔值 `required_internal_knowledge`、`attempted_internal_search`、`consumed_internal_knowledge`，以及引用复核和最终 `decision`；不得用单个 `knowledge_search:error` 同时表示这些事实。
- `required_internal_knowledge` 仅由服务端 triage 的明确内部知识证据要求产生，并且与 capability、授权和工具当前是否可用完全独立。能力缺失只能产生 `denied/unavailable`，不能把 required 降成 false。普通问答的后台预读为 optional；客户端、Prompt 和模型不能选择或降低 requirement。
- 服务端预读、Hermes 直接 `knowledge_search` 和 deferred `tool_call(name=knowledge_search)` 必须进入同一个 observer；任何正文或 title/snippet/path/version 等租户知识元数据进入 Hermes 上下文，都将 `consumed_internal_knowledge` 单调设置为 true，后续零命中不能回退。
- `optional + not_exposed` 在 Gateway `no_match|insufficient|timeout|system_error` 时不得被知识安全门禁阻断；有成功公开 URL 时记为 `allowed_public_only`，否则记为 `allowed_without_internal_knowledge`。公开问答是否必须联网取证属于独立的回答质量策略，不能由知识授权门禁越权代管。授权拒绝始终阻断。
- 只要内部正文或元数据已暴露给模型但没有可复核引用，`consumption` 必须为 `unknown` 并 fail closed；外网 URL 不能清洗或替代这次内部知识消费。
- 内部引用必须经过发送前 `path + version` 复核才能得到 `allowed_internal`；有公开工具证据时得到 `allowed_public_only`，无内部消费且无公开工具证据时得到 `allowed_without_internal_knowledge`。三者的 receipt semantic 不得相同。

稳定状态合同：

| 平面 | 允许值 | 所有者 |
|---|---|---|
| Gateway retrieval | `matched / no_match / insufficient / denied / error` | Knowledge Gateway |
| Failure kind | `none / authorization / timeout / malformed_result / system / revalidation / citation_violation / version_conflict` | Gateway Adapter + Bridge 终检 |
| Requirement | `required_internal_knowledge: bool` | 服务端 Triage + Bridge 复算 |
| Attempt | `attempted_internal_search: bool` | Hermes Bridge observer |
| Consumption | `consumed_internal_knowledge: bool`，附 `cited / not_exposed / unknown` 显示语义 | Hermes Bridge observer |
| Decision | `allowed_internal / allowed_public_only / allowed_without_internal_knowledge / blocked_*` | Hermes Bridge |

类型化裁决从 `knowledge_gate_receipt.v2` 开始。新增状态必须通过版本化 receipt 扩展；旧字段在迁移期只作兼容显示，不再作为授权或发送判断真相源。任何组件收到未知枚举值时 fail closed，并保留原始错误码用于审计。

性能合同：

- 文件门禁读取次数必须随候选文档数线性增长，不得随 WikiLink 边数退化为平方复杂度。
- 生产形态基准必须覆盖冷/热运行、链接密集文档、中途撤权和并发容量；记录分阶段 P50/P95/P99，不记录查询正文或身份明文。
- 生产必须启用 `KNOWLEDGE_GATEWAY_PERF_OBSERVE`；tenant Wiki 与 publication 混合范围不得绕过同一分段指标。
- 当前普通知识预读取目标为 P95 不超过 3 秒，任何单次不得超过 5 秒发送门禁；未达到目标应优化重复工作，不得仅放宽安全超时。
- 性能优化不得删除请求开始、Gateway 返回前、Hermes 发送前这三道独立复核，也不得引入跨请求授权缓存。

#### 2.3 QuanSyn relay-only 邮箱合同

QuanSyn 是双向邮箱。公开 `/pull`、`/push`、Desktop 按钮不得启动模型/Agent 回合、执行 Web 需求或推断 qs request 绑定。复用现有 transfer/files HTTP APIs、Hermes SessionDB/SessionStore、Desktop composer hook 和 Feishu adapter；禁止第二套 runtime/router/registry。

- `/pull` 有界分页读取全部当前新 Web-to-Mac 消息，最多 100 条，超限明确失败。文本与全部附件下载、哈希验证完成后才能展示。Desktop 插入当前 composer，不发送，随后确认导入；Feishu 在 pre_gateway_dispatch 拦截，使用现有 adapter 发送完整“待发送草稿”卡片（含附件名与路径），成功后确认导入并返回 skip。任何部分失败不得声称成功。
- `/push` 在 Desktop middleware 和 Feishu pre_gateway_dispatch 确定性执行，不使用 model tools、tool_describe、ai_lab_execute 或工具状态。Feishu 使用 SessionStore.get_or_create_session(source) 解析同一个当前会话，不能猜测会话 ID。
- 只读当前 Hermes session 持久可见 user/assistant 消息；排除 hidden/system/tool/error/streaming intermediates、工具调用、slash 命令和已标记 QuanSyn origin。保留时间顺序与角色。
- owner + session 的持久游标仅在 POST 成功且按 transfer ID 回读的正文、方向、目标与附件引用完全一致后推进。首次候选为全部合格消息，以后为 ID 大于成功游标的消息；超过五条只发布最新五条，skipped_count 明示较早未推送消息被永久丢弃。无新消息返回确定性 no-op success。
- 一个稳定幂等批次，无 reply_to/request 绑定；request_id 基于 owner/session/source IDs、准确文本与文件哈希。所有 MEDIA: 路径与 [Image attached at: /path] 附件通过现有 /files 上传。缺失、不安全、超 25 MB、超过 10 个、上传中变化、上传或发布失败均拒绝整个批次且不移动游标；已上传孤立文件由既有服务端生命周期管理。
- owner/principal 只从可信本机配置解析，凭据继续从 Keychain 读取。未知/未确认回执 fail closed。
- Desktop composer 插入 hook 不提供持久 origin 元数据，用户后续发送拉取草稿可能再次推送；不使用文本去重猜测来源。Feishu 草稿是 adapter 展示消息，不写入模型历史。
- `/copy` 仅发布当前 draft 正文，不推断 request 绑定。旧 `/quansyn`、“执行 QuanSyn …”“拉取并执行 QuanSyn …”与显式带 ID 的历史回传入口全部禁用；只保留本机设备配对所需的“绑定 QuanSyn …”。

### 3. 统一调用模型

所有 adapter 必须归一化为同一个逻辑调用：

```text
invoke(
  capability_id,
  capability_version,
  canonical_input,
  principal_context,
  client_context,
  request_id,
  idempotency_key,
  resource_versions,
  confirmation_token?
) -> CapabilityResult | CapabilityError
```

必填上下文：

- `principal_context` 仅由可信服务端认证结果生成，至少绑定 tenant、user/principal、session 和授权 epoch；客户端同名字段不得覆盖。
- `client_context` 至少包含入口、App/protocol/renderer 版本和支持的事件集合，用于兼容性判断，不作为身份凭证。
- `request_id` 用于全链路追踪；产生副作用的调用必须同时提供 tenant-scoped `idempotency_key`。
- 对并发敏感资源，调用必须携带当前资源版本、CAS hash 或等价前置条件。

标准执行顺序：

1. **Normalize**：adapter 只做协议解析和 canonical input 规范化。
2. **Resolve**：按精确 `capability_id@version` 解析；不允许模糊匹配或静默降级到不兼容版本。
3. **Authenticate**：从服务端会话/JWT/运行上下文生成 principal，拒绝客户端伪造身份。
4. **Authorize**：Policy Resolver 校验 tenant、principal、entitlement、effect、scope、服务状态和客户端渲染能力。
5. **Confirm**：需要确认的 mutate/execute 调用必须验证一次性 confirmation token。
6. **Deduplicate**：在执行前原子检查幂等记录；相同 key 和相同 canonical input digest 重放原结果，不同 digest 返回冲突。
7. **Execute**：调用唯一领域 Handler；Handler 在写入点再次校验权限和资源版本，防止 TOCTOU。
8. **Verify**：从领域真相源回读关键结果；不得仅凭函数返回值声称成功。
9. **Emit**：输出版本化语义事件、结构化结果和可持久化 receipt。
10. **Observe**：记录脱敏审计、延迟、状态和错误分类，不记录密钥或不必要正文。

### 4. 副作用与确认规范

所有 `write` / `execute` 能力统一采用：

```text
Proposal -> Confirm -> Execute -> Verify -> Receipt
```

- Proposal 只描述拟执行动作，不包含确认权限，不得触发写入。
- confirmation token 必须绑定 tenant、principal、session、request、capability ID/version、canonical input digest、资源版本、renderer protocol、过期时间和 nonce，并且单次消费。
- 确认之前资源版本变化、策略变化、客户端已不支持结果 renderer 或 token 过期时，调用必须失败关闭并要求重新提案。
- 跨服务动作使用可恢复步骤、明确超时和 compensation receipt；不得伪装成无法提供的全局事务。
- 客户端设备动作（文件选择、打开页面、系统分享）作为 `client_action` 事件交给 Native Executor，并要求客户端回传 receipt；它不是领域 Handler，也不是第二套 Runtime。

### 5. 开发规范

新增或修改 Gateway 能力必须同时完成以下工件：

1. 在模块化目录中声明 Capability Contract；一个文件/模块只承载一个稳定领域或一组强相关能力，禁止持续膨胀的单体 YAML。
2. 定义或复用输入、结果、错误、事件和 receipt schema；公共 envelope 通过 `$ref` 组合，不复制字段定义。
3. 注册唯一领域 Handler 和显式 allowlist binding；禁止通过命名约定或反射自动获得执行权。
4. 对有业务语义的结果注册 Renderer Contract、最低客户端版本、支持 action 和 fallback；纯布局组件不注册。
5. 为 `read`、`client`、`write`、`execute` 明确 effect、confirmation、idempotency、receipt、超时和重试策略。
6. 添加正向、未授权、跨租户、版本不兼容、输入非法、幂等重放、幂等冲突、资源版本冲突、确认重放和 Handler 失败测试。
7. 更新 PCM、覆盖矩阵和变更记录；生成物必须由生成器更新，不手工修改生成表格。

Handler 约束：

- Handler 接收已规范化输入和服务端 principal，但仍负责最终授权和资源版本检查。
- Handler 不读取 Prompt 文本推断权限，不信任客户端传入的 owner/tenant，不返回未声明字段。
- 写入应尽可能使用领域事务；外部副作用必须有可重试状态机或补偿策略。
- 错误必须映射到稳定错误码，不向调用方泄露堆栈、密钥、内部路径或跨租户存在性。
- 实现必须可取消并设置有界超时；重试仅用于声明为可重试且幂等安全的失败。

版本规范：

- Capability、Event、Renderer、Receipt 分别版本化，不要求锁步升级。
- 删除字段、收紧枚举、改变默认值/副作用/授权语义属于破坏性变更，必须提升主版本。
- 新增可选字段或向后兼容的错误码可提升次版本；文字说明修正可提升修订版本。
- 服务端可以并行支持多个已发布版本，但必须有弃用日期、调用量观测、迁移负责人和退出门槛；禁止静默重写旧版本语义。

### 6. 调用规范

Hermes/Skill/Workflow 调用方：

- 优先调用会话装配时生成的原生 capability tool；不得自行拼接内部 HTTP、数据库写入或领域 Store 操作。
- 只提交 schema 声明的业务输入。tenant、user、授权、receipt 状态等服务端字段不得由模型生成。
- 收到 proposal 后必须等待真实用户确认；模型、Skill 和子 Agent 均不得代替用户确认。
- 对 `capability_disabled`、`not_authorized`、`version_unsupported`、`confirmation_required`、`resource_conflict`、`idempotency_conflict` 不得盲目重试。
- 只有 `retryable=true` 且保留同一 idempotency key 时才能自动重试；修改输入必须使用新 key，并在需要时重新确认。
- 最终答复只能依据已验证的 result/receipt；proposal、queued、accepted 或 HTTP 2xx 不等于业务完成。

Web/iOS/后台调用方：

- 使用官方 SDK/API adapter，并传递支持的协议、事件和 renderer 版本；不得调用内部 Handler。
- UI action 必须引用服务端签发的 proposal/action ID，不能把本地按钮状态当作授权。
- 客户端至少处理结构化成功、可恢复失败、不可恢复失败、版本不支持和安全 fallback；未知事件不得触发副作用。
- 断线恢复必须使用 request/receipt 查询或事件重放，不重新生成随机幂等键重复执行。

### 7. 标准错误、回执与可观测性

最低错误集合：

| 错误码 | 含义 | 默认是否可重试 |
|---|---|---|
| `contract_invalid` | 输入或 envelope 不符合版本化 schema | 否 |
| `capability_not_found` | 能力或版本不存在 | 否 |
| `capability_disabled` | 能力被策略或发布开关禁用 | 否 |
| `not_authenticated` / `not_authorized` | 身份无效或权限不足 | 否 |
| `renderer_unsupported` | 客户端无法安全展示确认或结果 | 否，升级/切换客户端后重试 |
| `confirmation_required` / `confirmation_invalid` | 缺确认或 token 无效/过期/已消费 | 否，需重新提案 |
| `resource_conflict` | CAS/资源版本冲突 | 否，刷新后重新提案 |
| `idempotency_conflict` | 同 key 对应不同输入 digest | 否 |
| `rate_limited` | 超出配额或速率 | 是，遵循 `retry_after` |
| `dependency_unavailable` | 下游暂时不可用 | 仅在 `retryable=true` 时 |
| `execution_failed` | Handler 失败且未完成业务动作 | 由 receipt 明确 |
| `verification_failed` | 已执行但回读无法确认结果 | 不自动重做，转人工/补偿 |

每次调用至少记录：`request_id`、tenant/principal 的不可逆标识、capability ID/version、入口、policy 版本、input digest、idempotency key 的哈希、confirmation 状态、Handler、结果状态、事件/receipt ID、延迟和错误码。日志和指标不得包含 Bearer token、confirmation token、API key、完整敏感正文或跨租户可识别数据。

核心指标：成功率、P50/P95/P99 延迟、授权拒绝率、幂等重放/冲突率、确认过期/重放率、Handler/verification 失败率、旧版本调用量、未知 renderer 率、旁路违规数。对 mutate/execute 的旁路违规数目标恒为 0。

### 8. 测试、发布与治理门禁

合并前硬门：

- Schema 编译、Catalog 加载、PCM 生成和覆盖矩阵检查通过。
- 每个能力存在“契约 → binding → Handler → event → renderer/fallback → test”的闭环；不适用项必须显式说明。
- mutate/execute 覆盖跨租户拒绝、确认绑定与单次消费、并发幂等、资源冲突、回读验证和日志脱敏。
- adapter 一致性测试证明 Hermes native tool、HTTP、工作流等入口对同一输入产生等价领域调用和稳定错误。
- CI 扫描禁止新增绕过 Gateway 的 mutate endpoint、客户端直写 Store 或未登记 Handler。

发布要求：

- 先发布向后兼容 schema/Handler，再发布客户端 Renderer，最后启用能力；破坏性升级必须灰度。
- feature flag、回滚条件、on-call、dashboard、旧版本兼容窗口和迁移 owner 在启用前明确。
- 完成标准是调用可被授权执行、客户端可渲染、结果已回读验证、receipt 可追溯；“目录中有条目”不等于完成。

迁移旧入口时采用 strangler：先让旧入口调用 Gateway，禁止双写；当旧路径调用量归零、契约测试和生产回执达到门槛后删除旧执行代码，仅保留必要的历史数据解码。

### 9. 组件验收标准

Gateway 作为核心模块达到可发布状态，必须同时满足：

- **唯一入口**：所有已纳管副作用均经过 Gateway，自动旁路扫描和运行时审计无例外。
- **模块可扩展**：新增能力只增加契约、binding、Handler、renderer 和测试，不修改核心 dispatcher 分支。
- **入口一致**：同一 capability 从 Hermes、Web/iOS、工作流调用具有一致授权、幂等、错误和 receipt 语义。
- **安全关闭**：身份伪造、跨租户、版本未知、确认重放、资源过期和不支持 renderer 均 fail closed。
- **可恢复**：超时、断线和进程重启后可通过同一 request/idempotency/receipt 继续判断，不重复副作用。
- **可审计**：任何业务结果都能从 request 追踪到 policy、Handler、事件、验证和 receipt，且审计信息已脱敏。
- **可退役**：版本和旧入口有量化退出条件，不形成永久双轨。

### 10. 开发、接入、联调与 Debug 执行合同

本文件是 Gateway/Bridge 产品语义的唯一规范真相源。仓库根 `AGENTS.md` 负责强制所有工程任务进入本合同；PCM 是由本文件生成的产品能力视图；架构文档只解释运行链。任何生成物、架构说明、实现、测试或运行态与本文件冲突时，必须阻断发布并显式修正规范或实现，不得静默选择更宽松的解释。

#### 10.1 开发与变更设计

动手前必须形成最小影响清单：capability/domain、契约和 receipt 版本、状态所有者、唯一 Handler、全部调用 adapter、业务真相源、授权与确认边界、幂等/CAS、错误集合、超时与性能预算、迁移和回滚点。新增字段或状态必须明确所有者和单调性；不得用一个字符串同时表达 requirement、attempt、retrieval、consumption 和 decision。

变更只应发生在拥有该语义的模块：Gateway 负责可返回的领域证据，Bridge 负责最终消费与发送裁决，Domain Handler 负责最终业务授权和写入，adapter/Worker/客户端只做受控转换、透传和渲染。禁止为局部接入复制授权逻辑、候选索引、状态机或 Runtime。

#### 10.2 对接与联调

- 每个入口必须证明其 canonical input、服务端 principal、capability/version、Handler binding、错误、事件和 receipt 与其他入口等价；入口差异只能存在于协议和 renderer 层。
- 联调矩阵至少覆盖：成功、认证失败、授权拒绝、跨租户、输入非法、版本/renderer 不兼容、未知枚举、确认缺失/重放、幂等重放/冲突、资源冲突、依赖超时、断线恢复、Handler 失败和回读验证失败。
- Knowledge Gateway/Bridge 还必须覆盖 required/optional、attempted/unattempted、matched/no_match/insufficient/denied/timeout/system、consumed/not_exposed/unknown、发送前撤权/版本变化以及运行期直接和 deferred `knowledge_search`。
- UI、Workflow 和后台任务必须使用 durable request/receipt 恢复状态；不得因重连生成新幂等键重复副作用，也不得将 queued、accepted、HTTP 2xx 或进程退出 0 显示为完成。

#### 10.3 Debug 与事故定位

Debug 必须按以下证据顺序进行，后层不得替代前层：

1. 用 `request_id`、durable run ID 和终态确认请求是否实际执行、重试、取消或恢复。
2. 读取版本化结构化 receipt；Knowledge 路径先核对 `required_internal_knowledge`、`attempted_internal_search`、`consumed_internal_knowledge`、`retrieval_status`、`failure_kind`、`consumption` 和 `decision`。
3. 读取 Gateway/Handler/Bridge 的分阶段 timing，区分排队、授权、候选构建、检索/执行、返回前复核、发送前终检和客户端渲染。
4. 回读当前 policy、entitlement、capability/catalog/schema/renderer 版本、资源/CAS 版本和部署 revision；历史 discovery 或缓存不得作为当前授权证据。
5. 对照脱敏日志、事件和 receipt ID 还原跨组件链路；不得记录或外发 token、密钥、完整敏感正文和跨租户标识。
6. 最后检查 adapter 和客户端展示。用户可见错误文案只能作为症状，不能据此把 timeout、no_match、malformed result 或系统错误判为授权拒绝。

修复必须落在状态所有者，并补充能复现根因的回归。禁止用扩大安全超时、全局 fail-open、吞掉服务端错误、客户端重解释、关键词/版本特判、无界重试或第二套状态真相源掩盖问题。

#### 10.4 完成证据

完成声明必须同时给出：规范/契约版本、目标测试与结果、生成和防漂移检查、性能口径、旁路扫描、实际调用入口、durable run 终态、结构化 receipt、部署 revision（如发布）及剩余风险。模拟器、真机、测试环境和生产环境必须分别表述；测试通过不能替代生产回执，部署成功不能替代业务结果回读。

## Capability inventory

| Capability | Domain | Effect | Confirmation | Receipt | Event | Renderer | Status |
|---|---|---|---|---|---|---|---|
| `agent.create@1.0.0` | agent | write | required | required | `agent.changed` | `answer@1` | implemented |
| `agent.delete@1.0.0` | agent | write | required | required | `agent.changed` | `answer@1` | implemented |
| `agent.evaluate@1.0.0` | agent | write | required | required | `agent.changed` | `answer@1` | implemented |
| `agent.evaluation_status@1.0.0` | agent | read | none | none | `agent.snapshot` | `answer@1` | implemented |
| `agent.list@1.0.0` | agent | read | none | none | `agent.snapshot` | `answer@1` | implemented |
| `agent.update@1.0.0` | agent | write | required | required | `agent.changed` | `answer@1` | implemented |
| `artifact.consume_structured@1.0.0` | artifact | read | none | required | `artifact.consumed` | `artifact_consumption@1` | implemented |
| `artifact.download@1.0.0` | artifact | read | none | none | `artifact.download_ready` | `artifact@1` | implemented |
| `artifact.open@1.0.0` | artifact | read | none | none | `artifact.content` | `artifact@1` | implemented |
| `bookshelf.open@1.0.0` | bookshelf | read | none | none | `bookshelf.opened` | `bookshelf@1` | implemented |
| `bookshelf.search@1.0.0` | bookshelf | read | none | none | `bookshelf.results` | `bookshelf@1` | implemented |
| `bookshelf.subscribe@1.0.0` | bookshelf | write | required | required | `bookshelf.subscription_changed` | `bookshelf@1` | implemented |
| `data.analyze@1.0.0` | generated_artifact | write | required | required | `artifact.generated` | `data_analysis_card@1` | implemented |
| `document.word.create_from_text@1.0.0` | document | write | required | required | `document.created` | `workflow@1` | implemented |
| `file.download@1.0.0` | client_action | client_action | required | required | `client.action.requested` | `client_action@1` | implemented |
| `file.pick@1.0.0` | client_action | client_action | required | required | `client.action.requested` | `client_action@1` | implemented |
| `file.upload@1.0.0` | client_action | client_action | required | required | `client.action.requested` | `client_action@1` | implemented |
| `hermes.session.delete@1.0.0` | hermes_session | destructive | required | required | `hermes.session.deleted` | `hermes_session_detail@1` | implemented |
| `hermes.session.list@1.0.0` | hermes_session | read | none | none | `hermes.session.listed` | `hermes_session_list@1` | implemented |
| `hermes.session.open@1.0.0` | hermes_session | read | none | none | `hermes.session.opened` | `hermes_session_detail@1` | implemented |
| `hermes.session.resume@1.0.0` | hermes_session | write | required | required | `hermes.session.resumed` | `hermes_session_detail@1` | implemented |
| `knowledge.navigation@1.0.0` | knowledge | client | none | none | `knowledge.navigation` | `knowledge_action@1` | implemented |
| `knowledge.note.archive@1.0.0` | knowledge | write | required | required | `knowledge.action` | `knowledge_action@1` | implemented |
| `knowledge.note.create@1.0.0` | knowledge | write | required | required | `knowledge.action` | `knowledge_action@1` | implemented |
| `knowledge.note.merge@1.0.0` | knowledge | write | required | required | `knowledge.action` | `knowledge_action@1` | implemented |
| `knowledge.note.read@1.0.0` | knowledge | read | none | none | `knowledge.note` | `answer@1` | implemented |
| `knowledge.note.restore@1.0.0` | knowledge | write | required | required | `knowledge.action` | `knowledge_action@1` | implemented |
| `knowledge.note.search@1.0.0` | knowledge | read | none | none | `knowledge.results` | `answer@1` | implemented |
| `knowledge.note.update@1.0.0` | knowledge | write | required | required | `knowledge.action` | `knowledge_action@1` | implemented |
| `media.create@1.0.0` | generated_artifact | write | required | required | `artifact.generated` | `image_card@1` | implemented |
| `memory.create@1.0.0` | memory | write | required | required | `memory.changed` | `answer@1` | implemented |
| `memory.delete@1.0.0` | memory | write | required | required | `memory.changed` | `answer@1` | implemented |
| `memory.list@1.0.0` | memory | read | none | none | `memory.snapshot` | `answer@1` | implemented |
| `memory.update@1.0.0` | memory | write | required | required | `memory.changed` | `answer@1` | implemented |
| `notification.list@1.0.0` | notification | read | none | none | `notification.snapshot` | `answer@1` | implemented |
| `notification.mark_read@1.0.0` | notification | write | required | required | `notification.changed` | `answer@1` | implemented |
| `notification.preferences.update@1.0.0` | notification | write | required | required | `notification.preferences_changed` | `answer@1` | implemented |
| `office.pdf.create@1.0.0` | generated_artifact | write | required | required | `artifact.generated` | `artifact_card@1` | implemented |
| `office.spreadsheet.create@1.0.0` | generated_artifact | write | required | required | `artifact.generated` | `artifact_card@1` | implemented |
| `paper.academic.create_from_text@1.0.0` | paper | write | required | required | `document.created` | `workflow@1` | implemented |
| `photo.capture@1.0.0` | client_action | client_action | required | required | `client.action.requested` | `client_action@1` | implemented |
| `photo.import@1.0.0` | client_action | client_action | required | required | `client.action.requested` | `client_action@1` | implemented |
| `presentation.create_from_document@1.1.0` | presentation | write | required | required | `presentation.created` | `presentation_review@1` | implemented |
| `presentation.create_from_text@1.1.0` | presentation | write | required | required | `presentation.created` | `presentation_review@1` | implemented |
| `profile.read@1.0.0` | profile | read | none | none | `profile.snapshot` | `answer@1` | implemented |
| `profile.update@1.0.0` | profile | write | required | required | `profile.changed` | `answer@1` | implemented |
| `project.create@1.0.0` | project | write | required | required | `project.created` | `answer@1` | implemented |
| `project.delete@1.0.0` | project | write | required | required | `project.change_proposed` | `answer@1` | implemented |
| `project.list@1.0.0` | project | read | none | none | `project.snapshot` | `answer@1` | implemented |
| `project.open@1.0.0` | project | read | none | none | `project.snapshot` | `answer@1` | implemented |
| `project.update@1.0.0` | project | write | required | required | `project.change_proposed` | `answer@1` | implemented |
| `report.research.create_from_text@1.0.0` | report | write | required | required | `document.created` | `workflow@1` | implemented |
| `schedule.create@1.0.0` | schedule | write | required | required | `schedule.change_proposed` | `answer@1` | implemented |
| `schedule.delete@1.0.0` | schedule | write | required | required | `schedule.change_proposed` | `answer@1` | implemented |
| `schedule.list@1.0.0` | schedule | read | none | none | `schedule.snapshot` | `answer@1` | implemented |
| `schedule.update@1.0.0` | schedule | write | required | required | `schedule.change_proposed` | `answer@1` | implemented |
| `share.present@1.0.0` | client_action | client_action | required | required | `client.action.requested` | `client_action@1` | implemented |
| `skill.create@1.0.0` | skill | write | required | required | `skill.changed` | `answer@1` | implemented |
| `skill.delete@1.0.0` | skill | write | required | required | `skill.changed` | `answer@1` | implemented |
| `skill.list@1.0.0` | skill | read | none | none | `skill.snapshot` | `answer@1` | implemented |
| `skill.update@1.0.0` | skill | write | required | required | `skill.changed` | `answer@1` | implemented |
| `task.create@1.0.0` | task | write | required | required | `task.change_proposed` | `answer@1` | implemented |
| `task.delete@1.0.0` | task | write | required | required | `task.change_proposed` | `answer@1` | implemented |
| `task.execute@1.0.0` | task | execute | required | required | `task.execution_queued` | `task_execution_card@1` | implemented |
| `task.list@1.0.0` | task | read | none | none | `task.snapshot` | `answer@1` | implemented |
| `task.status@1.0.0` | task | read | none | none | `task.snapshot` | `answer@1` | implemented |
| `task.update@1.0.0` | task | write | required | required | `task.change_proposed` | `answer@1` | implemented |
| `voice.record@1.0.0` | client_action | client_action | required | required | `client.action.requested` | `client_action@1` | implemented |
| `voice.transcribe@1.0.0` | client_action | client_action | required | required | `client.action.requested` | `client_action@1` | implemented |
| `workflow.approve@1.0.0` | workflow | write | required | required | `workflow.approved` | `workflow@1` | implemented |
| `workflow.cancel@1.0.0` | workflow | write | required | required | `workflow.cancelled` | `workflow@1` | implemented |
| `workflow.create@1.0.0` | workflow | write | required | required | `workflow.created` | `workflow@1` | implemented |
| `workflow.open@1.0.0` | workflow | read | none | none | `workflow.summary` | `workflow@1` | implemented |
| `workflow.revise@1.0.0` | workflow | write | required | required | `workflow.revised` | `workflow@1` | implemented |
| `workflow.start@1.0.0` | workflow | execute | required | required | `workflow.started` | `workflow@1` | implemented |
| `workflow.status@1.0.0` | workflow | read | none | none | `workflow.summary` | `workflow@1` | implemented |

## Consumption contracts

| Contract | Kind | Receipt | Status |
|---|---|---|---|
| `artifact.structured_consumption` | artifact | `durable_structured_consumption_receipt` | implemented |
| `knowledge.natural_qa` | knowledge | `durable_answer_and_source_events` | implemented |
| `workflow.knowledge_need_injection` | workflow | `workflow_event_receipt` | implemented |

## iOS document-class E2E coverage

| iOS user function | Capability | Event | Renderer | Handler | Consumer | Policy | Automated evidence | Production receipt | Status |
|---|---|---|---|---|---|---|---|---|---|
| Search the authenticated reader's currently authorized bookshelf. | `bookshelf.search` | `bookshelf.results@1` | `bookshelf@1` | `bookshelf.search` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | bookshelf-reader | `tests/test_bookshelf_capabilities.py`, `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift` | implemented | implemented |
| Subscribe to or unsubscribe from one currently authorized book. | `bookshelf.subscribe` | `bookshelf.subscription_changed@1` | `bookshelf@1` | `bookshelf.subscribe` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | bookshelf-reader | `tests/test_bookshelf_capabilities.py` | implemented | implemented |
| Open one currently authorized book at its current immutable content version. | `bookshelf.open` | `bookshelf.opened@1` | `bookshelf@1` | `bookshelf.open` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | bookshelf-reader | `tests/test_bookshelf_capabilities.py`, `ios/AIPlatformAppUITests/ProductionBookshelfUITests.swift` | implemented | implemented |
| List tenant-visible agents. | `agent.list` | `agent.snapshot@1` | `answer@1` | `agent.list` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | agent-owner | `tests/test_agent_capabilities.py` | implemented | implemented |
| Create an owned tenant agent. | `agent.create` | `agent.changed@1` | `answer@1` | `agent.create` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | agent-owner | `tests/test_agent_capabilities.py` | implemented | implemented |
| Update an owned tenant agent. | `agent.update` | `agent.changed@1` | `answer@1` | `agent.update` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | agent-owner | `tests/test_agent_capabilities.py` | implemented | implemented |
| Delete an owned tenant agent. | `agent.delete` | `agent.changed@1` | `answer@1` | `agent.delete` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | agent-owner | `tests/test_agent_capabilities.py` | implemented | implemented |
| Start an agent evaluation. | `agent.evaluate` | `agent.changed@1` | `answer@1` | `agent.evaluate` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | agent-owner | `tests/test_agent_capabilities.py` | implemented | implemented |
| List Skills visible in the authenticated tenant/user Hermes sandbox. | `skill.list` | `skill.snapshot@1` | `answer@1` | `skill.list` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | tenant-skill-owner | `tests/test_skill_capabilities.py` | implemented | implemented |
| Create one governed Skill in the authenticated tenant/user Hermes sandbox. | `skill.create` | `skill.changed@1` | `answer@1` | `skill.create` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | tenant-skill-owner | `tests/test_skill_capabilities.py` | implemented | implemented |
| Replace one owned governed Skill in the authenticated tenant/user Hermes sandbox. | `skill.update` | `skill.changed@1` | `answer@1` | `skill.update` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | tenant-skill-owner | `tests/test_skill_capabilities.py` | implemented | implemented |
| Delete one owned custom Skill from the authenticated tenant/user Hermes sandbox. | `skill.delete` | `skill.changed@1` | `answer@1` | `skill.delete` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | tenant-skill-owner | `tests/test_skill_capabilities.py` | implemented | implemented |
| List native Hermes memory visible to the authenticated user. | `memory.list` | `memory.snapshot@1` | `answer@1` | `memory.list` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | native-memory-owner | `tests/test_memory_capabilities.py` | implemented | implemented |
| Add one bounded native Hermes memory entry after confirmation. | `memory.create` | `memory.changed@1` | `answer@1` | `memory.create` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | native-memory-owner | `tests/test_memory_capabilities.py` | implemented | implemented |
| Replace one owned native Hermes memory entry after confirmation. | `memory.update` | `memory.changed@1` | `answer@1` | `memory.update` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | native-memory-owner | `tests/test_memory_capabilities.py` | implemented | implemented |
| Delete one owned native Hermes memory entry after confirmation. | `memory.delete` | `memory.changed@1` | `answer@1` | `memory.delete` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | native-memory-owner | `tests/test_memory_capabilities.py` | implemented | implemented |
| Search the authenticated user's active or archived notes. | `knowledge.note.search` | `knowledge.results@1` | `answer@1` | `knowledge.search` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | personal-knowledge-owner | `tests/test_product_capabilities.py` | implemented | implemented |
| Read one authenticated user's note by stable note id. | `knowledge.note.read` | `knowledge.note@1` | `answer@1` | `knowledge.read` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | personal-knowledge-owner | `tests/test_product_capabilities.py` | implemented | implemented |
| Create a stable personal Markdown note after confirmation. | `knowledge.note.create` | `knowledge.action@1` | `knowledge_action@1` | `knowledge.create` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | personal-knowledge-confirmed-mutation | `tests/test_product_capabilities.py` | implemented | implemented |
| Replace a note with complete Markdown using compare-and-set. | `knowledge.note.update` | `knowledge.action@1` | `knowledge_action@1` | `knowledge.update` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | personal-knowledge-confirmed-mutation | `tests/test_product_capabilities.py`, `ios/AIPlatformAppTests/KnowledgeNoteStoreTests.swift` | implemented | implemented |
| CAS-update a target and archive only explicit merge sources. | `knowledge.note.merge` | `knowledge.action@1` | `knowledge_action@1` | `knowledge.merge` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | personal-knowledge-confirmed-mutation | `tests/test_product_capabilities.py`, `ios/AIPlatformAppTests/KnowledgeNoteStoreTests.swift` | implemented | implemented |
| Ordinarily archive one note without inventing a merge target. | `knowledge.note.archive` | `knowledge.action@1` | `knowledge_action@1` | `knowledge.archive` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | personal-knowledge-confirmed-mutation | `tests/test_product_capabilities.py`, `ios/AIPlatformAppTests/KnowledgeNoteStoreTests.swift` | implemented | implemented |
| Restore one ordinarily archived personal note. | `knowledge.note.restore` | `knowledge.action@1` | `knowledge_action@1` | `knowledge.restore` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | personal-knowledge-confirmed-mutation | `tests/test_product_capabilities.py` | implemented | implemented |
| Create a real workflow draft through the existing workflow handler. | `workflow.create` | `workflow.created@1` | `workflow@1` | `workflow.create` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | workflow-owner | `tests/test_product_capabilities.py` | implemented | implemented |
| Open an owned workflow summary. | `workflow.open` | `workflow.summary@1` | `workflow@1` | `workflow.open` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | workflow-owner | `tests/test_product_capabilities.py` | implemented | implemented |
| Read an owned workflow execution status. | `workflow.status` | `workflow.summary@1` | `workflow@1` | `workflow.status` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | workflow-owner | `tests/test_product_capabilities.py` | implemented | implemented |
| Start an approved workflow through its existing lifecycle handler. | `workflow.start` | `workflow.started@1` | `workflow@1` | `workflow.start` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | workflow-owner | `tests/test_product_capabilities.py` | implemented | implemented |
| Approve the exact current workflow plan through the existing lifecycle handler. | `workflow.approve` | `workflow.approved@1` | `workflow@1` | `workflow.approve` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | workflow-owner | `tests/test_workflow_capabilities.py`, `tests/test_workflows_api.py` | implemented | implemented |
| Save a CAS-bound workflow plan revision through the existing versioned plan editor. | `workflow.revise` | `workflow.revised@1` | `workflow@1` | `workflow.revise` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | workflow-owner | `tests/test_workflow_capabilities.py`, `tests/test_workflows_api.py` | implemented | implemented |
| Cancel and archive an owned workflow with timestamp CAS and a durable domain receipt. | `workflow.cancel` | `workflow.cancelled@1` | `workflow@1` | `workflow.cancel` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | workflow-owner | `tests/test_workflow_capabilities.py`, `tests/test_workflows_api.py` | implemented | implemented |
| List projects visible to the authenticated tenant member. | `project.list` | `project.snapshot@1` | `answer@1` | `project.list` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | qws-project-access | `tests/test_project_task_capabilities.py` | implemented | implemented |
| Create an owned QWS project from the canonical IPD template. | `project.create` | `project.created@1` | `answer@1` | `project.create` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | qws-project-access | `tests/test_project_task_capabilities.py` | implemented | implemented |
| Open a tenant-visible QWS project snapshot. | `project.open` | `project.snapshot@1` | `answer@1` | `project.open` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | qws-project-access | `tests/test_project_task_capabilities.py` | implemented | implemented |
| Propose definition changes to an owned QWS project using revision CAS. | `project.update` | `project.change_proposed@1` | `answer@1` | `project.update` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | qws-project-access | `tests/test_project_task_capabilities.py` | implemented | implemented |
| Archive an owned QWS project while preserving immutable audit history. | `project.delete` | `project.change_proposed@1` | `answer@1` | `project.delete` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | qws-project-access | `tests/test_project_task_capabilities.py` | implemented | implemented |
| List canonical tasks in a tenant-visible QWS project. | `task.list` | `task.snapshot@1` | `answer@1` | `task.list` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | qws-project-access | `tests/test_project_task_capabilities.py` | implemented | implemented |
| Propose a new canonical task in an owned QWS project. | `task.create` | `task.change_proposed@1` | `answer@1` | `task.create` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | qws-project-access | `tests/test_project_task_capabilities.py` | implemented | implemented |
| Propose edits to a canonical QWS task contract. | `task.update` | `task.change_proposed@1` | `answer@1` | `task.update` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | qws-project-access | `tests/test_project_task_capabilities.py` | implemented | implemented |
| Soft-delete a canonical QWS task through the governed archive proposal path. | `task.delete` | `task.change_proposed@1` | `answer@1` | `task.delete` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | qws-project-access | `tests/test_project_task_capabilities.py` | implemented | implemented |
| Queue an owner-bound QWS task conversation using an ephemeral delegated user token. | `task.execute` | `task.execution_queued@1` | `task_execution_card@1` | `task.execute` | `ios/AIPlatformApp/Networking/APIClient.swift:RendererRegistry` | qws-project-access | `tests/test_task_execute_capability.py` | implemented | implemented |
| Read a canonical QWS task and its current status. | `task.status` | `task.snapshot@1` | `answer@1` | `task.status` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | qws-project-access | `tests/test_project_task_capabilities.py` | implemented | implemented |
| Generate, revise, and download a multi-page Word document | `document.word.create_from_text` | `document.created@1` | `workflow@1` | `backend/capability_handlers.py:_word_create_from_text` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | workflow-owner + artifact-owner | `tests/e2e/test_word_workflow.py`, `tests/test_product_capabilities.py`, `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift` | implemented | implemented |
| Generate and revise a research report with traceable evidence | `report.research.create_from_text` | `document.created@1` | `workflow@1` | `backend/capability_handlers.py:_research_report_create_from_text` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | workflow-owner + artifact-owner | `tests/e2e/test_research_report_workflow.py`, `tests/test_product_capabilities.py`, `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift` | implemented | implemented |
| Generate an academic paper with verified citation correspondence | `paper.academic.create_from_text` | `document.created@1` | `workflow@1` | `backend/capability_handlers.py:_academic_paper_create_from_text` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | workflow-owner + artifact-owner | `tests/e2e/test_academic_paper_workflow.py`, `tests/test_product_capabilities.py`, `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift` | implemented | implemented |
| Create an editable PPTX workflow directly from user-provided text, using governed defaults and returning the workflow that will expose its rendered preview and authenticated download. | `presentation.create_from_text` | `presentation.created@1` | `presentation_review@1` | `presentation.create_from_text` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | workflow-owner | `tests/test_product_capabilities.py`, `tests/test_document_presentation.py` | implemented | implemented |
| Create an immutable XLSX artifact from bounded columns and rows. | `office.spreadsheet.create` | `artifact.generated@1` | `artifact_card@1` | `office.spreadsheet.create` | `ios/AIPlatformApp/Networking/APIClient.swift:RendererRegistry` | generated-artifact-owner | `tests/test_generated_artifact_capabilities.py` | implemented | implemented |
| Create an immutable PDF artifact from bounded text content. | `office.pdf.create` | `artifact.generated@1` | `artifact_card@1` | `office.pdf.create` | `ios/AIPlatformApp/Networking/APIClient.swift:RendererRegistry` | generated-artifact-owner | `tests/test_generated_artifact_capabilities.py` | implemented | implemented |
| Compute deterministic bounded column statistics and persist a JSON analysis artifact. | `data.analyze` | `artifact.generated@1` | `data_analysis_card@1` | `data.analyze` | `ios/AIPlatformApp/Networking/APIClient.swift:RendererRegistry` | generated-artifact-owner | `tests/test_generated_artifact_capabilities.py` | implemented | implemented |
| Create a deterministic PNG media card from a bounded prompt and dimensions. | `media.create` | `artifact.generated@1` | `image_card@1` | `media.create` | `ios/AIPlatformApp/Networking/APIClient.swift:RendererRegistry` | generated-artifact-owner | `tests/test_generated_artifact_capabilities.py` | implemented | implemented |
| List the current owner-bound Hermes session for a registered client chat session. | `hermes.session.list` | `hermes.session.listed@1` | `hermes_session_list@1` | `hermes.session.list` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | hermes-session-owner | `tests/test_hermes_session_capabilities.py` | implemented | implemented |
| Resolve metadata for the owner-bound Hermes session behind a registered client chat session. | `hermes.session.open` | `hermes.session.opened@1` | `hermes_session_detail@1` | `hermes.session.open` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | hermes-session-owner | `tests/test_hermes_session_capabilities.py` | implemented | implemented |
| Resume the owner-bound Hermes session behind a registered client chat session. | `hermes.session.resume` | `hermes.session.resumed@1` | `hermes_session_detail@1` | `hermes.session.resume` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | hermes-session-owner | `tests/test_hermes_session_capabilities.py` | implemented | implemented |
| Permanently delete the owner-bound Hermes session and its messages. | `hermes.session.delete` | `hermes.session.deleted@1` | `hermes_session_detail@1` | `hermes.session.delete` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | hermes-session-owner | `tests/test_hermes_session_capabilities.py` | implemented | implemented |
| Ask the authenticated iOS client to present the native document picker. | `file.pick` | `client.action.requested@1` | `client_action@1` | `file.pick` | `ios/AIPlatformApp/Views/Chat/NativeClientActionHost.swift:NativeClientActionRegistry` | client-action-owner | `tests/test_client_action_capabilities.py` | implemented | implemented |
| Pick and upload a private document through the authenticated owner-bound document API. | `file.upload` | `client.action.requested@1` | `client_action@1` | `file.upload` | `ios/AIPlatformApp/Views/Chat/NativeClientActionHost.swift:NativeClientActionRegistry` | client-action-owner | `tests/test_client_action_capabilities.py` | implemented | implemented |
| Download an owner-bound private document by source ID on the authenticated iOS client. | `file.download` | `client.action.requested@1` | `client_action@1` | `file.download` | `ios/AIPlatformApp/Views/Chat/NativeClientActionHost.swift:NativeClientActionRegistry` | client-action-owner | `tests/test_client_action_capabilities.py` | implemented | implemented |
| Ask the authenticated iOS client to present the camera and return a client receipt. | `photo.capture` | `client.action.requested@1` | `client_action@1` | `photo.capture` | `ios/AIPlatformApp/Views/Chat/NativeClientActionHost.swift:NativeClientActionRegistry` | client-action-owner | `tests/test_client_action_capabilities.py` | implemented | implemented |
| Ask the authenticated iOS client to present the photo library picker. | `photo.import` | `client.action.requested@1` | `client_action@1` | `photo.import` | `ios/AIPlatformApp/Views/Chat/NativeClientActionHost.swift:NativeClientActionRegistry` | client-action-owner | `tests/test_client_action_capabilities.py` | implemented | implemented |
| Ask the authenticated iOS client to present the native voice recorder. | `voice.record` | `client.action.requested@1` | `client_action@1` | `voice.record` | `ios/AIPlatformApp/Views/Chat/NativeClientActionHost.swift:NativeClientActionRegistry` | client-action-owner | `tests/test_client_action_capabilities.py` | implemented | implemented |
| Record audio on iOS and transcribe it through the authenticated fail-closed speech API. | `voice.transcribe` | `client.action.requested@1` | `client_action@1` | `voice.transcribe` | `ios/AIPlatformApp/Views/Chat/NativeClientActionHost.swift:NativeClientActionRegistry` | client-action-owner | `tests/test_client_action_capabilities.py`, `tests/test_voice_transcription_capability.py` | implemented | implemented |
| Ask the authenticated iOS client to present the native share sheet for supplied text or an owned artifact. | `share.present` | `client.action.requested@1` | `client_action@1` | `share.present` | `ios/AIPlatformApp/Views/Chat/NativeClientActionHost.swift:NativeClientActionRegistry` | client-action-owner | `tests/test_client_action_capabilities.py` | implemented | implemented |
| Read the authenticated user's current profile and tenant projection. | `profile.read` | `profile.snapshot@1` | `answer@1` | `profile.read` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | profile-owner | `tests/test_profile_capabilities.py` | implemented | implemented |
| Update the authenticated user's display name or avatar after confirmation. | `profile.update` | `profile.changed@1` | `answer@1` | `profile.update` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | profile-owner | `tests/test_profile_capabilities.py` | implemented | implemented |
| Read notifications owned by the authenticated tenant user. | `notification.list` | `notification.snapshot@1` | `answer@1` | `notification.list` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | notification-owner | `tests/test_notification_capabilities.py` | implemented | implemented |
| Mark one notification owned by the authenticated user as read with unread-state CAS. | `notification.mark_read` | `notification.changed@1` | `answer@1` | `notification.mark_read` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | notification-owner | `tests/test_notification_capabilities.py` | implemented | implemented |
| Update authenticated-user notification channels and enabled state with revision CAS. | `notification.preferences.update` | `notification.preferences_changed@1` | `answer@1` | `notification.preferences.update` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | notification-owner | `tests/test_notification_capabilities.py` | implemented | implemented |
| Read the canonical task schedule for a tenant-visible QWS project. | `schedule.list` | `schedule.snapshot@1` | `answer@1` | `schedule.list` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | qws-schedule-access | `tests/test_schedule_capabilities.py` | implemented | implemented |
| Propose dates for one currently unscheduled canonical QWS task. | `schedule.create` | `schedule.change_proposed@1` | `answer@1` | `schedule.create` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | qws-schedule-access | `tests/test_schedule_capabilities.py` | implemented | implemented |
| Propose replacement dates for one scheduled canonical QWS task. | `schedule.update` | `schedule.change_proposed@1` | `answer@1` | `schedule.update` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | qws-schedule-access | `tests/test_schedule_capabilities.py` | implemented | implemented |
| Propose clearing dates from one scheduled canonical QWS task. | `schedule.delete` | `schedule.change_proposed@1` | `answer@1` | `schedule.delete` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | qws-schedule-access | `tests/test_schedule_capabilities.py` | implemented | implemented |

PCM compiles every implemented, client-supported capability into a native Hermes tool at session assembly. Normal business execution does not depend on capability search or describe. QCP validates every invocation against the allowlisted contract; domain handlers remain the authorization truth.
