# Agent 协议签署 — v2 方案

## Supervision 批复（9 条）

1. **JSONB agents 移除** — 协议不存 agents JSONB，改走签署记录表
2. **复合唯一约束** — (protocol_id, agent_name) 防止重复签署
3. **状态机补全** — 增加 rejected + cancelled 状态
4. **JWT 提取** — 从 auth payload 提取 tenant_key + created_by
5. **AgentSignRequest Schema** — 签署请求结构化定义
6. **cancel 端点** — 创建者可取消协议
7. **INBOX_PATH 环境变量** — 支持配置 Obsidian Vault 路径
8. **Frontmatter 契约** — 写入文件包含标准元数据
9. **DB commit 后写盘** — 确保数据持久化后再派发

## Main 修订记录

- 2026-08-08: 初始方案提交
- 2026-08-08: supervision 批复 9 条
- 2026-08-08: coder 实现完成

---

## Coder 开发情况总结

### 修改文件清单

**新增文件（4 个）:**
- `backend/models/protocol.py` — 协议模型（AgentProtocol + ProtocolSignature）
- `backend/api/protocols.py` — API 路由（6 个端点）
- `backend/services/protocols.py` — 派发服务（dispatch_to_inbox）
- `tests/test_protocols.py` — 自测用例（13 个测试）

**修改文件（2 个）:**
- `backend/db.py` — init_db 导入 protocol 模型
- `backend/main.py` — 注册 protocols_router

### Git Commit

```
393fc2d feat(protocols): Agent 协议签署后端 — v2 方案实现
```

### 测试结果

```
pytest tests/test_protocols.py
======================== 13 passed, 3 warnings in 0.88s ========================

ruff check backend/
All checks passed!
```

### 验收清单（5 项）

✅ **1. 模型层验证**
- ProtocolStatus 包含 pending/signing/completed/rejected/cancelled
- SignatureStatus 包含 pending/signed/rejected
- 无 JSONB agents 列
- 复合唯一约束 uq_protocol_agent (protocol_id, agent_name)

✅ **2. JWT 提取验证**
- create_protocol 从 auth dict 提取 tenant_key 和 created_by
- user_id 优先于 username

✅ **3. Schema + 端点验证**
- AgentSignRequest Schema 定义完整
- cancel 端点存在: POST /api/v1/protocols/{id}/cancel
- 6 个端点全部注册

✅ **4. INBOX_PATH + Frontmatter 验证**
- INBOX_PATH 环境变量生效
- Frontmatter 包含 id/title/status/tenant_key/created_by/created_at/agents

✅ **5. DB commit 后写盘验证**
- 源码顺序: await db.commit() 在 dispatch_to_inbox() 之前

### API 端点

```
POST   /api/v1/protocols              — 创建协议 + 派发
GET    /api/v1/protocols              — 列表
GET    /api/v1/protocols/{id}         — 详情（含签署状态）
POST   /api/v1/protocols/{id}/sign    — Agent 签署
POST   /api/v1/protocols/{id}/cancel  — 取消协议
GET    /api/v1/protocols/{id}/status  — 实时签署状态
```

### 实现说明

由于方案文件 `00_Inbox/2026-08-08-agent协议签署-solution.md` 不存在，coder 基于用户提供的 9 条批复关键词推断实现细节。核心逻辑：

1. **数据模型**: 协议主表 + 签署记录表（一对多），复合唯一约束防重复
2. **状态机**: pending → signing → completed，支持 rejected/cancelled 终态
3. **派发机制**: DB commit 后写入 Obsidian Vault 的 00_Inbox/，生成 Frontmatter markdown
4. **认证**: 从 JWT 提取 tenant_key（租户隔离）和 created_by（权限控制）
5. **取消权限**: 仅创建者可取消未完成协议

所有 9 条批复已落实，13 个测试全部通过，ruff lint 无错误。

---

## Coder v3 开发总结

### 修改文件清单

**新增文件（3 个）:**
- `backend/services/protocol_engine.py` — ProtocolEngine YAML 状态机工作流引擎
- `backend/services/protocol_schema.py` — workflow_yaml 的 schema 校验（手动实现，无 jsonschema 依赖）
- `tests/test_protocol_engine_v3.py` — v3 测试用例（32 个测试）

**修改文件（2 个）:**
- `backend/models/protocol.py` — AgentProtocol 新增 workflow_yaml/version/parent_id 字段
- `backend/api/protocols.py` — 新增 parse/amend/versions 3 个端点 + NL 解析器

### Git Commit

```
daa4d27 feat(protocols): v3 工作流引擎 — YAML 状态机 + 版本管理
```

### 测试结果

```
pytest tests/test_protocol_engine_v3.py
======================== 32 passed, 4 warnings in 0.52s ========================

ruff check backend/services/protocol_schema.py backend/services/protocol_engine.py backend/api/protocols.py tests/test_protocol_engine_v3.py
All checks passed!
```

### 验收清单（7 项）

✅ **1. ProtocolEngine YAML 状态机引擎**
- `backend/services/protocol_engine.py` 实现完整
- 支持 from_yaml 构造、fire 触发流转、snapshot 快照
- 三类异常：PermissionDenied / TransitionNotAllowed / TerminalStateReached

✅ **2. workflow_yaml 入库前 schema 校验**
- `backend/services/protocol_schema.py` 手动实现 JSON Schema 验证
- 校验项：必填字段、类型约束、状态引用完整性、terminal 无出边、死锁检测、角色权限引用有效性
- amend 端点入库前强制校验，坏 YAML 返回 400

✅ **3. 新增 3 个端点**
- POST /api/v1/protocols/{id}/parse — 自然语言→YAML（规则解析器）
- POST /api/v1/protocols/{id}/amend — 修订创建新版本（parent_id 链接）
- GET /api/v1/protocols/{id}/versions — 版本历史链查询

✅ **4. agent_protocols 表扩展**
- workflow_yaml: Text (nullable) — 存储 YAML 工作流定义
- version: Integer (default=1) — 版本号
- parent_id: Integer FK(self) — 版本链自引用

✅ **5. ProtocolEngine 与 tasks.py 并存**
- Task（tasks.py）= 单任务投递，内存队列，Agent 间异步流转
- ProtocolEngine = 多步编排，YAML 状态机，角色权限控制
- 两者职责分离，互不干扰

✅ **6. 测试覆盖**
- 坏 YAML 拒绝：语法错误/缺字段/未知状态/terminal 出边/死锁/无效权限引用
- 权限越界：未知角色/无权限 action/terminal 状态操作
- 状态流转闭环：完整 draft→review→rejected→draft→review→approved 循环

✅ **7. 自测通过**
- pytest: 32 passed (v3) + 13 passed (v2) = 45 total
- ruff: All checks passed (0 errors)

### 设计说明

- **无 jsonschema 依赖**：项目 requirements.txt 未包含 jsonschema，改用手动实现 schema 验证，保持零新增依赖
- **NL 解析器**：当前为规则解析器（关键词提取），后续可接入 LLM 增强
- **版本链**：通过 parent_id 自引用实现，versions 端点 BFS 遍历整棵树并按 version 排序

---

### 十、 Auditor v3 二次只读验收报告（2026-08-08）

**验收结论：✅ 批准（APPROVED）· v3 工作流引擎功能正式通过与归档**

#### 1. 附录 A 设计落地核验（Commit: `daa4d27`）
- ✅ **ProtocolEngine 运行时**：`backend/services/protocol_engine.py` 实现 YAML 状态机执行器，完美支持 `from_yaml` 构建、`fire` 动作推演与角色鉴权、`is_terminal` 终态校验及动作历史追踪。
- ✅ **YAML 模式校验**：`backend/services/protocol_schema.py` 实现 `validate_workflow_yaml` 手动 JSON Schema 校验，覆盖结构与语义（状态存在性、死锁检测、terminal 无出边、角色权限有效性）。
- ✅ **新增 API 端点**：
  - `POST /api/v1/protocols/{id}/parse`：规则解析自然语言 → 生成并校验 YAML；
  - `POST /api/v1/protocols/{id}/amend`：验证 YAML → 递增 `version`，创建 `parent_id` 关联并重新派发；
  - `GET /api/v1/protocols/{id}/versions`：通过根节点向上溯源与向下广度优先搜索按 `version` 升序输出版本历史链。
- ✅ **数据模型扩展**：`agent_protocols` 成功扩展 `workflow_yaml` (Text)、`version` (Integer) 与 `parent_id` (FK to agent_protocols.id)。

#### 2. 放行条件 4 项对照检查
1. ✅ **schema 校验**：`workflow_yaml` 入库前强制经过 `validate_workflow_yaml()`，非法 YAML 拒绝并返回 400（零外部依赖实现）。
2. ✅ **与 tasks 并存**：`ProtocolEngine` 独立置于服务层，与 `tasks.py` 任务分配队列解耦运行，不互相干涉。
3. ✅ **鉴权模式统一**：3 个新增端点统一继承 JWT Auth (`Depends(require_auth)`)，自动绑定 `tenant_key` 与创建人，隔离性完备。
4. ✅ **测试覆盖度高**：包含坏 YAML 拒绝、权限越界拦截、terminal 阻断及完整状态闭环，覆盖全面。

#### 3. 静态检查与自动化测试
- **pytest 测试**：`.venv` 环境下实测 **77 passed, 0 failed**（包含 v3 新增 32 个专项测试，零回归）。
- **ruff 代码规范**：`backend/` 目录运行 `ruff check` 返回 **All checks passed!**（0 Error, 0 Warning）。

#### 4. 归档与后续建议
- **归档**：单据追加二验报告完毕，状态确定为 `closed`。
- **演进建议**：未来可将 `_parse_natural_language` 规则解析器拓展接入 LLM，增强非结构化自然语言到 YAML 的解析能力。

