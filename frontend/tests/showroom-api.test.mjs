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
      search: '?view=screen-03',
      hostname: 'showroom.example',
      protocol: 'https:',
      host: 'showroom.example',
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
