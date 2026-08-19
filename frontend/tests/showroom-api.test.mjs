import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../public/showroom/showroom-api.js', import.meta.url), 'utf8');

function storage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  };
}

function createApi() {
  let timerId = 0;
  const timers = new Map();
  const listeners = new Map();
  const window = {
    __SHOWROOM_TEST__: true,
    localStorage: storage({
      'ai-lab-platform.auth': JSON.stringify({ accessToken: 'platform-token' }),
    }),
    sessionStorage: storage(),
    location: {
      pathname: '/showroom/',
      search: '?view=screen-03',
      hash: '',
      hostname: 'showroom.example',
      protocol: 'https:',
      host: 'showroom.example',
      replace: (url) => { window.replacedLocation = url; },
    },
    document: {
      hidden: false,
      addEventListener: (type, listener) => listeners.set(type, listener),
    },
    addEventListener: (type, listener) => listeners.set(type, listener),
    setTimeout: (callback, delay) => {
      timerId += 1;
      timers.set(timerId, { callback, delay });
      return timerId;
    },
    clearTimeout: (id) => timers.delete(id),
    HermesShared: {
      JsonRpcGatewayClient: class {},
    },
  };
  class FakeWebSocket {}
  FakeWebSocket.CONNECTING = 0;
  FakeWebSocket.OPEN = 1;
  const context = vm.createContext({
    window,
    URLSearchParams,
    Headers,
    WebSocket: FakeWebSocket,
    fetch: async () => { throw new Error('unexpected fetch'); },
    console,
  });
  vm.runInContext(source, context);
  return { api: window.showroomApi, timers, window };
}

test('Hermes serve token is cached until an explicit refresh', async () => {
  const { api } = createApi();
  let requests = 0;
  api.request = async () => ({ token: `token-${++requests}` });

  assert.equal(await api.getHermesServeToken(), 'token-1');
  assert.equal(await api.getHermesServeToken(), 'token-1');
  assert.equal(requests, 1);
  assert.equal(await api.getHermesServeToken({ refresh: true }), 'token-2');
  assert.equal(requests, 2);
});

test('forced callers reuse the active Hermes connection promise', async () => {
  const { api } = createApi();
  api.hermesConnectPromise = Promise.resolve('live-session');
  api.getHermesServeToken = async () => { throw new Error('second connection started'); };

  assert.equal(await api.ensureHermes({ force: true }), 'live-session');
});

test('automatic reconnect uses five delays and then stops', () => {
  const { api, timers } = createApi();
  api.hermesSuspended = false;
  const delays = [];

  for (let attempt = 0; attempt < 5; attempt += 1) {
    api.scheduleHermesReconnect();
    const timer = timers.get(api.hermesReconnectTimer);
    delays.push(timer.delay);
    timers.delete(api.hermesReconnectTimer);
    api.hermesReconnectTimer = null;
  }
  api.scheduleHermesReconnect();

  assert.deepEqual(delays, [1000, 2000, 4000, 8000, 15000]);
  assert.equal(api.hermesReconnectExhausted, true);
  assert.equal(api.hermesStatus, 'error');
  assert.equal(api.hermesReconnectTimer, null);
});

test('suspending a page closes both sockets and clears reconnect timers', () => {
  const { api, window } = createApi();
  let gatewayClosed = 0;
  let showroomClosed = 0;
  api.hermes = { close: () => { gatewayClosed += 1; } };
  api.ws = { close: () => { showroomClosed += 1; } };
  api.hermesReconnectTimer = window.setTimeout(() => {}, 1000);
  api.retryTimer = window.setTimeout(() => {}, 1000);

  api.suspendHermes({ suspendShowroom: true });

  assert.equal(gatewayClosed, 1);
  assert.equal(showroomClosed, 1);
  assert.equal(api.hermesReconnectTimer, null);
  assert.equal(api.retryTimer, null);
  assert.equal(api.hermesStatus, 'idle');
});

test('assistant machine envelopes are hidden and extraction persists the returned session', async () => {
  const { api } = createApi();
  const content = `可见确认单\n<!-- AI_LAB_DEMAND_V1\n{"title":"测试"}\nAI_LAB_DEMAND_V1 -->`;
  assert.equal(api.visibleAssistantMessage(content), '可见确认单');

  api.request = async (path, options) => {
    assert.match(path, /\/demand\/extract$/);
    assert.equal(options.body.content, content);
    return { recognized: true, session: { data: { demand: { core_problem: '已回填' } } } };
  };
  const result = await api.extractDemand(content);
  assert.equal(result.recognized, true);
  assert.equal(api.session.data.demand.core_problem, '已回填');
});

test('V1.7 fenced YAML demand envelopes stay hidden from the customer', () => {
  const { api } = createApi();
  const content = `## 需求收敛确认单｜C036

这里是客户可见的收敛内容。

\`\`\`yaml
AI_LAB_DEMAND_V1:
  customer_code: C036
  business_scene: 基于既有混合底座建设 AI 基础设施
  status: draft
\`\`\``;

  assert.equal(
    api.visibleAssistantMessage(content),
    '## 需求收敛确认单｜C036\n\n这里是客户可见的收敛内容。',
  );
});

test('demand interview state envelopes stay invisible', () => {
  const { api } = createApi();
  const assistant = `只问一个问题
<!-- AI_LAB_DEMAND_STATE_V1 {"status":"collecting","dimensions":{}} AI_LAB_DEMAND_STATE_V1 -->`;

  assert.equal(api.visibleAssistantMessage(assistant), '只问一个问题');
});

test('demand extraction sends the isolated frontstage Hermes session id', async () => {
  const { api } = createApi();
  api.session = {
    data: {
      hermes_sessions: {
        backstage_stored_session_id: 'backstage-1',
        frontstage_stored_session_id: 'frontstage-1',
      },
    },
  };
  api.request = async (_path, options) => {
    assert.equal(options.body.hermes_stored_session_id, 'frontstage-1');
    return { recognized: false, session: api.session };
  };

  await api.extractDemand('AI_LAB_DEMAND_STATE_V1');
});

test('visitor insight envelopes and invisible control messages never reach the frontstage UI', () => {
  const { api } = createApi();
  const content = `客户摘要\n<!-- AI_LAB_VISITOR_INSIGHT_V1 {"verified_facts":["事实"]} AI_LAB_VISITOR_INSIGHT_V1 -->`;

  assert.equal(api.visibleAssistantMessage(content), '客户摘要');
});

test('staffing and incremental insight envelopes never reach the customer UI', () => {
  const { api } = createApi();
  const content = `<!-- AI_LAB_STAFFING_PLAN_V1 {"plan_id":"job-1"} AI_LAB_STAFFING_PLAN_V1 -->
<!-- AI_LAB_INSIGHT_STAGE_V1 {"event_id":"e1"} AI_LAB_INSIGHT_STAGE_V1 -->
<!-- AI_LAB_INSIGHT_SECTION_V1 {"event_id":"e2","payload":{"title":"报告"}} AI_LAB_INSIGHT_SECTION_V1 -->
<!-- AI_LAB_INSIGHT_V1 {"job_id":"job-1"} AI_LAB_INSIGHT_V1 -->`;

  assert.equal(api.visibleAssistantMessage(content), '');
});

test('insight job API methods persist every returned session', async () => {
  const { api } = createApi();
  api.sessionId = 'visit-1';
  const calls = [];
  api.request = async (path, options) => {
    calls.push([path, options]);
    return { session: { session_id: 'visit-1', data: { insight_job: { job_id: 'job-1' } } } };
  };

  await api.startInsightJob();
  await api.saveStaffingPlan('job-1', { squads: [] });
  await api.updateInsightProgress('job-1', { event_id: 'e1', kind: 'stage', stage: 'analysis' });
  await api.completeInsightJob('job-1', 'machine blocks');

  assert.deepEqual(calls.map(([path]) => path), [
    '/api/showroom/sessions/visit-1/insight/jobs',
    '/api/showroom/sessions/visit-1/insight/jobs/job-1/plan',
    '/api/showroom/sessions/visit-1/insight/jobs/job-1/progress',
    '/api/showroom/sessions/visit-1/insight/jobs/job-1/complete',
  ]);
  assert.equal(api.session.data.insight_job.job_id, 'job-1');
});

test('visitor insight extraction persists the active main session', async () => {
  const { api } = createApi();
  api.sessionId = 'visit-current';
  api.request = async (path, options) => {
    assert.equal(path, '/api/showroom/visits/visit-current/insight/extract');
    assert.match(options.body.content, /AI_LAB_VISITOR_INSIGHT_V1/);
    return { recognized: true, session: { session_id: 'visit-current', data: { customer_insight: { status: 'completed' } } } };
  };

  await api.extractVisitorInsight('<!-- AI_LAB_VISITOR_INSIGHT_V1 {} AI_LAB_VISITOR_INSIGHT_V1 -->');
  assert.equal(api.session.data.customer_insight.status, 'completed');
});

test('bootstrap follows the server-owned active main visit session', async () => {
  const { api, window } = createApi();
  api.connect = () => {};
  api.resumeHermes = () => {};
  api.request = async (path) => {
    if (path === '/health') return { ok: true };
    assert.match(path, /\/api\/showroom\/bootstrap/);
    return {
      active_main_session_id: 'visit-server-owned',
      runtime: { epoch: 7 },
      session: { session_id: 'visit-server-owned', slot: 'main', data: {} },
    };
  };

  await api.init({ force: true });

  assert.equal(api.sessionId, 'visit-server-owned');
  assert.equal(api.session.session_id, 'visit-server-owned');
  assert.equal(window.sessionStorage.getItem('ai-lab-showroom.session'), 'visit-server-owned');
});

test('rollover adopts the new main visit session', async () => {
  const { api, window } = createApi();
  api.sessionId = 'visit-old';
  api.slot = 'main';
  api.request = async (path, options) => {
    assert.equal(path, '/api/showroom/visits/visit-old/rollover');
    assert.equal(options.method, 'POST');
    return {
      session: {
        session_id: 'visit-new',
        slot: 'main',
        data: { visitor: { status: 'preparing' } },
      },
      runtime: { active_main_session_id: 'visit-new', epoch: 8 },
    };
  };

  await api.rolloverVisit();

  assert.equal(api.sessionId, 'visit-new');
  assert.equal(api.slot, 'main');
  assert.equal(api.state.active_main_session_id, 'visit-new');
  assert.equal(window.sessionStorage.getItem('ai-lab-showroom.session'), 'visit-new');
});

test('expired showroom authentication returns to login with the current screen', async () => {
  const { api, window } = createApi();
  api.request = async () => {
    const error = new Error('expired');
    error.status = 401;
    throw error;
  };

  await api.init({ force: true });

  assert.equal(
    window.replacedLocation,
    '/login?next=%2Fshowroom%2F%3Fview%3Dscreen-03',
  );
  assert.equal(window.localStorage.getItem('ai-lab-platform.auth'), null);
});
