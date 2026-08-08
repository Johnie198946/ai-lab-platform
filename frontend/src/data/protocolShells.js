const ROLE_SHELLS = {
  insight: {
    stage: "屏4 · 市场洞察",
    status: "洞察编纂中",
    emphasis: "竞品搜集 + 内部收集 + 报告编纂",
    summary:
      "围绕行业趋势、竞品动态与内部资产进行同步采集，最后输出结构化市场洞察报告与 Word 下载入口。",
    metrics: [
      { label: "竞品覆盖", value: "8 家" },
      { label: "内部信号", value: "24 条" },
      { label: "报告可信度", value: "88%" },
    ],
    streams: [
      {
        title: "竞品搜集过程",
        type: "progress",
        hint: "SSE · competitor",
        items: [
          { label: "字节跳动", meta: "模型发布与 Agent 动向", progress: 92 },
          { label: "阿里云", meta: "企业 AI 平台与生态打法", progress: 84 },
          { label: "腾讯", meta: "TeamMemory 与营销场景联动", progress: 77 },
          { label: "Google", meta: "Workspace AI 与开发入口", progress: 68 },
        ],
      },
      {
        title: "内部收集过程",
        type: "progress",
        hint: "SSE · internal",
        items: [
          { label: "产品路标", meta: "FusionOne AI 23.8.0", progress: 100 },
          { label: "算力产品族", meta: "TokenBox / TokenFactory", progress: 86 },
          { label: "营销工具包", meta: "Datasheet / PPT / 官网页", progress: 72 },
          { label: "研发物料", meta: "规格书 / 架构图 / Release Notes", progress: 63 },
        ],
      },
      {
        title: "报告编纂过程",
        type: "pipeline",
        hint: "SSE · report",
        items: [
          { label: "整合", state: "done" },
          { label: "分析", state: "done" },
          { label: "编辑", state: "active" },
          { label: "Office", state: "pending" },
          { label: "Word", state: "pending" },
        ],
      },
    ],
    sections: [
      {
        title: "核心结论",
        type: "text",
        content:
          "客户并不先看官网，而是先问 AI。市场洞察页需要先回答“谁在抢认知入口、谁在抢企业预算、谁在定义企业 AI 叙事”。当前结论是：超聚变必须把产品知识、竞品对比与营销论据整成可持续更新的统一信号面。",
      },
      {
        title: "重点机会",
        type: "cards",
        items: [
          {
            title: "认知入口前置",
            body: "把 AI 搜索结果里的品牌出现率视为新流量入口，优先补全产品问答素材。",
          },
          {
            title: "竞品拆解标准化",
            body: "沿产品、算力、生态、交付四个维度生成对比卡，支持屏4快速讲解。",
          },
          {
            title: "内部资料复用",
            body: "把产品路标、研发物料、营销模板编进统一知识底座，减少重复找数。",
          },
        ],
      },
      {
        title: "竞品机会表",
        type: "table",
        columns: ["对象", "主打能力", "风险提示", "我方动作"],
        rows: [
          ["阿里云", "模型与平台一体化", "生态覆盖强", "强调私有化交付与算力底座"],
          ["腾讯", "记忆与办公协同", "入口粘性高", "强化多 Agent 协同与本地部署"],
          ["Google", "办公生产力联动", "全球品牌强", "突出企业级合规与国产化适配"],
        ],
      },
      {
        title: "热度分布",
        type: "chart",
        items: [
          { label: "竞品热度", value: 82 },
          { label: "内部信号完备度", value: 67 },
          { label: "对外叙事成熟度", value: 58 },
        ],
      },
    ],
    actions: [
      { label: "下载洞察 Word", kind: "link", href: "/reports/market-insight-demo.docx" },
      { label: "同步到屏4 讲解视图", kind: "secondary" },
      { label: "推送产品经理继续 PRD", kind: "secondary" },
    ],
  },
  engineering: {
    stage: "屏6 · 开发工程师",
    status: "工程编译中",
    emphasis: "代码生成动效 + 硬件判定 + 演示切换",
    summary:
      "开发页强调软件工程事件流和硬件判定结果的并行展示，既要能看到代码生产过程，也要能明确说明当前任务是否进入硬件演示分支。",
    metrics: [
      { label: "工程步骤", value: "5 段" },
      { label: "接口编排", value: "12 条" },
      { label: "硬件分支", value: "软件优先" },
    ],
    streams: [
      {
        title: "软件工程师过程",
        type: "progress",
        hint: "SSE · engineering",
        items: [
          { label: "解析 PRD", meta: "提取接口与页面约束", progress: 100 },
          { label: "拆分前端壳体", meta: "登录 / 加载 / 输入 / 角色页", progress: 88 },
          { label: "生成组件代码", meta: "布局、状态与渲染器", progress: 74 },
          { label: "自检与构建", meta: "构建、回归、诊断", progress: 42 },
        ],
      },
      {
        title: "代码输出视图",
        type: "cards",
        hint: "JSON · architecture",
        items: [
          {
            title: "前端壳体",
            body: "统一 Workspace / Panel / Section 结构，确保 6 角色协议能按区块渲染。",
          },
          {
            title: "状态流",
            body: "保留现有会话恢复、角色编辑和本地草稿逻辑，减少接口面改动。",
          },
          {
            title: "演示分支",
            body: "硬件不参与时，直接落到软件演示页与视频入口。",
          },
        ],
      },
      {
        title: "硬件判定",
        type: "decision",
        hint: "JSON · hardware",
        decision: {
          title: "不涉及硬件开发",
          message: "当前任务聚焦前端重构与页面信息分区，请查看软件演示与构建结果。",
          cta: "查看演示视频入口",
        },
      },
    ],
    sections: [
      {
        title: "开发范围",
        type: "cards",
        items: [
          {
            title: "壳体统一",
            body: "登录页、加载页、需求输入页和关键角色页共享同一设计语言。",
          },
          {
            title: "页面滑动感",
            body: "通过层级分区和流程卡，模拟协议要求的左滑右入、动线切换感。",
          },
          {
            title: "稳定验证",
            body: "优先保证 `vite build` 可通过，再逐步接入真实 SSE 数据。",
          },
        ],
      },
      {
        title: "工程状态",
        type: "chart",
        items: [
          { label: "页面壳体", value: 91 },
          { label: "协议映射", value: 80 },
          { label: "真实接口接入", value: 46 },
        ],
      },
    ],
    actions: [
      { label: "打开演示视频页", kind: "primary" },
      { label: "查看构建结果", kind: "secondary" },
      { label: "导出工程说明", kind: "link", href: "/reports/engineering-demo.docx" },
    ],
  },
  marketing: {
    stage: "屏7 · 营销经理",
    status: "营销生产中",
    emphasis: "灵感初稿 + 四路并行材料 + MOR + 发布",
    summary:
      "营销页不是单一结果页，而是一个连续的生产流程页：先确认灵感方向，再并行创作，再经过 MOR 评审，最后进入发布与知识库沉淀。",
    metrics: [
      { label: "并行卡片", value: "4 路" },
      { label: "MOR 节点", value: "5 个" },
      { label: "发布触点", value: "3 个" },
    ],
    streams: [
      {
        title: "1.1 灵感初稿",
        type: "cards",
        hint: "JSON · style draft",
        items: [
          {
            title: "风格描述",
            body: "工业理性 + 展厅科技感，兼顾企业级可信与市场传播张力。",
          },
          {
            title: "卖点方向",
            body: "认知入口、AI 产能、算力成本可视化、合规可控交付。",
          },
          {
            title: "资产类型",
            body: "Datasheet、PPT、官网页、竞品对比表、邮件话术。",
          },
        ],
      },
      {
        title: "1.2 材料创作",
        type: "progress",
        hint: "SSE · material",
        items: [
          { label: "产品信息收集", meta: "资料对齐中", progress: 100 },
          { label: "主打胶片", meta: "视觉文案联调", progress: 78 },
          { label: "一指禅卖点", meta: "高管版金句蒸馏", progress: 64 },
          { label: "产品规格书", meta: "参数和对外表述校验", progress: 59 },
        ],
      },
      {
        title: "1.3 MOR 评审",
        type: "pipeline",
        hint: "JSON · mor",
        items: [
          { label: "产品经理", state: "done" },
          { label: "市场代表", state: "active" },
          { label: "研发代表", state: "pending" },
          { label: "产品主管", state: "pending" },
          { label: "SPDT 经理", state: "pending" },
        ],
      },
    ],
    sections: [
      {
        title: "发布节奏",
        type: "cards",
        items: [
          {
            title: "知识库沉淀",
            body: "把最终文案与模板沉淀进营销知识库，供后续任务复用。",
          },
          {
            title: "飞书宣贯",
            body: "把 MOR 通过内容推给一线与区域团队，保证认知一致。",
          },
          {
            title: "邮件触达",
            body: "同步外部客户和内部关键人，形成完整的发布动作闭环。",
          },
        ],
      },
      {
        title: "资产成熟度",
        type: "chart",
        items: [
          { label: "创意方向", value: 90 },
          { label: "物料完稿", value: 71 },
          { label: "评审通过率", value: 54 },
        ],
      },
    ],
    actions: [
      { label: "下载营销 Word", kind: "link", href: "/reports/marketing-demo.docx" },
      { label: "推送飞书与邮箱", kind: "primary" },
      { label: "发布到营销知识库", kind: "secondary" },
    ],
  },
};

const DEFAULT_ROLE_SHELL = {
  stage: "等待上游输入",
  status: "待触发",
  emphasis: "等待前序角色完成后进入当前阶段",
  summary:
    "当前角色暂不展示关键流程页壳体。你仍然可以编辑角色职责、技能和名字，并等待上游阶段完成后继续推进。",
  metrics: [
    { label: "当前模式", value: "待机" },
    { label: "依赖关系", value: "上游完成后唤起" },
    { label: "输出形态", value: "JSON + Word" },
  ],
  streams: [
    {
      title: "阶段说明",
      type: "cards",
      hint: "Protocol · waiting",
      items: [
        {
          title: "产品经理",
          body: "等待市场洞察完成后进入 PRD 与原型图渲染阶段。",
        },
        {
          title: "销售经理",
          body: "等待营销资产发布后进入邮件、翻译、总结和回复流程。",
        },
        {
          title: "老板",
          body: "等待市场、产品、开发、营销、销售全链路状态汇总后进入战情室。",
        },
      ],
    },
  ],
  sections: [
    {
      title: "统一协议",
      type: "text",
      content:
        "6 角色页面遵循统一规律：过程使用 SSE 流驱动，结果使用 JSON 渲染，下载使用 Word 链接承接。当前角色页保留等待壳体，便于后续继续扩展。",
    },
  ],
  actions: [{ label: "继续编辑当前角色", kind: "primary" }],
};

export const getRoleShell = (role) => {
  if (!role) {
    return DEFAULT_ROLE_SHELL;
  }

  const shell = ROLE_SHELLS[role.id] ?? DEFAULT_ROLE_SHELL;
  return {
    ...shell,
    title: role.title,
    name: role.name,
    badge: role.badge,
    focus: role.focus,
  };
};
