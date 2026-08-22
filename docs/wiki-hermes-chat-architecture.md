# AI Lab Wiki 素材与 Hermes 对话架构

## 1. 领域边界

AI Lab 有三个不同对象，不能再合并为一个“知识资产”：

| 层 | 对象 | 用户是否直接浏览 | 作用 |
| --- | --- | --- | --- |
| 素材层 | 平台绿色/黄色/租户红色 Wiki | 否 | 为 AI 和 Agent 提供事实、关系、历史与来源 |
| 对话加工层 | AI 回答、洞察、比较、方案 | 在聊天页 | 基于当前租户可见 Wiki 素材动态生成 |
| 用户笔记层 | 用户保存或自己撰写的 Markdown | 是，仅知识页 | 用户编辑、整理、双链和再次调用 |

知识页只管理用户笔记。平台 Wiki 不作为笔记、文章、目录卡片或订阅入口展示；用户在聊天中加工满意后，才把结果另存为自己的笔记。

## 2. 当前故障的代码级原因

1. `backend/api/chat.py` 过去只在请求前做一次文件检索，并把最多 5 条、每条约 240 字的摘要拼进 Prompt。
2. Wiki 标题命中在 `backend/api/knowledge.py` 中生成的 `snippet` 是空字符串，所以“超聚变”即使命中同名 Wiki，也可能不给模型任何事实正文。
3. Bridge 只校验 `knowledge_capability`，普通聊天没有主动调用现成的 Knowledge Gateway；Gateway 调用只用于工作流的 `KNOWLEDGE_RETRIEVAL` 节点。
4. `agent_capabilities.py` 声明允许 `delegate_task`，但 `hermes_bridge.py` 的轻量工具集没有启用 `delegation`，普通洞察聊天实际上无法委派子 Agent。
5. 子 Agent 不继承父会话；如果父 Agent 不把已授权 Wiki 证据写入 `context`，子 Agent 天然拿不到材料。

## 3. 本次实现的最小闭环

```text
iOS 问题
  -> FastAPI 根据 JWT 解析 tenant / entitlement
  -> 签发短时 knowledge capability
  -> Bridge 使用原始 knowledge_query 调 Knowledge Gateway
  -> Gateway 在 capability scope 内检索 Wiki 与一跳 WikiLinks
  -> Hermes 基于带 [[path]] 的素材回答
  -> 洞察类问题可 delegate_task，并显式把已授权素材放入 child context
  -> 父 Agent 汇总并保留引用
```

本次同时修复了：

- 自然语言问题中的实体短语抽取，例如“超聚变是做什么的”可还原“超聚变”。
- Wiki title、文件名和 frontmatter `aliases` 命中。
- title 命中返回正文事实片段，不再返回空 snippet。
- WikiLink 目标按标题、别名和相对 Wiki 路径解析。
- Bridge 用请求级 capability 再检索，缓存仍包含 tenant、policy version 和 scope。
- 普通聊天的 Hermes `delegation` 工具集真正启用。

## 4. 用户笔记同步边界

新增接口：

```http
PUT /api/v1/me/knowledge-notes/{note_id}
GET /api/v1/me/knowledge-notes/{note_id}/status
```

客户端上传原始 Markdown、`content_hash` 和可选 `base_hash`。服务端：

1. 从 JWT 取得租户，不接受客户端自报 tenant。
2. 写入 `raw/dialogues/tenants/<tenant_hash>/<note_id>.md`。
3. 用 SHA-256 做幂等和冲突检测；冲突返回 `409 sync_conflict`，不覆盖服务器内容。
4. 写入运输侧 `.sync.json`，记录 owner、hash 和同步时间。
5. 到此结束，不从移动端触发或复制 Wiki 编译逻辑。

后续分类、治理、`raw/dialogues -> Wiki`、K5 准入和存储规范继续由平台现有 Compiler/Agent 链负责。

## 5. GitHub 复用结论

- [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)：继续作为 Agent 运行时；复用 delegation、skills、session 和 MCP，不替换。
- [PrefectHQ/FastMCP](https://github.com/PrefectHQ/fastmcp)：下一阶段把 `wiki_search`、`wiki_read`、`wiki_neighbors` 暴露为 Hermes MCP 工具，让 Agent 在一个回合内迭代查 Wiki。
- [zcag/tela](https://github.com/zcag/tela)：参考其 Markdown 原文 + 原生 MCP + scoped permissions 的边界，不迁移 AI Lab Wiki。
- [Meilisearch](https://github.com/meilisearch/meilisearch)：Wiki 规模较大后，可选作关键词、别名和错别字索引；只做索引，不是知识源，也不要求向量。
- [OpenFGA](https://github.com/openfga/openfga)：团队/角色/知识包关系复杂后再替换自研关系授权；短期继续使用现有 capability policy。

不采用 Qdrant、GraphRAG 或 Neo4j 作为本体系的知识底座。Wiki Markdown、frontmatter、WikiLinks、catalog 和 matrix 仍是事实与关系的来源。

## 6. 下一阶段：真正的迭代 Wiki 工具

当前闭环是“每回合预检索 + Hermes 推理 + 可委派”，已经能解决实体问答和基于素材的洞察。达到完整 Hermes 式效果还需要一个请求级 MCP 工具面：

- `wiki_search(query, limit)`：关键词、实体、别名检索。
- `wiki_read(path, heading?)`：读取一篇已授权 Wiki 的指定段落。
- `wiki_neighbors(path, depth=1)`：沿 WikiLinks 读取相邻素材。
- `wiki_trace(paths)`：返回版本、来源和权限审计信息。

每次工具调用都必须携带或绑定当前 capability，服务端先做 scope 校验再读 Wiki；不得给 Hermes 本地 Vault 文件权限，也不得让 MCP 使用静态的全局租户令牌。
