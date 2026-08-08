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
