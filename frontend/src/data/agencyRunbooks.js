export const agencySource = {
  repository: "msitarzewski/agency-agents",
  revision: "ebe9c99acb5c96f9468de368d8bead775387d1a7",
  agentCount: 270,
};

export const agencyRunbooks = [
  {
    id: "IPD-01",
    slug: "market-insight",
    phase: "概念",
    title: "市场洞察",
    question: "这个问题真实存在并值得投入吗？",
    summary: "从客户、市场、竞品与产业四个维度形成有证据的机会判断。",
    outputs: ["需求合理性调研", "竞品矩阵", "产业证据清单"],
    capabilities: ["knowledge_search", "web_research", "web_extract"],
    agents: ["product-trend-researcher", "product-feedback-synthesizer", "testing-reality-checker"],
  },
  {
    id: "IPD-02",
    slug: "demand-analysis",
    phase: "概念",
    title: "需求分析",
    question: "需求应该接纳、附条件接纳，还是拒绝？",
    summary: "收敛目标、用户、范围与约束，形成可追溯的需求评审结论。",
    outputs: ["需求确认单", "需求评审结论", "初始产品包"],
    capabilities: ["knowledge_search", "specialist_execution"],
    agents: ["product-manager", "project-manager-senior", "testing-reality-checker"],
  },
  {
    id: "IPD-03",
    slug: "product-planning",
    phase: "计划",
    title: "产品规划",
    question: "具体要做成什么产品？",
    summary: "把市场机会转成产品组合、版本节奏、资源投入和收益判断。",
    outputs: ["产品组合规划书", "产品包定义", "资源与财务计划"],
    capabilities: ["knowledge_search", "specialist_execution"],
    agents: ["product-manager", "product-sprint-prioritizer", "project-manager-senior"],
  },
  {
    id: "IPD-04",
    slug: "architecture-design",
    phase: "计划",
    title: "架构设计",
    question: "产品决策如何转化为可评审的技术路径？",
    summary: "形成组件、数据流、接口、异常策略和关键技术风险。",
    outputs: ["架构方案", "接口清单", "技术风险清单"],
    capabilities: ["knowledge_search", "specialist_execution"],
    agents: ["engineering-software-architect", "engineering-backend-architect", "testing-reality-checker"],
  },
  {
    id: "IPD-05",
    slug: "development-plan",
    phase: "开发",
    title: "开发方案",
    question: "怎样拆成可执行、可验收的工程任务？",
    summary: "把产品包拆为模块、里程碑、依赖、风险和可测验收体系。",
    outputs: ["开发方案", "里程碑计划", "可测验收清单"],
    capabilities: ["knowledge_search", "specialist_execution"],
    agents: ["project-manager-senior", "engineering-senior-developer", "testing-test-results-analyzer"],
  },
  {
    id: "IPD-06",
    slug: "implementation-spec",
    phase: "开发",
    title: "实现规格",
    question: "如何把架构细化为可实现的规格？",
    summary: "定义模块、接口、数据字典、异常处理、权限与审计要求。",
    outputs: ["实现规格", "数据与接口契约", "异常处理规范"],
    capabilities: ["knowledge_search", "specialist_execution"],
    agents: ["engineering-software-architect", "engineering-senior-developer", "engineering-code-reviewer"],
  },
  {
    id: "IPD-07",
    slug: "integration-test",
    phase: "开发",
    title: "集成测试",
    question: "需求、规格和测试是否完整追溯？",
    summary: "设计 SDV/SIT 用例、环境、阈值和需求到用例的追溯关系。",
    outputs: ["SDV/SIT 方案", "追溯矩阵", "测试数据需求"],
    capabilities: ["knowledge_search", "specialist_execution"],
    agents: ["testing-api-tester", "testing-evidence-collector", "testing-test-results-analyzer"],
  },
  {
    id: "IPD-08",
    slug: "validation-test",
    phase: "验证",
    title: "验证测试",
    question: "方案是否真的可用、可靠并达到阈值？",
    summary: "覆盖功能、性能、客户现场、制造适配与可靠性验证。",
    outputs: ["验证方案", "BETA 反馈", "问题关闭计划"],
    capabilities: ["knowledge_search", "specialist_execution"],
    agents: ["testing-evidence-collector", "testing-performance-benchmarker", "testing-reality-checker"],
  },
  {
    id: "IPD-09",
    slug: "compliance-review",
    phase: "验证",
    title: "合规评审",
    question: "是否触碰安全、隐私或行业合规红线？",
    summary: "独立核查数据安全、网络安全、隐私与业务合规约束。",
    outputs: ["合规评审意见", "红线清单", "发布风险清单"],
    capabilities: ["knowledge_search", "web_research", "web_extract"],
    agents: ["security-compliance-auditor", "engineering-privacy-engineer", "testing-reality-checker"],
  },
  {
    id: "IPD-10",
    slug: "release-management",
    phase: "发布",
    title: "发布管理",
    question: "怎样可靠地完成交付和上市？",
    summary: "统筹部署、渠道、交付、服务和可获得性决策输入。",
    outputs: ["上市方案", "量产准备清单", "维护移交包"],
    capabilities: ["knowledge_search", "specialist_execution"],
    agents: ["engineering-devops-automator", "project-management-project-shepherd", "testing-evidence-collector"],
  },
  {
    id: "IPD-11",
    slug: "marketing-launch",
    phase: "发布",
    title: "营销推广",
    question: "如何把产品证据转化为合规的市场表达？",
    summary: "形成定位、内容、渠道、推广节奏和可度量的增长计划。",
    outputs: ["营销衔接方案", "内容矩阵", "渠道与指标计划"],
    capabilities: ["knowledge_search", "web_research", "specialist_execution"],
    agents: ["marketing-content-creator", "marketing-social-media-strategist", "design-brand-guardian"],
  },
  {
    id: "IPD-12",
    slug: "lifecycle-operations",
    phase: "生命周期",
    title: "生命周期经营",
    question: "怎样持续经营、迭代并安全退出？",
    summary: "监控采用率、价值、质量和服务成本，管理演进与退出。",
    outputs: ["生命周期看板", "版本路线图", "退出计划", "知识回流"],
    capabilities: ["knowledge_search", "specialist_execution"],
    agents: ["support-analytics-reporter", "support-infrastructure-maintainer", "product-feedback-synthesizer"],
  },
];

export function buildAgencyPrompt(runbook, customerBrief) {
  const agentLines = runbook.agents.map((agent) => `- ${agent}`).join("\n");
  const outputLines = runbook.outputs.map((output) => `- ${output}`).join("\n");
  const capabilityLines = runbook.capabilities.map((capability) => `- ${capability}`).join("\n");

  return `执行 AI Lab 001 业务实践 ${runbook.id}「${runbook.title}」。

你处于 Agency Agents 业务层。业务流程和对客交付由本 Runbook 负责；AI Lab 仅作为能力提供方。

客户需求：
${customerBrief.trim()}

业务问题：${runbook.question}
业务目标：${runbook.summary}

必须使用 agency-agents-router，按需加载并委派以下专家，不得只复述角色说明：
${agentLines}

执行时优先通过 ai_lab_capabilities 查询能力，再用 ai_lab_execute 调用以下能力：
${capabilityLines}

必须交付：
${outputLines}

执行规则：
1. 由 Agents Orchestrator 组织顺序和并行工作，并记录每个专家的真实贡献。
2. 需要内部事实时调用 AI Lab knowledge_search；需要外部事实时调用 web_research/web_extract。
3. 结论必须区分证据、推断和待确认项；没有工具结果时不得声称已经执行。
4. 最终输出采用中文 Markdown，依次包含：执行摘要、员工分工、证据与发现、正式交付物、风险、下一步。
5. Reality Checker 或相应质量角色必须完成最后评审；未通过时返工后再交付。`;
}
