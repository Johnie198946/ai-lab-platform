const state = {
  view: new URLSearchParams(location.search).get('view') || 'controller',
  stage: 0,
  paused: false,
  experienceStep: 0,
  selectedPhase: 0,
  selectedAgent: 'IPD-01',
  pipelineMode: 'orchestration',
  pipelinePlaying: false,
  giantMode: new URLSearchParams(location.search).get('mode') || 'workbench',
  selectedArtifact: new URLSearchParams(location.search).get('artifact') || null,
  artifactOpen: false,
  assistantOpen: false,
  avatarSpeaking: false,
  assistantQuestion: '',
  reviewStates: {},
  activeReview: null,
  reviewDecision: null,
  introSkipped: false,
};

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
    const primary = root.querySelectorAll('.ipd-command, .ipd-phase-rail, .approval-route, .giant-ipd-label, .giant-artifact-main > header, .insight-cover, .experience-top');
    const panels = root.querySelectorAll('.ipd-stage-grid > .panel, .deliverable-column, .giant-ipd > section, .giant-workbench > section, .insight-summary-grid > div, .experience-body > *, .control-grid > .panel');
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
      '.screen-header', '.ipd-command', '.ipd-phase-rail', '.approval-route',
      '.giant-ipd-label', '.giant-artifact-main > header', '.insight-cover',
      '.experience-top', '.ipd-stage-grid > .panel', '.deliverable-column',
      '.giant-ipd > section', '.giant-workbench > section', '.insight-summary-grid > div',
      '.experience-body > *', '.control-grid > .panel', '.ipd-phase.active',
      '.giant-phase-list button.active', '.agent-inspector', '.giant-stage-head',
      '.artifact-overlay', '.artifact-modal', '.artifact-modal-grid > aside',
      '.artifact-demo > *', '.review-overlay', '.feishu-review',
      '.review-package button', '.review-decision button', '.review-result > *',
      '.assistant-panel', '.digital-human', '.subtitle-card', '.giant-artifact-nav',
      '.giant-artifact-main', '.giant-presenter',
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

function getReviewState(gate) {
  return state.reviewStates[gate] || 'pending';
}

function approvalRouteBar(phase, giant = false) {
  const approved = phase.reviews.filter((gate) => getReviewState(gate) === 'approved').length;
  const nextGate = phase.reviews.find((gate) => getReviewState(gate) !== 'approved') || phase.reviews.at(-1);
  const reviewer = humanReviewers[nextGate] || humanReviewers.TR1;
  return `<div class="approval-route ${giant ? 'giant-approval-route' : ''}"><div class="approval-principle"><span>AI WORK</span><b>AI 负责产出</b><i>→</i><span>FEISHU</span><b>自动派审批</b><i>→</i><span>HUMAN</span><b>人负责评审确认</b></div><button data-review-gate="${nextGate}"><span class="feishu-mark">飞</span><div><small>下一人工关口 · ${nextGate}</small><b>${reviewer.role} · ${reviewer.person}</b></div><em>${approved}/${phase.reviews.length} 已通过　打开审批</em></button></div>`;
}

function feishuReviewOverlay() {
  if (!state.activeReview) return '';
  const gate = state.activeReview;
  const reviewer = humanReviewers[gate] || humanReviewers.TR1;
  const status = getReviewState(gate);
  const detail = reviewStatus[status];
  const phase = ipdPhases.find((item) => item.reviews.includes(gate)) || ipdPhases[state.selectedPhase];
  const decisionMode = status === 'pending';
  return `<div class="review-overlay" role="dialog" aria-modal="true" aria-label="飞书 ${gate} 人工审批"><div class="feishu-review"><header><div class="feishu-brand"><span class="feishu-mark">飞</span><div><small>FEISHU APPROVAL · IPD 人工关口</small><b>${gate} ${gate.startsWith('TR') ? '技术评审' : '决策评审'}</b></div></div><span class="review-status ${detail[1]}">${detail[0]}</span><button data-review-close aria-label="关闭飞书审批">${icon('close')}</button></header><div class="feishu-review-grid"><aside><div class="reviewer-avatar">${reviewer.person.slice(0, 1)}</div><span>审批人（演示映射）</span><h3>${reviewer.person}</h3><b>${reviewer.role}</b><small>${reviewer.group}</small><dl><div><dt>评审重点</dt><dd>${reviewer.focus}</dd></div><div><dt>来自阶段</dt><dd>0${ipdPhases.indexOf(phase) + 1} · ${phase.name}</dd></div><div><dt>响应时限</dt><dd>24 小时内</dd></div></dl></aside><main><div class="feishu-message"><div class="bot-avatar">AI</div><div><span>AI Lab IPD 助手　刚刚</span><p>您好，AI 已完成 <b>${phase.name}阶段</b> 的交付件生产，请您对 <b>${gate}</b> 关口进行人工评审。AI 不会代替您做通过决定。</p></div></div><section class="review-package"><header><span>待审材料包</span><em>${phase.outputs.length} 个交付件 · 来源完整</em></header>${phase.outputs.map((output, i) => `<button data-artifact-from-review="${output}"><span>0${i + 1}</span><div><b>${output}</b><small>${artifactDescriptions[output]}</small></div><em>预览 ↗</em></button>`).join('')}</section>${decisionMode ? `<section class="review-decision"><span>请选择评审结论</span><div><button class="approve ${state.reviewDecision === 'approved' ? 'active' : ''}" data-review-decision="approved"><i>✓</i><b>通过</b><small>允许进入下一关口</small></button><button class="change ${state.reviewDecision === 'changes' ? 'active' : ''}" data-review-decision="changes"><i>↻</i><b>要求修改</b><small>退回 AI 补充后复审</small></button><button class="reject ${state.reviewDecision === 'rejected' ? 'active' : ''}" data-review-decision="rejected"><i>×</i><b>拒绝</b><small>终止当前方案</small></button></div><label for="review-comment">审批意见</label><textarea id="review-comment" placeholder="请说明通过依据，或需要修改/拒绝的原因…"></textarea><button class="review-submit" data-review-submit>确认提交到飞书</button></section>` : `<section class="review-result ${detail[1]}"><span>${detail[0]}</span><h3>${status === 'approved' ? '人工评审已完成，结论已写入 IPD 单据链。' : status === 'changes' ? '材料已退回 AI，等待根据审批意见修订。' : '当前方案已被人工拒绝，后续阶段不会启动。'}</h3><p>审批人：${reviewer.person} · 结论时间：刚刚 · 全程可追溯</p>${status !== 'approved' ? '<button data-review-resubmit>模拟 AI 完成修订并重新提交</button>' : '<button data-review-close>完成</button>'}</section>`}</main></div></div></div>`;
}

const artifactDescriptions = {
  '需求确认单': '把现场对话收敛为问题、目标、用户、范围与约束，作为整个 IPD 流程的唯一需求入口。',
  '客户痛点': '记录停机损失、经验依赖和新员工上手困难，并保留客户原话与现场证据。',
  '产品战略边界': '明确首期只覆盖一条典型产线，不替代 MES，不触碰设备安全控制。',
  '需求合理性·调研支撑': '从客户、市场、竞品与产业四个维度证明问题真实且值得投入。',
  '需求评审结论': '形成建议产品、条件接纳或拒绝的正式判断，并列出进入下一阶段的前置条件。',
  '初始产品包': '将换模辅助工作台定义为软件、服务、数据采集和现场验证的组合交付。',
  '产品组合规划书': '说明该产品与现有智能制造能力的组合关系、投资顺序和版本节奏。',
  '产品包定义': '定义用户可感知的功能、服务、实施边界、成功标准与商业承诺。',
  '架构方案': '把需求映射为数据采集、步骤引导、异常提示、复盘和知识沉淀五层架构。',
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
  const ownerId = artifactOwners[title];
  const owner = phase.agents.find((agent) => agent.id === ownerId) || phase.agents[0];
  return {
    title,
    phase,
    phaseIndex: index,
    kind: artifactKind(title),
    summary: artifactDescriptions[title] || `这是${phase.name}阶段围绕“换模 45 → 20 分钟”形成的结构化交付件。`,
    owner,
  };
}

function artifactVisual(detail) {
  if (detail.kind === 'architecture') return `<div class="architecture-demo"><div><span>01</span><b>现场采集</b><small>动作 · 耗时 · 异常</small></div><i>→</i><div><span>02</span><b>智能引导</b><small>步骤 · 计时 · 提示</small></div><i>→</i><div><span>03</span><b>知识沉淀</b><small>复盘 · 版本 · 追溯</small></div></div><div class="artifact-spec-grid"><div><span>关键接口</span><b>事件流 / 任务 API / 知识索引</b></div><div><span>异常策略</span><b>断网可用 · 超时降级 · 人工接管</b></div><div><span>验收锚点</span><b>需求绑定规格与测试用例</b></div></div>`;
  if (detail.kind === 'roadmap') return `<div class="artifact-roadmap"><div class="done"><span>W1–2</span><b>建立基线</b><small>采集 20 次换模过程</small></div><div class="active"><span>W3–6</span><b>原型验证</b><small>一条产线闭环</small></div><div><span>W7–10</span><b>BETA 试用</b><small>两类关键用户</small></div><div><span>W11–12</span><b>决策评审</b><small>价值与规模化判断</small></div></div>`;
  if (detail.kind === 'checklist') return `<div class="artifact-checks"><div><i>✓</i><span><b>换模总时长 ≤ 20 分钟</b><small>连续 10 次测试，P90 达标</small></span><em>通过</em></div><div><i>✓</i><span><b>新员工可独立完成</b><small>不依赖老师傅口头提示</small></span><em>通过</em></div><div><i>!</i><span><b>异常恢复时间</b><small>需补充断网场景证据</small></span><em class="warn">待补证</em></div><div><i>✓</i><span><b>数据来源可追溯</b><small>需求—规格—用例已绑定</small></span><em>通过</em></div></div>`;
  if (detail.kind === 'metrics') return `<div class="artifact-metrics"><div><span>目标换模时间</span><b>≤ 20 min</b><small>当前 45 min</small></div><div><span>首期周期</span><b>12 weeks</b><small>单产线验证</small></div><div><span>资源满足度</span><b>92%</b><small>目标 ≥ 90%</small></div></div><div class="artifact-bars"><span style="--w:86%">需求完整度 <b>86%</b></span><span style="--w:72%">数据准备度 <b>72%</b></span><span style="--w:91%">方案可验证性 <b>91%</b></span></div>`;
  if (detail.kind === 'feedback') return `<div class="artifact-feedback"><blockquote>“步骤提示很清楚，但戴手套时需要更大的确认按钮。”<span>新员工 · BETA-07</span></blockquote><blockquote>“最有价值的是异常记录，复盘时终于能说清楚哪里慢。”<span>班组长 · BETA-03</span></blockquote></div><div class="feedback-tags"><span>按钮触达 P1</span><span>异常复盘 P0</span><span>语音记录 P2</span></div>`;
  return `<div class="artifact-document-figure" role="img" aria-label="需求从现场问题收敛到决策建议的关系图"><div><small>现场问题</small><b>45 min</b><span>换模停机时间</span></div><i>→</i><div><small>业务目标</small><b>≤ 20 min</b><span>12 周单线验证</span></div><i>→</i><div><small>决策建议</small><b>条件接纳</b><span>补齐数据后过门</span></div></div>`;
}

function artifactTableRows(detail) {
  if (detail.kind === 'architecture') return [['REQ-01', '动作与耗时采集', '事件流 / 本地缓存', '可追溯'], ['REQ-02', '换模步骤引导', '任务 API / 权限控制', '可验证'], ['REQ-03', '异常复盘', '知识索引 / 版本记录', '待评审']];
  if (detail.kind === 'roadmap') return [['M1', '过程数据基线', '20 次真实换模记录', 'W2'], ['M2', '单产线原型', '核心流程可操作', 'W6'], ['M3', 'BETA 结论', '两类用户完成验证', 'W10']];
  if (detail.kind === 'metrics') return [['业务价值', '停机时间', '45 min', '≤ 20 min'], ['交付能力', '资源满足度', '72%', '≥ 90%'], ['质量门禁', '验证覆盖率', '68%', '≥ 95%']];
  return [['E-01', '现场访谈与需求确认单', '已引用', '高'], ['E-02', '20 次换模过程样本', '采集中', '中'], ['E-03', '知识库方法与历史项目', '已引用', '高']];
}

function artifactDemo(detail, giant = false) {
  const cls = giant ? ' artifact-demo-giant' : '';
  const rows = artifactTableRows(detail);
  return `<article class="artifact-demo markdown-report${cls}">
    <div class="report-format-bar"><span>MARKDOWN REPORT</span><b>图文混排 · 自动生成目录 · 可导出 Word / PDF</b></div>
    <section class="report-copy"><span class="report-anchor">01 · 摘要</span><h3>${detail.title}</h3><p>${detail.summary}</p><blockquote>核心判断：先用单产线、可测量的闭环验证价值，再决定是否扩大投资范围。</blockquote></section>
    <figure class="report-figure"><div class="report-figure-head"><span>FIGURE 01</span><b>${detail.kind === 'feedback' ? '用户反馈与优先级' : detail.kind === 'roadmap' ? '阶段路线与关键里程碑' : detail.kind === 'metrics' ? '核心指标与目标差距' : '方案关键结构与证据关系'}</b></div>${artifactVisual(detail)}<figcaption>图 1 · 数据来自需求确认单、现场调研与 AI Lab 知识库；最终结论需由人工评审确认。</figcaption></figure>
    <section class="report-copy"><span class="report-anchor">02 · 证据明细</span><h3>结论如何被数据支撑</h3><p>以下表格保留来源、状态和可信度，方便评审人从摘要直接追溯到证据，而不必阅读整段生成过程。</p></section>
    <div class="report-table-wrap"><table class="report-table"><thead><tr><th>编号</th><th>证据 / 指标</th><th>当前结果</th><th>状态 / 目标</th></tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell, i) => `<${i === 0 ? 'th' : 'td'}>${cell}</${i === 0 ? 'th' : 'td'}>`).join('')}</tr>`).join('')}</tbody></table></div>
    <aside class="report-callout"><span>AI 建议</span><b>补齐缺失证据后，提交 ${detail.phase.reviews[0]} 人工评审</b><p>AI 负责生产和修订材料，人负责判断是否通过、退回修改或拒绝。</p></aside>
    <footer class="report-sources"><b>参考来源</b><span>[1] 需求确认单 V0.1　[2] 现场访谈记录　[3] 超聚变 IPD 产品开发流程</span></footer>
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
  return `<section class="assistant-panel ${state.avatarSpeaking ? 'speaking' : ''}" aria-label="AI 数字人讲解"><header><div><span class="ai-badge">AI 数字人</span><b>小融 · IPD 讲解员</b></div><button data-assistant-close aria-label="关闭讲解">${icon('close')}</button></header><div class="selected-context"><span>已选内容</span><b>${context}</b></div>${state.avatarSpeaking ? `<div class="digital-human"><div class="human-stage"><div class="human-orbit"></div><div class="human-head"><i></i><i></i><b></b></div><div class="sound-wave"><i></i><i></i><i></i><i></i></div></div><div class="subtitle-card" role="status" aria-live="polite"><span>AI GENERATED · 讲解字幕</span><p>${getArtifactDetail(context).summary}</p><small>01 / 03　点击下方问题可继续追问</small></div></div>` : `<div class="query-starters"><button data-assistant-query="这份内容解决了什么问题？">它解决什么问题？</button><button data-assistant-query="为什么由这些 Agent 协作完成？">Agent 为什么这样分工？</button><button data-assistant-query="进入下一阶段前还缺什么证据？">还缺什么证据？</button></div>`}<div class="assistant-composer"><input id="assistant-input" value="${question}" aria-label="向 AI 数字人提问"><button data-assistant-send aria-label="发送问题">${icon('send')}</button></div><footer><span>回答基于当前交付件与 AI Lab 知识库</span><button data-avatar-call>${state.avatarSpeaking ? '停止讲解' : '唤出数字人'}</button></footer></section>`;
}

const icons = {
  pause: '<path d="M9 5v14M15 5v14"/>',
  play: '<path d="m8 5 11 7-11 7z"/>',
  arrow: '<path d="M5 12h14M14 7l5 5-5 5"/>',
  display: '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  send: '<path d="m4 4 17 8-17 8 3-8zM7 12h14"/>',
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
    button.addEventListener('click', () => {
      state.stage = Number(button.dataset.stage);
      buildTourSteps();
      showToast(`全场已切换：${stages[state.stage][0]} · ${stages[state.stage][1]}`);
      if (state.view === 'controller') render();
    });
  });
}

function screenHeader(title, status = '现场联机') {
  return `<header class="screen-header">
    <div class="screen-brand"><i></i>AI LAB · ${title}</div>
    <div class="screen-state"><span>SESSION 001-A</span><b>${status}</b><span>郑州共创体验中心</span></div>
  </header>`;
}

function controllerView() {
  const screenNames = ['序章','迎宾','TokenOps','问诊','洞察','IPD','7290 主屏','运行原型'];
  const centerStates = [
    ['王女士','需求问诊','运行中'], ['赵总','原型体验','运行中'], ['—','空闲可用','可进入'], ['李经理','方案生成','即将完成'], ['—','空闲可用','可进入'],
  ];
  return `<div class="screen">
    ${screenHeader('TOUR CONTROL')}
    <div class="screen-content control-grid">
      <section class="panel control-hero">
        <p class="kicker">TODAY'S LIVE TOUR · ${stages[state.stage][0]}</p>
        <h2 class="hero-title">让每一位到访者，<br>都带走一个<em>自己的 AI 方案。</em></h2>
        <div class="route-strip">${stages.map((s, i) => `<div class="route-card ${i === state.stage ? 'active' : ''}"><b>${s[0]} · ${s[1]}</b><span>${i < state.stage ? '已完成' : i === state.stage ? '正在进行' : '等待进入'}</span></div>`).join('')}</div>
      </section>
      <section class="panel device-panel">
        <div class="panel-head"><strong>主演示屏幕</strong><span class="status">8 / 8 在线</span></div>
        <div class="device-grid">${screenNames.map((name, i) => `<div class="device-card"><div><b>SCREEN 0${i + 1}</b><i></i></div><p>${name}</p><small class="metric">${10 + i} ms · 60 FPS</small></div>`).join('')}</div>
      </section>
      <section class="panel center-panel">
        <div class="panel-head"><strong>五个独立体验中心</strong><span>仅显示授权摘要</span></div>
        <div class="center-list">${centerStates.map((row, i) => `<div class="center-row"><span class="num">0${i + 1}</span><div><b>${row[0]}</b><small>${row[1]}</small></div><span class="state">${row[2]}</span></div>`).join('')}</div>
      </section>
    </div>
  </div>`;
}

function introView() {
  const mode = document.body.classList.contains('direct-mode') ? 'direct' : 'preview';
  return `<div class="screen motion-opening-host" aria-label="AI Lab 线下体验序章">
    <iframe class="motion-opening-frame" src="./screen-00-replacement.html?embedded=${mode}" title="AI Lab 首屏：从灵感到价值" loading="eager"></iframe>
  </div>`;
}

function welcomeView() {
  return `<div class="screen welcome-screen">
    ${screenHeader('WELCOME', '欢迎到访')}
    <div class="screen-content welcome-layout">
      <div class="welcome-copy">
        <div class="welcome-chip"><i></i>今天，一起把想法变成现实</div>
        <p class="kicker">WELCOME TO AI LAB</p>
        <h2 class="hero-title">欢迎来到<br><span class="orange">AI 共创体验中心。</span></h2>
        <p class="lead">这里不只是看 AI。你会提出一个真实问题，与 AI 一起完成需求收敛、洞察、原型和建设方案。</p>
        <div class="welcome-stats"><div><strong>10s</strong><span>生成首个可用原型</span></div><div><strong>5×</strong><span>独立体验中心并行</span></div><div><strong>1份</strong><span>专属方案扫码带走</span></div></div>
      </div>
      <div class="welcome-art" aria-label="彩色 AI 共创入口视觉"><div class="portal"></div></div>
    </div>
  </div>`;
}

function dashboardView() {
  return `<div class="screen">
    ${screenHeader('TOKENOPS', '算力运行正常')}
    <div class="screen-content">
      <div class="dashboard-head"><div><p class="kicker">FUSIONONE · COMPUTE OPERATIONS</p><h2 class="hero-title">每一份算力，都在创造<em>可见的价值。</em></h2></div><div><span class="tag mint">实时刷新 2s</span> <span class="tag">本月</span></div></div>
      <div class="dashboard-grid">
        <section class="panel dash-main"><span class="tag blue">算力利用率</span><div class="dash-value"><strong class="metric">72%</strong><span>较改造前 +44%</span></div><div class="area-chart" aria-label="算力利用率从28%提升至72%的趋势图"><svg viewBox="0 0 500 150" preserveAspectRatio="none"><path d="M0 130 C70 125 85 105 140 110 S220 85 270 92 S350 52 400 62 S455 24 500 32 L500 150 L0 150Z" fill="#eaf0ff"/><path d="M0 130 C70 125 85 105 140 110 S220 85 270 92 S350 52 400 62 S455 24 500 32" fill="none" stroke="#2868f0" stroke-width="4" stroke-linecap="round"/></svg></div><div class="chart-legend"><span><i style="background:var(--blue)"></i>实际利用率</span><span><i style="background:var(--silver-2)"></i>行业基线</span></div></section>
        <section class="panel dash-card orange"><h3>本月节约成本</h3><strong class="metric">40%</strong><p>智能路由和资源池化共同贡献</p></section>
        <section class="panel dash-card mint"><h3>活跃 AI 工作负载</h3><strong class="metric">186</strong><p>跨研发、制造与运营场景</p></section>
        <section class="panel dash-card blue"><h3>vGPU 细粒度池化</h3><div class="resource-bars" aria-label="四组资源池利用率"><i style="height:66%"></i><i></i><i></i><i></i></div></section>
        <section class="panel dash-card"><h3>平均任务响应</h3><strong class="metric">1.8s</strong><p>高优任务已自动分配到最优资源</p></section>
      </div>
    </div>
  </div>`;
}

function clinicView() {
  return `<div class="screen">
    ${screenHeader('DEMAND CLINIC', '正在问诊')}
    <div class="screen-content">
      <div class="clinic-head"><div><p class="kicker">IPD 001 · 需求问诊</p><h2 class="hero-title">把一句想法，收敛成一个<em>可行动的问题。</em></h2></div><div><span class="tag orange">制造业</span> <span class="tag blue">第 4 轮</span></div></div>
      <div class="clinic-grid">
        <section class="panel chat-panel"><div class="panel-head"><strong>与用户的对话</strong><span class="status">正在收敛</span></div><div class="chat-body"><div class="bubble ai">您提到“换模慢”。更影响经营结果的是停机时间、良品率，还是订单交付周期？</div><div class="bubble user">主要是停机。现在换一次模具要 45 分钟，老师傅经验也很难复制。</div><div class="bubble ai">如果三个月内完成第一阶段，您希望达到什么结果？</div><div class="bubble user">先降到 20 分钟以内，让新员工也能按标准完成。</div><div class="bubble-note"><i></i>已识别目标指标与关键用户，正在补全约束条件</div></div><div class="chat-composer"><span>继续补充背景，或确认右侧需求单…</span><button aria-label="发送需求">${icon('send')}</button></div></section>
        <section class="panel form-panel"><div class="panel-head"><strong>需求收敛确认单</strong><span>自动保存 · 刚刚</span></div><div class="form-body"><div class="score-card"><strong class="metric">86%</strong><div><span>需求完整度</span><b>具备进入概念验证的条件</b></div></div><div class="field-grid"><div class="field wide"><label>核心问题</label><b>换模依赖老师傅经验，停机时间长且标准难以复制</b></div><div class="field"><label>目标指标</label><b>45 分钟 → 20 分钟内</b></div><div class="field"><label>首期周期</label><b>12 周</b></div><div class="field"><label>关键用户</label><b>班组长 / 新员工</b></div><div class="field"><label>建议形态</label><b>换模辅助工作台</b></div><div class="field wide"><label>下一步行动</label><b>采集一条典型产线的 20 次换模过程，建立动作基线</b></div></div><button class="form-cta" data-action="confirm-demand">确认需求，进入深度洞察</button></div></section>
      </div>
    </div>
  </div>`;
}

function insightView() {
  return `<div class="screen">
    ${screenHeader('DEEP INSIGHT', '洞察已生成')}
    <div class="insight-report-shell">
      <aside class="insight-toc"><span>REPORT OUTLINE</span><h3>深度洞察报告</h3><p>Markdown · V0.1</p><nav><button class="active" data-insight-section="insight-summary"><i>01</i>执行摘要</button><button data-insight-section="insight-root"><i>02</i>根因图谱</button><button data-insight-section="insight-impact"><i>03</i>影响分析</button><button data-insight-section="insight-evidence"><i>04</i>证据明细</button><button data-insight-section="insight-action"><i>05</i>行动建议</button></nav><div><span>阅读进度</span><b>5 个章节 · 8 分钟</b></div></aside>
      <article class="insight-report-page" aria-label="需求深度洞察完整报告">
        <header id="insight-summary" class="insight-cover"><div><span>DEEP INSIGHT · 2026.08.18</span><h1>不是“换模慢”，而是<br><em>经验没有成为组织能力。</em></h1><p>AI 将需求对话转化为问题结构、影响判断与可执行建议；报告中的每项结论均保留证据入口，供人工确认。</p></div><div class="insight-cover-visual" role="img" aria-label="生产线换模场景抽象示意图"><span>45</span><b>MIN</b><i></i><i></i><i></i><small>当前换模基线</small></div></header>
        <section class="insight-summary-grid"><div><span>核心判断</span><b>经验隐性化是首要根因</b><p>关键步骤依赖老师傅现场口授，无法稳定复制。</p></div><div><span>目标差距</span><b>25 min</b><p>当前 45 分钟，业务目标为 20 分钟以内。</p></div><div><span>建议动作</span><b>先验证 1 条产线</b><p>两周建立动作—耗时—异常数据基线。</p></div></section>
        <section id="insight-root" class="insight-report-section"><div class="report-section-title"><span>02 · ROOT CAUSE</span><h2>问题根因图谱</h2><p>从可见症状追溯到流程、知识和反馈机制。</p></div><figure class="insight-root-figure"><div class="root-core"><small>表层症状</small><strong>平均换模停机 45 分钟</strong></div><div class="root-branch"><span></span><i></i><i></i><i></i></div><div class="root-causes"><div class="cause"><b>经验隐性化</b><span>关键动作仅掌握在老师傅手中</span></div><div class="cause"><b>过程不可见</b><span>没有步骤耗时与异常数据</span></div><div class="cause"><b>反馈未闭环</b><span>换模结束后缺少结构化复盘</span></div></div><figcaption>图 1 · 根因关系基于 4 轮需求对话与现场观察生成，综合置信度 88%。</figcaption></figure></section>
        <section id="insight-impact" class="insight-report-section"><div class="report-section-title"><span>03 · BUSINESS IMPACT</span><h2>价值影响排序</h2></div><figure class="insight-impact-chart"><div><span>产线停机损失</span><i style="--w:92%"></i><b>92</b></div><div><span>人员培养周期</span><i style="--w:76%"></i><b>76</b></div><div><span>交付稳定性</span><i style="--w:62%"></i><b>62</b></div><div><span>质量追溯成本</span><i style="--w:54%"></i><b>54</b></div><figcaption>图 2 · 影响指数（0–100），数值标签始终可见，不仅依赖颜色区分。</figcaption></figure></section>
        <section id="insight-evidence" class="insight-report-section"><div class="report-section-title"><span>04 · EVIDENCE</span><h2>证据与缺口明细</h2></div><div class="report-table-wrap"><table class="report-table"><thead><tr><th>证据</th><th>观察结果</th><th>可信度</th><th>状态</th></tr></thead><tbody><tr><th>现场访谈</th><td>关键动作依赖老师傅口授</td><td>高</td><td>已验证</td></tr><tr><th>换模记录</th><td>平均耗时 45 分钟</td><td>中高</td><td>已采集</td></tr><tr><th>步骤级数据</th><td>尚无统一埋点与异常分类</td><td>—</td><td>待补齐</td></tr><tr><th>新员工测试</th><td>独立完成率尚未量化</td><td>低</td><td>待验证</td></tr></tbody></table></div></section>
        <section id="insight-action" class="insight-report-section insight-action-section"><div class="report-section-title"><span>05 · RECOMMENDATION</span><h2>IPD 第一步行动</h2></div><div class="insight-action-card"><span>建议从小范围验证开始</span><h3>选择 1 条高频换模产线，建立“动作—耗时—异常”数据基线。</h3><p>预计两周获得首批有效数据，不改造 MES、不触碰设备安全控制；完成后提交 TR1 人工评审。</p><div><b>负责人：需求分析 Agent</b><b>人工确认：需求管理专家</b><b>输出：需求合理性调研支撑</b></div></div></section>
        <footer class="insight-report-footer"><b>参考来源</b><span>[1] 需求确认单　[2] 现场访谈第 1–4 轮　[3] AI Lab 制造业知识库</span></footer>
      </article>
    </div>
  </div>`;
}

function pipelineView() {
  const phase = ipdPhases[state.selectedPhase];
  const selectedAgent = phase.agents.find((agent) => agent.id === state.selectedAgent) || phase.agents[0];
  const statusLabel = { working: '正在研判', waiting: '等待上游', locked: '阶段锁定' };
  const orchestration = `<div class="ipd-stage-grid">
    <section class="panel ipd-input-card">
      <div class="panel-head"><strong>本阶段任务</strong><span class="tag orange">${phase.name}</span></div>
      <div class="ipd-card-body"><p>${phase.objective}</p><h4>从刚刚的需求接收 · 点击打开</h4>${phase.inputs.map((item, i) => `<button class="ipd-input-row" data-artifact-title="${item}"><span>0${i + 1}</span><b>${item}</b><i>${i === 0 ? '查看内容' : '已挂载 · 打开'}</i></button>`).join('')}<div class="ipd-rule"><b>接力铁律</b><span>上一棒交不出评审输入，下一棒不启动。</span></div></div>
    </section>
    <section class="panel ipd-orchestration-card ${state.pipelinePlaying ? 'is-playing' : ''}">
      <div class="panel-head"><strong>多 Agent 协作编排</strong><span>${phase.agents.length} 个角色 · 1 个人工关口</span></div>
      <div class="base-agent-legend"><span>基础执行 Agent</span>${Object.values(baseAgents).map((agent) => `<div class="${agent.label === selectedAgent.base ? 'active' : ''}"><b>${agent.label}</b><small>${agent.verb}</small></div>`).join('')}<em>＋ IPD 专业角色插件</em></div>
      <div class="agent-lane"><div class="demand-node"><small>需求上下文</small><b>换模 45 → 20 分钟</b></div><div class="flow-arrow"><i></i><i></i><i></i></div><div class="agent-stack">${phase.agents.map((agent, i) => `<button class="agent-node ${agent.id === selectedAgent.id ? 'selected' : ''} ${agent.status}" data-ipd-agent="${agent.id}"><span>${agent.base} × ${agent.id}</span><b>${agent.name}</b><small>${agent.role}</small><em>${statusLabel[agent.status]}</em>${i < phase.agents.length - 1 ? '<i class="parallel-mark">并行</i>' : ''}</button>`).join('')}</div><div class="flow-arrow merge"><i></i><i></i><i></i></div><div class="human-node"><span>HUMAN</span><b>专家确认</b><small>结论可追溯</small></div></div>
      <div class="agent-inspector"><div class="agent-avatar">${selectedAgent.id.split('-')[1]}</div><div><small>${selectedAgent.base} 基础 Agent · 挂载 ${selectedAgent.role}</small><b>${selectedAgent.name}：${baseAgents[selectedAgent.base].verb}</b><p>${selectedAgent.job}</p></div><span class="agent-permission">${selectedAgent.base === 'Coder' ? '批准后写入' : selectedAgent.base === 'Supervision' ? '独立审查' : '检索与起草'}</span></div>
    </section>
    <section class="panel ipd-gate-card">
      <div class="panel-head"><strong>评审与决策门</strong><span>Evidence Gate</span></div>
      <div class="ipd-card-body"><div class="gate-list">${phase.reviews.map((review) => { const reviewer = humanReviewers[review] || humanReviewers.TR1; const reviewState = reviewStatus[getReviewState(review)]; return `<button class="gate-item ${reviewState[1]}" data-review-gate="${review}"><span>${review}</span><div><b>${reviewer.role}</b><small>${reviewer.person} · ${reviewState[0]}</small></div></button>`; }).join('')}</div><h4>计划产出 · 全部可演示</h4><div class="output-cloud">${phase.outputs.map(item => `<button data-artifact-title="${item}"><span>${item}</span><i>打开演示 ↗</i></button>`).join('')}</div></div>
    </section>
  </div>`;
  const deliverables = `<div class="ipd-deliverable-board">${ipdPhases.map((item, i) => `<section class="panel deliverable-column ${i === state.selectedPhase ? 'active' : ''}"><header><span>0${i + 1}</span><div><b>${item.name}</b><small>${item.reviews.join(' / ')}</small></div></header><div>${item.outputs.map((output, j) => `<button class="artifact ${i === 0 && j < 2 ? 'ready' : ''}" data-artifact-title="${output}"><i></i><span>${output}</span><em>${i === 0 && j < 2 ? '打开 · 生成中' : '打开演示'}</em></button>`).join('')}</div></section>`).join('')}</div>`;
  const canAdvance = phase.reviews.every((review) => getReviewState(review) === 'approved');
  const pendingReview = phase.reviews.find((review) => getReviewState(review) !== 'approved');
  return `<div class="screen">
    ${screenHeader('IPD ORCHESTRATION', `${phase.name}阶段 · ${phase.reviews[0]} 准备中`)}
    <div class="screen-content ipd-screen-content">
      <div class="ipd-command"><div><p class="kicker">DEMAND-DRIVEN IPD · 12 AGENTS</p><h2 class="ipd-title">需求“换模 45 → 20 分钟”将如何被<em>12 个角色</em>接力完成？</h2></div><div class="ipd-controls"><div class="ipd-mode-toggle"><button class="${state.pipelineMode === 'orchestration' ? 'active' : ''}" data-ipd-mode="orchestration">协作编排</button><button class="${state.pipelineMode === 'deliverables' ? 'active' : ''}" data-ipd-mode="deliverables">交付件全景</button></div><button class="ipd-play" data-ipd-play>${state.pipelinePlaying ? '暂停演示' : '播放协作'}</button><button class="ipd-cast" data-ipd-cast>${icon('display')}投到 06 主屏</button></div></div>
      <div class="ipd-phase-rail">${ipdPhases.map((item, i) => `<button class="ipd-phase ${i === state.selectedPhase ? 'active' : ''} ${i < state.selectedPhase ? 'done' : ''}" data-ipd-phase="${i}"><span>0${i + 1}</span><div><b>${item.name}</b><small>${item.short}</small></div><em>${item.reviews.join(' · ')}</em></button>`).join('')}</div>
      ${approvalRouteBar(phase)}
      ${state.pipelineMode === 'orchestration' ? orchestration : deliverables}
      <div class="ipd-footer"><span><b>职责边界：</b>AI 生产交付件 · 人在飞书完成评审与确认</span><span><b>门禁状态：</b>${canAdvance ? '本阶段全部人工审批通过' : `等待 ${pendingReview} 人工结论`}</span><button data-ipd-advance ${canAdvance ? '' : 'disabled'}>${canAdvance ? '进入下一阶段' : `待 ${pendingReview} 审批`}</button></div>
    </div>
    ${artifactOverlay()}${feishuReviewOverlay()}${assistantDock()}
  </div>`;
}

function giantWorkbenchView() {
  if (state.giantMode === 'artifact') return giantArtifactView();
  if (state.giantMode === 'orchestration') return giantOrchestrationView();
  return `<div class="giant-workbench">
    <section class="giant-col"><span class="giant-label">01 · 用户对话 / CONVERSATION</span><div class="giant-chat"><div class="bubble ai">如果把换模时间降到 20 分钟，最先受益的会是谁？</div><div class="bubble user">班组长和新员工，他们需要一套能边做边提示的工具。</div><div class="bubble ai">明白。我们将优先生成“换模辅助工作台”，包含步骤、计时、异常提示和复盘。</div></div><div class="summary-card"><h3>对话已确认</h3><dl><div><dt>目标用户</dt><dd>班组长 / 新员工</dd></div><div><dt>核心指标</dt><dd>换模 ≤ 20 分钟</dd></div><div><dt>首期范围</dt><dd>1 条典型产线</dd></div></dl></div></section>
    <section class="giant-col"><span class="giant-label">02 · 共创工作台 / LIVE WORKBENCH</span><h2 class="giant-title">换模辅助工作台 <span style="color:var(--orange)">V1</span></h2><p class="giant-sub">需求确认后，表单与可操作原型同步生成</p><div class="giant-form"><div class="giant-field wide"><span>任务目标</span><b>通过步骤引导和实时计时，将换模过程标准化</b></div><div class="giant-field"><span>当前步骤</span><b>02 · 拆卸旧模具</b></div><div class="giant-field"><span>本次计时</span><b class="metric">06:42</b></div></div><div class="prototype-window"><header><i></i><i></i><i></i></header><div class="proto-body"><div class="proto-menu"><i></i><i></i><i></i><i></i></div><div class="proto-main"><div></div><div></div><div></div></div></div></div></section>
    <section class="giant-col"><span class="giant-label">03 · 需求与价值 / OUTCOME</span><div class="summary-card"><h3>需求确认单</h3><dl><div><dt>问题完整度</dt><dd>86%</dd></div><div><dt>方案可验证性</dt><dd>高</dd></div><div><dt>预计验证周期</dt><dd>12 周</dd></div><div><dt>数据准备度</dt><dd>需采集</dd></div></dl></div><div class="summary-card"><h3>第一阶段交付</h3><dl><div><dt>交互原型</dt><dd>已生成</dd></div><div><dt>需求说明</dt><dd>已生成</dd></div><div><dt>验证清单</dt><dd>6 项</dd></div></dl></div><div class="value-card"><span>目标改善</span><b class="metric">45 → 20 min</b><small>换模停机时间预计降低 55%</small></div></section>
  </div>`;
}

function giantOrchestrationView() {
  const phase = ipdPhases[state.selectedPhase];
  return `<div class="giant-ipd ${state.pipelinePlaying ? 'is-playing' : ''}">
    <section class="giant-ipd-left"><div class="giant-ipd-label">01 · 需求如何进入 IPD</div><div class="giant-demand"><span>已收敛需求</span><h2>把换模停机从<br><em>45 分钟降至 20 分钟</em></h2><p>让班组长和新员工都能按照标准完成换模，并持续沉淀现场经验。</p><div><b>关键用户</b><span>班组长 / 新员工</span></div><div><b>首期范围</b><span>1 条典型产线 · 12 周</span></div></div><div class="giant-phase-list">${ipdPhases.map((item, i) => `<button class="${i === state.selectedPhase ? 'active' : ''}" data-ipd-phase="${i}"><span>0${i + 1}</span><div><b>${item.name}</b><small>${item.short}</small></div></button>`).join('')}</div></section>
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
  return `<div class="screen">
    ${screenHeader('LIVE PROTOTYPE', '原型可操作')}
    <div class="screen-content"><p class="kicker">WORKBUDDY · GENERATED EXPERIENCE</p><h2 class="hero-title">换模辅助工作台 <span class="orange">V1</span></h2><p class="lead">这是根据刚才的对话即时生成的可操作原型。</p><div class="live-layout"><aside class="panel live-side"><h3>换模任务 #0248</h3><div class="live-nav"><div>01 · 安全确认</div><div class="active">02 · 拆卸旧模具</div><div>03 · 清洁定位面</div><div>04 · 安装新模具</div><div>05 · 首件试制</div><div>06 · 完成复盘</div></div></aside><section class="panel live-main"><div class="panel-head" style="margin:-16px -16px 14px"><strong>现场执行面板</strong><span class="status">计时中 · 06:42</span></div><div class="live-kpis"><div class="live-kpi"><span>目标总时长</span><b class="metric">20:00</b></div><div class="live-kpi"><span>当前进度</span><b class="metric">33%</b></div><div class="live-kpi"><span>安全检查</span><b style="color:var(--mint)">已通过</b></div></div><div class="task-board"><div class="task-col"><h4>当前操作</h4><div class="task">确认吊装设备处于待机位<b>已完成</b></div><div class="task">松开四角固定螺栓<b>进行中 · 2/4</b></div></div><div class="task-col"><h4>智能提示</h4><div class="task">右后角螺栓上次出现扭矩异常，请优先检查。<b>查看历史记录</b></div></div><div class="task-col"><h4>现场记录</h4><div class="task">点击记录异常、拍照或语音补充。<b>添加一条记录</b></div></div></div></section></div></div>
  </div>`;
}

const experienceSteps = ['进入体验','需求问诊','确认需求','深度洞察','生成原型','体验修改','方案带走'];

function experienceWelcome(station) {
  return `<div class="experience-welcome"><section class="panel welcome-card"><p class="kicker">START YOUR OWN AI JOURNEY</p><h2 class="hero-title">今天，你想让 AI<br>帮你解决<em>什么问题？</em></h2><p class="lead">选择一个角色开始，或者直接说出你正在面对的真实业务问题。</p><div class="role-grid"><button class="role-card" data-exp-next><b>企业经营者</b><span>增长、效率和管理问题</span></button><button class="role-card" data-exp-next><b>业务负责人</b><span>流程、协同和执行问题</span></button><button class="role-card" data-exp-next><b>技术负责人</b><span>系统、数据和 AI 落地</span></button><button class="role-card" data-exp-next><b>自由探索</b><span>从一句想法开始</span></button></div></section><aside class="panel station-guide"><h3>体验中心 ${station}</h3><ol><li>全过程约 8–12 分钟</li><li>你的需求拥有独立会话，不会与其他工位串扰</li><li>最后会生成专属建设方案和短效二维码</li></ol><div class="privacy">你的详细对话仅在本工位显示。主控端默认只看到体验阶段和授权后的需求摘要。</div></aside></div>`;
}

function experienceMiddle(step) {
  const configs = {
    1: ['先聊聊你的真实问题','AI 会通过几轮对话，帮助你从现象找到真正需要解决的问题。','您最希望改善的是效率、成本、质量，还是客户体验？','我们订单品种越来越多，排产经常临时调整。'],
    2: ['确认我们理解得对不对','所有信息都可以修改；只有你确认后，才会进入下一步。','核心问题：多品种订单下，人工排产调整慢且容易遗漏约束。','目标：把临时订单的响应时间从 2 小时缩短至 20 分钟。'],
    3: ['看见问题背后的机会','AI 正在把需求转化为根因、价值影响和第一步行动建议。','根因：订单、产能和物料约束分散在多个系统与个人经验中。','建议：先选择一个车间，建立统一排产约束表并验证推荐效果。'],
    4: ['第一个原型已经生成','这不是最终产品，而是用于快速验证方向的可操作版本。','智能排产工作台 V1','包含订单优先级、产能约束、缺料提醒和方案对比。'],
    5: ['现在，请亲手试一试','修改条件、点击方案，告诉 AI 哪些地方不符合你的实际工作。','体验任务：插入一个紧急订单','观察推荐方案是否保持关键客户订单按期交付。'],
  };
  const c = configs[step];
  return `<div class="experience-step"><section class="panel step-copy"><span class="tag orange">步骤 0${step + 1}</span><h2 style="margin-top:16px">${c[0]}</h2><p>${c[1]}</p><div class="step-actions"><button class="back" data-exp-back>上一步</button><button class="next" data-exp-next>${step === 5 ? '生成建设方案' : '继续下一步'}</button></div></section><section class="panel step-preview"><div class="panel-head" style="margin:-17px -17px 16px"><strong>${step === 1 ? '与 AI 对话' : step === 4 || step === 5 ? '可操作原型' : 'AI 生成内容'}</strong><span class="status">实时保存</span></div>${step === 1 ? `<div class="bubble ai">${c[2]}</div><div class="bubble user" style="margin:10px 0 0 auto">${c[3]}</div><div class="chat-composer" style="margin:18px 0 0"><span>继续补充你的情况…</span><button aria-label="发送">${icon('send')}</button></div>` : step === 4 || step === 5 ? `<div class="prototype-window" style="height:300px"><header><i></i><i></i><i></i></header><div class="proto-body" style="height:268px"><div class="proto-menu"><i></i><i></i><i></i><i></i></div><div class="proto-main"><div></div><div></div><div></div></div></div></div><p class="lead">${c[3]}</p>` : `<div class="score-card"><strong>${step === 2 ? '92%' : '3×'}</strong><div><span>${step === 2 ? '需求完整度' : '关键根因'}</span><b>${c[2]}</b></div></div><div class="action-box"><span>${step === 2 ? '目标指标' : '第一步建议'}</span><b>${c[3]}</b></div>`}</section></div>`;
}

function experienceResult() {
  const squares = Array.from({ length: 49 }, (_, i) => `<i style="${(i * 7 + 3) % 11 === 0 ? 'background:transparent' : ''}"></i>`).join('');
  return `<section class="panel qr-card"><div><span class="tag mint">全流程已完成</span><h2 style="margin-top:17px">你的《AI 建设建议方案》<br>已经生成。</h2><p>包括需求摘要、问题洞察、原型方向、首期验证范围和下一步推进建议。二维码将在 24 小时后失效。</p><div style="display:flex;gap:8px;margin-top:20px"><button class="soft-button" data-exp-back>返回修改</button><button class="mini-action" style="min-height:44px">提交需求并预约沟通</button></div></div><div class="qr-box" aria-label="专属方案二维码">${squares}</div></section>`;
}

function experienceView() {
  const station = state.view.split('-').pop();
  const body = state.experienceStep === 0 ? experienceWelcome(station) : state.experienceStep === 6 ? experienceResult() : experienceMiddle(state.experienceStep);
  return `<div class="screen experience-screen">${screenHeader(`EXPERIENCE CENTER ${station}`, '独立会话')}
    <div class="screen-content"><div class="experience-top"><div><p class="kicker">YOUR OWN AI CO-CREATION</p><h2 class="hero-title" style="font-size:34px">完整体验，从一个<em>真实问题</em>开始。</h2></div><div class="station-badge"><small>当前工位</small><b>CENTER ${station}</b></div></div><div class="journey">${experienceSteps.map((label,i)=>`<button data-exp-step="${i}" class="${i<state.experienceStep?'done':''} ${i===state.experienceStep?'active':''}"><span>${i+1}</span>${label}</button>`).join('')}</div><div class="experience-body">${body}</div></div>
  </div>`;
}

const builders = {
  controller: controllerView,
  'screen-00': introView,
  'screen-01': welcomeView,
  'screen-02': dashboardView,
  'screen-03': clinicView,
  'screen-04': insightView,
  'screen-05': pipelineView,
  'screen-06': giantWorkbenchView,
  'screen-07': livePrototypeView,
};

function attachScreenActions() {
  document.querySelector('[data-intro-replay]')?.addEventListener('click', () => {
    state.introSkipped = false;
    render();
  });
  document.querySelector('[data-intro-skip]')?.addEventListener('click', () => {
    state.introSkipped = true;
    render();
  });
  document.querySelectorAll('[data-insight-section]').forEach((button) => button.addEventListener('click', () => {
    const target = document.getElementById(button.dataset.insightSection);
    target?.scrollIntoView({ behavior: state.paused ? 'auto' : 'smooth', block: 'start' });
    document.querySelectorAll('[data-insight-section]').forEach((item) => item.classList.toggle('active', item === button));
  }));
  document.querySelector('[data-action="confirm-demand"]')?.addEventListener('click', () => showToast('需求已确认 · 洞察报告正在生成'));
  document.querySelector('[data-action="ignite"]')?.addEventListener('click', () => { setView('screen-06'); showToast('001 实战主屏已启动'); });
  document.querySelectorAll('[data-ipd-phase]').forEach((button) => button.addEventListener('click', () => {
    state.selectedPhase = Number(button.dataset.ipdPhase);
    state.selectedAgent = ipdPhases[state.selectedPhase].agents[0].id;
    state.selectedArtifact = null;
    state.artifactOpen = false;
    state.activeReview = null;
    state.reviewDecision = null;
    render('phase');
  }));
  document.querySelectorAll('[data-ipd-agent]').forEach((button) => button.addEventListener('click', () => {
    state.selectedAgent = button.dataset.ipdAgent;
    render('agent');
  }));
  document.querySelectorAll('[data-ipd-mode]').forEach((button) => button.addEventListener('click', () => {
    state.pipelineMode = button.dataset.ipdMode;
    render('mode');
  }));
  document.querySelectorAll('[data-ipd-play]').forEach((button) => button.addEventListener('click', () => {
    state.pipelinePlaying = !state.pipelinePlaying;
    render(state.pipelinePlaying ? 'workflow-play' : 'workflow-pause');
  }));
  document.querySelector('[data-ipd-cast]')?.addEventListener('click', () => {
    state.giantMode = 'orchestration';
    setView('screen-06', 'cast');
    showToast('IPD 编排沙盘已投送到 06 主屏');
  });
  document.querySelector('[data-ipd-advance]')?.addEventListener('click', () => {
    state.selectedPhase = Math.min(ipdPhases.length - 1, state.selectedPhase + 1);
    state.selectedAgent = ipdPhases[state.selectedPhase].agents[0].id;
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
  document.querySelector('[data-review-submit]')?.addEventListener('click', () => {
    if (!state.reviewDecision) {
      showToast('请先选择通过、要求修改或拒绝');
      return;
    }
    const comment = document.getElementById('review-comment')?.value.trim();
    if (state.reviewDecision !== 'approved' && !comment) {
      showToast('要求修改或拒绝时，请填写审批意见');
      return;
    }
    state.reviewStates[state.activeReview] = state.reviewDecision;
    const resultText = reviewStatus[state.reviewDecision][0];
    state.reviewDecision = null;
    render('review-result');
    showToast(`飞书审批已提交：${resultText}`);
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
    state.assistantQuestion = button.dataset.assistantQuery;
    state.avatarSpeaking = true;
    render('assistant');
  }));
  document.querySelector('[data-assistant-send]')?.addEventListener('click', () => {
    state.assistantQuestion = document.getElementById('assistant-input')?.value || '请解释当前内容。';
    state.avatarSpeaking = true;
    render('assistant');
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
  document.querySelectorAll('[data-exp-step]').forEach((button) => button.addEventListener('click', () => {
    state.experienceStep = Number(button.dataset.expStep);
    render();
  }));
  document.querySelectorAll('[data-exp-next]').forEach((button) => button.addEventListener('click', () => {
    state.experienceStep = Math.min(6, state.experienceStep + 1);
    render();
  }));
  document.querySelectorAll('[data-exp-back]').forEach((button) => button.addEventListener('click', () => {
    state.experienceStep = Math.max(0, state.experienceStep - 1);
    render();
  }));
}

function render(intent = 'refresh') {
  const meta = viewMeta[state.view] || viewMeta.controller;
  const canvas = document.getElementById('screen-canvas');
  const token = ++motionSystem.renderToken;
  const commit = () => {
    if (token !== motionSystem.renderToken) return;
    stopScreenMotion();
    const builder = state.view.startsWith('experience-') ? experienceView : (builders[state.view] || controllerView);
    canvas.innerHTML = builder();
    document.getElementById('page-title').textContent = meta[0];
    document.getElementById('frame-label').textContent = meta[1];
    document.getElementById('frame-size').textContent = meta[2];
    canvas.classList.remove('switching');
    attachScreenActions();
    runScreenMotion(intent);
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
  state.view = view;
  if (!view.startsWith('experience-')) state.experienceStep = 0;
  const params = new URLSearchParams(location.search);
  params.set('view', view);
  if (view === 'screen-06' && state.giantMode !== 'workbench') params.set('mode', state.giantMode); else params.delete('mode');
  if (view === 'screen-06' && state.giantMode === 'artifact' && state.selectedArtifact) params.set('artifact', state.selectedArtifact); else params.delete('artifact');
  history.replaceState({}, '', `${location.pathname}?${params}`);
  buildNavigation();
  render(intent);
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

document.getElementById('next-stage').addEventListener('click', () => {
  state.stage = (state.stage + 1) % stages.length;
  buildTourSteps();
  showToast(`已推进到${stages[state.stage][0]} · ${stages[state.stage][1]}`);
  if (state.view === 'controller') render();
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
  if (event.key === 'Escape' && (state.artifactOpen || state.assistantOpen || state.activeReview)) {
    const selector = state.activeReview ? '.review-overlay' : state.artifactOpen ? '.artifact-overlay' : '.assistant-panel';
    closeSurface(selector, () => {
      state.artifactOpen = false;
      state.assistantOpen = false;
      state.avatarSpeaking = false;
      state.activeReview = null;
      state.reviewDecision = null;
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
