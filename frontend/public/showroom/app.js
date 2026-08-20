const state = {
  view: new URLSearchParams(location.search).get('view') || 'controller',
  stage: 0,
  paused: false,
  experienceStep: 0,
  selectedPhase: 0,
  selectedAgent: 'IPD-01',
  pipelineMode: 'orchestration',
  pipelinePlaying: false,
  ipdDrawer: null,
  agentDetailOpen: false,
  giantMode: new URLSearchParams(location.search).get('mode') || 'workbench',
  selectedArtifact: new URLSearchParams(location.search).get('artifact') || null,
  artifactOpen: false,
  assistantOpen: false,
  avatarSpeaking: false,
  assistantQuestion: '',
  assistantAnswer: '',
  backendStatus: 'connecting',
  backendDetail: '',
  bootstrapped: false,
  screenConfigs: [],
  content: null,
  session: null,
  knowledge: {},
  capabilities: {},
  centers: [],
  reviewStates: {},
  activeReview: null,
  reviewDecision: null,
  introSkipped: false,
  pendingClarify: null,
  streamingReply: '',
  chatError: '',
  lastQuestion: '',
  chatMessages: [],
  hermesStatus: 'idle',
  hermesDetail: '',
  hermesRetryStopped: false,
  demandSheetVisible: false,
  demandSheetPendingFocus: false,
  visitorInsightBusy: false,
  controllerHermesTask: '',
  controllerFailureHandling: false,
  hostGreetingPending: false,
  visitCompleteNotice: null,
  visitEndConfirmOpen: false,
  visitEndBusy: false,
  lastRolloverSessionId: '',
  rawHermesMessageCount: 0,
  frontstageActivating: false,
  demandCorrectionPending: false,
  insightCatalog: null,
  insightTask: '',
  selectedEmployeeId: '',
  insightAutoSeconds: 0,
  insightAutoPaused: false,
  insightAssistantMessages: [],
  insightAssistantBusy: false,
  insightAssistantStatus: '',
  insightSelectedSection: 'summary',
  insightSelectedText: '',
  insightPendingRevision: null,
  insightActiveRequest: null,
  insightRevisionError: null,
  insightRevisionApplying: false,
  insightHighlightedSections: [],
  insightFieldCatalog: [],
  insightPlacementCandidates: [],
  insightReadinessOpen: false,
  insightTbdTarget: null,
  insightReviewRunning: false,
  insightReviewTaskId: '',
};

const STATIC_DISPLAY_VIEWS = new Set(['screen-00', 'screen-01', 'screen-02']);
const demandExtractionInFlight = new Set();
const insightEventIds = new Set();
let insightProgressQueue = Promise.resolve();
let insightAutoTimer = null;
let insightServerPollTimer = null;

function resetSessionUiState(nextSession = null) {
  clearInsightAutoAdvance();
  insightProgressQueue = Promise.resolve();
  demandExtractionInFlight.clear();
  insightEventIds.clear();
  Object.assign(state, {
    stage: 0,
    experienceStep: Number(nextSession?.step || 0),
    selectedPhase: 0,
    selectedAgent: 'IPD-01',
    pipelineMode: 'orchestration',
    pipelinePlaying: false,
    ipdDrawer: null,
    agentDetailOpen: false,
    selectedArtifact: null,
    artifactOpen: false,
    assistantOpen: false,
    avatarSpeaking: false,
    assistantQuestion: '',
    assistantAnswer: '',
    session: nextSession,
    bootstrapped: Boolean(nextSession),
    centers: [],
    reviewStates: {},
    activeReview: null,
    reviewDecision: null,
    pendingClarify: null,
    streamingReply: '',
    chatError: '',
    lastQuestion: '',
    chatMessages: [],
    hermesStatus: 'idle',
    hermesDetail: '',
    hermesRetryStopped: false,
    demandSheetVisible: false,
    demandSheetPendingFocus: false,
    visitorInsightBusy: false,
    controllerHermesTask: '',
    controllerFailureHandling: false,
    hostGreetingPending: false,
    visitCompleteNotice: null,
    visitEndConfirmOpen: false,
    visitEndBusy: false,
    rawHermesMessageCount: 0,
    frontstageActivating: false,
    demandCorrectionPending: false,
    insightCatalog: null,
    insightTask: '',
    selectedEmployeeId: '',
    insightAutoSeconds: 0,
    insightAutoPaused: false,
    insightAssistantMessages: [],
    insightAssistantBusy: false,
    insightAssistantStatus: '',
    insightSelectedSection: 'summary',
    insightSelectedText: '',
    insightPendingRevision: null,
    insightActiveRequest: null,
    insightRevisionError: null,
    insightRevisionApplying: false,
    insightHighlightedSections: [],
    insightFieldCatalog: [],
    insightPlacementCandidates: [],
    insightReadinessOpen: false,
    insightTbdTarget: null,
    insightReviewRunning: false,
    insightReviewTaskId: '',
  });
}

function applySessionRollover(nextSession, runtime = null, expectedSessionId = '') {
  const nextSessionId = nextSession?.session_id || expectedSessionId;
  if (nextSessionId && state.lastRolloverSessionId === nextSessionId) return false;
  resetSessionUiState(nextSession || null);
  state.lastRolloverSessionId = nextSessionId;
  if (runtime) applyBackendSnapshot(runtime, false);
  return true;
}

const INSIGHT_REVISION_INTENT = /修改|修正|调整|改为|改成|补齐|补充到|删除|新增|更新|回填|填入|写入|同步|替换|应用到(?:本章|报告)/;
const INSIGHT_FIELD_SECTIONS = {
  judgment: 'insight-summary', gap: 'insight-summary', recommendation: 'insight-summary',
  'concept.customer_user': 'concept-customer', 'concept.market': 'concept-market',
  'concept.competition': 'concept-competition', 'concept.technology': 'concept-technology',
  'concept.strategic_fit': 'concept-strategy', 'concept.capability_mapping': 'concept-capability',
  'concept.assessment': 'concept-assessment', 'concept.special_checks': 'concept-checks',
  'concept.knowledge_status': 'concept-knowledge', evidence: 'concept-knowledge', sources: 'concept-knowledge',
  'concept.verdict': 'concept-verdict', 'concept.initial_product_package': 'concept-package',
  'concept.demo_slice': 'concept-package', ipd_handoff: 'concept-package',
};

function isStaticDisplayView(view = state.view) {
  return STATIC_DISPLAY_VIEWS.has(view);
}

function isConversationView(view = state.view) {
  return ['controller', 'screen-03', 'screen-04'].includes(view) || view.startsWith('experience-');
}

const motionSystem = {
  gsap: window.gsap || null,
  context: null,
  workflow: null,
  media: null,
  reduceMotion: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  renderToken: 0,
};

if (motionSystem.gsap) {
  document.documentElement.classList.add('gsap-enabled');
  motionSystem.media = motionSystem.gsap.matchMedia();
  motionSystem.media.add({
    reduceMotion: '(prefers-reduced-motion: reduce)',
    allowMotion: '(prefers-reduced-motion: no-preference)',
  }, ({ conditions }) => {
    motionSystem.reduceMotion = Boolean(conditions.reduceMotion);
  });
}

function motionEnabled() {
  return Boolean(motionSystem.gsap && !state.paused && !motionSystem.reduceMotion);
}

function stopScreenMotion() {
  motionSystem.workflow?.kill();
  motionSystem.workflow = null;
  motionSystem.context?.revert();
  motionSystem.context = null;
}

function clearMotionProps(targets) {
  if (!motionSystem.gsap || !targets?.length) return;
  motionSystem.gsap.set(targets, { clearProps: 'transform,opacity,visibility,willChange' });
}

function playWorkflowLoop(root) {
  if (!motionEnabled() || !state.pipelinePlaying) return;
  const agents = root.querySelectorAll('.agent-node, .giant-agent');
  const streams = root.querySelectorAll('.flow-arrow i, .giant-stream i');
  if (!agents.length) return;

  const gsap = motionSystem.gsap;
  const timeline = gsap.timeline({ repeat: -1, repeatDelay: 0.65 });
  agents.forEach((agent, index) => {
    timeline
      .fromTo(agent, { autoAlpha: 0.58, scale: 0.985 }, {
        autoAlpha: 1,
        scale: 1.025,
        duration: 0.22,
        ease: 'power2.out',
        overwrite: 'auto',
      }, index * 0.48)
      .to(agent, {
        scale: 1,
        duration: 0.24,
        ease: 'power2.inOut',
      }, index * 0.48 + 0.22);
  });
  if (streams.length) {
    timeline.fromTo(streams, { x: -8, autoAlpha: 0.18 }, {
      x: 18,
      autoAlpha: 1,
      duration: 0.52,
      stagger: 0.055,
      ease: 'power1.inOut',
    }, 0.12);
  }
  motionSystem.workflow = timeline;
}

function runScreenMotion(intent = 'refresh') {
  const root = document.getElementById('screen-canvas');
  const gsap = motionSystem.gsap;
  if (!root || !gsap) return;
  if (!motionEnabled()) {
    root.style.opacity = '1';
    root.style.transform = 'none';
    return;
  }

  motionSystem.context = gsap.context(() => {
    const timeline = gsap.timeline({ defaults: { ease: 'power2.out' } });
    timeline.fromTo(root, { autoAlpha: 0, y: 6 }, {
      autoAlpha: 1,
      y: 0,
      duration: 0.24,
      clearProps: 'transform,opacity,visibility',
    });

    const header = root.querySelector('.screen-header');
    const primary = root.querySelectorAll('.ipd-command, .ipd-phase-rail, .ipd-focus-head, .giant-ipd-label, .giant-artifact-main > header, .insight-cover, .experience-top');
    const panels = root.querySelectorAll('.ipd-focus-grid > .panel, .ipd-utility-row > *, .deliverable-column, .giant-ipd > section, .giant-workbench > section, .insight-summary-grid > div, .experience-body > *, .control-grid > .panel');
    if (header) timeline.fromTo(header, { autoAlpha: 0, y: -8 }, { autoAlpha: 1, y: 0, duration: 0.26 }, 0.03);
    if (primary.length) timeline.fromTo(primary, { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: 0.32, stagger: 0.045 }, 0.06);
    if (panels.length) timeline.fromTo(panels, { autoAlpha: 0, y: 14 }, { autoAlpha: 1, y: 0, duration: 0.38, stagger: 0.055 }, 0.1);

    if (intent === 'phase') {
      timeline.fromTo('.ipd-phase.active, .giant-phase-list button.active', { scale: 0.965 }, { scale: 1, duration: 0.34, ease: 'back.out(1.2)' }, 0.08);
      timeline.fromTo('.agent-inspector, .giant-stage-head', { autoAlpha: 0, x: 14 }, { autoAlpha: 1, x: 0, duration: 0.34 }, 0.14);
    }
    if (intent === 'agent') {
      timeline.fromTo('.agent-node.selected, .giant-agent.active', { scale: 0.965, autoAlpha: 0.65 }, { scale: 1, autoAlpha: 1, duration: 0.28, ease: 'back.out(1.2)' }, 0.04);
      timeline.fromTo('.agent-inspector', { autoAlpha: 0, x: 12 }, { autoAlpha: 1, x: 0, duration: 0.28 }, 0.08);
    }
    if (intent === 'ipd-drawer') {
      timeline.fromTo('.ipd-drawer-scrim', { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.18 }, 0);
      timeline.fromTo('.ipd-detail-drawer', { autoAlpha: 0, y: 24, scale: 0.992 }, { autoAlpha: 1, y: 0, scale: 1, duration: 0.32 }, 0.03);
    }
    if (intent === 'agent-detail') {
      timeline.fromTo('.agent-inspector', { autoAlpha: 0, height: 0, y: -8 }, { autoAlpha: 1, height: 'auto', y: 0, duration: 0.28 }, 0.04);
    }
    if (intent === 'artifact-open') {
      timeline.fromTo('.artifact-overlay', { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.2 }, 0);
      timeline.fromTo('.artifact-modal', { autoAlpha: 0, y: 20, scale: 0.985 }, { autoAlpha: 1, y: 0, scale: 1, duration: 0.38, ease: 'power2.out' }, 0.04);
      timeline.fromTo('.artifact-modal-grid > aside, .artifact-demo > *', { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: 0.28, stagger: 0.035 }, 0.18);
    }
    if (intent === 'review-open' || intent === 'review-result') {
      timeline.fromTo('.review-overlay', { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.2 }, 0);
      timeline.fromTo('.feishu-review', { autoAlpha: 0, y: 18, scale: 0.987 }, { autoAlpha: 1, y: 0, scale: 1, duration: 0.36 }, 0.04);
      timeline.fromTo('.review-package button, .review-decision button, .review-result > *', { autoAlpha: 0, y: 8 }, { autoAlpha: 1, y: 0, duration: 0.25, stagger: 0.04 }, 0.18);
    }
    if (intent === 'review-decision') {
      timeline.fromTo('.review-decision button.active', { scale: 0.96 }, { scale: 1, duration: 0.26, ease: 'back.out(1.25)' }, 0.04);
    }
    if (intent === 'assistant') {
      timeline.fromTo('.assistant-panel', { autoAlpha: 0, y: 14, scale: 0.985 }, { autoAlpha: 1, y: 0, scale: 1, duration: 0.32 }, 0.04);
      timeline.fromTo('.digital-human, .subtitle-card', { autoAlpha: 0, y: 8 }, { autoAlpha: 1, y: 0, duration: 0.28, stagger: 0.06 }, 0.16);
    }
    if (intent === 'cast') {
      timeline.fromTo('.giant-ipd-left, .giant-artifact-nav', { autoAlpha: 0, x: -18 }, { autoAlpha: 1, x: 0, duration: 0.42 }, 0.02);
      timeline.fromTo('.giant-ipd-center, .giant-artifact-main', { autoAlpha: 0, y: 12 }, { autoAlpha: 1, y: 0, duration: 0.46 }, 0.1);
      timeline.fromTo('.giant-ipd-right, .giant-presenter', { autoAlpha: 0, x: 18 }, { autoAlpha: 1, x: 0, duration: 0.42 }, 0.18);
    }

    timeline.add(() => clearMotionProps(root.querySelectorAll([
      '.screen-header', '.ipd-command', '.ipd-phase-rail', '.ipd-focus-head',
      '.giant-ipd-label', '.giant-artifact-main > header', '.insight-cover',
      '.experience-top', '.ipd-focus-grid > .panel', '.ipd-utility-row > *', '.deliverable-column',
      '.giant-ipd > section', '.giant-workbench > section', '.insight-summary-grid > div',
      '.experience-body > *', '.control-grid > .panel', '.ipd-phase.active',
      '.giant-phase-list button.active', '.agent-inspector', '.giant-stage-head',
      '.artifact-overlay', '.artifact-modal', '.artifact-modal-grid > aside',
      '.artifact-demo > *', '.review-overlay', '.feishu-review',
      '.review-package button', '.review-decision button', '.review-result > *',
      '.assistant-panel', '.digital-human', '.subtitle-card', '.giant-artifact-nav',
      '.giant-artifact-main', '.giant-presenter', '.ipd-drawer-scrim', '.ipd-detail-drawer',
    ].join(','))));
    playWorkflowLoop(root);
  }, root);
}

function closeSurface(selector, mutate, nextIntent = 'refresh') {
  const surface = document.querySelector(selector);
  if (!surface || !motionEnabled()) {
    mutate();
    render(nextIntent);
    return;
  }
  motionSystem.gsap.to(surface, {
    autoAlpha: 0,
    y: 10,
    scale: 0.99,
    duration: 0.18,
    ease: 'power2.in',
    overwrite: true,
    onComplete: () => {
      mutate();
      render(nextIntent);
    },
  });
}

const viewGroups = [
  {
    label: 'CONTROL',
    items: [{ id: 'controller', number: 'C', name: '导览主控台', sub: 'iPad Controller' }],
  },
  {
    label: 'MAIN TOUR · 主演示',
    items: [
      { id: 'screen-00', number: '00', name: 'AI Lab 序章', sub: '揭幕与简短介绍' },
      { id: 'screen-01', number: '01', name: '迎宾与合影', sub: '入口宽屏' },
      { id: 'screen-02', number: '02', name: '算力运营大盘', sub: 'FUSIONONE' },
      { id: 'screen-03', number: '03', name: '需求问诊台', sub: '用户对话与确认单' },
      { id: 'screen-04', number: '04', name: '深度洞察报告', sub: '根因与行动建议' },
      { id: 'screen-05', number: '05', name: 'IPD 流水线', sub: '六阶段点火器' },
      { id: 'screen-06', number: '06', name: '001 实战主屏', sub: '7290 工作台' },
      { id: 'screen-07', number: '07', name: '运行原型', sub: 'WorkBuddy Window' },
    ],
  },
  {
    label: 'CO-CREATION · 独立体验中心',
    items: Array.from({ length: 5 }, (_, i) => ({
      id: `experience-0${i + 1}`,
      number: `E${i + 1}`,
      name: `体验中心 0${i + 1}`,
      sub: '完整独立全流程',
      experience: true,
    })),
  },
];

const viewMeta = {
  controller: ['导览主控台', 'CONTROLLER / iPAD', '1366 × 1024'],
  'screen-00': ['AI Lab 序章', 'SCREEN 00 / OPENING', '5280 × 1080'],
  'screen-01': ['迎宾与合影', 'SCREEN 01 / ENTRANCE', '5280 × 1080'],
  'screen-02': ['TokenOps 算力运营', 'SCREEN 02 / DASHBOARD', '3840 × 1080'],
  'screen-03': ['001 需求即时问诊台', 'SCREEN 03 / INTERACTIVE', '1920 × 1080'],
  'screen-03-team': ['AI 项目组集结', 'SCREEN 003.5 / STAFFING', '1920 × 1080'],
  'screen-04': ['需求深度洞察报告', 'SCREEN 04 / INSIGHT', '1920 × 1080'],
  'screen-05': ['IPD 微缩流水线', 'SCREEN 05 / PIPELINE', '1920 × 1080'],
  'screen-06': ['IPD 001 实战主屏', 'SCREEN 06 / WORKBENCH', '7290 × 1080'],
  'screen-07': ['生成原型运行窗口', 'SCREEN 07 / LIVE APP', '1080 × 1920'],
};

for (let i = 1; i <= 5; i += 1) {
  viewMeta[`experience-0${i}`] = [`独立体验中心 0${i}`, `EXPERIENCE CENTER 0${i}`, '1920 × 1080'];
}

const stages = [
  ['站 1', '迎宾'], ['站 2', '算力'], ['站 3', '问诊'], ['站 4', '实战'], ['站 5', '共创'],
];

const ipdPhases = [
  {
    name: '概念', short: '问题值得做吗？', objective: '从客户需求出发，判断市场成立、战略匹配和需求完备性。',
    reviews: ['TR1', 'CDCP'], inputs: ['需求确认单', '客户痛点', '产品战略边界'],
    outputs: ['需求合理性·调研支撑', '需求评审结论', '初始产品包'],
    agents: [
      { id: 'IPD-01', name: '市场洞察', role: 'MI 研判者', base: 'Main', job: '围绕已确认需求完成市场、客户、竞品和产业四维研判。', status: 'working' },
      { id: 'IPD-02', name: '需求分析', role: '需求评审官', base: 'Supervision', job: '判断需求合理性：建议产品、条件接纳或明确拒绝。', status: 'waiting' },
    ],
  },
  {
    name: '计划', short: '具体做成什么？', objective: '完成产品定义、商业计划、架构与资源承诺，形成正式开发合同。',
    reviews: ['TR2', 'TR3', 'PDCP'], inputs: ['需求评审结论', '初始产品包', '市场机会'],
    outputs: ['产品组合规划书', '产品包定义', '架构方案', '资源与财务计划'],
    agents: [
      { id: 'IPD-03', name: '产品规划', role: '产品管理部', base: 'Main', job: '先定产品再规划，形成组合、节奏、投资和收益判断。', status: 'locked' },
      { id: 'IPD-04', name: '架构设计', role: '系统架构师', base: 'Main', job: '把产品决策转化为可评审的系统架构与关键技术路径。', status: 'locked' },
    ],
  },
  {
    name: '开发', short: '怎样工程化实现？', objective: '把产品定义转化为可开发、可测试、可追溯的实现规格。',
    reviews: ['TR4', 'TR4A'], inputs: ['PDCP 合同', '架构方案', '完整规格'],
    outputs: ['开发方案', '56 项可测验收', '实现规格', 'SDV/SIT 方案'],
    agents: [
      { id: 'IPD-05', name: '开发方案', role: '方案与验收设计', base: 'Main', job: '不假装开发，输出可执行方案与可测验收体系。', status: 'locked' },
      { id: 'IPD-06', name: '实现规格', role: '规格设计师', base: 'Coder', job: '把架构细化成模块、接口、数据与异常处理规格。', status: 'locked' },
      { id: 'IPD-07', name: '集成测试', role: 'SDV/SIT 设计师', base: 'Supervision', job: '建立需求—规格—用例追溯，设计系统集成验证。', status: 'locked' },
    ],
  },
  {
    name: '验证', short: '真的可用且合规吗？', objective: '完成客户、制造、压力、认证和合规验证，确认发布准备度。',
    reviews: ['TR5', 'EDCP'], inputs: ['系统构建', '测试基线', '合规红线'],
    outputs: ['验证方案', 'BETA 反馈', '合规评审意见', '发布风险清单'],
    agents: [
      { id: 'IPD-08', name: '验证测试', role: 'TR5 验证官', base: 'Supervision', job: '为功能、性能、客户和制造验证设置明确阈值。', status: 'locked' },
      { id: 'IPD-09', name: '合规评审', role: '独立守门人', base: 'Supervision', job: '核查出口管制、网络安全和隐私红线，不编造合规结论。', status: 'locked' },
    ],
  },
  {
    name: '发布', short: '怎样可靠上市？', objective: '完成量产、营销、产能爬坡和开发到维护的平稳过渡。',
    reviews: ['TR6', 'ADCP', 'MOR'], inputs: ['TR5 结论', '验证证据', '上市准备'],
    outputs: ['上市方案', '量产准备清单', '营销衔接方案', '维护移交包'],
    agents: [
      { id: 'IPD-10', name: '发布管理', role: '上市经理', base: 'Main', job: '统筹量产、渠道、交付和可获得性决策输入。', status: 'locked' },
      { id: 'IPD-11', name: '营销推广', role: 'MOR 衔接者', base: 'Main', job: '把产品证据转化为合规的市场表达与推广节奏。', status: 'locked' },
    ],
  },
  {
    name: '生命周期', short: '怎样持续经营？', objective: '持续监控销售、服务和产品健康度，并管理安全退出。',
    reviews: ['EOP', 'EOM', 'EOS'], inputs: ['上市产品', '运营与服务数据', '客户反馈'],
    outputs: ['生命周期看板', '版本路线图', '退出计划', '知识回流'],
    agents: [
      { id: 'IPD-12', name: '生命周期', role: '产品经营官', base: 'Main', job: '监控全生命周期表现，管理演进、停产、停售和停服。', status: 'locked' },
    ],
  },
];

const baseAgents = {
  Main: { label: 'Main', verb: '主持与起草', desc: '理解目标、调用知识与技能，组织专业角色完成初稿。' },
  Supervision: { label: 'Supervision', verb: '质询与把关', desc: '独立审查证据、提出修改意见，并控制评审门。' },
  Coder: { label: 'Coder', verb: '工程化落实', desc: '只在批准后，把方案变成规格、代码和可验证结果。' },
};

const humanReviewers = {
  TR1: { person: '王敏（示例）', role: '需求管理专家', group: 'PDT 需求评审组', focus: '需求完整性、客户证据、产品边界' },
  CDCP: { person: '李哲（示例）', role: '产品线投资代表', group: 'IPMT 决策委员会', focus: '市场机会、战略匹配、是否进入计划' },
  TR2: { person: '周航（示例）', role: '系统工程负责人', group: '技术评审组', focus: '需求到规格的完整映射' },
  TR3: { person: '孙凯（示例）', role: '架构评审主席', group: '架构与技术委员会', focus: '概要设计、关键技术路径、风险' },
  PDCP: { person: '赵宁（示例）', role: 'IPMT 投资决策人', group: '产品投资委员会', focus: '产品合同、资源、财务与合规承诺' },
  TR4: { person: '刘磊（示例）', role: '开发代表', group: '系统开发评审组', focus: '系统级构建前的规格完整性' },
  TR4A: { person: '何静（示例）', role: '测试与制造代表', group: '技术成熟度评审组', focus: 'SDV 证据、供应与制造支撑能力' },
  TR5: { person: '陈璐（示例）', role: '质量与验证负责人', group: '产品验证评审组', focus: '客户、制造、性能与可靠性验证' },
  EDCP: { person: '赵宁（示例）', role: 'IPMT 早期销售授权人', group: '产品投资委员会', focus: '少量提前上市的风险与边界' },
  TR6: { person: '贺斌（示例）', role: '制造与交付负责人', group: '系统上市评审组', focus: '量产、交付与全球发货准备度' },
  ADCP: { person: '李哲（示例）', role: '产品线投资代表', group: 'IPMT 决策委员会', focus: '正式上市与可获得性决策' },
  MOR: { person: '梁舒（示例）', role: 'MO 负责人', group: '营销运作评审组', focus: '营销交付件与发布口径衔接' },
  EOP: { person: '蒋雯（示例）', role: '产品经营负责人', group: '生命周期委员会', focus: '停止生产的业务与客户影响' },
  EOM: { person: '许阳（示例）', role: '市场与服务负责人', group: '生命周期委员会', focus: '停售节奏、渠道和存量客户保障' },
  EOS: { person: '李哲（示例）', role: '产品线总经理', group: '生命周期委员会', focus: '停服、迁移与最终退出授权' },
};

const reviewStatus = {
  pending: ['待评审', 'pending'], approved: ['已通过', 'approved'], changes: ['需修改', 'changes'], rejected: ['已拒绝', 'rejected'],
};

function currentSessionData() {
  return state.session?.data || {};
}

function getScreenConfig(screenId) {
  return state.screenConfigs.find((screen) => screen.screen_id === screenId) || {};
}

function architectStatusLabel() {
  return {
    idle: '等待连接',
    connecting: '正在连接大架构师',
    online: '大架构师在线',
    generating: '正在研判',
    waiting: '等待你的选择',
    reconnecting: '连接恢复中',
    error: '连接异常',
    'quota-required': '模型额度不足',
    'auth-required': '需要登录',
  }[state.hermesStatus] || '等待连接';
}

function updateHermesStatusIndicators() {
  document.querySelectorAll('[data-hermes-status-indicator]').forEach((indicator) => {
    indicator.dataset.hermesStatus = state.hermesStatus;
    indicator.textContent = architectStatusLabel();
    indicator.title = state.hermesDetail || architectStatusLabel();
    indicator.classList.toggle('error', ['error', 'quota-required', 'auth-required'].includes(state.hermesStatus));
  });
}

function friendlyHermesError(message = '') {
  const raw = String(message || '').trim();
  if (/insufficient balance|余额不足|status[_ ]?code[^\d]*402|error code:\s*402/i.test(raw)) {
    return 'DeepSeek 模型额度不足，请充值或配置可用的备用模型后重试。';
  }
  if (/prompt_cache_(?:retention|options).*not supported/i.test(raw)) {
    return '当前模型不支持请求中的缓存参数，请联系管理员检查模型兼容配置。';
  }
  if (/model is not supported when using Codex with a ChatGPT account|deepseek-v4-flash.*not supported/i.test(raw)) {
    return '当前会话仍绑定旧模型，正在切换到可用模型；请重新备课。';
  }
  return raw || '大架构师本轮回复失败';
}

function hermesFailureStatus(message = '') {
  return /insufficient balance|余额不足|status[_ ]?code[^\d]*402|error code:\s*402/i.test(String(message || ''))
    ? 'quota-required'
    : 'error';
}

function currentDemand() {
  return currentSessionData().demand || {};
}

function currentDemandDocument() {
  return currentSessionData().demand_document || {};
}

function hasDemandConfirmationContent(demand = {}) {
  const document = currentDemandDocument();
  const fields = ['core_problem', 'target_metric', 'cycle', 'users', 'solution', 'next_action'];
  return Boolean(
    document.source_hash
    || document.status === 'confirmed'
    || demand.confirmed
    || Number(demand.completeness || 0) > 0
    || fields.some((field) => String(demand[field] || '').trim()),
  );
}

function demandTable(section) {
  const table = section?.table || {};
  const columns = Array.isArray(table.columns) ? table.columns : [];
  const rows = Array.isArray(table.rows) ? table.rows : [];
  if (!columns.length || !rows.length) return '';
  return `<div class="demand-doc-table-wrap"><table><thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join('')}</tr></thead><tbody>${rows.map((row) => `<tr>${columns.map((_, index) => `<td>${escapeHtml(row?.[index] || '')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}

function demandSectionContent(section) {
  const table = demandTable(section);
  const items = Array.isArray(section?.items) ? section.items.filter(Boolean) : [];
  const body = String(section?.body || '').trim();
  return `${table}${items.length ? `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : ''}${body ? `<p>${escapeHtml(body)}</p>` : ''}`;
}

const demandSectionRegistry = {
  facts: { label: '已确认事实', tone: 'blue' },
  goal: { label: '目标指标', tone: 'mint' },
  non_goals: { label: '非目标', tone: 'violet' },
  constraints: { label: '约束与边界', tone: 'orange' },
  acceptance: { label: '验收标准', tone: 'mint' },
  solution_direction: { label: 'AI 初步方案方向', tone: 'blue' },
  unknown: { label: '补充内容', tone: 'neutral' },
};

function demandDocumentView(document = {}) {
  const sections = Array.isArray(document.sections) ? document.sections : [];
  if (!sections.length && !document.raw_markdown) return '';
  return `<details class="demand-document"><summary><span><b>完整需求确认单</b><small>${sections.length} 个章节 · 展开查看事实、边界与验收</small></span><em>展开</em></summary><div class="demand-document-body">${sections.map((section, index) => {
    const plugin = demandSectionRegistry[section.type] || demandSectionRegistry.unknown;
    return `<section class="demand-doc-section ${plugin.tone}"><header><span>${String(index + 1).padStart(2, '0')}</span><div><small>${escapeHtml(plugin.label)}</small><h4>${escapeHtml(section.title || plugin.label)}</h4></div></header>${demandSectionContent(section)}</section>`;
  }).join('')}${document.warnings?.length ? `<div class="demand-doc-warning">${document.warnings.map((warning) => escapeHtml(warning)).join(' · ')}</div>` : ''}</div></details>`;
}

async function maybeExtractDemand(rawContent, options = {}) {
  const content = String(rawContent || '').trim();
  if (!content || !/(?:需求(?:收敛)?确认单|四维确认单|AI_LAB_DEMAND_(?:STATE_)?V1)/.test(content)) return;
  if (currentDemand().confirmed || demandExtractionInFlight.has(content)) return;
  demandExtractionInFlight.add(content);
  state.demandSheetPendingFocus = true;
  try {
    const result = await window.showroomApi.extractDemand(content);
    if (!result?.recognized) state.demandSheetPendingFocus = false;
    if (result?.recognized && !result.unchanged && !result.locked && !options.silent) {
      showToast('需求收敛单已自动回填 · 请核对后确认');
    }
  } catch (error) {
    state.demandSheetPendingFocus = false;
    if (!options.silent) showToast(`需求单回填失败：${error.message}`);
  } finally {
    demandExtractionInFlight.delete(content);
  }
}

function demandInterview() {
  return currentSessionData().demand_interview || {
    followup_count: 0,
    dimensions: {},
    missing: ['business_scene', 'user_role', 'current_blocker', 'target_outcome'],
  };
}

function demandPolicyPrompt(question) {
  const interview = demandInterview();
  const followupCount = Math.min(3, Number(interview.followup_count || 0));
  const dimensions = interview.dimensions || {};
  const mustConverge = followupCount >= 2
    || ['business_scene', 'user_role', 'current_blocker', 'target_outcome'].every((key) => String(dimensions[key] || '').trim());
  return [
    '[AI_LAB_DEMAND_POLICY_V1]',
    '当前是站3需求问诊，不是方案设计阶段。禁止输出完整建设方案、总体架构、实施路线或技术选型。',
    '任务是收敛四维：业务场景、用户角色、当前阻碍、目标结果。每轮最多只问一个关键问题。',
    `已完成追问轮次：${followupCount}/3。当前四维：${JSON.stringify(dimensions)}。`,
    mustConverge
      ? '本轮必须停止追问，未知项写“TBD”，直接输出可见需求收敛确认单，并附 AI_LAB_DEMAND_V1。'
      : '若四维已齐，立即输出需求收敛确认单；否则只追问缺失维度中最关键的一项。',
    '每次回复末尾都必须附：<!-- AI_LAB_DEMAND_STATE_V1 {"status":"collecting|ready|draft","dimensions":{"business_scene":"","user_role":"","current_blocker":"","target_outcome":""}} AI_LAB_DEMAND_STATE_V1 -->',
    '需求确认后应引导用户进入屏幕04深度洞察，再到屏幕05/06完成001 IPD实践；站3不得代替后续环节出方案。',
    `用户原始问题：${question}`,
  ].join('\n');
}

function isPrematureScheme(content) {
  if (currentDemand().confirmed || /AI_LAB_DEMAND_V1/.test(content)) return false;
  return /(?:建设建议方案|总体架构|技术架构|实施路线|分阶段实施|完整方案)/.test(content);
}

async function maybeExtractVisitorInsight(rawContent, options = {}) {
  const content = String(rawContent || '').trim();
  if (!content || !/AI_LAB_VISITOR_INSIGHT_V1/.test(content)) return;
  try {
    const result = await window.showroomApi.extractVisitorInsight(content);
    state.visitorInsightBusy = false;
    state.controllerHermesTask = '';
    if (!result?.recognized) {
      const reason = result?.reason || '客户洞察结构化数据无法识别';
      state.chatError = reason;
      if (!options.silent) showToast(`${reason}，请点击重新洞察`);
    } else if (!result.unchanged && !options.silent) {
      showToast('客户洞察已回填并安全写入 Wiki');
    }
    render('refresh');
  } catch (error) {
    state.visitorInsightBusy = false;
    state.controllerHermesTask = '';
    if (!options.silent) showToast(`客户洞察落盘失败：${error.message}`);
    render('refresh');
  }
}

function visitorFormData() {
  const people = String(document.getElementById('visitor-people')?.value || '').split(/[；;\n]+/).map((item) => {
    const [name, title = ''] = item.split(/\s*[/／]\s*/, 2);
    return { name: name?.trim() || '', title: title.trim() };
  }).filter((person) => person.name || person.title);
  return {
    company_name: document.getElementById('visitor-company')?.value.trim() || '',
    customer_code: document.getElementById('visitor-code')?.value.trim() || '',
    visitors: people,
    visit_type: document.getElementById('visitor-type')?.value || 'first',
    allow_history: Boolean(document.getElementById('visitor-history')?.checked),
    history_session_id: document.getElementById('visitor-history-session')?.value.trim() || '',
    purpose: document.getElementById('visitor-purpose')?.value.trim() || '',
    focus_topics: String(document.getElementById('visitor-focus')?.value || '').split(/[、,，;；]+/).map((item) => item.trim()).filter(Boolean),
  };
}

async function beginVisitorInsight() {
  const visitor = visitorFormData();
  if (!visitor.company_name) {
    showToast('请先填写公司名称');
    document.getElementById('visitor-company')?.focus();
    return;
  }
  state.visitorInsightBusy = true;
  state.controllerHermesTask = 'visitor-insight';
  render('refresh');
  try {
    state.session = await window.showroomApi.saveVisitor(visitor);
    const contract = `[AI_LAB_CONTROL] 主持人后台备课。请先检索内部 Wiki，再联网核验 ${visitor.company_name} 的公开近期动态。联网时只能使用企业名称与公开业务关键词，不得发送来访人姓名。可见摘要限制在1200个汉字以内：只写客户定位、3条已核验动态、3条待验证假设和3条接待建议；不要输出完整检索过程、长表格或重复背景。末尾必须附带一个严格 JSON 数据块：\n<!-- AI_LAB_VISITOR_INSIGHT_V1 {"customer_positioning":[],"business_structure":[],"recent_actions":[],"verified_facts":[],"structural_tensions":[],"hypotheses":[],"reception_advice":[],"sources":[{"id":"S1","title":"","url":"","date":"","confidence":"high|medium|low"}],"warnings":[]} AI_LAB_VISITOR_INSIGHT_V1 -->\n机器块要求：只允许标准 JSON；所有键和字符串使用英文双引号；字符串内换行必须写成\\n；禁止尾逗号、注释、Markdown代码围栏和省略号占位；每个数组最多5项，sources最多8项。`;
    await window.showroomApi.submitHermesPrompt(contract, {
      skillCommand: 'solution-consultant-persona',
      stationContext: '当前处于主演示主控台的主持人后台备课态。不要进入前台问诊；不要展示工具日志。',
    });
  } catch (error) {
    state.visitorInsightBusy = false;
    state.controllerHermesTask = '';
    const detail = friendlyHermesError(error.message);
    window.showroomApi.saveSession({ data: { customer_insight: { status: 'failed', warnings: [detail] } } }).catch(() => {});
    showToast(`启动洞察失败：${detail}`);
    render('refresh');
  }
}

async function startHostGreeting({ force = false } = {}) {
  if (state.hostGreetingPending || (!force && state.session?.data?.host_greeting_initialized)) return;
  state.hostGreetingPending = true;
  state.controllerHermesTask = 'host-prep';
  state.chatError = '';
  render('refresh');
  try {
    await window.showroomApi.submitHermesPrompt(
      '[AI_LAB_CONTROL] 现在进入主持人备课态。请主动、自然地询问主持人：今天接待哪位客户，以及本次访问最关注什么。不要假装已经知道客户，不要输出工具日志。',
      { skillCommand: 'solution-consultant-persona', stationContext: '主演示主控台；主持人后台备课态。' },
    );
  } catch (error) {
    state.hostGreetingPending = false;
    state.controllerHermesTask = '';
    const detail = friendlyHermesError(error.message);
    state.chatError = detail;
    state.hermesDetail = detail;
    state.hermesStatus = hermesFailureStatus(error.message);
    showToast(`V1.7 启动失败：${detail}`);
    render('refresh');
  }
}

async function failControllerHermesTask(message = '') {
  if (state.view !== 'controller' || state.controllerFailureHandling) return;
  const insightRunning = state.session?.data?.customer_insight?.status === 'running';
  const task = state.controllerHermesTask || (insightRunning ? 'visitor-insight' : (state.hostGreetingPending ? 'host-prep' : ''));
  if (!task) return;
  state.controllerFailureHandling = true;
  const detail = friendlyHermesError(message);
  state.chatError = detail;
  state.hermesDetail = detail;
  state.hermesStatus = hermesFailureStatus(message);
  state.hostGreetingPending = false;
  state.visitorInsightBusy = false;
  state.controllerHermesTask = '';
  try {
    const patch = task === 'visitor-insight'
      ? { customer_insight: { status: 'failed', warnings: [detail] } }
      : { host_greeting_initialized: false };
    state.session = await window.showroomApi.saveSession({ data: patch });
  } catch (_) {
    // The visible error remains actionable even if persistence is temporarily unavailable.
  } finally {
    state.controllerFailureHandling = false;
    render('refresh');
  }
}

async function completeControllerHermesTask(rawAnswer = '') {
  if (state.view !== 'controller') return;
  const task = state.controllerHermesTask;
  state.hostGreetingPending = false;
  state.controllerHermesTask = '';
  if (task === 'host-prep' && !state.session?.data?.host_greeting_initialized) {
    state.session = await window.showroomApi.saveSession({ data: { host_greeting_initialized: true } });
  }
  if (task === 'visitor-insight' && !/AI_LAB_VISITOR_INSIGHT_V1/.test(rawAnswer)) {
    await failControllerHermesTask('洞察回复缺少结构化确认数据，请重新发起洞察。');
  }
}

function currentInsight() {
  return currentSessionData().insight || {};
}

function currentInsightJob() {
  return currentSessionData().insight_job || {};
}

function currentStaffingPlan() {
  return currentSessionData().staffing_plan || {};
}

function insightPlanningPrompt(job, catalog) {
  const demand = currentDemand();
  return `[AI_LAB_CONTROL] 站3需求已由人确认。现在只规划本次深度洞察的AI项目组，不开始检索、不输出解释文字。\n任务ID：${job.job_id}\n需求指纹：${job.source_hash}\n核心问题：${demand.core_problem || ''}\n目标：${demand.target_metric || ''}\n可用角色ID：${Object.keys(catalog?.roles || {}).join('、')}\n请为四个受控角色分别给出贴合本需求的task。不得创建角色、Skill或工具。只返回一个完整机器块：\n<!-- AI_LAB_STAFFING_PLAN_V1 {"schema_version":"1.0","plan_id":"${job.job_id}","demand_hash":"${job.source_hash}","mission":"...","active_stage":"IPD0","squads":[{"stage":"IPD0","objective":"...","status":"planned","employees":[{"employee_id":"researcher","task":"...","status":"waiting"},{"employee_id":"industry-analyst","task":"...","status":"waiting"},{"employee_id":"product-manager","task":"...","status":"waiting"},{"employee_id":"evidence-reviewer","task":"...","status":"waiting"}]}],"workflow_edges":[["researcher","industry-analyst"],["industry-analyst","product-manager"],["researcher","evidence-reviewer"],["product-manager","evidence-reviewer"]]} AI_LAB_STAFFING_PLAN_V1 -->`;
}

function insightExecutionPrompt(job, plan) {
  const demand = currentDemand();
  const completed = (job.completed_sections || []).join('、') || '无';
  return `[AI_LAB_CONTROL] 你现在以已安装的IPD-01市场洞察技能执行概念阶段四维调研，不是通用聊天。不得展示工具日志、查询词或内部推理。\n任务ID：${job.job_id}\n需求指纹：${job.source_hash}\n任务：${plan.mission || demand.core_problem || ''}\n已完成章节：${completed}\n必须尽可能完整覆盖：客户/用户/场景与业务价值；产业趋势、市场空间、政策动态；竞争格局与替代方案；技术趋势、可行性与工作量；与超聚变业务边界、战略及现有产品能力匹配度。优先内部Wiki，关键事实证据不足再联网。所有外部事实必须有URL、日期、置信度。每个字段都必须标记verified、inferred、tbd或not_applicable；不得省略字段。未知时输出{\"status\":\"tbd\",\"reason\":\"缺少什么\",\"owner\":\"由谁补证\",\"action\":\"如何补证\"}，不得用空对象或虚构事实代替。\n按真实进展输出AI_LAB_INSIGHT_STAGE_V1与员工状态块；完成后依次输出summary、root_causes、impacts、evidence章节机器块。不要输出正式建设方案。`;
}

function requirementAnalysisPrompt(job) {
  const demand = currentDemand();
  return `[AI_LAB_CONTROL] 你现在以已安装的IPD-02需求分析技能，基于同一任务已完成的IPD-01调研，形成产品原型前的需求评审输入。\n任务ID：${job.job_id}\n需求指纹：${job.source_hash}\n已确认需求：${demand.core_problem || ''}\n必须完整输出12个概念阶段章节，不得遗漏或留下空对象：需求与001切片；客户用户与价值；产业市场与政策；竞争与替代；技术可行性；战略边界；能力映射；收益风险优先级；四类专项检查；事实假设与访谈；需求评审结论；初始产品包。已有材料能支撑时尽可能填写完整；未知字段统一输出{\"status\":\"tbd\",\"reason\":\"缺少什么\",\"owner\":\"由谁补证\",\"action\":\"如何补证\"}，不得虚构。\n输出recommendation与ipd_handoff章节，并输出concept章节，payload必须包含：demand_trace、customer_user、market、competition、technology、strategic_fit、capability_mapping、assessment、special_checks(cyber/reliability/energy/function_performance)、knowledge_status(facts/inferences/hypotheses/tbds每项含item/owner/action/interview_items)、verdict(decision/rationale/conditions)、initial_product_package(scope/non_goals/components/dependencies/quality_goals)、demo_slice(user/action/input/output/acceptance/dependencies)。每一项标记verified、inferred、tbd或not_applicable。不得输出完整建设方案。最后输出AI_LAB_INSIGHT_V1，sections列出已完成章节。`;
}

function extractInsightEnvelopes(content) {
  const patterns = [
    ['plan', /<!--\s*AI_LAB_STAFFING_PLAN_V1\s*(\{[\s\S]*?\})\s*AI_LAB_STAFFING_PLAN_V1\s*-->/gi],
    ['progress', /<!--\s*AI_LAB_INSIGHT_(?:STAGE|SECTION)_V1\s*(\{[\s\S]*?\})\s*AI_LAB_INSIGHT_(?:STAGE|SECTION)_V1\s*-->/gi],
  ];
  const found = [];
  patterns.forEach(([type, pattern]) => {
    let match;
    while ((match = pattern.exec(content))) {
      try { found.push({ type, payload: JSON.parse(match[1]) }); } catch { /* wait for a valid complete block */ }
    }
  });
  return found;
}

function queueInsightProgress(event) {
  const job = currentInsightJob();
  if (!event?.event_id || insightEventIds.has(event.event_id) || event.job_id !== job.job_id) return;
  insightEventIds.add(event.event_id);
  insightProgressQueue = insightProgressQueue.then(async () => {
    const result = await window.showroomApi.updateInsightProgress(job.job_id, event);
    state.session = result.session;
    if (event.kind === 'section' && event.section === 'summary') startInsightAutoAdvance();
  }).catch((error) => {
    state.chatError = error.message;
    showToast(`洞察进度保存失败：${error.message}`);
  });
}

function processInsightStream(content) {
  extractInsightEnvelopes(content).filter((item) => item.type === 'progress').forEach((item) => queueInsightProgress(item.payload));
}

function clearInsightAutoAdvance() {
  if (insightAutoTimer) window.clearInterval(insightAutoTimer);
  insightAutoTimer = null;
}

function startInsightAutoAdvance() {
  if (state.view !== 'screen-03-team' || state.insightAutoSeconds > 0) return;
  state.insightAutoSeconds = 3;
  clearInsightAutoAdvance();
  insightAutoTimer = window.setInterval(() => {
    if (state.insightAutoPaused || document.hidden) return;
    state.insightAutoSeconds -= 1;
    if (state.insightAutoSeconds <= 0) {
      clearInsightAutoAdvance();
      setView('screen-04');
      return;
    }
    render('refresh');
  }, 1000);
  render('refresh');
}

async function beginInsightExecution(job = currentInsightJob(), plan = currentStaffingPlan()) {
  state.insightTask = 'executing-market';
  state.hermesDetail = 'IPD-01正在开展四维市场洞察';
  await window.showroomApi.submitHermesSkill(insightExecutionPrompt(job, plan), 'ipd-01-market-insight', {
    stationContext: '当前处于003.5与004，只执行IPD0深度洞察、证据核验和001实践交接；不得输出正式建设方案。',
  });
}

async function beginRequirementAnalysis(job = currentInsightJob()) {
  state.insightTask = 'executing-requirement';
  state.hermesDetail = 'IPD-02正在形成需求评审与001实践输入';
  await window.showroomApi.submitHermesSkill(requirementAnalysisPrompt(job), 'ipd-02-requirement-analysis', {
    stationContext: '当前处于004概念阶段，只形成需求评审输入、初始产品包和001最小实践切片；不得开展IPD-03正式产品规划。',
  });
}

function insightAssistantSkill(section, question) {
  if (/市场|竞争|产业|政策|技术|证据|来源|相反/.test(question) || ['concept-market', 'concept-competition', 'concept-technology'].includes(section)) return 'ipd-01-market-insight';
  if (/修改|修正|接纳|评审|产品|能力|专项|风险|收益|优先级|001|缺什么/.test(question) || ['concept-strategy', 'concept-capability', 'concept-assessment', 'concept-checks', 'concept-verdict', 'concept-package'].includes(section)) return 'ipd-02-requirement-analysis';
  return 'solution-consultant-persona';
}

async function ensureInsightFieldCatalog() {
  if (state.insightFieldCatalog.length) return state.insightFieldCatalog;
  try {
    const result = await window.showroomApi.getInsightFieldCatalog();
    state.insightFieldCatalog = result.fields || [];
  } catch (_) {
    state.insightFieldCatalog = Object.entries(INSIGHT_FIELD_SECTIONS).map(([field_id, section]) => ({ field_id, section }));
  }
  return state.insightFieldCatalog;
}

function insightAssistantPrompt(question, request = {}) {
  const insight = currentInsight();
  const review = currentInsightReview();
  const job = currentInsightJob();
  const section = request.targetSection || state.insightSelectedSection || 'summary';
  const selected = request.selectedText ?? state.insightSelectedText;
  const expectedRevision = Boolean(request.expectedRevision);
  const catalog = JSON.stringify(state.insightFieldCatalog).slice(0, 30000);
  return `[AI_LAB_CONTROL] 当前处于004 IPD需求洞察共创台。只解释或修订洞察报告，不修改客户已确认需求，不输出完整建设方案。\n报告版本：${review.version || 'V0.1'}\n任务ID：${job.job_id || ''}\n需求指纹：${review.demand_hash || job.source_hash || ''}\n请求ID：${request.requestId || ''}\n用户当前查看章节（仅作为优先提示，不是硬限制）：${section}\n选中内容：${selected || '无'}\n用户问题：${question}\n前端字段目录：${catalog}\n报告快照：${JSON.stringify(insight).slice(0, 50000)}\n请先正常回答用户，再判断回答中的哪些片段应回填。普通解释只输出可见回答。涉及回填或修改时，从你的可见回答中抽取真正要写入的片段，理解字段目录的业务含义，可跨章节映射，但只能选择目录中存在的字段。随后附带一个隐藏机器块：<!-- AI_LAB_INSIGHT_REVISION_V2 {"schema_version":"2.0","request_id":"${request.requestId || ''}","job_id":"${job.job_id || ''}","demand_hash":"${review.demand_hash || job.source_hash || ''}","base_version":"${review.version || 'V0.1'}","preferred_section":"${section}","intent":"...","extractions":[{"source_excerpt":"回答中应回填的原文","semantic_intent":"内容的业务含义","target_section":"字段目录中的section","target_field":"字段目录中的field_id","value":{},"confidence":0.95,"reason":"映射理由","alternative_targets":[]}],"warnings":[]} AI_LAB_INSIGHT_REVISION_V2 -->。${expectedRevision ? '本轮已由用户明确要求回填，必须生成机器块。' : ''}不要因为用户停留在某一章就把所有内容强塞入该章。客户事实有误时不要生成修订块，要明确建议退回003。回答必须区分事实、推断、假设和TBD；引用外部事实时给出来源、日期与置信度。`;
}

function insightRevisionRepairPrompt(request) {
  const insight = currentInsight();
  const review = currentInsightReview();
  const job = currentInsightJob();
  return `[AI_LAB_CONTROL] 修复上一轮004语义回填协议。不要重复解释，只从上一轮回答中抽取应写入报告的内容。\n用户原始要求：${request.userInstruction}\n优先章节（不是硬限制）：${request.targetSection}\n选中内容：${request.selectedText || '无'}\n请求ID：${request.requestId}\n报告版本：${review.version || request.baseVersion}\n任务ID：${job.job_id || request.jobId}\n需求指纹：${review.demand_hash || job.source_hash || request.demandHash}\n前端字段目录：${JSON.stringify(state.insightFieldCatalog).slice(0, 30000)}\n当前报告：${JSON.stringify(insight).slice(0, 50000)}\n只输出：<!-- AI_LAB_INSIGHT_REVISION_V2 {"schema_version":"2.0","request_id":"${request.requestId}","job_id":"${job.job_id || request.jobId}","demand_hash":"${review.demand_hash || job.source_hash || request.demandHash}","base_version":"${review.version || request.baseVersion}","preferred_section":"${request.targetSection}","intent":"...","extractions":[{"source_excerpt":"应回填原文","semantic_intent":"业务含义","target_section":"目录section","target_field":"目录field_id","value":{},"confidence":0.95,"reason":"...","alternative_targets":[]}],"warnings":[]} AI_LAB_INSIGHT_REVISION_V2 -->`;
}

async function repairInsightRevision(request, { manual = false } = {}) {
  const nextRequest = { ...request, repairAttempt: manual ? 1 : Number(request.repairAttempt || 0) + 1 };
  state.insightActiveRequest = nextRequest;
  state.insightRevisionError = null;
  state.insightAssistantBusy = true;
  state.insightAssistantStatus = manual ? '正在重新生成回填草案' : '正在修复回填数据格式';
  state.streamingReply = '';
  render('refresh');
  const skill = insightAssistantSkill(nextRequest.targetSection, nextRequest.userInstruction);
  await window.showroomApi.submitHermesSkill(insightRevisionRepairPrompt(nextRequest), skill, {
    stationContext: '004洞察共创台协议修复：只补充结构化修订块，不重复可见回答。',
  });
}

async function sendInsightAssistant(question, options = {}) {
  const value = String(question || '').trim();
  if (!value || state.insightAssistantBusy) return;
  const review = currentInsightReview();
  if (review.status === 'confirmed') {
    showToast('该版本已确认锁定，请先发起新版本');
    return;
  }
  const expectedRevision = Boolean(options.forceRevision) || INSIGHT_REVISION_INTENT.test(value);
  await ensureInsightFieldCatalog();
  const job = currentInsightJob();
  const request = {
    requestId: `insight-request-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    userInstruction: value,
    targetSection: state.insightSelectedSection || 'summary',
    selectedText: state.insightSelectedText || '',
    expectedRevision,
    repairAttempt: 0,
    baseVersion: review.version || 'V0.1',
    jobId: job.job_id || '',
    demandHash: review.demand_hash || job.source_hash || '',
  };
  state.insightActiveRequest = request;
  state.insightRevisionError = null;
  state.insightAssistantMessages.push({ role: 'user', content: value });
  state.insightAssistantBusy = true;
  state.insightAssistantStatus = /证据|来源|核验|相反/.test(value) ? '正在核验证据' : expectedRevision ? '正在形成回填草案' : '正在读取报告';
  state.streamingReply = '';
  render('refresh');
  const skill = insightAssistantSkill(state.insightSelectedSection, value);
  try {
    await window.showroomApi.submitHermesSkill(insightAssistantPrompt(value, request), skill, {
      stationContext: '004洞察共创台：IPD-01负责市场事实，IPD-02负责需求评审，V1.7只负责编排解释。所有修改先生成差异预览。',
    });
  } catch (error) {
    state.insightAssistantBusy = false;
    state.insightAssistantStatus = '';
    state.insightActiveRequest = null;
    showToast(`洞察助手暂不可用：${error.message}`);
    render('refresh');
  }
}

async function runInsightReviewTask(result) {
  state.session = result.session || state.session;
  state.insightReviewTaskId = result.task?.task_id || state.insightReviewTaskId;
  state.insightReviewRunning = true;
  const gate = state.session?.data?.insight_review_gate;
  if (gate) {
    gate.status = 'reviewing';
    (gate.ai_reviewers || []).forEach((reviewer, index) => { reviewer.status = index === 0 ? 'working' : 'waiting'; });
  }
  state.hermesStatus = 'generating';
  state.hermesDetail = 'AI概念评审会正在会签';
  render('refresh');
  await window.showroomApi.submitHermesSkill(result.review_prompt, 'ipd-02-requirement-analysis', {
    stationContext: '004 AI概念预审：由Supervision角色独立审查，不冒充真人签字；只返回受控评审结论。',
  });
}

async function completeInsightAssistantRequest(rawAnswer, visibleAnswer) {
  const request = state.insightActiveRequest;
  if (!request) {
    state.insightAssistantBusy = false;
    state.insightAssistantStatus = '';
    if (visibleAnswer) state.insightAssistantMessages.push({ role: 'assistant', content: visibleAnswer });
    render('refresh');
    return;
  }
  if (visibleAnswer && !request.repairAttempt) {
    state.insightAssistantMessages.push({ role: 'assistant', content: visibleAnswer });
  }
  state.streamingReply = '';
  state.insightAssistantStatus = request.expectedRevision ? '正在校验回填草案' : '正在确认本轮处理结果';
  render('refresh');
  try {
    const result = await window.showroomApi.extractInsightRevision(rawAnswer, request);
    if (result.result_type === 'revision_ready' && result.revision) {
      state.session = result.session;
      state.insightPendingRevision = result.revision;
      state.insightRevisionError = null;
      state.insightActiveRequest = null;
      state.insightAssistantBusy = false;
      state.insightAssistantStatus = '';
      state.hermesStatus = 'online';
      showToast('回填草案已生成，请确认差异后应用');
      render('refresh');
      return;
    }
    if (result.result_type === 'placement_required') {
      state.insightPlacementCandidates = result.placement_candidates || [];
      state.insightActiveRequest = request;
      state.insightAssistantBusy = false;
      state.insightAssistantStatus = '';
      state.hermesStatus = 'online';
      showToast('AI已找到回填内容，请确认填写位置');
      render('refresh');
      return;
    }
    if (result.result_type === 'repair_required') {
      if (Number(request.repairAttempt || 0) < 1) {
        await repairInsightRevision(request);
        return;
      }
      state.insightRevisionError = {
        message: result.message || 'AI已给出说明，但尚未形成可回填草案',
        request,
      };
    }
    state.insightAssistantBusy = false;
    state.insightAssistantStatus = '';
    state.insightActiveRequest = result.result_type === 'repair_required' ? request : null;
    state.hermesStatus = 'online';
    render('refresh');
  } catch (error) {
    state.insightAssistantBusy = false;
    state.insightAssistantStatus = '';
    state.insightRevisionError = { message: error.message, request };
    state.insightActiveRequest = request;
    showToast(`回填草案校验失败：${error.message}`);
    render('refresh');
  }
}

function focusAppliedInsightSections(revision, result) {
  const sections = new Set(result?.affected_sections || []);
  if (revision?.target_section) sections.add(revision.target_section);
  (result?.changed_fields || revision?.changes?.map((change) => change.field) || [])
    .map((field) => INSIGHT_FIELD_SECTIONS[field])
    .filter(Boolean)
    .forEach((section) => sections.add(section));
  const validSections = [...sections].filter((section) => document.getElementById(section));
  state.insightHighlightedSections = validSections;
  render('refresh');
  window.requestAnimationFrame(() => {
    const target = document.getElementById(validSections[0]);
    target?.scrollIntoView({ behavior: motionSystem.reduceMotion ? 'auto' : 'smooth', block: 'center' });
    window.setTimeout(() => {
      validSections.forEach((section) => document.getElementById(section)?.classList.remove('insight-just-filled'));
      state.insightHighlightedSections = [];
    }, 2400);
  });
}

async function beginInsightFlow(demand) {
  state.session = await window.showroomApi.confirmDemand(demand);
  const result = await window.showroomApi.startInsightJob();
  state.session = result.session;
  state.insightCatalog = result.catalog;
  setView('screen-03-team');
  const job = result.job || {};
  if (job.status === 'completed') {
    startInsightAutoAdvance();
    return;
  }
  startInsightServerPolling();
}

function stopInsightServerPolling() {
  if (insightServerPollTimer) window.clearInterval(insightServerPollTimer);
  insightServerPollTimer = null;
}

async function pollInsightServerJob() {
  const job = currentInsightJob();
  if (!job.job_id || !job.execution_id || !['screen-03-team', 'screen-04'].includes(state.view)) return;
  try {
    const result = await window.showroomApi.getInsightJob(job.job_id);
    state.session = result.session;
    const refreshed = result.job || {};
    if ((refreshed.completed_sections || []).includes('summary') && state.view === 'screen-03-team') startInsightAutoAdvance();
    if (['completed', 'failed', 'interrupted', 'superseded'].includes(refreshed.status)) stopInsightServerPolling();
    render('refresh');
  } catch (error) {
    state.chatError = `读取服务端洞察进度失败：${error.message}`;
    render('refresh');
  }
}

function startInsightServerPolling() {
  stopInsightServerPolling();
  pollInsightServerJob();
  insightServerPollTimer = window.setInterval(pollInsightServerJob, 2000);
}

function currentPrototype() {
  return currentSessionData().prototype || {};
}

function hydrateContent(content = {}) {
  state.content = content;
  if (Array.isArray(content.navigation)) viewGroups.splice(0, viewGroups.length, ...content.navigation);
  if (content.views) {
    Object.keys(viewMeta).forEach((key) => delete viewMeta[key]);
    Object.assign(viewMeta, content.views);
    viewMeta['screen-03-team'] ||= ['AI 项目组集结', 'SCREEN 003.5 / STAFFING', '1920 × 1080'];
  }
  if (Array.isArray(content.stages)) stages.splice(0, stages.length, ...content.stages);
  if (Array.isArray(content.ipd_phases)) ipdPhases.splice(0, ipdPhases.length, ...content.ipd_phases);
  if (content.base_agents) {
    Object.keys(baseAgents).forEach((key) => delete baseAgents[key]);
    Object.assign(baseAgents, content.base_agents);
  }
  if (content.reviewers) {
    Object.keys(humanReviewers).forEach((key) => delete humanReviewers[key]);
    Object.assign(humanReviewers, content.reviewers);
  }
  if (content.artifacts) {
    Object.keys(artifactDescriptions).forEach((key) => delete artifactDescriptions[key]);
    Object.keys(artifactOwners).forEach((key) => delete artifactOwners[key]);
    Object.entries(content.artifacts).forEach(([title, artifact]) => {
      artifactDescriptions[title] = artifact.summary || '';
      if (artifact.owner) artifactOwners[title] = artifact.owner;
    });
  }
  if (Array.isArray(content.experience?.labels)) {
    experienceSteps.splice(0, experienceSteps.length, ...content.experience.labels);
  }
}

function getReviewState(gate) {
  return state.reviewStates[gate] || 'pending';
}

function approvalRouteBar(phase, giant = false) {
  const approved = phase.reviews.filter((gate) => getReviewState(gate) === 'approved').length;
  const nextGate = phase.reviews.find((gate) => getReviewState(gate) !== 'approved') || phase.reviews.at(-1);
  const reviewer = humanReviewers[nextGate] || humanReviewers.TR1;
  const channel = state.capabilities.feishu_configured ? '飞书自动派审批' : '平台审批（飞书待配置）';
  return `<div class="approval-route ${giant ? 'giant-approval-route' : ''}"><div class="approval-principle"><span>AI WORK</span><b>AI 负责产出</b><i>→</i><span>REVIEW</span><b>${channel}</b><i>→</i><span>HUMAN</span><b>人负责评审确认</b></div><button data-review-gate="${nextGate}"><span class="feishu-mark">飞</span><div><small>下一人工关口 · ${nextGate}</small><b>${reviewer.role} · ${reviewer.person}</b></div><em>${approved}/${phase.reviews.length} 已通过　打开审批</em></button></div>`;
}

function feishuReviewOverlay() {
  if (!state.activeReview) return '';
  const gate = state.activeReview;
  const reviewer = humanReviewers[gate] || humanReviewers.TR1;
  const status = getReviewState(gate);
  const detail = reviewStatus[status];
  const phase = ipdPhases.find((item) => item.reviews.includes(gate)) || ipdPhases[state.selectedPhase];
  const decisionMode = status === 'pending';
  return `<div class="review-overlay" role="dialog" aria-modal="true" aria-label="${gate} 人工审批"><div class="feishu-review"><header><div class="feishu-brand"><span class="feishu-mark">飞</span><div><small>${state.capabilities.feishu_configured ? 'FEISHU APPROVAL' : 'PLATFORM APPROVAL · FEISHU PENDING'} · IPD 人工关口</small><b>${gate} ${gate.startsWith('TR') ? '技术评审' : '决策评审'}</b></div></div><span class="review-status ${detail[1]}">${detail[0]}</span><button data-review-close aria-label="关闭审批">${icon('close')}</button></header><div class="feishu-review-grid"><aside><div class="reviewer-avatar">${reviewer.person.slice(0, 1)}</div><span>审批人映射</span><h3>${reviewer.person}</h3><b>${reviewer.role}</b><small>${reviewer.group}</small><dl><div><dt>评审重点</dt><dd>${reviewer.focus}</dd></div><div><dt>来自阶段</dt><dd>0${ipdPhases.indexOf(phase) + 1} · ${phase.name}</dd></div><div><dt>响应时限</dt><dd>24 小时内</dd></div></dl></aside><main><div class="feishu-message"><div class="bot-avatar">AI</div><div><span>AI Lab IPD 助手　刚刚</span><p>AI 已完成 <b>${phase.name}阶段</b> 的交付件生产，请对 <b>${gate}</b> 关口进行人工评审。</p></div></div><section class="review-package"><header><span>待审材料包</span><em>${phase.outputs.length} 个交付件</em></header>${phase.outputs.map((output, i) => `<button data-artifact-from-review="${output}"><span>0${i + 1}</span><div><b>${output}</b><small>${artifactDescriptions[output]}</small></div><em>预览 ↗</em></button>`).join('')}</section>${decisionMode ? `<section class="review-decision"><span>请选择评审结论</span><div><button class="approve ${state.reviewDecision === 'approved' ? 'active' : ''}" data-review-decision="approved"><i>✓</i><b>通过</b><small>允许进入下一关口</small></button><button class="change ${state.reviewDecision === 'changes' ? 'active' : ''}" data-review-decision="changes"><i>↻</i><b>要求修改</b><small>退回 AI 补充后复审</small></button><button class="reject ${state.reviewDecision === 'rejected' ? 'active' : ''}" data-review-decision="rejected"><i>×</i><b>拒绝</b><small>终止当前方案</small></button></div><label for="review-comment">审批意见</label><textarea id="review-comment" placeholder="请说明通过依据，或需要修改/拒绝的原因…"></textarea><button class="review-submit" data-review-submit>确认提交审批</button></section>` : `<section class="review-result ${detail[1]}"><span>${detail[0]}</span><h3>${status === 'approved' ? '人工评审已完成，结论已写入 IPD 单据链。' : status === 'changes' ? '材料已退回 AI，等待修订。' : '当前方案已被人工拒绝。'}</h3><p>审批人：${reviewer.person} · 全程可追溯</p>${status !== 'approved' ? '<button data-review-resubmit>重新提交</button>' : '<button data-review-close>完成</button>'}</section>`}</main></div></div></div>`;
}

const artifactDescriptions = {
  '需求确认单': '把现场对话收敛为问题、目标、用户、范围与约束，作为整个 IPD 流程的唯一需求入口。',
  '客户痛点': '记录客户原话、业务影响、关键用户和现场证据，形成可追溯的问题定义。',
  '产品战略边界': '明确首期覆盖范围、非目标、依赖条件与不可触碰的业务红线。',
  '需求合理性·调研支撑': '从客户、市场、竞品与产业四个维度证明问题真实且值得投入。',
  '需求评审结论': '形成建议产品、条件接纳或拒绝的正式判断，并列出进入下一阶段的前置条件。',
  '初始产品包': '根据已确认需求定义软件、服务、数据与验证活动的组合交付。',
  '产品组合规划书': '说明该产品与现有智能制造能力的组合关系、投资顺序和版本节奏。',
  '产品包定义': '定义用户可感知的功能、服务、实施边界、成功标准与商业承诺。',
  '架构方案': '把已确认需求映射为组件、数据流、接口、异常策略和知识沉淀架构。',
  '资源与财务计划': '列出人力、算力、现场资源、预算与收益假设，供 PDCP 做正式承诺。',
  '开发方案': '把产品包拆成可执行的模块、里程碑、依赖、风险和工程任务。',
  '56 项可测验收': '用可观察、可测量、可复现的条目约束交付，避免“看起来完成”。',
  '实现规格': '细化模块、接口、数据字典、异常处理、权限和审计要求。',
  'SDV/SIT 方案': '定义单系统设计验证和系统集成测试的用例、环境、阈值及追溯关系。',
  '验证方案': '覆盖功能、性能、客户现场、制造适配和可靠性验证。',
  'BETA 反馈': '汇总班组长与新员工的实操反馈、问题严重度和关闭计划。',
  '合规评审意见': '独立检查数据安全、隐私、网络安全及行业合规红线。',
  '发布风险清单': '列出上市前未关闭风险、影响范围、责任人、缓解措施与接受条件。',
  '上市方案': '定义目标客户、首发场景、发布节奏、渠道和成功指标。',
  '量产准备清单': '核对交付、安装、运维、培训、供应和服务能力是否就绪。',
  '营销衔接方案': '将验证证据转化为可公开、可追溯且不越过合规边界的市场表达。',
  '维护移交包': '把版本、缺陷、监控、服务手册和责任界面移交给维护团队。',
  '生命周期看板': '持续观察采用率、业务价值、质量、服务成本和产品健康度。',
  '版本路线图': '根据运营证据规划增强版本、兼容策略和资源投入。',
  '退出计划': '定义停产、停售、停服的通知、数据迁移、备件和客户保障。',
  '知识回流': '将现场数据、复盘结论和客户反馈重新沉淀到需求与产品知识库。',
};

const artifactOwners = {
  '需求合理性·调研支撑': 'IPD-01', '需求评审结论': 'IPD-02', '初始产品包': 'IPD-02',
  '产品组合规划书': 'IPD-03', '产品包定义': 'IPD-03', '架构方案': 'IPD-04', '资源与财务计划': 'IPD-03',
  '开发方案': 'IPD-05', '56 项可测验收': 'IPD-05', '实现规格': 'IPD-06', 'SDV/SIT 方案': 'IPD-07',
  '验证方案': 'IPD-08', 'BETA 反馈': 'IPD-08', '合规评审意见': 'IPD-09', '发布风险清单': 'IPD-09',
  '上市方案': 'IPD-10', '量产准备清单': 'IPD-10', '营销衔接方案': 'IPD-11', '维护移交包': 'IPD-10',
  '生命周期看板': 'IPD-12', '版本路线图': 'IPD-12', '退出计划': 'IPD-12', '知识回流': 'IPD-12',
};

function findArtifactPhase(title) {
  const index = ipdPhases.findIndex((phase) => phase.inputs.includes(title) || phase.outputs.includes(title));
  return { index: index < 0 ? state.selectedPhase : index, phase: ipdPhases[index < 0 ? state.selectedPhase : index] };
}

function artifactKind(title) {
  if (/架构|实现规格|开发方案|SDV|SIT/.test(title)) return 'architecture';
  if (/规划|路线图|上市方案|营销/.test(title)) return 'roadmap';
  if (/验收|验证|清单|评审|风险|退出|移交/.test(title)) return 'checklist';
  if (/财务|看板/.test(title)) return 'metrics';
  if (/BETA|客户痛点/.test(title)) return 'feedback';
  return 'document';
}

function getArtifactDetail(title) {
  const { index, phase } = findArtifactPhase(title);
  const manifest = state.content?.artifacts?.[title] || {};
  const saved = currentSessionData().artifacts?.[title] || {};
  const demand = currentDemand();
  const demandBacked = ['需求确认单', '客户痛点', '产品战略边界'].includes(title) && demand.confirmed;
  const content = saved.content || (demandBacked ? {
    demand: demand.core_problem,
    target: demand.target_metric,
    sources: currentInsight().sources || [],
  } : manifest.content || {});
  const ownerId = manifest.owner || artifactOwners[title];
  const owner = phase.agents.find((agent) => agent.id === ownerId) || phase.agents[0];
  return {
    title,
    phase,
    phaseIndex: index,
    kind: manifest.kind || artifactKind(title),
    summary: saved.content?.summary || (demandBacked ? demand.core_problem : '') || manifest.summary || artifactDescriptions[title] || `这是${phase.name}阶段形成的结构化交付件。`,
    content,
    generated: demandBacked || Boolean(saved.updated_at && saved.content && Object.keys(saved.content).length),
    owner,
  };
}

function artifactVisual(detail) {
  const demand = currentDemand();
  const problem = detail.content.demand || demand.core_problem || '待确认';
  const target = detail.content.target || demand.target_metric || '待确认';
  const cycle = demand.cycle || '待确认';
  const users = demand.users || '待确认';
  const sourceCount = Array.isArray(detail.content.sources) ? detail.content.sources.length : 0;
  if (detail.kind === 'architecture') return `<div class="architecture-demo"><div><span>01</span><b>需求输入</b><small>${escapeHtml(problem)}</small></div><i>→</i><div><span>02</span><b>方案编排</b><small>组件 · 数据流 · 接口</small></div><i>→</i><div><span>03</span><b>证据闭环</b><small>规格 · 测试 · 追溯</small></div></div><div class="artifact-spec-grid"><div><span>目标锚点</span><b>${escapeHtml(target)}</b></div><div><span>关键用户</span><b>${escapeHtml(users)}</b></div><div><span>证据来源</span><b>${sourceCount} 条知识证据</b></div></div>`;
  if (detail.kind === 'roadmap') return `<div class="artifact-roadmap"><div><span>阶段 1</span><b>范围确认</b><small>${escapeHtml(problem)}</small></div><div><span>阶段 2</span><b>原型验证</b><small>${escapeHtml(target)}</small></div><div><span>阶段 3</span><b>用户验证</b><small>${escapeHtml(users)}</small></div><div><span>决策门</span><b>人工评审</b><small>${escapeHtml(cycle)}</small></div></div>`;
  if (detail.kind === 'checklist') return `<div class="artifact-checks"><div><i>1</i><span><b>问题定义</b><small>${escapeHtml(problem)}</small></span><em>待评审</em></div><div><i>2</i><span><b>目标指标</b><small>${escapeHtml(target)}</small></span><em>待评审</em></div><div><i>3</i><span><b>用户与范围</b><small>${escapeHtml(users)} · ${escapeHtml(cycle)}</small></span><em class="warn">待补证</em></div><div><i>4</i><span><b>数据来源可追溯</b><small>${sourceCount} 条证据已绑定</small></span><em>待评审</em></div></div>`;
  if (detail.kind === 'metrics') return `<div class="artifact-metrics"><div><span>目标指标</span><b>${escapeHtml(target)}</b><small>来自需求确认单</small></div><div><span>首期周期</span><b>${escapeHtml(cycle)}</b><small>待人工确认</small></div><div><span>知识证据</span><b>${sourceCount}</b><small>已绑定来源</small></div></div><div class="artifact-bars"><span style="--w:${Math.max(4, Number(demand.completeness || 0))}%">需求完整度 <b>${Number(demand.completeness || 0)}%</b></span></div>`;
  if (detail.kind === 'feedback') return `<div class="artifact-feedback"><blockquote>尚未采集真实 BETA 用户反馈。<span>等待用户验证阶段回填</span></blockquote></div>`;
  return `<div class="artifact-document-figure" role="img" aria-label="需求从现场问题收敛到决策建议的关系图"><div><small>现场问题</small><b>已确认</b><span>${escapeHtml(problem)}</span></div><i>→</i><div><small>业务目标</small><b>${escapeHtml(target)}</b><span>${escapeHtml(cycle)}</span></div><i>→</i><div><small>下一关口</small><b>${escapeHtml(detail.phase.reviews[0])}</b><span>等待人工评审</span></div></div>`;
}

function artifactTableRows(detail) {
  const demand = currentDemand();
  const sources = Array.isArray(detail.content.sources) ? detail.content.sources : [];
  const rows = [
    ['REQ-01', '核心问题', detail.content.demand || demand.core_problem || '待确认', demand.confirmed ? '已确认' : '待确认'],
    ['REQ-02', '目标指标', detail.content.target || demand.target_metric || '待确认', '待评审'],
    ['REQ-03', '关键用户 / 周期', `${demand.users || '待确认'} / ${demand.cycle || '待确认'}`, '待评审'],
  ];
  sources.slice(0, 3).forEach((source, index) => rows.push([`E-${String(index + 1).padStart(2, '0')}`, source.title || source.path || '知识证据', source.path || '已绑定', `相关度 ${source.score ?? '—'}`]));
  return rows;
}

function artifactDemo(detail, giant = false) {
  const cls = giant ? ' artifact-demo-giant' : '';
  if (!detail.generated) return `<div class="artifact-empty-state"><span>尚未生成</span><b>${escapeHtml(detail.title)}还没有真实业务内容</b><p>请先完成需求确认，再由当前 IPD 阶段生成交付件。系统不会用演示模板冒充用户结果。</p></div>`;
  const rows = artifactTableRows(detail);
  const recommendation = currentDemand().next_action || '补齐缺失证据后再提交人工评审';
  const sourceLabels = ['需求确认单', ...(detail.content.sources || []).slice(0, 2).map((source) => source.title || source.path).filter(Boolean)];
  return `<article class="artifact-demo markdown-report${cls}">
    <div class="report-format-bar"><span>MARKDOWN REPORT</span><b>图文混排 · 自动生成目录 · 可导出 Word / PDF</b></div>
    <section class="report-copy"><span class="report-anchor">01 · 摘要</span><h3>${escapeHtml(detail.title)}</h3><p>${escapeHtml(detail.summary)}</p><blockquote>下一步建议：${escapeHtml(recommendation)}</blockquote></section>
    <figure class="report-figure"><div class="report-figure-head"><span>FIGURE 01</span><b>${detail.kind === 'feedback' ? '用户反馈与优先级' : detail.kind === 'roadmap' ? '阶段路线与关键里程碑' : detail.kind === 'metrics' ? '核心指标与目标差距' : '方案关键结构与证据关系'}</b></div>${artifactVisual(detail)}<figcaption>图 1 · 内容来自当前会话已绑定的需求与证据；最终结论需由人工评审确认。</figcaption></figure>
    <section class="report-copy"><span class="report-anchor">02 · 证据明细</span><h3>结论如何被数据支撑</h3><p>以下表格保留来源、状态和可信度，方便评审人从摘要直接追溯到证据，而不必阅读整段生成过程。</p></section>
    <div class="report-table-wrap"><table class="report-table"><thead><tr><th>编号</th><th>证据 / 指标</th><th>当前结果</th><th>状态 / 目标</th></tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell, i) => `<${i === 0 ? 'th' : 'td'}>${escapeHtml(cell)}</${i === 0 ? 'th' : 'td'}>`).join('')}</tr>`).join('')}</tbody></table></div>
    <aside class="report-callout"><span>AI 建议</span><b>补齐缺失证据后，提交 ${detail.phase.reviews[0]} 人工评审</b><p>AI 负责生产和修订材料，人负责判断是否通过、退回修改或拒绝。</p></aside>
    <footer class="report-sources"><b>参考来源</b><span>${sourceLabels.map((source, index) => `[${index + 1}] ${escapeHtml(source)}`).join('　')}</span></footer>
  </article>`;
}

function artifactOverlay() {
  if (!state.artifactOpen || !state.selectedArtifact) return '';
  const detail = getArtifactDetail(state.selectedArtifact);
  return `<div class="artifact-overlay" data-artifact-overlay role="dialog" aria-modal="true" aria-label="${detail.title}交付件预览"><div class="artifact-modal"><header><div><span>IPD DELIVERABLE · 0${detail.phaseIndex + 1} ${detail.phase.name}</span><h2>${detail.title}</h2></div><button data-artifact-close aria-label="关闭交付件">${icon('close')}</button></header><div class="artifact-modal-grid"><aside><div class="artifact-file-icon">${detail.title.slice(0, 2)}</div><span>当前版本</span><b>V0.${detail.phaseIndex + 1} · 演示数据</b><span>主责角色</span><b>${detail.owner.id} ${detail.owner.name}</b><span>基础 Agent</span><b>${detail.owner.base} · ${baseAgents[detail.owner.base].verb}</b><div class="artifact-source"><i></i><p>Markdown 被拆成段落、图片、图表与表格内容块；正式版可同步导出 Word / PDF。</p></div></aside><main><p>${detail.summary}</p>${artifactDemo(detail)}</main><section class="artifact-actions"><span>如何生成</span><div class="base-agent-chain"><div><b>Main</b><small>检索知识<br>生成初稿</small></div><i>→</i><div><b>Supervision</b><small>质询证据<br>控制门禁</small></div><i>→</i><div><b>Coder</b><small>批准后<br>工程落实</small></div></div><button class="artifact-explain" data-artifact-explain>让 AI 数字人解释</button><button class="artifact-project" data-artifact-project>${icon('display')}投到 06 主屏</button><small>现场用户看到的是结论、证据和交付件，不展示内部执行日志。</small></section></div></div></div>`;
}

function assistantDock() {
  const context = state.selectedArtifact || `${ipdPhases[state.selectedPhase].name}阶段`;
  if (!state.assistantOpen) return `<button class="assistant-trigger" data-assistant-toggle aria-label="打开 AI 数字人讲解"><span class="mini-human"><i></i></span><span><small>选中内容后问我</small><b>${context}</b></span><em>⌘ K</em></button>`;
  const question = state.assistantQuestion || `请用一句话解释“${context}”对客户有什么价值。`;
  return `<section class="assistant-panel ${state.avatarSpeaking ? 'speaking' : ''}" aria-label="AI 数字人讲解"><header><div><span class="ai-badge">AI 数字人</span><b>小融 · IPD 讲解员</b></div><button data-assistant-close aria-label="关闭讲解">${icon('close')}</button></header><div class="selected-context"><span>已选内容</span><b>${context}</b></div>${state.avatarSpeaking ? `<div class="digital-human"><div class="human-stage"><div class="human-orbit"></div><div class="human-head"><i></i><i></i><b></b></div><div class="sound-wave"><i></i><i></i><i></i><i></i></div></div><div class="subtitle-card" role="status" aria-live="polite"><span>AI GENERATED · 讲解字幕</span><p>${escapeHtml(state.assistantAnswer || getArtifactDetail(context).summary)}</p><small>${state.backendStatus === 'online' ? '回答来自 AI Lab Platform 知识服务' : '当前使用本地内容兜底'}</small></div></div>` : `<div class="query-starters"><button data-assistant-query="这份内容解决了什么问题？">它解决什么问题？</button><button data-assistant-query="为什么由这些 Agent 协作完成？">Agent 为什么这样分工？</button><button data-assistant-query="进入下一阶段前还缺什么证据？">还缺什么证据？</button></div>`}<div class="assistant-composer"><input id="assistant-input" value="${escapeHtml(question)}" aria-label="向 AI 数字人提问"><button data-assistant-send aria-label="发送问题">${icon('send')}</button></div><footer><span>回答基于当前交付件与 AI Lab 知识库</span><button data-avatar-call>${state.avatarSpeaking ? '停止讲解' : '唤出数字人'}</button></footer></section>`;
}

const icons = {
  pause: '<path d="M9 5v14M15 5v14"/>',
  play: '<path d="m8 5 11 7-11 7z"/>',
  arrow: '<path d="M5 12h14M14 7l5 5-5 5"/>',
  display: '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  send: '<path d="m4 4 17 8-17 8 3-8zM7 12h14"/>',
  stop: '<rect x="7" y="7" width="10" height="10" rx="1"/>',
};

function icon(name) {
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.arrow}</svg>`;
}

function initIcons(root = document) {
  root.querySelectorAll('[data-icon]').forEach((node) => { node.innerHTML = icon(node.dataset.icon); });
}

function buildNavigation() {
  document.getElementById('view-nav').innerHTML = viewGroups.map((group) => `
    <p class="nav-section">${group.label}</p>
    ${group.items.map((item) => `
      <button class="nav-button ${item.experience ? 'experience' : ''} ${item.id === state.view ? 'active' : ''}" data-view="${item.id}" ${item.id === state.view ? 'aria-current="page"' : ''}>
        <span class="nav-number">${item.number}</span>
        <span><b>${item.name}</b><small>${item.sub}</small></span>
      </button>
    `).join('')}
  `).join('');

  document.querySelectorAll('.nav-button').forEach((button) => {
    button.addEventListener('click', () => setView(button.dataset.view));
  });
}

function buildTourSteps() {
  document.getElementById('tour-steps').innerHTML = stages.map((stage, index) => `
    <button class="tour-step ${index < state.stage ? 'done' : ''} ${index === state.stage ? 'active' : ''}" data-stage="${index}" aria-label="切换到${stage[0]}：${stage[1]}">
      <i></i>${stage[0]} · ${stage[1]}
    </button>
  `).join('');
  document.getElementById('stage-name').textContent = `${stages[state.stage][0]} · ${stages[state.stage][1]}`;
  document.querySelectorAll('.tour-step').forEach((button) => {
    button.addEventListener('click', () => commitTourStage(Number(button.dataset.stage)));
  });
}

function screenHeader(title, status = '现场联机') {
  const sessionLabel = isStaticDisplayView() && !state.bootstrapped
    ? 'DISPLAY MODE'
    : (state.session?.session_id || 'SESSION CONNECTING');
  return `<header class="screen-header">
    <div class="screen-brand"><i></i>AI LAB · ${title}</div>
    <div class="screen-state"><span>${escapeHtml(sessionLabel)}</span><b>${status}</b><span>${escapeHtml(state.content?.venue || '共创体验中心')}</span></div>
  </header>`;
}

function controllerView() {
  const screenNames = state.screenConfigs.map((screen) => screen.title).slice(0, 9);
  const centers = Array.from({ length: 5 }, (_, index) => {
    const live = state.centers.find((center) => Number(center.slot) === index + 1);
    return live || { slot: String(index + 1), role: '—', step: 0, status: 'idle' };
  });
  const visitor = state.session?.data?.visitor || {};
  const insight = state.session?.data?.customer_insight || {};
  const persona = state.session?.data?.persona_skill_version || state.capabilities?.persona_skill_version || '—';
  const hostMessages = state.chatMessages.filter((message) => message.role === 'assistant').slice(-3);
  const insightReady = ['completed', 'partial'].includes(insight.status);
  const hostError = ['error', 'quota-required'].includes(state.hermesStatus);
  const summary = insight.summary || {};
  const focus = (visitor.focus_topics || []).join('、');
  const people = (visitor.visitors || []).map((person) => `${person.name || ''}${person.title ? ` / ${person.title}` : ''}`).join('；');
  return `<div class="screen">
    ${screenHeader('TOUR CONTROL', `V${escapeHtml(persona)} · ${escapeHtml(visitor.status || '待录入')}`)}
    <div class="screen-content control-grid visitor-control-grid">
      <section class="panel control-hero">
        <p class="kicker">TODAY'S LIVE TOUR · ${stages[state.stage][0]}</p>
        <h2 class="hero-title">${visitor.company_name ? `正在为 <em>${escapeHtml(visitor.company_name)}</em><br>准备一场有背景的共创。` : '先认识来访客户，<br>再开始一场<em>有准备的共创。</em>'}</h2>
        <div class="visitor-session-bar"><span>当前客户 <b>${escapeHtml(visitor.company_name || '待录入')}</b></span><span>客户代码 <b>${escapeHtml(visitor.customer_code || '—')}</b></span><span>Session <b>${escapeHtml(state.session?.session_id || '—')}</b></span><button data-visit-complete ${visitor.company_name || state.visitCompleteNotice ? '' : 'disabled'}>结束本次接待</button></div>
        <div class="route-strip">${stages.map((s, i) => `<div class="route-card ${i === state.stage ? 'active' : ''}"><b>${s[0]} · ${s[1]}</b><span>${i < state.stage ? '已完成' : i === state.stage ? '正在进行' : '等待进入'}</span></div>`).join('')}</div>
      </section>
      <section class="panel visitor-workbench">
        <div class="panel-head"><div><strong>来访客户洞察</strong><small>内部 Wiki 优先 · 公开网络仅核验企业信息</small></div><span class="status ${insight.status === 'failed' ? 'error' : ''}">${escapeHtml(insight.status === 'running' ? '洞察中' : insightReady ? '准备完成' : '待录入')}</span></div>
        <div class="visitor-form-grid">
          <label class="field wide">公司名称 <em class="required-mark">必填</em><input id="visitor-company" value="${escapeHtml(visitor.company_name || '')}" placeholder="例如：超聚变数字技术有限公司" required></label>
          <label class="field">客户代码<input id="visitor-code" value="${escapeHtml(visitor.customer_code || '')}" placeholder="自动生成，可编辑"></label>
          <label class="field">首次 / 复访<select id="visitor-type"><option value="first" ${visitor.visit_type !== 'return' ? 'selected' : ''}>首次来访</option><option value="return" ${visitor.visit_type === 'return' ? 'selected' : ''}>复访</option></select></label>
          <label class="field wide">来访人 / 职务<input id="visitor-people" value="${escapeHtml(people)}" placeholder="张三 / CTO；李四 / 架构负责人"></label>
          <label class="field wide">访问目的<textarea id="visitor-purpose" placeholder="这次希望共同解决什么？">${escapeHtml(visitor.purpose || '')}</textarea></label>
          <label class="field wide">关注方向<input id="visitor-focus" value="${escapeHtml(focus)}" placeholder="算力运营、Agent 编排、IPD"></label>
          <label class="visitor-history"><input type="checkbox" id="visitor-history" ${visitor.allow_history ? 'checked' : ''}> 复访时允许读取指定历史 Session</label>
          <label class="field wide visitor-history-session ${visitor.allow_history ? '' : 'is-hidden'}">历史 Session ID<input id="visitor-history-session" value="${escapeHtml(visitor.history_session_id || '')}" placeholder="必须精确选择已归档 Session"></label>
        </div>
        ${insight.status === 'failed' && insight.warnings?.length ? `<div class="controller-error"><b>本次洞察未完成</b><span>${escapeHtml(insight.warnings.at(-1))}</span></div>` : ''}
        <button class="form-cta visitor-insight-cta" data-visitor-insight ${state.visitorInsightBusy || insight.status === 'running' ? 'disabled' : ''}>${state.visitorInsightBusy || insight.status === 'running' ? 'V1.7 正在洞察…' : '再次洞察'}</button>
      </section>
      <section class="panel host-prep-panel">
        <div class="panel-head"><div><strong>V1.7 主持人备课</strong><small>真实 Hermes 会话 · 不展示工具日志</small></div><span class="status ${hostError ? 'error' : ''}" data-hermes-status-indicator data-hermes-status="${escapeHtml(state.hermesStatus)}">${escapeHtml(architectStatusLabel())}</span></div>
        ${hostError ? `<div class="controller-error"><b>${state.hermesStatus === 'quota-required' ? '模型服务额度不足' : '本轮备课未完成'}</b><span>${escapeHtml(state.hermesDetail || state.chatError || '请稍后重试')}</span><button data-host-retry>重新备课</button></div>` : ''}
        <div class="host-message-list">${hostMessages.length ? hostMessages.map((message) => `<div class="host-message">${escapeHtml(message.content)}</div>`).join('') : '<div class="host-message empty">连接 V1.7 后，由大架构师主动询问今天接待哪位客户。</div>'}</div>
      </section>
      ${insightReady ? `<section class="panel visitor-insight-result"><div class="panel-head"><div><strong>${escapeHtml(visitor.company_name)} · 洞察摘要</strong><small>${insight.sources?.length || 0} 条来源 · ${escapeHtml(insight.updated_at || '')}</small></div><span class="status">已落盘</span></div><div class="insight-mini-grid"><div><span>客户定位</span>${(summary.customer_positioning || []).slice(0, 3).map((item) => `<b>${escapeHtml(item)}</b>`).join('') || '<b>TBD</b>'}</div><div><span>待验证假设</span>${(summary.hypotheses || []).slice(0, 3).map((item) => `<b>${escapeHtml(item)}</b>`).join('') || '<b>TBD</b>'}</div><div><span>接待建议</span>${(summary.reception_advice || []).slice(0, 3).map((item) => `<b>${escapeHtml(item)}</b>`).join('') || '<b>TBD</b>'}</div></div><details><summary>查看完整报告、来源与 Wiki 路径</summary><div class="insight-detail"><p><b>公开 Wiki：</b>${escapeHtml(insight.public_wiki_slug || '无可靠事实，未写公共页')}</p><p><b>受限记录：</b>${escapeHtml(insight.private_record_path || '待写入')}</p>${(insight.sources || []).map((source) => `<p><a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">${escapeHtml(source.title)}</a> · ${escapeHtml(source.date || '')} · ${escapeHtml(source.confidence || '')}</p>`).join('')}</div></details><button class="form-cta" data-view="screen-03">客户已入场 · 打开需求问诊台</button></section>` : ''}
      <section class="panel device-panel">
        <div class="panel-head"><strong>主演示屏幕</strong><span class="status">${state.backendStatus === 'online' ? `${screenNames.length} 屏已配置` : '连接中'}</span></div>
        <div class="device-grid">${screenNames.map((name, i) => `<div class="device-card"><div><b>SCREEN 0${i + 1}</b><i></i></div><p>${escapeHtml(name)}</p><small class="metric">配置来自 /api/screens</small></div>`).join('')}</div>
      </section>
      <section class="panel center-panel">
        <div class="panel-head"><strong>五个独立体验中心</strong><span>仅显示授权摘要</span></div>
        <div class="center-list">${centers.map((center, i) => `<div class="center-row"><span class="num">0${i + 1}</span><div><b>${escapeHtml(center.role || '访客')}</b><small>${experienceSteps[center.step] || '进入体验'}</small></div><span class="state">${center.status === 'idle' ? '可进入' : center.status === 'submitted' ? '已提交' : '运行中'}</span></div>`).join('')}</div>
      </section>
      ${state.visitCompleteNotice ? `<section class="visit-complete-toast"><b>${escapeHtml(visitor.company_name || '当前客户')} 已完成参观</b><span>Wiki ${insight.private_record_path ? '已保存' : '待补齐'}，可结束本次接待并为下一位客户换场。</span><div><button data-visit-continue>稍后处理</button><button data-visit-open-confirm>结束并换场</button></div></section>` : ''}
      ${state.visitEndConfirmOpen ? `<div class="visit-end-overlay" role="presentation"><section class="visit-end-dialog" role="dialog" aria-modal="true" aria-labelledby="visit-end-title"><span class="visit-end-icon">↗</span><p class="kicker">SESSION ROLLOVER</p><h3 id="visit-end-title">结束本次接待？</h3><p>当前接待将归档，并为下一位客户创建全新的 Session。主会话与五个体验工位的客户内容都会清空。</p><dl><div><dt>当前客户</dt><dd>${escapeHtml(visitor.company_name || '当前客户')}</dd></div><div><dt>当前 Session</dt><dd>${escapeHtml(state.session?.session_id || '—')}</dd></div></dl><div class="visit-end-actions"><button data-visit-end-cancel ${state.visitEndBusy ? 'disabled' : ''}>取消</button><button class="danger" data-visit-end-confirm ${state.visitEndBusy ? 'disabled' : ''}>${state.visitEndBusy ? '正在归档并创建新 Session…' : '结束并接待下一位'}</button></div></section></div>` : ''}
    </div>
  </div>`;
}

function introView() {
  const mode = document.body.classList.contains('direct-mode') ? 'direct' : 'preview';
  return `<div class="screen motion-opening-host" aria-label="AI Lab 线下体验序章">
    <iframe class="motion-opening-frame" src="./screen-00-html.html?embedded=${mode}" title="AI Lab 首屏：AI Lab × Token Factory HTML 品牌序章" loading="eager" allow="autoplay"></iframe>
  </div>`;
}

function welcomeView() {
  const content = state.content?.screens?.['screen-01'] || {};
  return `<div class="screen welcome-screen">
    ${screenHeader('WELCOME', '欢迎到访')}
    <div class="screen-content welcome-layout">
      <div class="welcome-copy">
        <div class="welcome-chip"><i></i>今天，一起把想法变成现实</div>
        <p class="kicker">WELCOME TO AI LAB</p>
        <h2 class="hero-title">${escapeHtml(content.headline || '欢迎来到 AI 共创体验中心。')}</h2>
        <p class="lead">${escapeHtml(content.lead || '')}</p>
        <div class="welcome-stats">${(content.stats || []).map((item) => `<div><strong>${escapeHtml(item.value)}</strong><span>${escapeHtml(item.label)}</span></div>`).join('')}</div>
      </div>
      <div class="welcome-art" aria-label="彩色 AI 共创入口视觉"><div class="portal"></div></div>
    </div>
  </div>`;
}

function dashboardView() {
  const content = state.content?.screens?.['screen-02'] || {};
  const metrics = content.metrics || {};
  const utilization = metrics.utilization || {};
  return `<div class="screen">
    ${screenHeader('TOKENOPS', '算力运行正常')}
    <div class="screen-content">
      <div class="dashboard-head"><div><p class="kicker">FUSIONONE · COMPUTE OPERATIONS</p><h2 class="hero-title">${escapeHtml(content.headline || '')}</h2></div><div><span class="tag mint">现场展示模式</span> <span class="tag">无需业务后端</span></div></div>
      <div class="dashboard-grid">
        <section class="panel dash-main"><span class="tag blue">${escapeHtml(utilization.label)}</span><div class="dash-value"><strong class="metric">${escapeHtml(utilization.value)}</strong><span>${escapeHtml(utilization.delta)}</span></div><div class="area-chart" aria-label="算力利用率趋势图"><svg viewBox="0 0 500 150" preserveAspectRatio="none"><path d="M0 130 C70 125 85 105 140 110 S220 85 270 92 S350 52 400 62 S455 24 500 32 L500 150 L0 150Z" fill="#eaf0ff"/><path d="M0 130 C70 125 85 105 140 110 S220 85 270 92 S350 52 400 62 S455 24 500 32" fill="none" stroke="#2868f0" stroke-width="4" stroke-linecap="round"/></svg></div><div class="chart-legend"><span><i style="background:var(--blue)"></i>实际利用率</span><span><i style="background:var(--silver-2)"></i>行业基线</span></div></section>
        <section class="panel dash-card orange"><h3>${escapeHtml(metrics.saving?.label)}</h3><strong class="metric">${escapeHtml(metrics.saving?.value)}</strong><p>${escapeHtml(metrics.saving?.note)}</p></section>
        <section class="panel dash-card mint"><h3>${escapeHtml(metrics.workloads?.label)}</h3><strong class="metric">${escapeHtml(metrics.workloads?.value)}</strong><p>${escapeHtml(metrics.workloads?.note)}</p></section>
        <section class="panel dash-card blue"><h3>vGPU 细粒度池化</h3><div class="resource-bars" aria-label="四组资源池利用率"><i style="height:66%"></i><i></i><i></i><i></i></div></section>
        <section class="panel dash-card"><h3>${escapeHtml(metrics.latency?.label)}</h3><strong class="metric">${escapeHtml(metrics.latency?.value)}</strong><p>${escapeHtml(metrics.latency?.note)}</p></section>
      </div>
    </div>
  </div>`;
}

function clarifyCard() {
  const clarify = state.pendingClarify;
  if (!clarify?.question) return '';
  const choices = clarify.choices || [];
  return `<section class="clarify-card" aria-label="架构师需求澄清"><span>架构师正在确认</span><b>${escapeHtml(clarify.question)}</b><div>${choices.map((choice) => `<button data-clarify-choice="${escapeHtml(choice)}">${escapeHtml(choice)}</button>`).join('')}</div></section>`;
}

function liveChatFeedback() {
  if (state.pendingClarify) return '';
  if (state.streamingReply) {
    return `<div class="bubble ai streaming" aria-live="polite">${escapeHtml(state.streamingReply)}</div>`;
  }
  if (state.avatarSpeaking) {
    return '<div class="bubble ai streaming thinking" aria-live="polite"><i></i><i></i><i></i><span>架构师正在分析你的需求…</span></div>';
  }
  if (state.hermesRetryStopped) {
    return `<div class="chat-error" role="alert"><b>无法连接大架构师</b><span>${escapeHtml(state.hermesDetail || '已停止自动重试，请检查网络后重新连接')}</span><button data-hermes-reconnect>重新连接</button></div>`;
  }
  if (state.chatError) {
    return `<div class="chat-error" role="alert"><b>本轮回复失败</b><span>${escapeHtml(state.chatError)}</span><button data-chat-retry>重新发送</button></div>`;
  }
  if (['connecting', 'reconnecting'].includes(state.hermesStatus)) {
    return `<div class="bubble ai streaming thinking" aria-live="polite"><i></i><i></i><i></i><span>${escapeHtml(state.hermesDetail || architectStatusLabel())}</span></div>`;
  }
  return '';
}

function emptyChatState() {
  if (state.chatMessages.length || state.streamingReply || state.pendingClarify) return '';
  return `<div class="chat-empty"><span>AI 需求问诊</span><b>把真实问题交给大架构师</b><p>从业务目标、用户场景、数据约束到验收标准，一轮一轮收敛成需求确认单。</p></div>`;
}

function clinicView() {
  const demand = currentDemand();
  const demandDocument = currentDemandDocument();
  const messages = state.chatMessages;
  const architectRole = state.content?.screens?.['screen-03']?.conversation_role || '首席解决方案架构师';
  const busy = ['connecting', 'reconnecting', 'generating', 'waiting'].includes(state.hermesStatus);
  const showDemandSheet = hasDemandConfirmationContent(demand);
  const revealDemandSheet = showDemandSheet && !state.demandSheetVisible;
  state.demandSheetVisible = showDemandSheet;
  const fieldLock = demand.confirmed ? 'disabled' : '';
  const demandSheet = showDemandSheet ? `
        <section class="panel form-panel demand-sheet${revealDemandSheet ? ' reveal' : ''}" aria-label="需求收敛确认单" tabindex="-1"><div class="panel-head"><div><strong>需求收敛确认单</strong><small>${escapeHtml(demandDocument.title || 'AI 已完成需求收敛')}</small></div><span class="demand-document-status ${demand.confirmed ? 'confirmed' : 'draft'}">${demand.confirmed ? '已确认' : 'AI 已生成 · 待确认'}</span></div><div class="form-body"><div class="score-card"><strong class="metric">${Number(demand.completeness || 0)}%</strong><div><span>需求完整度</span><b>${Number(demand.completeness || 0) >= 80 ? '具备进入概念验证的条件' : '仍需补充关键约束'}</b></div></div><div class="field-grid"><label class="field wide">核心问题<textarea data-demand-field="core_problem" ${fieldLock}>${escapeHtml(demand.core_problem)}</textarea></label><label class="field">目标指标<input data-demand-field="target_metric" value="${escapeHtml(demand.target_metric)}" ${fieldLock}></label><label class="field">首期周期<input data-demand-field="cycle" value="${escapeHtml(demand.cycle)}" ${fieldLock}></label><label class="field">关键用户<input data-demand-field="users" value="${escapeHtml(demand.users)}" ${fieldLock}></label><label class="field">建议形态<input data-demand-field="solution" value="${escapeHtml(demand.solution)}" ${fieldLock}></label><label class="field wide">下一步行动<textarea data-demand-field="next_action" ${fieldLock}>${escapeHtml(demand.next_action)}</textarea></label></div>${demandDocumentView(demandDocument)}<button class="form-cta" data-action="confirm-demand">${demand.confirmed ? '需求已确认 · 查看深度洞察' : '确认需求，进入深度洞察'}</button></div></section>` : '';
  return `<div class="screen">
    ${screenHeader('DEMAND CLINIC', '正在问诊')}
    <div class="screen-content">
      <div class="clinic-head"><div><p class="kicker">IPD 001 · 需求问诊</p><h2 class="hero-title">${state.content?.screens?.['screen-03']?.headline || '把一句想法，收敛成一个可行动的问题。'}</h2></div><div><span class="tag orange">${escapeHtml(demand.industry || '待识别行业')}</span> <span class="tag blue">第 ${Math.max(1, Math.ceil(messages.length / 2))} 轮</span></div></div>
      <div class="clinic-grid${showDemandSheet ? ' has-demand-sheet' : ' conversation-only'}">
        <section class="panel chat-panel"><div class="panel-head"><strong>与${escapeHtml(architectRole)}对话</strong><span class="status" data-hermes-status-indicator data-hermes-status="${escapeHtml(state.hermesStatus)}">${escapeHtml(architectStatusLabel())}</span></div><div class="chat-body">${emptyChatState()}${messages.map((message) => `<div class="bubble ${message.role === 'user' ? 'user' : 'ai'}">${escapeHtml(message.content)}</div>`).join('')}${clarifyCard()}${liveChatFeedback()}<div class="bubble-note"><i></i>${escapeHtml(getScreenConfig('screen-03').skill_command || 'solution-consultant-persona')} · Hermes 独立会话</div></div><div class="chat-composer"><input id="demand-chat-input" placeholder="向大架构师描述你的真实业务问题…" ${busy ? 'disabled' : ''}><button ${state.hermesStatus === 'generating' ? 'data-demand-stop' : 'data-demand-send'} aria-label="${state.hermesStatus === 'generating' ? '停止生成' : '发送需求'}">${icon(state.hermesStatus === 'generating' ? 'stop' : 'send')}</button></div></section>
        ${demandSheet}
      </div>
    </div>
  </div>`;
}

const staffingStageFallback = [
  ['IPD0', '洞察与需求合理性'], ['IPD1', '产品规划与架构'], ['IPD2', '开发与实现设计'],
  ['IPD3', '验证与合规'], ['IPD4', '发布与上市'], ['IPD5', '生命周期经营'],
];

const insightStageLabels = {
  planning: '正在规划项目分工', internal_research: '正在检索内部知识', external_research: '内部证据不足，正在补充公开资料',
  analysis: '正在形成根因与影响判断', writing: '正在撰写结构化报告', ipd_handoff: '正在整理001实践输入',
  completed: '深度洞察已完成', partial: '已形成部分报告', failed: '项目组执行失败', interrupted: '任务已暂停',
};
const employeeStatusLabels = { waiting: '等待上游', working: '正在工作', reviewing: '正在核验', done: '已完成', blocked: '证据不足', failed: '执行失败' };

function staffingView() {
  const job = currentInsightJob();
  const plan = currentStaffingPlan();
  const demand = currentDemand();
  const stagesList = state.insightCatalog?.stages || staffingStageFallback.map(([id, name]) => ({ id, name }));
  const employees = plan.squads?.[0]?.employees || [];
  const selected = employees.find((item) => item.employee_id === state.selectedEmployeeId) || employees[0];
  const completed = job.completed_sections || [];
  const stageText = insightStageLabels[job.active_stage] || insightStageLabels[job.status] || '正在读取需求确认单';
  const outputs = [
    ['summary', '执行摘要'], ['root_causes', '根因图谱'], ['impacts', '影响分析'],
    ['evidence', '证据明细'], ['recommendation', '行动建议'], ['ipd_handoff', '001 IPD交接输入'],
  ];
  const failed = ['failed', 'interrupted'].includes(job.status);
  const summaryReady = completed.includes('summary');
  return `<div class="screen staffing-screen">
    ${screenHeader('AI PROJECT TEAM', `003.5 · ${escapeHtml(stageText)}`)}
    <div class="screen-content staffing-content">
      <section class="staffing-mission"><div><p class="kicker">DEMAND CONFIRMED · IPD0 STARTED</p><h2>需求已经确认，正在为本次任务组建<em>AI项目组</em></h2><p>${escapeHtml(plan.mission || demand.core_problem || '正在读取需求确认单')}</p></div><div><span>本次目标</span><b>${escapeHtml(demand.target_metric || '形成可评审的深度洞察')}</b><small>预计交付 6 个结构化章节</small></div></section>
      <div class="staffing-grid">
        <aside class="staffing-stages" aria-label="IPD阶段">${stagesList.map((stage, index) => `<div class="${index === 0 ? 'active' : 'locked'}"><span>${escapeHtml(stage.id || `IPD${index}`)}</span><b>${escapeHtml(stage.name)}</b><small>${index === 0 ? '本次已集结' : '由后续人工评审解锁'}</small></div>`).join('')}</aside>
        <main class="staffing-team"><header><div><span>IPD0 · AI员工编组</span><h3>${escapeHtml(plan.squads?.[0]?.objective || 'V1.7正在规划每位AI员工的具体任务')}</h3></div><b>${employees.length || '—'} 名 AI员工</b></header>
          ${employees.length ? `<div class="employee-grid">${employees.map((employee, index) => `<button class="employee-card ${employee.status || 'waiting'} ${employee.employee_id === selected?.employee_id ? 'selected' : ''}" style="--employee-index:${index}" data-employee-id="${escapeHtml(employee.employee_id)}" aria-pressed="${employee.employee_id === selected?.employee_id}"><span class="employee-avatar">${escapeHtml(employee.display_name?.slice(0, 1) || 'AI')}</span><div><small>AI员工 · ${escapeHtml(employee.job_title)}</small><h4>${escapeHtml(employee.display_name)}</h4><p>${escapeHtml(employee.task)}</p><em>${escapeHtml(employeeStatusLabels[employee.status] || '等待上游')}</em></div><strong>${escapeHtml((employee.deliverables || []).join(' · '))}</strong></button>`).join('')}</div>` : '<div class="staffing-planning"><i></i><b>V1.7正在规划项目分工</b><span>规划完成后，这里只会出现已校验的AI员工与真实能力。</span></div>'}
          ${selected ? `<details class="employee-badge" open><summary>查看 ${escapeHtml(selected.display_name)} 的能力工牌</summary><div><dl><dt>基础 Agent</dt><dd>${escapeHtml(selected.base_agent)}</dd><dt>已加载 Skill</dt><dd>${escapeHtml((selected.skill_ids || []).join('、') || '本次未加载')}</dd><dt>可调用工具</dt><dd>${escapeHtml((selected.tool_ids || []).join('、') || '本次未加载')}</dd></dl><dl><dt>允许读取</dt><dd>${escapeHtml((selected.inputs || []).join('、'))}</dd><dt>正在形成</dt><dd>${escapeHtml((selected.deliverables || []).join('、'))}</dd><dt>权限边界</dt><dd>${escapeHtml((selected.permissions || []).join('；'))}</dd></dl></div></details>` : ''}
        </main>
        <aside class="staffing-workboard" aria-live="polite"><header><span>LIVE WORKBOARD</span><h3>项目组正在做什么</h3></header><div class="work-state ${failed ? 'failed' : ''}"><i></i><b>${escapeHtml(stageText)}</b><span>${job.active_employee_id ? `当前AI员工：${escapeHtml(employees.find((item) => item.employee_id === job.active_employee_id)?.display_name || job.active_employee_id)}` : '状态来自Hermes真实任务事件'}</span></div><div class="section-progress">${outputs.map(([key, label]) => `<div class="${completed.includes(key) ? 'done' : key === job.active_stage ? 'active' : ''}"><i>${completed.includes(key) ? '✓' : '·'}</i><span>${label}</span><b>${completed.includes(key) ? '已回填' : '等待生成'}</b></div>`).join('')}</div>${failed ? `<div class="staffing-error"><b>${escapeHtml(job.error || '本轮任务未完成')}</b><button data-insight-retry>重新执行</button></div>` : `<button class="soft-button staffing-stop" data-insight-stop ${['completed', 'partial'].includes(job.status) ? 'disabled' : ''}>停止本轮任务</button>`}${summaryReady ? `<div class="summary-ready"><b>执行摘要已完成</b><span>${state.insightAutoPaused ? '自动进入已暂停' : `${state.insightAutoSeconds || 3} 秒后进入深度洞察报告`}</span><button data-insight-open>立即查看报告</button></div>` : ''}</aside>
      </div>
      <footer class="staffing-flow"><div><span>01</span><b>输入材料</b><small>已确认需求 + 授权背景</small></div><i></i><div><span>02</span><b>AI员工协作</b><small>真实检索、分析与核验</small></div><i></i><div><span>03</span><b>章节产出</b><small>完成即回填004</small></div><i></i><div><span>04</span><b>人工评审</b><small>AI工作，人做决策</small></div></footer>
    </div>
  </div>`;
}

function insightValue(value, empty = '待补充') {
  if (value && typeof value === 'object' && String(value.status || '').toLowerCase() === 'tbd') {
    return `<div class="insight-tbd-card"><span>TBD · 待核实</span><b>${escapeHtml(value.reason || empty)}</b><small>责任人：${escapeHtml(value.owner || '待指派')}</small><small>补证动作：${escapeHtml(value.action || '待登记')}</small></div>`;
  }
  if (Array.isArray(value)) {
    if (!value.length) return `<span class="insight-empty">${empty}</span>`;
    return `<ul class="concept-list">${value.map((item) => `<li>${typeof item === 'object' ? Object.entries(item).map(([key, val]) => `<b>${escapeHtml(key)}：</b>${escapeHtml(Array.isArray(val) ? val.join('、') : String(val ?? ''))}`).join('　') : escapeHtml(String(item))}</li>`).join('')}</ul>`;
  }
  if (value && typeof value === 'object') {
    const entries = Object.entries(value);
    if (!entries.length) return `<span class="insight-empty">${empty}</span>`;
    return `<dl class="concept-dl">${entries.map(([key, val]) => `<div><dt>${escapeHtml(key)}</dt><dd>${typeof val === 'object' ? insightValue(val) : escapeHtml(String(val ?? ''))}</dd></div>`).join('')}</dl>`;
  }
  return value ? `<p>${escapeHtml(String(value))}</p>` : `<span class="insight-empty">${empty}</span>`;
}

function insightConceptSection(id, number, eyebrow, title, value) {
  const highlighted = state.insightHighlightedSections.includes(id);
  return `<section id="${id}" class="insight-report-section concept-section ${highlighted ? 'insight-just-filled' : ''}" data-report-section="${id}"><div class="report-section-title"><span>${number} · ${eyebrow}</span><h2>${escapeHtml(title)}</h2>${highlighted ? '<em class="insight-filled-badge">已回填</em>' : ''}<button data-insight-ask-section="${id}">与AI讨论本章</button></div><div class="concept-card">${insightValue(value)}</div></section>`;
}

function currentInsightReview() {
  return currentSessionData().insight_review || { status: 'draft', version: 'V0.1', coverage: {} };
}

function currentInsightReviewGate() {
  return currentSessionData().insight_review_gate || { status: 'draft', ai_reviewers: [], final_decision: {} };
}

function insightReviewPanel(gate) {
  if (!gate.task_id) return '';
  const statusLabels = { assigned: '已指派', reviewing: '评审中', approved: '已通过', conditional: '条件通过', changes: '要求修改', rejected: '已拒绝', failed: '执行失败' };
  const notificationLabels = { queued: '发送中', sent: '已通知', failed: '通知失败', '': '未发送' };
  return `<section class="ai-review-panel" aria-live="polite"><header><div><span>AI CONCEPT REVIEW</span><h3>AI 概念评审会</h3></div><b class="${escapeHtml(gate.status)}">${escapeHtml(statusLabels[gate.status] || '待指派')}</b></header><div class="review-assignment"><span>由 ${escapeHtml(gate.assigned_by || '当前用户')} 指派</span><em>${escapeHtml(gate.report_version || '')}</em><small>${escapeHtml(gate.assigned_at || '')}</small></div><div class="ai-reviewer-list">${(gate.ai_reviewers || []).map((reviewer) => `<article class="${escapeHtml(reviewer.status || 'waiting')}"><i>${escapeHtml((reviewer.display_name || 'AI').slice(0, 1))}</i><div><span>AI员工 · ${escapeHtml(reviewer.job_title)}</span><b>${escapeHtml(reviewer.display_name)}</b><p>${escapeHtml(reviewer.responsibility)}</p><small>${escapeHtml(reviewer.conclusion || (reviewer.status === 'done' ? '会签完成' : reviewer.status === 'working' ? '正在审查' : '等待上游'))}</small></div></article>`).join('')}</div>${gate.final_decision?.decision ? `<div class="ai-review-decision ${escapeHtml(gate.status)}"><span>主审结论</span><h4>${escapeHtml(statusLabels[gate.status] || gate.final_decision.decision)}</h4><p>${escapeHtml(gate.final_decision.summary || '')}</p>${(gate.final_decision.conditions || []).length ? `<ul>${gate.final_decision.conditions.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : ''}</div>` : ''}<footer><span>飞书联系人：${escapeHtml((gate.human_contact_bindings || []).map((item) => item.role).join('、') || '待配置')}</span><b class="notification-${escapeHtml(gate.notification_status || 'idle')}">通知状态：${escapeHtml(notificationLabels[gate.notification_status || ''] || gate.notification_status)}</b>${gate.notification_status === 'failed' ? '<button data-review-notify-retry>重试通知</button>' : ''}${gate.status === 'failed' ? '<button data-review-task-retry>重新评审</button>' : ''}${['assigned', 'reviewing', 'failed'].includes(gate.status) ? '<button data-review-override>现场确认并放行</button>' : ''}</footer></section>`;
}

function insightReadinessDrawer(coverage) {
  if (!state.insightReadinessOpen) return '';
  const blockers = coverage.blocking_items || [];
  const target = state.insightTbdTarget;
  return `<div class="readiness-overlay" role="dialog" aria-modal="true" aria-label="进入下一步前的待办"><section class="readiness-drawer"><header><div><span>READINESS CHECK</span><h2>进入下一步前还缺什么</h2><p>空项不会被静默忽略。可以让AI补齐，或登记为有责任人的TBD。</p></div><button data-readiness-close aria-label="关闭">${icon('close')}</button></header><div class="readiness-list">${blockers.length ? blockers.map((item, index) => `<article><div><span>${escapeHtml(item.label)}</span><b>${escapeHtml(item.reason)}</b><small>${escapeHtml(item.field)}</small></div><button data-readiness-locate="${escapeHtml(item.section)}">查看章节</button><button data-readiness-ai="${escapeHtml(item.label)}">让AI补齐</button>${String(item.field || '').startsWith('concept.') ? `<button data-readiness-tbd="${index}">登记TBD</button>` : ''}</article>`).join('') : '<div class="readiness-empty"><b>没有未处置缺口</b><p>可以提交AI概念评审。</p></div>'}</div>${target ? `<form class="tbd-form" data-tbd-form><header><span>登记为受控TBD</span><b>${escapeHtml(target.label)}</b></header><label>缺口原因<textarea name="reason" required>${escapeHtml(target.reason || '')}</textarea></label><label>责任人<input name="owner" required placeholder="例如：客户HR业务负责人"></label><label>补证动作<textarea name="action" required placeholder="例如：访谈实际使用岗位并确认权限边界"></textarea></label><label>预计完成时间<input name="due_at" placeholder="例如：下一次评审前"></label><footer><button type="button" data-tbd-cancel>取消</button><button type="submit">保存TBD</button></footer></form>` : ''}<footer><button data-readiness-close>继续完善报告</button></footer></section></div>`;
}

function insightAssistantView(review) {
  const messages = state.insightAssistantMessages.slice(-8);
  const revision = state.insightPendingRevision || (review.revisions || []).find((item) => item.revision_id === review.pending_revision_id);
  return `<aside class="insight-assistant" aria-label="洞察共创助手"><header><div><span>INSIGHT COPILOT</span><h3>洞察共创助手</h3></div><b class="${state.insightAssistantBusy ? 'working' : ''}">${state.insightAssistantBusy ? '工作中' : '可对话'}</b></header>
    ${state.insightSelectedText ? `<div class="assistant-context"><span>已选中报告内容</span><p>${escapeHtml(state.insightSelectedText.slice(0, 500))}</p><div><button data-insight-context-action="explain">解释</button><button data-insight-context-action="ask">追问</button><button data-insight-context-action="revise">修改本段</button><button data-insight-context-action="verify">核验证据</button><button data-insight-clear-selection>取消</button></div></div>` : ''}
    <div class="insight-assistant-log" aria-live="polite">${messages.length ? messages.map((message) => `<div class="assistant-message ${message.role}"><span>${message.role === 'user' ? '你' : 'AI'}</span><p>${escapeHtml(message.content)}</p></div>`).join('') : '<div class="assistant-welcome"><b>可以直接追问，也可以要求修改。</b><p>修改不会直接覆盖报告，AI会先给出差异预览。</p></div>'}${state.pendingClarify && state.insightAssistantBusy ? `<div class="assistant-clarify"><b>${escapeHtml(state.pendingClarify.question || '请补充选择')}</b>${(state.pendingClarify.choices || []).map((choice) => `<button data-insight-clarify="${escapeHtml(choice)}">${escapeHtml(choice)}</button>`).join('')}</div>` : ''}${state.insightAssistantBusy ? `<div class="assistant-working"><i></i><span>${escapeHtml(state.insightAssistantStatus || '正在读取报告')}</span><p>${escapeHtml(state.streamingReply)}</p></div>` : ''}</div>
    ${state.insightRevisionError ? `<section class="revision-error" role="alert"><b>${escapeHtml(state.insightRevisionError.message)}</b><p>报告尚未改变。你可以重新生成语义回填草案。</p><button data-revision-repair>重新生成回填草案</button></section>` : ''}
    ${state.insightPlacementCandidates.length ? `<section class="placement-preview" aria-label="确认填写位置"><header><span>SEMANTIC PLACEMENT</span><h4>AI建议填写位置</h4><p>这段内容可能属于多个章节，请选择最合适的位置。</p></header>${state.insightPlacementCandidates.map((item, index) => `<div><blockquote>${escapeHtml(item.source_excerpt || '本轮回答内容')}</blockquote><button data-placement-choice="${escapeHtml(item.recommended_field)}" data-placement-index="${index}">推荐 · ${escapeHtml(item.recommended_field)}</button>${(item.alternatives || []).map((field) => `<button data-placement-choice="${escapeHtml(field)}" data-placement-index="${index}">${escapeHtml(field)}</button>`).join('')}</div>`).join('')}</section>` : ''}
    ${revision ? `<section class="revision-preview" aria-label="待回填内容"><header><span>BACKFILL PREVIEW</span><h4>待回填内容 · 尚未应用</h4><p>AI已按语义映射到 ${(revision.affected_sections || []).length || 1} 个章节</p></header>${(revision.changes || []).map((change) => `<div><b>${escapeHtml(change.target_section || INSIGHT_FIELD_SECTIONS[change.field] || '')} · ${escapeHtml(change.semantic_intent || change.field)}</b>${change.source_excerpt ? `<blockquote>${escapeHtml(change.source_excerpt)}</blockquote>` : ''}<del><small>原内容</small>${escapeHtml(typeof change.before === 'object' ? JSON.stringify(change.before) : String(change.before ?? ''))}</del><ins><small>新内容</small>${escapeHtml(typeof change.after === 'object' ? JSON.stringify(change.after) : String(change.after ?? ''))}</ins><em>匹配置信度 ${Math.round(Number(change.confidence || 1) * 100)}%</em></div>`).join('')}${(revision.affected_sections || []).length ? `<p class="revision-impact">影响章节：${escapeHtml(revision.affected_sections.join('、'))}</p>` : ''}${(revision.warnings || []).length ? `<div class="revision-warnings" role="alert">${revision.warnings.map((warning) => `<span>${escapeHtml(warning)}</span>`).join('')}</div>` : ''}<footer><button data-revision-discard ${state.insightRevisionApplying ? 'disabled' : ''}>放弃</button><button data-revision-continue ${state.insightRevisionApplying ? 'disabled' : ''}>继续追问</button><button data-revision-apply ${state.insightRevisionApplying ? 'disabled' : ''}>${state.insightRevisionApplying ? '正在校验并回填…' : '应用回填到报告'}</button></footer></section>` : ''}
    <div class="assistant-quick"><button data-insight-quick="这个判断依据是什么？">判断依据</button><button data-insight-quick="还有哪些相反证据？">相反证据</button><button data-insight-quick="进入001实践前还缺什么？">还缺什么</button><button data-insight-quick="请补齐IPD概念阶段洞察并给出结构化修订草案。">补齐IPD洞察</button></div>
    <div class="insight-composer"><textarea id="insight-assistant-input" placeholder="追问报告，或说‘把本章的结论改为…’" ${state.insightAssistantBusy ? 'disabled' : ''}></textarea><button ${state.insightAssistantBusy ? 'data-insight-assistant-stop' : 'data-insight-assistant-send'} aria-label="${state.insightAssistantBusy ? '停止生成' : '发送'}">${icon(state.insightAssistantBusy ? 'stop' : 'send')}</button></div></aside>`;
}

function insightView() {
  const insight = currentInsight();
  const job = currentInsightJob();
  const demand = currentDemand();
  const concept = insight.concept || {};
  const review = currentInsightReview();
  const reviewGate = currentInsightReviewGate();
  const coverage = review.coverage || {};
  const live = ['planning', 'running', 'partial', 'interrupted'].includes(job.status);
  const locked = review.status === 'confirmed';
  const pending = Boolean(review.pending_revision_id);
  const readiness = coverage.readiness || (coverage.confirmable ? 'ready' : 'blocked');
  const canSubmitReview = Boolean(coverage.can_submit_review ?? coverage.confirmable) && !pending && !locked;
  const chapters = [
    ['insight-summary', '01', '执行摘要'], ['concept-customer', '02', '客户与业务价值'], ['concept-market', '03', '产业市场与政策'],
    ['concept-competition', '04', '竞争与替代方案'], ['concept-technology', '05', '技术可行性'], ['concept-strategy', '06', '战略与业务边界'],
    ['concept-capability', '07', '产品能力映射'], ['concept-assessment', '08', '收益风险与优先级'], ['concept-checks', '09', '四类专项检查'],
    ['concept-knowledge', '10', '事实、假设与访谈'], ['concept-verdict', '11', '需求评审结论'], ['concept-package', '12', '初始产品包与001切片'],
  ];
  return `<div class="screen insight-cocreation-screen">${screenHeader('IPD INSIGHT CO-CREATION', live ? 'IPD-01 / IPD-02 持续回填' : locked ? `${review.version} 已确认` : `${review.version || 'V0.1'} 待人工确认`)}
    <div class="insight-cocreation-shell">
      <aside class="insight-toc"><span>IPD CONCEPT OUTLINE</span><h3>需求洞察共创台</h3><p>${escapeHtml(review.version || 'V0.1')} · ${Number(coverage.percent || 0)}%覆盖</p><nav>${chapters.map(([id, number, label], index) => `<button class="${index === 0 ? 'active' : ''}" data-insight-section="${id}"><i>${number}</i>${label}</button>`).join('')}</nav><div><span>人机职责</span><b>AI调研与修订，人确认结论</b></div></aside>
      <article class="insight-report-page" id="insight-report-document" aria-label="IPD概念阶段需求洞察报告">
        ${live ? `<div class="insight-live-banner" aria-live="polite"><i></i><div><b>${escapeHtml(insightStageLabels[job.active_stage] || 'AI项目组正在继续工作')}</b><span>章节完成后会实时回填；你现在也可以边看边追问。</span></div><button data-view="screen-03-team">查看项目组</button></div>` : ''}
        <header id="insight-summary" class="insight-cover ${state.insightHighlightedSections.includes('insight-summary') ? 'insight-just-filled' : ''}" data-report-section="insight-summary"><div><span>IPD CONCEPT INSIGHT · ${escapeHtml(review.version || 'V0.1')}</span><h1>${escapeHtml(insight.title || demand.core_problem || '需求洞察报告')}</h1><p>${escapeHtml(insight.judgment || '正在把已确认需求转化为产品原型前的IPD洞察与评审输入。')}</p></div><div class="coverage-ring" style="--coverage:${Number(coverage.percent || 0)}"><b>${Number(coverage.percent || 0)}%</b><span>IPD覆盖度</span></div></header>
        <section class="insight-summary-grid"><div><span>核心判断</span><b>${escapeHtml(insight.judgment || '待形成')}</b></div><div><span>目标差距</span><b>${escapeHtml(insight.gap || 'TBD')}</b></div><div><span>采纳建议</span><b>${escapeHtml(concept.verdict?.decision || insight.recommendation || '待评审')}</b></div></section>
        ${insightConceptSection('concept-customer', '02', 'CUSTOMER & VALUE', '客户、用户、场景与业务价值', concept.customer_user)}
        ${insightConceptSection('concept-market', '03', 'MARKET & POLICY', '产业趋势、市场空间与政策动态', concept.market)}
        ${insightConceptSection('concept-competition', '04', 'COMPETITION', '竞争格局、替代方案与差异化机会', concept.competition)}
        ${insightConceptSection('concept-technology', '05', 'TECHNOLOGY', '技术趋势、可行性与工作量', concept.technology)}
        ${insightConceptSection('concept-strategy', '06', 'STRATEGIC FIT', '超聚变业务边界、战略与产品匹配', concept.strategic_fit)}
        ${insightConceptSection('concept-capability', '07', 'CAPABILITY MAP', '产品能力映射与能力缺口', concept.capability_mapping)}
        ${insightConceptSection('concept-assessment', '08', 'ASSESSMENT', '收益、风险、工作量与优先级', concept.assessment)}
        ${insightConceptSection('concept-checks', '09', 'SPECIAL CHECKS', '网络安全、可靠可用、节能减排、功能性能', concept.special_checks)}
        ${insightConceptSection('concept-knowledge', '10', 'KNOWLEDGE STATUS', '事实、推断、假设、TBD与明白人访谈', concept.knowledge_status)}
        ${insightConceptSection('concept-verdict', '11', 'REVIEW VERDICT', '需求评审结论', concept.verdict)}
        <section id="concept-package" class="insight-report-section concept-section ${state.insightHighlightedSections.includes('concept-package') ? 'insight-just-filled' : ''}" data-report-section="concept-package"><div class="report-section-title"><span>12 · PRODUCT PACKAGE</span><h2>初始产品包与001最小实践切片</h2>${state.insightHighlightedSections.includes('concept-package') ? '<em class="insight-filled-badge">已回填</em>' : ''}<button data-insight-ask-section="concept-package">与AI讨论本章</button></div><div class="concept-split"><div><h3>初始产品包</h3>${insightValue(concept.initial_product_package)}</div><div><h3>001实践切片</h3>${insightValue(concept.demo_slice)}</div></div></section>
        <footer class="insight-report-footer"><b>证据来源</b><span>${(insight.sources || []).length ? (insight.sources || []).slice(0, 12).map((source, index) => `[${index + 1}] ${escapeHtml(source.title || source.path || source.url)}`).join('　') : '暂无可核验来源，不能确认'}</span></footer>
      </article>
      <div class="insight-right-rail">${insightAssistantView(review)}${insightReviewPanel(reviewGate)}</div>
    </div>
    <footer class="insight-confirm-bar"><div><span>洞察覆盖度</span><b>${Number(coverage.percent || 0)}%</b></div><div><span>准备状态</span><b class="readiness-${escapeHtml(readiness)}">${readiness === 'ready' ? '可评审' : readiness === 'conditional' ? '有条件' : '待处置'}</b></div><div><span>TBD / 待访谈</span><b>${Number(coverage.tbd_count || 0) + Number((coverage.conditional_items || []).length)}</b></div><div><span>当前版本</span><b>${escapeHtml(review.version || 'V0.1')}</b></div><div class="confirm-actions"><button data-insight-return-demand ${state.insightAssistantBusy ? 'disabled' : ''}>需求理解有误，退回003修订</button>${locked ? `<strong>已由 ${escapeHtml(review.confirmed_by || '用户')} 确认</strong><button class="primary" data-view="screen-05">进入001 IPD实践</button>` : `<button class="primary" data-insight-confirm aria-describedby="insight-confirm-hint">${canSubmitReview ? readiness === 'conditional' ? '带TBD提交AI评审' : '确认当前洞察，提交AI评审' : '查看进入下一步前还缺什么'}</button><small id="insight-confirm-hint">${canSubmitReview ? 'AI预审通过或条件通过后自动进入005' : `${(coverage.blocking_items || []).length} 项缺口需要处置`}</small>`}</div></footer>
    ${insightReadinessDrawer(coverage)}
  </div>`;
}

function pipelineView() {
  const phase = ipdPhases[state.selectedPhase];
  const demand = currentDemand();
  const selectedAgent = phase.agents.find((agent) => agent.id === state.selectedAgent) || phase.agents[0];
  const statusLabel = { working: '正在研判', waiting: '等待上游', locked: '阶段锁定' };
  const canAdvance = phase.reviews.every((review) => getReviewState(review) === 'approved');
  const pendingReview = phase.reviews.find((review) => getReviewState(review) !== 'approved') || phase.reviews.at(-1);
  const reviewer = humanReviewers[pendingReview] || humanReviewers.TR1;
  const approvedCount = phase.reviews.filter((review) => getReviewState(review) === 'approved').length;
  const currentOutput = phase.outputs[0];
  const permission = selectedAgent.base === 'Coder' ? '批准后写入' : selectedAgent.base === 'Supervision' ? '独立审查' : '检索与起草';
  const drawer = state.ipdDrawer ? `<div class="ipd-drawer-layer"><button class="ipd-drawer-scrim" data-ipd-drawer-close aria-label="关闭展开内容"></button><section class="ipd-detail-drawer" role="dialog" aria-modal="false" aria-label="${state.ipdDrawer === 'materials' ? '本阶段输入材料' : '本阶段全部交付件'}"><header><div><span>${state.ipdDrawer === 'materials' ? 'SOURCE MATERIALS' : 'DELIVERABLE LIBRARY'}</span><h3>${state.ipdDrawer === 'materials' ? `已挂载 ${phase.inputs.length} 项输入材料` : `${phase.name}阶段 · ${phase.outputs.length} 项交付件`}</h3></div><button data-ipd-drawer-close aria-label="关闭">${icon('close')}</button></header><div class="ipd-drawer-grid">${(state.ipdDrawer === 'materials' ? phase.inputs : phase.outputs).map((item, i) => `<button data-artifact-title="${item}"><span>0${i + 1}</span><div><b>${item}</b><small>${artifactDescriptions[item] || (state.ipdDrawer === 'materials' ? '已挂载到当前阶段，可打开查看内容与来源。' : '点击打开完整报告、图表、表格和评审依据。')}</small></div><em>打开 ↗</em></button>`).join('')}</div></section></div>` : '';
  return `<div class="screen">
    ${screenHeader('IPD ORCHESTRATION', `${phase.name}阶段 · ${phase.reviews[0]} 准备中`)}
    <div class="screen-content ipd-screen-content">
      <div class="ipd-command"><div><p class="kicker">DEMAND-DRIVEN IPD · CURRENT FOCUS</p><h2 class="ipd-title"><em>0${state.selectedPhase + 1} ${phase.name}</em> · ${phase.short}</h2></div><div class="ipd-controls"><button class="ipd-play" data-ipd-play>${state.pipelinePlaying ? '暂停协作' : '播放协作'}</button><button class="ipd-cast" data-ipd-cast>${icon('display')}投到 06 主屏</button></div></div>
      <div class="ipd-phase-rail" aria-label="IPD 六阶段导航">${ipdPhases.map((item, i) => `<button class="ipd-phase ${i === state.selectedPhase ? 'active' : ''} ${i < state.selectedPhase ? 'done' : ''}" data-ipd-phase="${i}" aria-current="${i === state.selectedPhase ? 'step' : 'false'}"><span>0${i + 1}</span><div><b>${item.name}</b><small>${i === state.selectedPhase ? item.short : item.reviews.join(' · ')}</small></div></button>`).join('')}</div>
      <div class="ipd-focus-grid">
        <section class="panel ipd-focus-main ${state.pipelinePlaying ? 'is-playing' : ''}">
          <header class="ipd-focus-head"><div><span>01 · AI 当前工作</span><h3>${phase.objective}</h3><p>需求上下文：<b>${escapeHtml(demand.core_problem || '等待已确认需求')}</b> · ${escapeHtml(demand.target_metric || '')}</p></div><button data-artifact-title="${currentOutput}"><small>当前主交付件</small><b>${currentOutput}</b><em>打开演示 ↗</em></button></header>
          <div class="ipd-workflow-label"><div><b>多 Agent 协作</b><span>${phase.agents.length} 个专业角色编排在基础 Agent 上</span></div><div class="ipd-agent-key"><span>Main · 主持</span><span>Supervision · 把关</span><span>Coder · 落实</span></div></div>
          <div class="agent-lane ipd-focus-lane"><div class="demand-node"><small>INPUT</small><b>已确认需求</b><span>${phase.inputs.length} 项材料</span></div><div class="flow-arrow"><i></i><i></i><i></i></div><div class="agent-stack">${phase.agents.map((agent) => `<button class="agent-node ${agent.id === selectedAgent.id ? 'selected' : ''} ${agent.status}" data-ipd-agent="${agent.id}"><span>${agent.base} × ${agent.id}</span><b>${agent.name}</b><small>${agent.role}</small><em>${statusLabel[agent.status]}</em></button>`).join('')}</div><div class="flow-arrow merge"><i></i><i></i><i></i></div><div class="human-node"><span>HUMAN</span><b>${pendingReview}</b><small>人工签字</small></div></div>
          <button class="agent-detail-toggle" data-agent-detail aria-expanded="${state.agentDetailOpen}"><span><b>${selectedAgent.id} · ${selectedAgent.name}</b><small>${selectedAgent.base} 基础 Agent × ${selectedAgent.role}</small></span><em>${state.agentDetailOpen ? '收起职责 ↑' : '查看职责 ↓'}</em></button>
          ${state.agentDetailOpen ? `<div class="agent-inspector"><div class="agent-avatar">${selectedAgent.id.split('-')[1]}</div><div><small>${selectedAgent.base} 基础 Agent · ${baseAgents[selectedAgent.base].desc}</small><b>${selectedAgent.name}：${baseAgents[selectedAgent.base].verb}</b><p>${selectedAgent.job}</p></div><span class="agent-permission">${permission}</span></div>` : ''}
        </section>
        <aside class="panel ipd-decision-focus">
          <div class="decision-eyebrow"><span>02 · 下一人工关口</span><b>${approvedCount}/${phase.reviews.length} 已通过</b></div>
          <div class="decision-gate"><span>${pendingReview}</span><div><small>由谁确认</small><h3>${reviewer.person}</h3><b>${reviewer.role}</b><p>${reviewer.focus}</p></div></div>
          <div class="decision-progress"><i style="--review-progress:${Math.max(8, approvedCount / phase.reviews.length * 100)}%"></i></div>
          <button class="decision-primary" data-review-gate="${pendingReview}"><span class="feishu-mark">飞</span><div><small>AI 已备好材料包</small><b>打开飞书审批</b></div><em>通过 / 修改 / 拒绝 →</em></button>
          <div class="decision-boundary"><span>职责边界</span><b>AI 负责工作，人负责评审确认</b></div>
        </aside>
      </div>
      <div class="ipd-utility-row">
        <button data-ipd-drawer="materials" aria-expanded="${state.ipdDrawer === 'materials'}"><span>输入材料</span><b>${phase.inputs.length} 项已挂载</b><em>展开查看</em></button>
        <button data-ipd-drawer="deliverables" aria-expanded="${state.ipdDrawer === 'deliverables'}"><span>阶段交付件</span><b>${phase.outputs.length} 项均可演示</b><em>展开查看</em></button>
        <div><span>阶段门禁</span><b>${canAdvance ? '人工审批已完成' : `等待 ${pendingReview} 结论`}</b><button data-ipd-advance ${canAdvance ? '' : 'disabled'}>${canAdvance ? '进入下一阶段' : '审批后解锁'}</button></div>
      </div>
    </div>
    ${drawer}${artifactOverlay()}${feishuReviewOverlay()}${assistantDock()}
  </div>`;
}

function giantWorkbenchView() {
  if (state.giantMode === 'artifact') return giantArtifactView();
  if (state.giantMode === 'orchestration') return giantOrchestrationView();
  const demand = currentDemand();
  const prototype = currentPrototype();
  const messages = state.chatMessages;
  return `<div class="giant-workbench">
    <section class="giant-col"><span class="giant-label">01 · 用户对话 / CONVERSATION</span><div class="giant-chat">${messages.slice(-3).map((message) => `<div class="bubble ${message.role === 'user' ? 'user' : 'ai'}">${escapeHtml(message.content)}</div>`).join('')}</div><div class="summary-card"><h3>${demand.confirmed ? '对话已确认' : '需求收敛中'}</h3><dl><div><dt>目标用户</dt><dd>${escapeHtml(demand.users || '待确认')}</dd></div><div><dt>核心指标</dt><dd>${escapeHtml(demand.target_metric || '待确认')}</dd></div><div><dt>首期范围</dt><dd>${escapeHtml(demand.cycle || '待确认')}</dd></div></dl></div></section>
    <section class="giant-col"><span class="giant-label">02 · 共创工作台 / LIVE WORKBENCH</span><h2 class="giant-title">${escapeHtml(prototype.title || demand.solution || '等待生成原型')}</h2><p class="giant-sub">数据来自 ${escapeHtml(state.session?.session_id || '当前会话')}</p><div class="giant-form"><div class="giant-field wide"><span>任务目标</span><b>${escapeHtml(prototype.goal || demand.core_problem || '等待确认')}</b></div><div class="giant-field"><span>当前进度</span><b>${Number(prototype.progress || 0)}%</b></div><div class="giant-field"><span>本次计时</span><b class="metric">${escapeHtml(prototype.elapsed || '00:00')}</b></div></div><div class="prototype-window"><header><i></i><i></i><i></i></header><div class="proto-body"><div class="proto-menu"><i></i><i></i><i></i><i></i></div><div class="proto-main"><div></div><div></div><div></div></div></div></div></section>
    <section class="giant-col"><span class="giant-label">03 · 需求与价值 / OUTCOME</span><div class="summary-card"><h3>需求确认单</h3><dl><div><dt>问题完整度</dt><dd>${Number(demand.completeness || 0)}%</dd></div><div><dt>确认状态</dt><dd>${demand.confirmed ? '已确认' : '待确认'}</dd></div><div><dt>预计验证周期</dt><dd>${escapeHtml(demand.cycle || '待确认')}</dd></div><div><dt>数据准备</dt><dd>${escapeHtml(demand.next_action || '待确认')}</dd></div></dl></div><div class="summary-card"><h3>第一阶段交付</h3><dl>${ipdPhases[0].outputs.map((output) => `<div><dt>${escapeHtml(output)}</dt><dd>${currentSessionData().artifacts?.[output] ? '已更新' : '基线版本'}</dd></div>`).join('')}</dl></div><div class="value-card"><span>目标改善</span><b class="metric">${escapeHtml(demand.target_metric || '待确认')}</b><small>${escapeHtml(currentInsight().judgment || '')}</small></div></section>
  </div>`;
}

function giantOrchestrationView() {
  const phase = ipdPhases[state.selectedPhase];
  const demand = currentDemand();
  return `<div class="giant-ipd ${state.pipelinePlaying ? 'is-playing' : ''}">
    <section class="giant-ipd-left"><div class="giant-ipd-label">01 · 需求如何进入 IPD</div><div class="giant-demand"><span>${demand.confirmed ? '已确认需求' : '待确认需求'}</span><h2>${escapeHtml(demand.core_problem || '等待需求输入')}</h2><p>${escapeHtml(demand.target_metric || '')}</p><div><b>关键用户</b><span>${escapeHtml(demand.users || '待确认')}</span></div><div><b>首期范围</b><span>${escapeHtml(demand.cycle || '待确认')}</span></div></div><div class="giant-phase-list">${ipdPhases.map((item, i) => `<button class="${i === state.selectedPhase ? 'active' : ''}" data-ipd-phase="${i}"><span>0${i + 1}</span><div><b>${item.name}</b><small>${item.short}</small></div></button>`).join('')}</div></section>
    <section class="giant-ipd-center"><div class="giant-ipd-label">02 · ${phase.name}阶段 · MULTI-AGENT COLLABORATION</div><div class="giant-stage-head"><div><span>当前阶段</span><h2>${phase.name}：${phase.short}</h2><p>${phase.objective}</p></div><strong>${phase.agents.length} AGENTS</strong></div>${approvalRouteBar(phase, true)}<div class="giant-agent-flow"><div class="giant-source"><span>INPUT</span><b>${phase.inputs[0]}</b></div><div class="giant-stream"><i></i><i></i><i></i></div><div class="giant-agent-grid">${phase.agents.map(agent => `<button class="giant-agent ${agent.id === state.selectedAgent ? 'active' : ''}" data-ipd-agent="${agent.id}"><span>${agent.base} × ${agent.id}</span><b>${agent.name}</b><small>${agent.role}</small><em>${baseAgents[agent.base].verb}</em></button>`).join('')}</div><div class="giant-stream"><i></i><i></i><i></i></div><div class="giant-human"><span>HUMAN GATE</span><b>专家确认</b><small>拒绝 / 补充 / 通过</small></div></div><div class="collab-ticker"><span class="pulse"></span><b>${state.pipelinePlaying ? '协作演示进行中' : '协作演示已暂停'}</b><p>${phase.agents[0].base} 挂载“${phase.agents[0].name}”专业角色；所有判断都将附带证据来源。</p><button data-ipd-play>${state.pipelinePlaying ? '暂停' : '播放协作'}</button></div></section>
    <section class="giant-ipd-right"><div class="giant-ipd-label">03 · 交付件与评审门</div><div class="giant-gates">${phase.reviews.map((review) => { const reviewer = humanReviewers[review] || humanReviewers.TR1; const reviewState = reviewStatus[getReviewState(review)]; return `<button class="giant-gate ${reviewState[1]}" data-review-gate="${review}"><span>${review}</span><div><b>${reviewer.role}</b><small>${reviewer.person} · ${reviewState[0]}</small></div></button>`; }).join('')}</div><div class="giant-output-list"><h3>本阶段计划产出 · 点击演示</h3>${phase.outputs.map((output, i) => `<button data-artifact-title="${output}"><span>${i + 1}</span><b>${output}</b><em>${i === 0 && state.selectedPhase === 0 ? '生成中' : '打开 ↗'}</em></button>`).join('')}</div><div class="giant-redline"><span>IPD REDLINE</span><b>AI 不拥有评审签字权</b><p>技术与投资决策必须由对应层级的人在飞书完成确认。</p></div><button class="giant-back" data-giant-back>返回成果工作台</button></section>
    ${artifactOverlay()}${feishuReviewOverlay()}${assistantDock()}
  </div>`;
}

function giantArtifactView() {
  const detail = getArtifactDetail(state.selectedArtifact || ipdPhases[state.selectedPhase].outputs[0]);
  const outlines = ['业务结论', '关键证据', '方案内容', '风险与边界', '下一步行动'];
  const gate = detail.phase.reviews.find((review) => getReviewState(review) !== 'approved') || detail.phase.reviews.at(-1);
  return `<div class="giant-artifact-screen"><section class="giant-artifact-nav"><div class="giant-ipd-label">01 · IPD 交付件目录</div><button class="giant-artifact-back" data-giant-orchestration>← 返回 IPD 编排全景</button><div class="giant-artifact-meta"><span>0${detail.phaseIndex + 1} · ${detail.phase.name}阶段</span><h2>${detail.title}</h2><p>${detail.summary}</p></div><nav>${outlines.map((item, i) => `<button class="${i === 0 ? 'active' : ''}"><span>0${i + 1}</span>${item}</button>`).join('')}</nav><div class="artifact-owner"><span>主责专业角色</span><b>${detail.owner.id} · ${detail.owner.name}</b><small>${detail.owner.base} 基础 Agent挂载 ${detail.owner.role}</small></div></section><main class="giant-artifact-main"><div class="giant-ipd-label">02 · LIVE DELIVERABLE · 演示内容</div><header><div><span>AI GENERATED · V0.${detail.phaseIndex + 1}</span><h1>${detail.title}</h1></div><button data-artifact-open-current>查看详情与来源</button></header><p class="artifact-lead">${detail.summary}</p>${artifactDemo(detail, true)}<div class="artifact-evidence-strip"><div><span>来源</span><b>需求确认单 · 现场调研 · AI Lab 知识库</b></div><button data-review-gate="${gate}"><span>飞书人工评审</span><b>${gate} · ${reviewStatus[getReviewState(gate)][0]}</b></button><div><span>职责边界</span><b>AI 产出 · 人工签字</b></div></div></main><aside class="giant-presenter"><div class="giant-ipd-label">03 · AI 数字人讲解</div><div class="presenter-stage"><div class="presenter-halo"></div><div class="presenter-body"><div class="presenter-face"><i></i><i></i><b></b></div></div><div class="presenter-wave"><i></i><i></i><i></i><i></i><i></i></div></div><div class="presenter-name"><span>AI GENERATED PRESENTER</span><b>小融 · IPD 讲解员</b><small>讲解内容基于当前交付件和知识库</small></div><div class="presenter-subtitle"><span>实时字幕 · 01 / 03</span><p>${detail.summary}</p></div><div class="presenter-actions"><button data-presenter-question="为什么需要这份交付件？">为什么需要它？</button><button data-presenter-question="进入下一阶段前还缺什么？">下一步缺什么？</button></div><div class="presenter-composer"><span>继续追问当前内容…</span><button>${icon('send')}</button></div></aside>${artifactOverlay()}${feishuReviewOverlay()}</div>`;
}

function livePrototypeView() {
  const prototype = currentPrototype();
  const configured = state.content?.screens?.['screen-07'] || {};
  const steps = configured.steps || [];
  return `<div class="screen">
    ${screenHeader('LIVE PROTOTYPE', '原型可操作')}
    <div class="screen-content"><p class="kicker">WORKBUDDY · GENERATED EXPERIENCE</p><h2 class="hero-title">${escapeHtml(prototype.title || configured.title || '等待生成原型')}</h2><p class="lead">${escapeHtml(prototype.goal || '需求确认后由 AI 生成可操作原型。')}</p><div class="live-layout"><aside class="panel live-side"><h3>任务 ${escapeHtml(configured.task_id || '')}</h3><div class="live-nav">${steps.map((step, index) => `<div class="${index === 1 ? 'active' : ''}">0${index + 1} · ${escapeHtml(step)}</div>`).join('')}</div></aside><section class="panel live-main"><div class="panel-head" style="margin:-16px -16px 14px"><strong>现场执行面板</strong><span class="status">计时中 · ${escapeHtml(prototype.elapsed || '00:00')}</span></div><div class="live-kpis"><div class="live-kpi"><span>目标总时长</span><b class="metric">${escapeHtml(prototype.target_time || '—')}</b></div><div class="live-kpi"><span>当前进度</span><b class="metric">${Number(prototype.progress || 0)}%</b></div><div class="live-kpi"><span>会话状态</span><b style="color:var(--mint)">${escapeHtml(state.session?.status || 'active')}</b></div></div><div class="task-board"><div class="task-col"><h4>当前操作</h4><div class="task">${escapeHtml(steps[1] || '等待任务')}<b>进行中</b></div></div><div class="task-col"><h4>数据来源</h4><div class="task">当前会话原型数据<b>${escapeHtml(state.session?.session_id || '')}</b></div></div><div class="task-col"><h4>现场记录</h4><div class="task">记录将写入独立会话<b>支持继续完善</b></div></div></div></section></div></div>
  </div>`;
}

const experienceSteps = ['进入体验','需求问诊','确认需求','深度洞察','生成原型','体验修改','方案带走'];

function experienceWelcome(station) {
  const roles = state.content?.experience?.roles || [];
  return `<div class="experience-welcome"><section class="panel welcome-card"><p class="kicker">START YOUR OWN AI JOURNEY</p><h2 class="hero-title">今天，你想让 AI<br>帮你解决<em>什么问题？</em></h2><p class="lead">选择一个角色开始，后续内容将写入本工位独立会话。</p><div class="role-grid">${roles.map((role) => `<button class="role-card" data-exp-role="${escapeHtml(role.name)}" data-exp-next><b>${escapeHtml(role.name)}</b><span>${escapeHtml(role.description)}</span></button>`).join('')}</div></section><aside class="panel station-guide"><h3>体验中心 ${station}</h3><ol><li>全过程约 8–12 分钟</li><li>当前 Session：${escapeHtml(state.session?.session_id || '连接中')}</li><li>每个工位拥有独立持久化会话</li></ol><div class="privacy">主控端只读取工位、阶段和状态，不读取详细对话。</div></aside></div>`;
}

function experienceMiddle(step) {
  const session = currentSessionData();
  const demand = currentDemand();
  const insight = currentInsight();
  const prototype = currentPrototype();
  const messages = state.chatMessages;
  const copy = {
    1: ['先聊聊你的真实问题', '每条消息都会进入本工位独立会话。'],
    2: ['确认我们理解得对不对', '只有确认后的结构化需求才会进入 IPD。'],
    3: ['看见问题背后的机会', '洞察来自当前需求、知识检索和 AI 分析。'],
    4: ['第一个原型已经生成', '原型数据与当前会话关联，可继续修改。'],
    5: ['现在，请亲手试一试', '修改结果会持续写回当前会话。'],
  }[step];
  let preview = '';
  if (step === 1) preview = `<div class="experience-chat-log">${emptyChatState()}${messages.slice(-6).map((message) => `<div class="bubble ${message.role === 'user' ? 'user' : 'ai'}">${escapeHtml(message.content)}</div>`).join('')}${clarifyCard()}${liveChatFeedback()}</div><div class="chat-composer" style="margin:18px 0 0"><input id="experience-chat-input" placeholder="向大架构师说出你的真实业务问题…" ${['connecting', 'reconnecting', 'generating', 'waiting'].includes(state.hermesStatus) ? 'disabled' : ''}><button ${state.hermesStatus === 'generating' ? 'data-demand-stop' : 'data-experience-send'} aria-label="${state.hermesStatus === 'generating' ? '停止生成' : '发送'}">${icon(state.hermesStatus === 'generating' ? 'stop' : 'send')}</button></div>`;
  else if (step === 2) preview = `<div class="score-card"><strong>${Number(demand.completeness || 0)}%</strong><div><span>需求完整度</span><b>${escapeHtml(demand.core_problem || '等待收敛')}</b></div></div><div class="action-box"><span>目标指标</span><b>${escapeHtml(demand.target_metric || '待确认')}</b></div>`;
  else if (step === 3) preview = `<div class="score-card"><strong>${(insight.causes || []).length}</strong><div><span>关键根因</span><b>${escapeHtml(insight.judgment || '等待生成')}</b></div></div><div class="action-box"><span>第一步建议</span><b>${escapeHtml(insight.recommendation || demand.next_action || '待生成')}</b></div>`;
  else preview = `<div class="prototype-window" style="height:300px"><header><i></i><i></i><i></i></header><div class="proto-body" style="height:268px"><div class="proto-menu"><i></i><i></i><i></i><i></i></div><div class="proto-main"><div></div><div></div><div></div></div></div></div><p class="lead">${escapeHtml(prototype.title || '等待生成原型')} · ${Number(prototype.progress || 0)}%</p>`;
  return `<div class="experience-step"><section class="panel step-copy"><span class="tag orange">步骤 0${step + 1}</span><h2 style="margin-top:16px">${copy[0]}</h2><p>${copy[1]}</p><div class="step-actions"><button class="back" data-exp-back>上一步</button><button class="next" data-exp-next>${step === 5 ? '生成建设方案' : '保存并继续'}</button></div></section><section class="panel step-preview"><div class="panel-head" style="margin:-17px -17px 16px"><strong>${step === 1 ? '与首席解决方案架构师对话' : step >= 4 ? '可操作原型' : '当前会话数据'}</strong><span class="status">${step === 1 ? '专属技能已加载' : '后端已连接'}</span></div>${preview}</section></div>`;
}

function experienceResult() {
  const squares = Array.from({ length: 49 }, (_, i) => `<i style="${(i * 7 + 3) % 11 === 0 ? 'background:transparent' : ''}"></i>`).join('');
  return `<section class="panel qr-card"><div><span class="tag mint">全流程已完成</span><h2 style="margin-top:17px">你的《AI 建设建议方案》<br>已经生成。</h2><p>方案关联会话 ${escapeHtml(state.session?.session_id || '')}，包括需求摘要、洞察、原型方向和验证范围。</p><div style="display:flex;gap:8px;margin-top:20px"><button class="soft-button" data-exp-back>返回修改</button><button class="mini-action" data-experience-submit style="min-height:44px">提交需求并预约沟通</button></div></div><div class="qr-box" aria-label="专属方案二维码">${squares}</div></section>`;
}

function experienceView() {
  const station = state.view.split('-').pop();
  const body = state.experienceStep === 0 ? experienceWelcome(station) : state.experienceStep === 6 ? experienceResult() : experienceMiddle(state.experienceStep);
  return `<div class="screen experience-screen">${screenHeader(`EXPERIENCE CENTER ${station}`, '独立会话')}
    <div class="screen-content"><div class="experience-top"><div><p class="kicker">YOUR OWN AI CO-CREATION</p><h2 class="hero-title" style="font-size:34px">完整体验，从一个<em>真实问题</em>开始。</h2></div><div class="station-badge"><small>当前工位</small><b>CENTER ${station}</b></div></div><div class="journey">${experienceSteps.map((label,i)=>`<button data-exp-step="${i}" class="${i<state.experienceStep?'done':''} ${i===state.experienceStep?'active':''}"><span>${i+1}</span>${label}</button>`).join('')}</div><div class="experience-body">${body}</div></div>
  </div>`;
}

function parallelWorkbenchView() {
  const centers = Array.from({ length: 5 }, (_, index) => {
    const center = state.centers.find((item) => Number(item.slot) === index + 1);
    return center || { slot: String(index + 1), role: '等待访客', step: 0, status: 'idle' };
  });
  return `<div class="screen">${screenHeader('PARALLEL EXPERIENCE', '五工位独立会话')}<div class="screen-content"><div class="experience-top"><div><p class="kicker">5 ISOLATED SESSIONS</p><h2 class="hero-title">五个人，同时完成自己的<em>全流程体验。</em></h2></div><span class="tag mint">${centers.filter((item) => item.status !== 'idle').length} / 5 使用中</span></div><div class="role-grid" style="grid-template-columns:repeat(5,minmax(0,1fr));margin-top:24px">${centers.map((center) => `<button class="role-card" data-view="experience-0${center.slot}"><span>CENTER 0${center.slot}</span><b>${escapeHtml(center.role)}</b><small>${escapeHtml(experienceSteps[center.step] || '进入体验')}</small><em>${center.status === 'submitted' ? '已提交' : center.status === 'idle' ? '可进入' : '运行中'}</em></button>`).join('')}</div></div></div>`;
}

function schemeExportView() {
  return `<div class="screen">${screenHeader('SCHEME EXPORT', state.session?.status === 'submitted' ? '方案已提交' : '等待提交')}<div class="screen-content">${experienceResult()}${state.session?.slot === 'main' ? '<button class="form-cta" data-main-visit-complete style="margin-top:18px">完成本次参观并通知导览主控台</button>' : ''}</div></div>`;
}

async function sendSessionMessage(inputId, reuseExisting = false) {
  const input = document.getElementById(inputId);
  const question = input?.value.trim();
  if (!question) return;
  if (['generating', 'waiting'].includes(state.hermesStatus)) {
    showToast(state.hermesStatus === 'waiting' ? '请先回答当前澄清问题' : '大架构师正在回复，可先停止本轮');
    return;
  }
  input.value = '';
  state.avatarSpeaking = true;
  state.streamingReply = '';
  state.chatError = '';
  state.lastQuestion = question;
  try {
    if (!reuseExisting) state.chatMessages.push({ role: 'user', content: question });
    render('refresh');
    const config = getScreenConfig('screen-03');
    const prompt = state.view === 'screen-03' ? demandPolicyPrompt(question) : question;
    await window.showroomApi.submitHermesPrompt(prompt, {
      skillCommand: config.skill_command,
      stationContext: config.station_context,
    });
  } catch (error) {
    state.chatError = error.message;
    state.avatarSpeaking = false;
    showToast(`架构师回复失败：${error.message}`);
    render('refresh');
  }
}

const builders = {
  controller: controllerView,
  'screen-00': introView,
  'screen-01': welcomeView,
  'screen-02': dashboardView,
  'screen-03': clinicView,
  'screen-03-team': staffingView,
  'screen-04': insightView,
  'screen-05': pipelineView,
  'screen-06': giantWorkbenchView,
  'screen-07': livePrototypeView,
  'screen-08': parallelWorkbenchView,
  'screen-09': schemeExportView,
};

function attachScreenActions() {
  document.querySelectorAll('#screen-canvas [data-view]').forEach((button) => button.addEventListener('click', () => setView(button.dataset.view)));
  document.querySelector('[data-intro-replay]')?.addEventListener('click', () => {
    state.introSkipped = false;
    render();
  });
  document.querySelector('[data-intro-skip]')?.addEventListener('click', () => {
    state.introSkipped = true;
    render();
  });
  document.querySelector('[data-visitor-insight]')?.addEventListener('click', beginVisitorInsight);
  document.querySelector('[data-host-retry]')?.addEventListener('click', async () => {
    state.hermesStatus = 'online';
    state.hermesDetail = '';
    state.chatError = '';
    try {
      // The page may still hold a Hermes session created with an older model
      // provider.  Re-bootstrap first, then reconnect exactly once against
      // the server's current active session (gpt-luna in production).
      window.showroomApi.suspendHermes({ suspendShowroom: false });
      await window.showroomApi.init({ force: true, skipHermes: true });
      state.session = await window.showroomApi.saveSession({ data: { host_greeting_initialized: false } });
      await window.showroomApi.retryHermes();
    } catch (error) {
      showToast(`重新备课失败：${friendlyHermesError(error.message)}`);
    }
  });
  document.getElementById('visitor-history')?.addEventListener('change', (event) => {
    document.querySelector('.visitor-history-session')?.classList.toggle('is-hidden', !event.currentTarget.checked);
  });
  document.querySelector('[data-visit-complete]')?.addEventListener('click', () => {
    state.visitEndConfirmOpen = true;
    render('refresh');
  });
  document.querySelector('[data-main-visit-complete]')?.addEventListener('click', async () => {
    try {
      await window.showroomApi.completeVisit('screen-09');
      showToast('已通知导览主控台，由主持人确认换场');
    } catch (error) { showToast(`通知失败：${error.message}`); }
  });
  document.querySelector('[data-visit-continue]')?.addEventListener('click', () => {
    state.visitCompleteNotice = null;
    render('refresh');
  });
  document.querySelector('[data-visit-open-confirm]')?.addEventListener('click', () => {
    state.visitEndConfirmOpen = true;
    render('refresh');
  });
  document.querySelector('[data-visit-end-cancel]')?.addEventListener('click', () => {
    if (state.visitEndBusy) return;
    state.visitEndConfirmOpen = false;
    render('refresh');
  });
  document.querySelector('[data-visit-end-confirm]')?.addEventListener('click', async () => {
    if (state.visitEndBusy) return;
    state.visitEndBusy = true;
    render('refresh');
    try {
      const result = await window.showroomApi.rolloverVisit('controller');
      const adopted = applySessionRollover(result.session, result.runtime);
      render('refresh');
      showToast(`换场完成 · 新 Session ${result.session.session_id}`);
      if (adopted) await window.showroomApi.init({ force: true });
    } catch (error) {
      state.visitEndBusy = false;
      state.visitEndConfirmOpen = true;
      render('refresh');
      showToast(`换场失败，当前接待未清空：${error.message}`);
    }
  });
  document.querySelectorAll('[data-insight-section]').forEach((button) => button.addEventListener('click', () => {
    const target = document.getElementById(button.dataset.insightSection);
    state.insightSelectedSection = button.dataset.insightSection;
    target?.scrollIntoView({ behavior: state.paused ? 'auto' : 'smooth', block: 'start' });
    document.querySelectorAll('[data-insight-section]').forEach((item) => item.classList.toggle('active', item === button));
  }));
  document.getElementById('insight-report-document')?.addEventListener('mouseup', () => {
    const selection = window.getSelection();
    const text = selection?.toString().trim() || '';
    if (!text) return;
    const anchor = selection.anchorNode?.parentElement?.closest('[data-report-section]');
    state.insightSelectedText = text.slice(0, 2000);
    state.insightSelectedSection = anchor?.dataset.reportSection || state.insightSelectedSection;
    render('refresh');
  });
  document.querySelectorAll('[data-insight-ask-section]').forEach((button) => button.addEventListener('click', () => {
    state.insightSelectedSection = button.dataset.insightAskSection;
    const input = document.getElementById('insight-assistant-input');
    if (input) { input.value = '请解释本章的关键判断及其证据，并指出还存在的相反证据。'; input.focus(); }
  }));
  document.querySelector('[data-insight-clear-selection]')?.addEventListener('click', () => {
    state.insightSelectedText = '';
    render('refresh');
  });
  document.querySelectorAll('[data-insight-context-action]').forEach((button) => button.addEventListener('click', () => {
    const selected = state.insightSelectedText;
    const prompts = {
      explain: '请解释这段内容的业务含义、判断依据和边界。',
      ask: '请围绕这段内容继续追问，指出还需要客户澄清的问题。',
      revise: '请根据当前上下文修改这段内容，并回填到本章报告。',
      verify: '请核验这段内容的证据，区分事实、推断、假设和TBD，并指出相反证据。',
    };
    const action = button.dataset.insightContextAction;
    const prompt = `${prompts[action] || prompts.ask}\n\n已选内容：${selected}`;
    sendInsightAssistant(prompt, { forceRevision: action === 'revise' });
  }));
  document.querySelectorAll('[data-insight-quick]').forEach((button) => button.addEventListener('click', () => sendInsightAssistant(button.dataset.insightQuick)));
  document.querySelectorAll('[data-placement-choice]').forEach((button) => button.addEventListener('click', () => {
    const field = button.dataset.placementChoice;
    const original = state.insightActiveRequest?.userInstruction || '把上一轮内容回填到报告';
    state.insightPlacementCandidates = [];
    state.insightSelectedSection = INSIGHT_FIELD_SECTIONS[field] || state.insightSelectedSection;
    sendInsightAssistant(`${original}\n请将应回填内容明确映射到字段 ${field}，并生成语义回填草案。`, { forceRevision: true });
  }));
  document.querySelector('[data-insight-assistant-send]')?.addEventListener('click', () => sendInsightAssistant(document.getElementById('insight-assistant-input')?.value));
  document.getElementById('insight-assistant-input')?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      sendInsightAssistant(event.currentTarget.value);
    }
  });
  document.querySelector('[data-insight-assistant-stop]')?.addEventListener('click', async () => {
    await window.showroomApi.interruptHermes().catch(() => null);
    state.insightAssistantBusy = false;
    state.insightAssistantStatus = '';
    state.streamingReply = '';
    render('refresh');
  });
  document.querySelectorAll('[data-insight-clarify]').forEach((button) => button.addEventListener('click', async () => {
    const answer = button.dataset.insightClarify;
    const requestId = state.pendingClarify?.request_id;
    if (!answer || !requestId) return;
    state.insightAssistantMessages.push({ role: 'assistant', content: state.pendingClarify.question || '请补充选择' });
    state.insightAssistantMessages.push({ role: 'user', content: answer });
    state.pendingClarify = null;
    state.insightAssistantStatus = '已收到选择，正在继续处理';
    render('refresh');
    try { await window.showroomApi.respondHermesClarify(requestId, answer); }
    catch (error) { showToast(`提交澄清失败：${error.message}`); }
  }));
  document.querySelector('[data-revision-apply]')?.addEventListener('click', async () => {
    const revision = state.insightPendingRevision || (currentInsightReview().revisions || []).find((item) => item.revision_id === currentInsightReview().pending_revision_id);
    const revisionId = revision?.revision_id;
    if (!revisionId) return;
    state.insightRevisionApplying = true;
    render('refresh');
    try {
      const result = await window.showroomApi.applyInsightRevision(revisionId);
      state.session = result.session;
      state.insightPendingRevision = null;
      state.insightRevisionError = null;
      state.insightRevisionApplying = false;
      focusAppliedInsightSections(revision, result);
      showToast(`已回填到报告，当前版本 ${result.version || currentInsightReview().version}`);
    } catch (error) {
      state.insightRevisionApplying = false;
      showToast(`应用回填失败：${error.message}`);
      render('refresh');
    }
  });
  document.querySelector('[data-revision-discard]')?.addEventListener('click', async () => {
    const revisionId = state.insightPendingRevision?.revision_id || currentInsightReview().pending_revision_id;
    if (!revisionId) return;
    try {
      const result = await window.showroomApi.discardInsightRevision(revisionId);
      state.session = result.session;
      state.insightPendingRevision = null;
      state.insightRevisionError = null;
      showToast('已放弃本次修订，报告未改变');
      render('refresh');
    } catch (error) { showToast(`放弃修订失败：${error.message}`); }
  });
  document.querySelector('[data-revision-continue]')?.addEventListener('click', () => document.getElementById('insight-assistant-input')?.focus());
  document.querySelector('[data-revision-repair]')?.addEventListener('click', () => {
    const request = state.insightRevisionError?.request || state.insightActiveRequest;
    if (!request || state.insightAssistantBusy) return;
    repairInsightRevision(request, { manual: true }).catch((error) => {
      state.insightAssistantBusy = false;
      state.insightAssistantStatus = '';
      state.insightRevisionError = { message: error.message, request };
      showToast(`重新生成回填草案失败：${error.message}`);
      render('refresh');
    });
  });
  document.querySelector('[data-insight-confirm]')?.addEventListener('click', async () => {
    const coverage = currentInsightReview().coverage || {};
    if (!(coverage.can_submit_review ?? coverage.confirmable)) {
      state.insightReadinessOpen = true;
      render('refresh');
      return;
    }
    try {
      const result = await window.showroomApi.createInsightReviewTask();
      showToast('已指派AI概念评审会，正在独立会签');
      await runInsightReviewTask(result);
    } catch (error) { showToast(`暂不能提交评审：${error.message}`); }
  });
  document.querySelectorAll('[data-readiness-close]')?.forEach((button) => button.addEventListener('click', () => {
    state.insightReadinessOpen = false;
    state.insightTbdTarget = null;
    render('refresh');
  }));
  document.querySelectorAll('[data-readiness-locate]').forEach((button) => button.addEventListener('click', () => {
    state.insightReadinessOpen = false;
    const target = document.getElementById(button.dataset.readinessLocate);
    target?.scrollIntoView({ behavior: motionSystem.reduceMotion ? 'auto' : 'smooth', block: 'start' });
  }));
  document.querySelectorAll('[data-readiness-ai]').forEach((button) => button.addEventListener('click', () => {
    state.insightReadinessOpen = false;
    sendInsightAssistant(`请基于现有报告和证据补齐“${button.dataset.readinessAi}”。无法确认的内容必须登记为带责任人与补证动作的TBD，并生成语义回填草案。`, { forceRevision: true });
  }));
  document.querySelectorAll('[data-readiness-tbd]').forEach((button) => button.addEventListener('click', () => {
    state.insightTbdTarget = (currentInsightReview().coverage?.blocking_items || [])[Number(button.dataset.readinessTbd)] || null;
    render('refresh');
  }));
  document.querySelector('[data-tbd-cancel]')?.addEventListener('click', () => { state.insightTbdTarget = null; render('refresh'); });
  document.querySelector('[data-tbd-form]')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const target = state.insightTbdTarget;
    if (!target) return;
    try {
      const result = await window.showroomApi.registerInsightTbd({ field: target.field, reason: form.get('reason'), owner: form.get('owner'), action: form.get('action'), due_at: form.get('due_at') });
      state.session = result.session;
      state.insightTbdTarget = null;
      showToast('已登记为受控TBD，可继续检查其他缺口');
      render('refresh');
    } catch (error) { showToast(`登记TBD失败：${error.message}`); }
  });
  document.querySelector('[data-review-task-retry]')?.addEventListener('click', async () => {
    try { await runInsightReviewTask(await window.showroomApi.retryInsightReviewTask(currentInsightReviewGate().task_id)); }
    catch (error) { showToast(`重新评审失败：${error.message}`); }
  });
  document.querySelector('[data-review-notify-retry]')?.addEventListener('click', async () => {
    try {
      const result = await window.showroomApi.retryInsightReviewNotification(currentInsightReviewGate().task_id);
      state.session = result.session;
      showToast('飞书通知已重新提交');
      render('refresh');
    } catch (error) { showToast(`重试通知失败：${error.message}`); }
  });
  document.querySelector('[data-review-override]')?.addEventListener('click', async () => {
    const reason = window.prompt('请填写现场确认并放行的理由（将写入审计记录）');
    if (!reason || reason.trim().length < 4) return;
    try {
      const result = await window.showroomApi.overrideInsightReviewTask(currentInsightReviewGate().task_id, reason.trim());
      state.session = result.session;
      showToast('现场放行已记录，正在进入001 IPD实践');
      setView('screen-05');
    } catch (error) { showToast(`现场放行失败：${error.message}`); }
  });
  document.querySelector('[data-insight-reopen]')?.addEventListener('click', async () => {
    try {
      const result = await window.showroomApi.reopenInsight();
      state.session = result.session;
      showToast('已基于确认快照发起新草稿版本');
      render('refresh');
    } catch (error) { showToast(`发起新版本失败：${error.message}`); }
  });
  document.querySelector('[data-insight-return-demand]')?.addEventListener('click', async () => {
    if (!window.confirm('退回003会废止当前洞察与需求的输入关系，但历史版本仍会保留。继续吗？')) return;
    try {
      const result = await window.showroomApi.reopenDemand();
      state.session = result.session;
      state.insightAssistantMessages = [];
      state.insightPendingRevision = null;
      showToast('已退回003，历史洞察已保留为作废版本');
      setView('screen-03');
    } catch (error) { showToast(`退回需求失败：${error.message}`); }
  });
  document.querySelector('[data-action="confirm-demand"]')?.addEventListener('click', async () => {
    const demand = { ...currentDemand() };
    document.querySelectorAll('[data-demand-field]').forEach((field) => {
      demand[field.dataset.demandField] = field.value.trim();
    });
    try {
      showToast('需求已确认 · 正在集结AI项目组');
      await beginInsightFlow(demand);
    } catch (error) {
      showToast(`需求确认失败：${error.message}`);
    }
  });
  document.querySelectorAll('[data-employee-id]').forEach((button) => button.addEventListener('click', () => {
    state.selectedEmployeeId = button.dataset.employeeId;
    state.insightAutoPaused = true;
    render('agent');
  }));
  document.querySelector('.employee-badge')?.addEventListener('toggle', (event) => {
    if (event.currentTarget.open) state.insightAutoPaused = true;
  });
  document.querySelector('[data-insight-open]')?.addEventListener('click', () => {
    clearInsightAutoAdvance();
    setView('screen-04');
  });
  document.querySelectorAll('[data-insight-stop]').forEach((button) => button.addEventListener('click', async () => {
    const job = currentInsightJob();
    if (!job.job_id) return;
    try {
      const result = await window.showroomApi.interruptInsightJob(job.job_id);
      state.session = result.session;
      state.insightTask = '';
      render('refresh');
    } catch (error) { showToast(`停止失败：${error.message}`); }
  }));
  document.querySelector('[data-insight-retry]')?.addEventListener('click', async () => {
    try {
      const result = await window.showroomApi.retryInsightJob(currentInsightJob().job_id);
      state.session = result.session;
      startInsightServerPolling();
      render('refresh');
    } catch (error) { showToast(`重新执行失败：${error.message}`); }
  });
  document.querySelectorAll('[data-demand-field]:not([disabled])').forEach((field) => field.addEventListener('change', async () => {
    const name = field.dataset.demandField;
    if (!name) return;
    try {
      await window.showroomApi.saveDemandDraft({ [name]: field.value.trim() }, [name]);
    } catch (error) {
      showToast(`需求草稿保存失败：${error.message}`);
    }
  }));
  document.querySelector('[data-demand-send]')?.addEventListener('click', () => sendSessionMessage('demand-chat-input'));
  document.querySelector('[data-demand-stop]')?.addEventListener('click', async () => {
    try {
      await window.showroomApi.interruptHermes();
      state.avatarSpeaking = false;
      state.streamingReply = '';
      state.pendingClarify = null;
      render('refresh');
    } catch (error) {
      showToast(`停止失败：${error.message}`);
    }
  });
  document.getElementById('demand-chat-input')?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') sendSessionMessage('demand-chat-input');
  });
  document.querySelector('[data-chat-retry]')?.addEventListener('click', () => {
    const inputId = state.view.startsWith('experience-') ? 'experience-chat-input' : 'demand-chat-input';
    const input = document.getElementById(inputId);
    if (!input || !state.lastQuestion) return;
    input.value = state.lastQuestion;
    state.chatError = '';
    sendSessionMessage(inputId, true);
  });
  document.querySelector('[data-hermes-reconnect]')?.addEventListener('click', async () => {
    state.hermesRetryStopped = false;
    state.chatError = '';
    state.hermesStatus = 'connecting';
    state.hermesDetail = '正在重新连接大架构师';
    render('refresh');
    try {
      await window.showroomApi.retryHermes();
    } catch (error) {
      showToast(`重新连接失败：${error.message}`);
    }
  });
  document.querySelectorAll('[data-clarify-choice]').forEach((button) => button.addEventListener('click', async () => {
    const choice = button.dataset.clarifyChoice;
    const requestId = state.pendingClarify?.request_id;
    if (!choice || !requestId) return;
    document.querySelectorAll('[data-clarify-choice]').forEach((item) => { item.disabled = true; });
    try {
      const question = state.pendingClarify?.question;
      if (question && state.chatMessages.at(-1)?.content !== question) {
        state.chatMessages.push({ role: 'assistant', content: question });
      }
      state.chatMessages.push({ role: 'user', content: choice });
      state.pendingClarify = null;
      render('refresh');
      await window.showroomApi.respondHermesClarify(requestId, choice);
    } catch (error) {
      state.chatError = error.message;
      state.avatarSpeaking = false;
      showToast(`提交澄清失败：${error.message}`);
      render('refresh');
    }
  }));
  document.querySelectorAll('[data-demand-field]').forEach((field) => field.addEventListener('change', async () => {
    try {
      const session = await window.showroomApi.saveSession({ data: { demand: { [field.dataset.demandField]: field.value.trim() } } });
      state.session = session;
      showToast('需求字段已保存');
    } catch (error) {
      showToast(`自动保存失败：${error.message}`);
    }
  }));
  document.querySelector('[data-action="ignite"]')?.addEventListener('click', () => { setView('screen-06'); showToast('001 实战主屏已启动'); });
  document.querySelectorAll('[data-ipd-phase]').forEach((button) => button.addEventListener('click', () => {
    state.selectedPhase = Number(button.dataset.ipdPhase);
    state.selectedAgent = ipdPhases[state.selectedPhase].agents[0].id;
    state.selectedArtifact = null;
    state.artifactOpen = false;
    state.activeReview = null;
    state.reviewDecision = null;
    state.ipdDrawer = null;
    state.agentDetailOpen = false;
    render('phase');
  }));
  document.querySelectorAll('[data-ipd-agent]').forEach((button) => button.addEventListener('click', () => {
    state.selectedAgent = button.dataset.ipdAgent;
    render('agent');
  }));
  document.querySelectorAll('[data-ipd-drawer]').forEach((button) => button.addEventListener('click', () => {
    state.ipdDrawer = state.ipdDrawer === button.dataset.ipdDrawer ? null : button.dataset.ipdDrawer;
    render('ipd-drawer');
  }));
  document.querySelectorAll('[data-ipd-drawer-close]').forEach((button) => button.addEventListener('click', () => {
    closeSurface('.ipd-detail-drawer', () => { state.ipdDrawer = null; });
  }));
  document.querySelector('[data-agent-detail]')?.addEventListener('click', () => {
    state.agentDetailOpen = !state.agentDetailOpen;
    render('agent-detail');
  });
  document.querySelectorAll('[data-ipd-play]').forEach((button) => button.addEventListener('click', () => {
    state.pipelinePlaying = !state.pipelinePlaying;
    render(state.pipelinePlaying ? 'workflow-play' : 'workflow-pause');
  }));
  document.querySelector('[data-ipd-cast]')?.addEventListener('click', () => {
    state.giantMode = 'orchestration';
    setView('screen-06', 'cast');
    showToast('IPD 编排沙盘已投送到 06 主屏');
  });
  document.querySelector('[data-ipd-advance]')?.addEventListener('click', async () => {
    state.selectedPhase = Math.min(ipdPhases.length - 1, state.selectedPhase + 1);
    if (state.backendStatus === 'online') {
      try {
        state.session = await window.showroomApi.generateIpdArtifacts(state.selectedPhase);
      } catch (error) {
        showToast(`交付件生成失败：${error.message}`);
      }
    }
    state.selectedAgent = ipdPhases[state.selectedPhase].agents[0].id;
    state.ipdDrawer = null;
    state.agentDetailOpen = false;
    render('phase');
    showToast(`已进入${ipdPhases[state.selectedPhase].name}阶段`);
  });
  document.querySelectorAll('[data-review-gate]').forEach((button) => button.addEventListener('click', () => {
    state.activeReview = button.dataset.reviewGate;
    state.reviewDecision = null;
    render('review-open');
  }));
  document.querySelectorAll('[data-review-close]').forEach((button) => button.addEventListener('click', () => {
    closeSurface('.review-overlay', () => {
      state.activeReview = null;
      state.reviewDecision = null;
    });
  }));
  document.querySelectorAll('[data-review-decision]').forEach((button) => button.addEventListener('click', () => {
    state.reviewDecision = button.dataset.reviewDecision;
    render('review-decision');
  }));
  document.querySelector('[data-review-submit]')?.addEventListener('click', async (event) => {
    if (!state.reviewDecision) {
      showToast('请先选择通过、要求修改或拒绝');
      return;
    }
    const comment = document.getElementById('review-comment')?.value.trim();
    if (state.reviewDecision !== 'approved' && !comment) {
      showToast('要求修改或拒绝时，请填写审批意见');
      return;
    }
    const gate = state.activeReview;
    const decision = state.reviewDecision;
    const resultText = reviewStatus[decision][0];
    event.currentTarget.disabled = true;
    event.currentTarget.textContent = '正在提交…';
    try {
      if (state.backendStatus === 'online') {
        const snapshot = await window.showroomApi.submitReview(gate, decision, comment || '', ipdPhases[state.selectedPhase].name);
        applyBackendSnapshot(snapshot, false);
      } else {
        state.reviewStates[gate] = decision;
      }
      state.reviewDecision = null;
      render('review-result');
      showToast(`${state.capabilities.feishu_configured ? '飞书审批' : '平台审批'}已提交：${resultText}`);
    } catch (error) {
      event.currentTarget.disabled = false;
      event.currentTarget.textContent = '确认提交审批';
      showToast(`提交失败：${error.message}`);
    }
  });
  document.querySelector('[data-review-resubmit]')?.addEventListener('click', () => {
    state.reviewStates[state.activeReview] = 'pending';
    state.reviewDecision = null;
    render('review-open');
    showToast('AI 已完成修订，材料重新提交飞书');
  });
  document.querySelectorAll('[data-artifact-from-review]').forEach((button) => button.addEventListener('click', () => {
    state.selectedArtifact = button.dataset.artifactFromReview;
    state.artifactOpen = true;
    state.activeReview = null;
    render('artifact-open');
  }));
  document.querySelectorAll('[data-artifact-title]').forEach((button) => button.addEventListener('click', () => {
    state.selectedArtifact = button.dataset.artifactTitle;
    state.artifactOpen = true;
    state.avatarSpeaking = false;
    render('artifact-open');
  }));
  document.querySelector('[data-artifact-open-current]')?.addEventListener('click', () => {
    state.artifactOpen = true;
    render('artifact-open');
  });
  document.querySelector('[data-artifact-close]')?.addEventListener('click', () => {
    closeSurface('.artifact-overlay', () => { state.artifactOpen = false; });
  });
  document.querySelector('[data-artifact-overlay]')?.addEventListener('click', (event) => {
    if (event.target === event.currentTarget) {
      closeSurface('.artifact-overlay', () => { state.artifactOpen = false; });
    }
  });
  document.querySelector('[data-artifact-explain]')?.addEventListener('click', () => {
    state.artifactOpen = false;
    state.assistantOpen = true;
    state.avatarSpeaking = true;
    state.assistantQuestion = `请解释“${state.selectedArtifact}”对客户的价值。`;
    render('assistant');
  });
  document.querySelector('[data-artifact-project]')?.addEventListener('click', () => {
    state.artifactOpen = false;
    state.giantMode = 'artifact';
    state.avatarSpeaking = true;
    setView('screen-06', 'cast');
    showToast(`“${state.selectedArtifact}”已投送到 06 主屏`);
  });
  document.querySelector('[data-assistant-toggle]')?.addEventListener('click', () => {
    state.assistantOpen = true;
    render('assistant');
  });
  document.querySelector('[data-assistant-close]')?.addEventListener('click', () => {
    closeSurface('.assistant-panel', () => {
      state.assistantOpen = false;
      state.avatarSpeaking = false;
    });
  });
  document.querySelectorAll('[data-assistant-query]').forEach((button) => button.addEventListener('click', () => {
    askAssistant(button.dataset.assistantQuery);
  }));
  document.querySelector('[data-assistant-send]')?.addEventListener('click', () => {
    askAssistant(document.getElementById('assistant-input')?.value || '请解释当前内容。');
  });
  document.getElementById('assistant-input')?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') document.querySelector('[data-assistant-send]')?.click();
  });
  document.querySelector('[data-avatar-call]')?.addEventListener('click', () => {
    state.avatarSpeaking = !state.avatarSpeaking;
    render('assistant');
  });
  document.querySelectorAll('[data-presenter-question]').forEach((button) => button.addEventListener('click', () => {
    showToast(`数字人正在回答：${button.dataset.presenterQuestion}`);
  }));
  document.querySelector('[data-giant-orchestration]')?.addEventListener('click', () => {
    state.giantMode = 'orchestration';
    setView('screen-06', 'cast');
  });
  document.querySelector('[data-giant-back]')?.addEventListener('click', () => {
    state.giantMode = 'workbench';
    const params = new URLSearchParams(location.search);
    params.delete('mode');
    params.delete('artifact');
    history.replaceState({}, '', `${location.pathname}?${params.toString()}`);
    render();
  });
  document.querySelectorAll('[data-exp-step]').forEach((button) => button.addEventListener('click', async () => {
    state.experienceStep = Number(button.dataset.expStep);
    if (state.backendStatus === 'online') state.session = await window.showroomApi.saveSession({ step: state.experienceStep });
    render();
  }));
  document.querySelectorAll('[data-exp-next]').forEach((button) => button.addEventListener('click', async () => {
    state.experienceStep = Math.min(6, state.experienceStep + 1);
    if (state.backendStatus === 'online') {
      const data = button.dataset.expRole ? { role: button.dataset.expRole } : {};
      state.session = await window.showroomApi.saveSession({ step: state.experienceStep, data });
    }
    render();
  }));
  document.querySelectorAll('[data-exp-back]').forEach((button) => button.addEventListener('click', async () => {
    state.experienceStep = Math.max(0, state.experienceStep - 1);
    if (state.backendStatus === 'online') state.session = await window.showroomApi.saveSession({ step: state.experienceStep });
    render();
  }));
  document.querySelector('[data-experience-send]')?.addEventListener('click', () => sendSessionMessage('experience-chat-input'));
  document.getElementById('experience-chat-input')?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') sendSessionMessage('experience-chat-input');
  });
  document.querySelector('[data-experience-submit]')?.addEventListener('click', async () => {
    try {
      state.session = await window.showroomApi.saveSession({ status: 'submitted', step: 6 });
      showToast('需求与方案已提交，工作人员可在后台继续跟进');
      render();
    } catch (error) {
      showToast(`提交失败：${error.message}`);
    }
  });
}

function render(intent = 'refresh') {
  const meta = viewMeta[state.view] || viewMeta.controller;
  const canvas = document.getElementById('screen-canvas');
  const token = ++motionSystem.renderToken;
  const commit = () => {
    if (token !== motionSystem.renderToken) return;
    stopScreenMotion();
    const staticDisplay = isStaticDisplayView();
    if (!staticDisplay && !state.bootstrapped && ['auth-required', 'display'].includes(state.backendStatus)) {
      canvas.innerHTML = `<div class="screen"><div class="screen-content"><section class="panel" style="margin:auto;max-width:720px;text-align:center"><p class="kicker">AUTHENTICATION REQUIRED</p><h2 class="hero-title">登录后加载真实业务数据</h2><p class="lead">页面不会在未连接后端时展示伪造的在线数据。</p><button class="form-cta" data-login-showroom>登录 AI Lab Platform</button></section></div></div>`;
      canvas.querySelector('[data-login-showroom]')?.addEventListener('click', () => document.getElementById('network-status').click());
      return;
    }
    if (!staticDisplay && !state.bootstrapped && !['demo', 'offline'].includes(state.backendStatus)) {
      canvas.innerHTML = `<div class="screen"><div class="screen-content"><section class="panel" style="margin:auto;max-width:720px;text-align:center"><p class="kicker">AI LAB DATA CONTRACT</p><h2 class="hero-title">正在加载后端数据…</h2><p class="lead">读取屏幕配置、体验会话、IPD 交付件和全场状态。</p></section></div></div>`;
      return;
    }
    const builder = state.view.startsWith('experience-') ? experienceView : (builders[state.view] || controllerView);
    canvas.innerHTML = builder();
    document.getElementById('page-title').textContent = meta[0];
    document.getElementById('frame-label').textContent = meta[1];
    document.getElementById('frame-size').textContent = meta[2];
    canvas.classList.remove('switching');
    attachScreenActions();
    runScreenMotion(intent);
    if (state.demandSheetPendingFocus && state.view === 'screen-03') {
      requestAnimationFrame(() => {
        const demandSheet = canvas.querySelector('.demand-sheet');
        if (!demandSheet) return;
        state.demandSheetPendingFocus = false;
        demandSheet.scrollIntoView({
          behavior: motionEnabled() ? 'smooth' : 'auto',
          block: 'nearest',
          inline: 'nearest',
        });
        demandSheet.focus({ preventScroll: true });
      });
    }
  };

  if (!canvas.firstElementChild || !motionEnabled()) {
    commit();
    return;
  }

  canvas.classList.add('switching');
  motionSystem.gsap.to(canvas, {
    autoAlpha: 0,
    y: 4,
    duration: 0.12,
    ease: 'power1.in',
    overwrite: true,
    onComplete: commit,
  });
}

function setView(view, intent = 'view') {
  const wasConversationView = isConversationView();
  if (view !== 'screen-03-team') clearInsightAutoAdvance();
  state.view = view;
  if (!view.startsWith('experience-')) state.experienceStep = 0;
  const params = new URLSearchParams(location.search);
  params.set('view', view);
  if (view === 'screen-06' && state.giantMode !== 'workbench') params.set('mode', state.giantMode); else params.delete('mode');
  if (view === 'screen-06' && state.giantMode === 'artifact' && state.selectedArtifact) params.set('artifact', state.selectedArtifact); else params.delete('artifact');
  history.replaceState({}, '', `${location.pathname}?${params}`);
  buildNavigation();
  render(intent);
  if (['screen-03-team', 'screen-04'].includes(view) && currentInsightJob().execution_id) startInsightServerPolling();
  else stopInsightServerPolling();
  if (isConversationView(view) && state.bootstrapped) {
    window.showroomApi?.resumeHermes();
  } else if (wasConversationView) {
    window.showroomApi?.suspendHermes();
  }
  if (!isStaticDisplayView(view) && !state.bootstrapped) {
    window.showroomApi?.init({ force: true });
  }
}

function setDirectMode(enabled) {
  document.body.classList.toggle('direct-mode', enabled);
  const params = new URLSearchParams(location.search);
  if (enabled) params.set('direct', '1'); else params.delete('direct');
  history.replaceState({}, '', `${location.pathname}?${params}`);
}

function showToast(message) {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove('show'), 2600);
}

function escapeHtml(value) {
  return String(value || '').replace(/[&<>'"]/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
  }[character]));
}

function applyBackendSnapshot(snapshot, rerender = true) {
  if (!snapshot) return;
  const stageIndex = Number(String(snapshot.stage || '').split('-').at(-1)) - 1;
  if (Number.isInteger(stageIndex) && stageIndex >= 0 && stageIndex < stages.length) {
    state.stage = stageIndex;
  }
  Object.entries(snapshot.reviews || {}).forEach(([gate, record]) => {
    if (record?.decision) state.reviewStates[gate] = record.decision;
  });
  buildTourSteps();
  const clientCount = document.querySelector('.venue-card strong');
  if (clientCount && snapshot.connected_clients !== undefined) clientCount.textContent = `${snapshot.connected_clients} 屏`;
  if (rerender && ['controller', 'screen-05', 'screen-06'].includes(state.view)) render('refresh');
}

function setBackendStatus(status, detail = '') {
  state.backendStatus = status;
  state.backendDetail = detail;
  const button = document.getElementById('network-status');
  if (!button) return;
  const labels = {
    online: '后端实时连接', connecting: '正在连接', reconnecting: '正在重连',
    'auth-required': '需要登录', offline: '后端离线', demo: '本地演示', display: '纯展示模式',
  };
  button.dataset.status = status;
  button.querySelector('span').textContent = labels[status] || status;
  button.title = detail || labels[status] || status;
  if (!state.bootstrapped && ['auth-required', 'offline', 'demo', 'display'].includes(status)) render('refresh');
}

async function commitTourStage(nextStage) {
  if (state.backendStatus === 'auth-required') {
    showToast('请先登录 AI Lab Platform，再进行全场联动');
    return;
  }
  try {
    if (state.backendStatus === 'online') {
      showToast(`正在同步${stages[nextStage][0]}到全场屏幕…`);
      const snapshot = await window.showroomApi.commitStage(`station-${nextStage + 1}`, {
        view: state.view,
      });
      applyBackendSnapshot(snapshot);
    } else {
      state.stage = nextStage;
      buildTourSteps();
      if (state.view === 'controller') render();
    }
    showToast(`全场已切换：${stages[nextStage][0]} · ${stages[nextStage][1]}`);
  } catch (error) {
    setBackendStatus(error.status === 401 ? 'auth-required' : 'offline', error.message);
    showToast(`同步失败：${error.message}`);
  }
}

async function askAssistant(question) {
  state.assistantQuestion = question;
  state.assistantAnswer = state.backendStatus === 'online' ? '正在连接 AI Lab 知识服务…' : '';
  state.avatarSpeaking = true;
  render('assistant');
  if (state.backendStatus !== 'online') return;
  try {
    const answer = await window.showroomApi.streamChat(question, {
      agentId: 'main_agent',
      onDelta: (text) => {
        state.assistantAnswer = text;
        const subtitle = document.querySelector('.subtitle-card p');
        if (subtitle) subtitle.textContent = text;
      },
    });
    if (answer) state.assistantAnswer = answer;
  } catch (error) {
    state.assistantAnswer = getArtifactDetail(state.selectedArtifact || `${ipdPhases[state.selectedPhase].name}阶段`).summary;
    const subtitle = document.querySelector('.subtitle-card p');
    if (subtitle) subtitle.textContent = state.assistantAnswer;
    showToast(`AI 服务暂不可用，已切换本地讲解：${error.message}`);
  }
}

document.getElementById('next-stage').addEventListener('click', () => {
  commitTourStage((state.stage + 1) % stages.length);
});

document.getElementById('network-status').addEventListener('click', () => {
  if (state.backendStatus === 'auth-required') {
    const next = encodeURIComponent(`${location.pathname}${location.search}`);
    location.href = `/login?next=${next}`;
    return;
  }
  showToast(state.backendDetail || (state.backendStatus === 'online' ? 'API、WebSocket 与多屏状态同步正常' : '当前保持本地可操作兜底'));
});

document.getElementById('motion-toggle').addEventListener('click', (event) => {
  state.paused = !state.paused;
  document.body.classList.toggle('motion-paused', state.paused);
  motionSystem.gsap?.globalTimeline.paused(state.paused);
  event.currentTarget.innerHTML = icon(state.paused ? 'play' : 'pause');
  event.currentTarget.setAttribute('aria-label', state.paused ? '继续动态效果' : '暂停动态效果');
  showToast(state.paused ? '动态效果已暂停' : '动态效果已继续');
});

document.getElementById('direct-toggle').addEventListener('click', () => setDirectMode(true));
document.getElementById('exit-direct').addEventListener('click', () => setDirectMode(false));
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && (state.artifactOpen || state.assistantOpen || state.activeReview || state.ipdDrawer)) {
    const selector = state.activeReview ? '.review-overlay' : state.artifactOpen ? '.artifact-overlay' : state.ipdDrawer ? '.ipd-detail-drawer' : '.assistant-panel';
    closeSurface(selector, () => {
      state.artifactOpen = false;
      state.assistantOpen = false;
      state.avatarSpeaking = false;
      state.activeReview = null;
      state.reviewDecision = null;
      state.ipdDrawer = null;
    });
  }
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k' && ['screen-05', 'screen-06'].includes(state.view)) {
    event.preventDefault();
    state.assistantOpen = true;
    render('assistant');
  }
});

buildNavigation();
buildTourSteps();
initIcons();
setDirectMode(new URLSearchParams(location.search).get('direct') === '1');
render();

window.showroomApi?.on('status', ({ status, detail }) => setBackendStatus(status, detail));
window.showroomApi?.on('bootstrap', ({ screens, content, runtime, session, knowledge, centers, capabilities, persona_skill: personaSkill }) => {
  hydrateContent(content);
  state.screenConfigs = screens || [];
  state.session = session;
  Object.entries(session?.data?.reviews || {}).forEach(([gate, record]) => {
    if (record?.decision) state.reviewStates[gate] = record.decision;
  });
  state.experienceStep = Number(session?.step || 0);
  state.knowledge = knowledge || {};
  state.centers = centers || [];
  state.capabilities = capabilities || {};
  state.capabilities.persona_skill_version = personaSkill?.version || '';
  state.bootstrapped = true;
  document.body.dataset.screenConfigCount = String(screens.length);
  buildNavigation();
  buildTourSteps();
  applyBackendSnapshot(runtime, false);
  render('refresh');
});
window.showroomApi?.on('hermes-status', ({ status, detail, retryStopped }) => {
  const previousStatus = state.hermesStatus;
  state.hermesStatus = status;
  state.hermesDetail = detail || '';
  state.hermesRetryStopped = Boolean(retryStopped);
  const structuralStatuses = new Set(['generating', 'waiting', 'error', 'quota-required', 'auth-required']);
  const requiresStructuralRender = structuralStatuses.has(status) || structuralStatuses.has(previousStatus);
  if (requiresStructuralRender && (['controller', 'screen-03', 'screen-03-team', 'screen-04'].includes(state.view) || state.view.startsWith('experience-'))) {
    render('refresh');
  } else {
    updateHermesStatusIndicators();
  }
});
window.showroomApi?.on('hermes-ready', ({ lane, messages, running, raw_message_count: rawMessageCount }) => {
  if (lane === 'insight-review') {
    state.insightAssistantMessages = (Array.isArray(messages) ? messages : [])
      .filter((message) => message.content && !String(message.content).startsWith('[AI_LAB_CONTROL]'))
      .slice(-20);
    if (running) {
      const reviewGate = currentInsightReviewGate();
      const resumedJob = currentInsightJob();
      const completed = new Set(resumedJob.completed_sections || []);
      if (reviewGate.task_id && ['assigned', 'reviewing'].includes(reviewGate.status)) {
        state.insightReviewRunning = true;
        state.insightReviewTaskId = reviewGate.task_id;
        state.insightAssistantBusy = false;
      } else {
        state.insightAssistantBusy = true;
        state.insightAssistantStatus = '正在恢复未完成的共创对话';
      }
    }
  } else {
    state.chatMessages = Array.isArray(messages) ? messages : [];
  }
  state.rawHermesMessageCount = Number(rawMessageCount || 0);
  state.avatarSpeaking = Boolean(running);
  state.streamingReply = '';
  state.pendingClarify = null;
  state.chatError = '';
  state.hermesRetryStopped = false;
  render('refresh');
  const staleInsight = state.view === 'controller' && !running && state.session?.data?.customer_insight?.status === 'running';
  const staleHostGreeting = state.view === 'controller' && !running
    && state.session?.data?.host_greeting_initialized
    && !state.chatMessages.some((message) => message.role === 'assistant' && String(message.content || '').trim());
  if (staleInsight) {
    failControllerHermesTask('上次客户洞察未完成，请重新发起。');
  }
  if (staleHostGreeting) {
    state.chatError = '上次主持人备课未完成，请重新备课。';
    state.hermesDetail = state.chatError;
    state.hermesStatus = 'error';
    window.showroomApi.saveSession({ data: { host_greeting_initialized: false } }).then((session) => {
      state.session = session;
      render('refresh');
    }).catch(() => {});
  } else if (state.view === 'controller' && !running && !state.session?.data?.host_greeting_initialized) {
    startHostGreeting();
  }
  if (state.view === 'screen-03' && !state.session?.data?.frontstage_started && !state.frontstageActivating) {
    state.frontstageActivating = true;
    window.showroomApi.activateFrontstage(state.rawHermesMessageCount).then((result) => {
      state.chatMessages = [];
      state.session = result.session;
      return window.showroomApi.submitHermesPrompt(
        '[AI_LAB_CONTROL] 客户已入场。请根据允许读取的背景静默准备，然后生成一句自然欢迎语并直接进入需求问诊。',
        { skillCommand: 'solution-consultant-persona', stationContext: result.station_context },
      );
    }).catch((error) => {
      state.chatError = error.message;
      showToast(`前台接待准备失败：${error.message}`);
    }).finally(() => { state.frontstageActivating = false; });
  }
  const latestConfirmation = [...state.chatMessages]
    .reverse()
    .find((message) => message.role === 'assistant' && /(?:需求(?:收敛)?确认单|四维确认单|AI_LAB_DEMAND_V1)/.test(message.rawContent || message.content));
  if (latestConfirmation && !hasDemandConfirmationContent(currentDemand())) {
    maybeExtractDemand(latestConfirmation.rawContent || latestConfirmation.content, { silent: true });
  }
  if (['screen-03-team', 'screen-04'].includes(state.view) && currentInsightJob().execution_id) startInsightServerPolling();
});
window.showroomApi?.on('hermes-event', (event) => {
  const payload = event.payload || {};
  if (event.type === 'message.start') {
    state.avatarSpeaking = true;
    state.hermesStatus = 'generating';
  } else if (event.type === 'message.delta') {
    state.avatarSpeaking = true;
    state.hermesStatus = 'generating';
    state.streamingReply += String(payload.text || '');
    const streamingBubble = document.querySelector('.bubble.ai.streaming');
    if (streamingBubble) streamingBubble.textContent = state.streamingReply;
    const insightStreaming = document.querySelector('.assistant-working p');
    if (insightStreaming) insightStreaming.textContent = window.showroomApi.visibleAssistantMessage(state.streamingReply);
    return;
  } else if (event.type === 'message.complete') {
    const rawAnswer = String(payload.text || '').trim();
    const answer = window.showroomApi.visibleAssistantMessage(rawAnswer);
    if (state.insightReviewRunning) {
      const taskId = state.insightReviewTaskId || currentInsightReviewGate().task_id;
      state.insightReviewRunning = false;
      state.streamingReply = '';
      state.avatarSpeaking = false;
      if (payload.status === 'error') {
        state.hermesStatus = 'error';
        state.chatError = friendlyHermesError(rawAnswer || 'AI评审执行失败');
        window.showroomApi.completeInsightReviewTask(taskId, rawAnswer || 'AI评审执行失败').catch(() => null);
        showToast(`AI评审失败：${state.chatError}`);
        render('refresh');
        return;
      }
      window.showroomApi.completeInsightReviewTask(taskId, rawAnswer).then((result) => {
        state.session = result.session;
        state.hermesStatus = 'online';
        if (result.released) {
          showToast('AI概念评审已通过，正在进入001 IPD实践');
          setView('screen-05');
        } else {
          const decision = result.task?.final_decision?.summary || 'AI评审要求继续修改';
          state.insightAssistantMessages.push({ role: 'assistant', content: `AI评审意见：${decision}` });
          showToast('AI评审已返回修改意见');
          render('refresh');
        }
      }).catch((error) => {
        state.hermesStatus = 'error';
        state.chatError = error.message;
        showToast(`保存AI评审结论失败：${error.message}`);
        render('refresh');
      });
      return;
    }
    if (state.insightAssistantBusy) {
      state.avatarSpeaking = false;
      if (payload.status === 'error') {
        state.insightAssistantBusy = false;
        state.insightAssistantStatus = '';
        state.insightActiveRequest = null;
        state.streamingReply = '';
        state.insightAssistantMessages.push({ role: 'assistant', content: friendlyHermesError(rawAnswer || '洞察助手本轮失败') });
        state.hermesStatus = 'error';
        render('refresh');
        return;
      }
      completeInsightAssistantRequest(rawAnswer, answer).catch((error) => {
        state.insightAssistantBusy = false;
        state.insightAssistantStatus = '';
        state.insightRevisionError = {
          message: error.message || 'AI已给出说明，但尚未形成可回填草案',
          request: state.insightActiveRequest,
        };
        render('refresh');
      });
      return;
    }
    state.streamingReply = '';
    state.pendingClarify = null;
    state.avatarSpeaking = false;
    if (payload.status === 'error') {
      const rawError = rawAnswer || answer || '大架构师本轮回复失败';
      state.chatError = friendlyHermesError(rawError);
      state.hermesDetail = state.chatError;
      state.hermesStatus = hermesFailureStatus(rawError);
      failControllerHermesTask(rawError);
      const job = currentInsightJob();
      if (job.job_id && state.insightTask) {
        window.showroomApi.failInsightJob(job.job_id, state.chatError).catch(() => {});
        state.insightTask = '';
      }
    } else {
      if (state.insightTask === 'planning') {
        const planEnvelope = extractInsightEnvelopes(rawAnswer).find((item) => item.type === 'plan');
        const job = currentInsightJob();
        if (!planEnvelope || !job.job_id) {
          state.chatError = 'V1.7未返回有效项目组规划';
          state.hermesStatus = 'error';
          if (job.job_id) window.showroomApi.failInsightJob(job.job_id, state.chatError).catch(() => {});
          state.insightTask = '';
          render('refresh');
          return;
        }
        window.showroomApi.saveStaffingPlan(job.job_id, planEnvelope.payload).then((result) => {
          state.session = result.session;
          state.selectedEmployeeId = result.plan?.squads?.[0]?.employees?.[0]?.employee_id || '';
          return beginInsightExecution(result.job, result.plan);
        }).catch(async (error) => {
          state.chatError = error.message;
          state.hermesStatus = 'error';
          state.insightTask = '';
          try {
            const recovered = await window.showroomApi.failInsightJob(job.job_id, error.message);
            state.session = recovered.session;
            if (recovered.job?.status === 'completed') {
              state.chatError = '';
              state.hermesStatus = 'ready';
              startInsightAutoAdvance();
              showToast('全部章节已保存，项目组已完成');
            }
          } catch (_) {
            // Keep the original finalization error visible when recovery also fails.
          }
          render('refresh');
        });
        state.streamingReply = '';
        state.avatarSpeaking = false;
        render('refresh');
        return;
      }
      if (state.insightTask === 'executing-market') {
        const job = currentInsightJob();
        processInsightStream(rawAnswer);
        insightProgressQueue.then(() => beginRequirementAnalysis(job)).catch((error) => {
          state.chatError = error.message;
          state.hermesStatus = 'error';
          window.showroomApi.failInsightJob(job.job_id, error.message).catch(() => {});
          state.insightTask = '';
          render('refresh');
        });
        state.streamingReply = '';
        state.avatarSpeaking = false;
        return;
      }
      if (state.insightTask === 'executing-requirement') {
        const job = currentInsightJob();
        processInsightStream(rawAnswer);
        insightProgressQueue.then(() => window.showroomApi.completeInsightJob(job.job_id, rawAnswer)).then((result) => {
          state.session = result.session;
          state.insightTask = '';
          if ((result.job?.completed_sections || []).includes('summary')) startInsightAutoAdvance();
          render('refresh');
        }).catch((error) => {
          state.chatError = error.message;
          state.hermesStatus = 'error';
          window.showroomApi.failInsightJob(job.job_id, error.message).catch(() => {});
          state.insightTask = '';
          render('refresh');
        });
        state.streamingReply = '';
        state.avatarSpeaking = false;
        return;
      }
      if (state.view === 'screen-03' && isPrematureScheme(rawAnswer) && !state.demandCorrectionPending) {
        state.demandCorrectionPending = true;
        state.hermesStatus = 'generating';
        state.hermesDetail = '正在将回答纠正为需求收敛单';
        window.showroomApi.submitHermesPrompt(
          '[AI_LAB_CONTROL] 上一回答越过了站3边界。不要展示或延续方案；请立即依据已有对话输出需求收敛确认单，未知项写TBD，并附AI_LAB_DEMAND_STATE_V1与AI_LAB_DEMAND_V1。',
          { skillCommand: 'solution-consultant-persona', stationContext: getScreenConfig('screen-03').station_context },
        ).catch((error) => {
          state.demandCorrectionPending = false;
          state.chatError = error.message;
          state.hermesStatus = 'error';
          render('refresh');
        });
        render('refresh');
        return;
      }
      state.demandCorrectionPending = false;
      if (answer && !(state.chatMessages.at(-1)?.role === 'assistant' && state.chatMessages.at(-1)?.content === answer)) {
        state.chatMessages.push({ role: 'assistant', content: answer, rawContent: rawAnswer });
      }
      state.chatError = '';
      state.hermesStatus = 'online';
      completeControllerHermesTask(rawAnswer).catch((error) => showToast(`备课状态保存失败：${error.message}`));
      if (state.view === 'controller' && /AI_LAB_VISITOR_INSIGHT_V1/.test(rawAnswer)) {
        maybeExtractVisitorInsight(rawAnswer);
      } else if (state.view === 'screen-03') {
        maybeExtractDemand(rawAnswer);
      }
    }
  } else if (event.type === 'clarify.request') {
    state.pendingClarify = {
      request_id: payload.request_id,
      question: payload.question,
      choices: payload.choices || [],
    };
    state.streamingReply = '';
    state.avatarSpeaking = true;
    state.hermesStatus = 'waiting';
  } else if (event.type === 'status.update') {
    state.hermesDetail = String(payload.text || payload.status || '大架构师正在处理');
  } else if (event.type === 'error') {
    const rawError = String(payload.message || '大架构师服务异常');
    state.chatError = friendlyHermesError(rawError);
    state.hermesDetail = state.chatError;
    state.avatarSpeaking = false;
    state.hermesStatus = hermesFailureStatus(rawError);
    failControllerHermesTask(rawError);
  } else {
    return;
  }
  render('refresh');
});
window.showroomApi?.on('session', (session) => {
  const demandChanged = JSON.stringify(state.session?.data?.demand || {})
    !== JSON.stringify(session?.data?.demand || {});
  const demandDocumentChanged = JSON.stringify(state.session?.data?.demand_document || {})
    !== JSON.stringify(session?.data?.demand_document || {});
  const visitorChanged = JSON.stringify(state.session?.data?.visitor || {})
    !== JSON.stringify(session?.data?.visitor || {});
  const visitorInsightChanged = JSON.stringify(state.session?.data?.customer_insight || {})
    !== JSON.stringify(session?.data?.customer_insight || {});
  const insightJobChanged = JSON.stringify(state.session?.data?.insight_job || {})
    !== JSON.stringify(session?.data?.insight_job || {});
  const insightChanged = JSON.stringify(state.session?.data?.insight || {})
    !== JSON.stringify(session?.data?.insight || {});
  const insightReviewChanged = JSON.stringify(state.session?.data?.insight_review || {})
    !== JSON.stringify(session?.data?.insight_review || {});
  const insightReviewGateChanged = JSON.stringify(state.session?.data?.insight_review_gate || {})
    !== JSON.stringify(session?.data?.insight_review_gate || {});
  state.session = session;
  state.experienceStep = Number(session?.step || state.experienceStep);
  Object.entries(session?.data?.reviews || {}).forEach(([gate, record]) => {
    if (record?.decision) state.reviewStates[gate] = record.decision;
  });
  if (state.view === 'screen-03' && (demandChanged || demandDocumentChanged)) render('refresh');
  if (state.view === 'controller' && (visitorChanged || visitorInsightChanged)) render('refresh');
  if (['screen-03-team', 'screen-04'].includes(state.view) && (insightJobChanged || insightChanged || insightReviewChanged || insightReviewGateChanged)) render('refresh');
});
window.showroomApi?.on('message', (message) => {
  if (message.type === 'STATE' || message.type === 'COMMIT' || message.type === 'REVIEW') {
    applyBackendSnapshot(message.state);
  }
  if (message.type === 'VISIT_COMPLETE' && message.session_id === state.session?.session_id) {
    state.visitCompleteNotice = message;
    if (state.view === 'controller') render('refresh');
  }
  if (message.type === 'SESSION_SWITCH_ABORT' && message.session_id === state.session?.session_id) {
    state.visitEndBusy = false;
    state.visitEndConfirmOpen = false;
    if (state.view === 'controller') render('refresh');
    showToast('换场未完成，已恢复当前接待');
  }
  if (['VISITOR_UPDATED', 'INSIGHT_UPDATED', 'STAFFING_PLAN_READY', 'AI_EMPLOYEE_STATUS', 'INSIGHT_STAGE_UPDATED', 'INSIGHT_SECTION_COMPLETED', 'INSIGHT_JOB_COMPLETED', 'INSIGHT_JOB_FAILED', 'INSIGHT_REVISION_READY', 'INSIGHT_REVISION_APPLIED', 'INSIGHT_REVISION_DISCARDED', 'INSIGHT_TBD_REGISTERED', 'INSIGHT_CONFIRMED', 'INSIGHT_VERSION_OPENED', 'INSIGHT_REVIEW_ASSIGNED', 'AI_REVIEWER_STATUS', 'INSIGHT_REVIEW_COMPLETED', 'INSIGHT_REVIEW_CHANGES_REQUESTED', 'INSIGHT_REVIEW_RELEASED', 'INSIGHT_REVIEW_NOTIFICATION_UPDATED', 'DEMAND_REOPENED'].includes(message.type) && message.session_id === state.session?.session_id) {
    window.showroomApi.init({ force: true });
  }
  if (message.type === 'SESSION_SWITCH_COMMIT' && message.session_id === state.session?.session_id) {
    applySessionRollover(null, message.state, message.new_session_id);
    render('refresh');
    window.showroomApi.init({ force: true });
  }
});
window.showroomApi?.init();
