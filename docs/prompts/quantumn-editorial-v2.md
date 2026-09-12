# Quantumn 编辑生产协议 v2

> 复用既有 Hermes 作者、独立审稿和 no-agent 发行任务。本文是任务指令，不是新的执行器。作者不得审自己稿，发行脚本不得生成内容。全书样稿通过人工可读性与独立事实复核后才开启该协议的日常发行。

## 内容合同

- 读者为非技术中文读者；保持专业机构的证据严谨，不采用报告摘要式写法。
- 完整书 `book`：至少 20,000 有效汉字、至少八个实质章节；字数只是下限，不代表深度合格。
- 连载章节 `chapter`：至少 3,000 有效汉字，明确标明系列、章次、已完成/未完成学习目标，不包装成整书。
- 历史短专栏只作为历史短文保留，不能省略新合同再上架，也不能通过改标签升格为书。
- 有效正文计数和章节 hash 以 `backend.services.publication_editorial` 当前实现为准。标题、URL、代码、引用块、参考文献、重复段落不用于凑字。父章包含其子节。公开原文按原作保真与合法授权处理，不人为扩写原作者。

## 作者任务

### 输入和范围

只操作用户已授权的 `~/.hermes/outputs/quantumn-daily/` 出版产物和本期隔离教学 sandbox。先读当前日期、部署 SHA、现有出版状态、本协议、质量验证器和 `scripts/publication_operator.py`，禁止从旧示例猜字段。只用原生 Hermes 工具，不裸调模型 API、不改 Cron、源码、部署和发布状态。

授权政策为既有 `~/.hermes/outputs/publication-20260908/recurring-publication-policy.json`。私人 Wiki 可指导选题，但原始私有内容不得公开；需引用私人材料时必须有独立脱敏/授权证据，否则换公开来源。

### 每次执行

1. 先读两系列既有全书规划与最近已发正文/目录、Follow Builders 新增来源，以及尚未关闭的 `review-report.json`。优先修复待审稿，不为了当天日期重复首期主题。
2. 先履行主编职责：结合新增来源、已授权 Wiki、历史目录和未关闭缺口提出候选选题，去除复述原文、已有内容改标题和证据不足的候选。没有能给读者带来明确新价值的选题时，输出 `NO_WORTHY_TOPIC`，不得创建稿件或凑刊。
3. 把候选及取舍写入本期 `editorial-pitches.json`，全局至多选择两个、每系列至多一个。推进历史因果线的稿件进入 `ai-history`，可复现实操进入 `ai-practice`，独立研究/科普/趣味/观点作品进入既有 `quantumn-originals` 并使用稳定的 `source_publication_id`，不新建平行书架。选题必须选择 `tutorial / research_report / popular_science / feature / critical_essay` 之一，并形成 `editorial_brief`：`genre / question / thesis / reader_value / novelty / counterargument / uncertainties / evidence_urls / selection_reason`。`thesis` 必须是可反驳的 Quantumn 编研判断，不是来源摘要或情绪化立场。
4. 在每系列长期 `book-plan.json` 维护目标读者、学习目标、有序章次、前置知识、已讲内容、下一章增量、已用案例。它是出版业务资料，不保存第二份 Agent 会话或执行上下文。
5. 为当前章节列出研究问题：为什么重要、概念与前置条件、因果原理、完整例子/操作、失败反例、限制、读者可能追问。逐项写 `research_gaps`，不以“内容需完善”代替具体问题。
6. Wiki-first 收集获授权知识；不足则核验公开一手来源，必要时用自有隔离样本实测。对数字、时间、原理、版本/操作和因果说法留原始位置。无法补证就删除或明确未知，不能以“据说”扩写。
7. 实际写章。用 `## 第N章 标题` 及 H3 小节组织，每章有连续讲解，不只有列表。具体告诉读者为什么、如何、做完观察什么、出错怎么办。正文自然但必须能区分已核实事实、来源观点、Quantumn 推论、最强反例、不确定性和行动含义；不得把模型推论冒充来源事实。教学人物/资料必须标示为例子，不能伪装客户案例。未测 UI 不称 UI 已通过。结尾附“来源与延伸阅读”，只放必要短引、来源说明和原文链接，未经许可不复制第三方全文。
8. 每次返工写新 revision 目录，保留旧正文、旧证据和旧拒稿。清空新 revision 的批准字段；真实计算正文/章节/来源 hash，记录 `previous_body_hash`，逐缺口说明修改位置与新证据。正文无实质变化不得递增版本冒充修复。
9. 用质量验证器生成 `editorial-v2` 合同/metrics，并逐项处理机械门禁。`editorial_brief` 和来源 receipt 一起进入联合目标 hash；不得降低阈值、不自造 approved。作者 session 标识来自本次真实 Hermes 会话；未知则 blocked，不能编造 `hermes:` 字符串。
10. 原子更新只含本期明确文件列表及 hash 的 `draft-manifest.json`，状态 `prepared` 或 `blocked`。草稿中 `review.decision=pending`。通过确定性 `publication_editorial_remote.py prepare` 仅上传明列稿件到私有 intake、取得服务端 revision/attempt/target 并写回合同，进入待独立审核；禁止 stage、release 或对外发布。

### 既有稿件治理

- 已发布旧版本保持正文不可变，只标为历史文章；发现问题走勘误或新版本，不回写旧正文。
- 未发布的 `editorial-v1`、旧短稿和无 `editorial_brief` 稿件不得 stage/release；保留原稿，建立新 revision，重新选定体裁和论点后补研。
- 已拒稿必须先关闭原 `research_gaps`，不得换标题、换 issue 或重置重试次数逃避审稿。
- 内容重复的稿件合并为一个选题；其余稿件在治理清单中标为 `rewrite_required / research_blocked / duplicate / keep_published`，禁止静默删除。

### 返工闭环

审核拒绝后，下一次作者执行必须读取同一目标 revision 的审稿缺口，而不是换题逃避。不超过三轮返工；三轮仍有实质缺口则 `blocked` 并给出需要的证据/操作，不能以日期到点自动通过。基础设施失败不算内容修改轮次，也不应丢弃已有章节。支持跨日续写原期，不默默换 issue ID 隐藏缺刊。

## 独立审稿任务

只读当前 `draft-manifest.json` 明列且 hash 一致的正文与证据；路径必须限制在明确本期目录，拒绝路径逃逸、未知文件和符号链接逃逸。阅读全章，不只读摘要或检索片段。检查作者与本次真实 Hermes 会话不同，保存真实执行来源回执；`hermes:` 前缀本身不是独立执行证明。

1. **事实审校**：核对原始来源，逐项审核数字、日期、技术机制、版本、命令与限制。检查练习真实输出和失败/修复记录，不以“有一个 log 文件”当实测通过。
2. **非技术读者审校**：逐章问“我为什么要读？术语懂吗？原理讲了吗？示例能照做吗？预期结果是什么？出错如何处理？我还会追问什么？”提出具体缺口，不把晦涩、过短、泛泛而谈仅降为 warning。
3. **整书审校**：检查目录完整、前后术语与例子一致、跨章/跨期重复、学习目标覆盖、结论与边界、不必要重复免责声明。不同日期复述同一篇应拒绝，除非明确标为勘误/修订并说明增量。
4. **原创论点审校**：逐项检查 `editorial_brief` 中的问题、论点、读者价值、新增信息、反方、不确定性和选题理由是否真实出现在正文且被来源支持。检查体裁匹配：教程需可执行与失败恢复，研究报告需方法和证据分级，科普需心智模型与误区，趣味文章不能用故事掩盖事实缺口，观点文章必须正面处理最强反方。
5. 每章记录实际正文摘录锚点、审稿发现和结论；整书记录连贯性、非重复性、新手可读性、论点、反方、不确定性、读者价值与体裁匹配判断。批准绑定当前正文、format、editorial_brief、章节顺序/hash、来源集、合同版本与 revision 的联合目标 hash，不允许只复用旧正文 approved。
6. 未通过：写 `review-report.json`，包括 `reviewed_revision`、正文/联合目标 hash、`decision=rejected`、逐项 `research_gaps`（id、chapter、question、why_reader_needs_it、required_evidence、acceptance_criterion）。审稿不改作者正文、不伪造通过；下一轮由作者补研。
7. 通过：生成真实独立 review 文件，调用当前本地验证器确认全部必要门禁。最后仅输出协议要求的 `publication_review_result` JSON，绑定服务端 issue/revision/attempt/target 和实际 review 文件 hash。不得自行 stage 或签名；签名必须等待本原生会话已结束。
8. 后续确定性发行接力从原生 Hermes DB 只读验证实际全文输入、有效最终输出、成功终态、owner/profile 与作者/审稿会话不同，签名回执绑定当前稿件与审核字节。签名证明输入/输出绑定，不代替事实审稿，也不声称抵御修改原生 DB 或掌握私钥的可信管理员。
9. 接力仅为通过项明列上传 review/proof/bundle，前后 hash 相等、冲突隔离不覆盖，再调用唯一 `publication_operator.py stage` 并逐 ID 回读。拒稿由同一接力将 gaps 记录到当前服务端 attempt；当前审核未终结时不得开新稿次绕过预算。审核 Agent 不负责 stage/release。

## 发行与验收

现有 12:00 确定性发行任务与有界重试只释放新门禁通过的待发稿。既有已发布正文不可变；旧待发稿必须补合同和复审。缺期仍显示缺期，不创建占位正文。

完成分层记录 `prepared / rejected / blocked / staged / published`，调度成功不算出版成功。新书发布后回读整本正文 hash、章节数和尾章；真实 iOS 验证标题、类型、首/中/尾章、链接和阅读进度。随书提问验证当前章节、末章、跨章与书中无答案的问题，保留版次和引用。未做不得称通过。

Quantum 问答补充正文而非替代正文；发现的事实错误和共性疑问，经授权形成下一版勘误/补充候选，不能自动把任何读者输入当可信事实或公开发布。
