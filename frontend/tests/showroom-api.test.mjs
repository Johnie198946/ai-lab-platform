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

test('visitor insight envelopes and invisible control messages never reach the frontstage UI', () => {
  const { api } = createApi();
  const content = `客户摘要\n<!-- AI_LAB_VISITOR_INSIGHT_V1 {"verified_facts":["事实"]} AI_LAB_VISITOR_INSIGHT_V1 -->`;

  assert.equal(api.visibleAssistantMessage(content), '客户摘要');
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
