# 存量稿件治理清单（2026-09-12）

本清单是对本机 Hermes 出版产物的只读盘点，不是生产发布状态证明。历史文件不删除、不覆盖；已发布版本继续保持不可变，未发布版本必须进入 `editorial-v2` 新 revision 后才可重新审稿。

## 治理规则

- `keep_published`：若生产库已发布，保留冻结正文，只允许另发勘误或新版。
- `rewrite_required`：未达到当前篇幅/结构门槛，或缺少被目标哈希绑定的 `editorial_brief`。
- `research_blocked`：已有独立审稿拒稿且仍有未关闭证据缺口。
- `duplicate`：与另一稿件实质相同，不作为独立出版候选。

## 盘点结果

| 稿件 | 有效汉字 | 当前证据 | 治理决定 |
|---|---:|---|---|
| `quantumn-daily/2026-09-09/ai-history.md` | 873 | 无编辑合同；同日存在另一历史稿变体 | `rewrite_required`；与同日历史稿合并选题，不单独上架 |
| `quantumn-daily/2026-09-09/ai-history-2026-09-09.md` | 1,157 | 无编辑合同；低于 3,000 字章节门槛 | `rewrite_required`；保留“可检验的智能”主题作为科普候选 |
| `quantumn-daily/2026-09-09/ai-practice.md` | 919 | 无编辑合同；同日存在另一实践稿变体 | `rewrite_required`；与同日实践稿合并选题，不单独上架 |
| `quantumn-daily/2026-09-09/ai-practice-2026-09-09.md` | 1,159 | 无编辑合同；低于 3,000 字章节门槛 | `rewrite_required`；保留“事实可追溯与可修正”作为教程候选 |
| `quantumn-daily/2026-09-10/ai-history.md` | 1,247 | 旧独立审核记录不能满足 `editorial-v2` | 若已发布则 `keep_published`；否则 `rewrite_required` |
| `quantumn-daily/2026-09-10/ai-practice.md` | 1,208 | 旧独立审核记录不能满足 `editorial-v2` | 若已发布则 `keep_published`；否则 `rewrite_required` |
| `quantumn-editorial-v2/personal-knowledge-handbook/manuscript-v2.md` | 37,552 / 10章 | `editorial-v1` revision 1 已拒稿；出版授权、UI验收、Agent边界、实验复现缺口未关闭 | `research_blocked`；保留拒稿及全部证据 |
| `quantumn-editorial-v2/personal-knowledge-handbook-r2/manuscript-v3.md` | 37,552 / 10章 | `editorial-v1` revision 2 待审；与 v2 文本相似度 99.32%，无 `editorial_brief` | `duplicate + rewrite_required`；不得沿用旧待审批准，建立 `editorial-v2` 新 revision |

## 首批重编选题

1. `popular_science`：**从“机器会不会思考”到“结论能不能检验”**。核心判断：图灵测试真正留给普通人的不是一条智能及格线，而是一套把抽象争论变成可观察问题的方法。
2. `tutorial`：**让一条知识既有出处，又能被后来证据改正**。核心判断：可靠知识库的关键不是摘要更漂亮，而是事实、解释、冲突和版本之间保留可回退关系。
3. `critical_essay`：**个人知识库最大的风险不是忘记，而是过早相信**。核心判断：AI 自动整理提高的是加工速度；若缺少来源、反例和权限边界，它也会更快固化错误。

以上选题仍需作者生成完整 `editorial_brief`、补足公开或已授权证据，并经过独立审稿；本清单不构成批准。
