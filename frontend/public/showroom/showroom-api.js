(function showroomApiBootstrap(global) {
  "use strict";

  const AUTH_KEY = "ai-lab-platform.auth";
  const SESSION_KEY = "ai-lab-showroom.session";
  const HERMES_RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 15000];

  function readJson(key) {
    try {
      return JSON.parse(global.localStorage.getItem(key) || "null");
    } catch {
      return null;
    }
  }

  function accessToken() {
    return readJson(AUTH_KEY)?.accessToken || "";
  }

  function showroomSessionId() {
    const existing = global.sessionStorage.getItem(SESSION_KEY);
    if (existing) return existing;
    const created = `showroom-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    global.sessionStorage.setItem(SESSION_KEY, created);
    return created;
  }

  function workstationSlot() {
    const params = new URLSearchParams(global.location.search);
    const explicit = params.get("slot");
    if (explicit && /^[1-5]$/.test(explicit)) return explicit;
    const view = params.get("view") || "";
    const matched = view.match(/^experience-0?([1-5])$/);
    return matched?.[1] || "main";
  }

  function isStaticDisplayView() {
    const view = new URLSearchParams(global.location.search).get("view") || "controller";
    return ["screen-00", "screen-01", "screen-02"].includes(view);
  }

  function isConversationView() {
    const view = new URLSearchParams(global.location.search).get("view") || "controller";
    return view === "screen-03" || /^experience-0?[1-5]$/.test(view);
  }

  function normalizeHermesMessages(messages) {
    return (Array.isArray(messages) ? messages : [])
      .filter((message) => ["user", "assistant"].includes(message?.role))
      .map((message) => ({
        role: message.role,
        content: visibleHermesMessage(
          message.role,
          String(message.content ?? message.text ?? ""),
        ),
      }))
      .filter((message) => message.content.trim());
  }

  function visibleHermesMessage(role, content) {
    if (role !== "user") return content;
    const invocation = global.HermesShared?.skillInvocationText?.(content);
    if (!invocation) return content;
    const marker = "用户原始问题：";
    const markerIndex = invocation.lastIndexOf(marker);
    return markerIndex >= 0 ? invocation.slice(markerIndex + marker.length).trim() : invocation;
  }

  class ShowroomApi {
    constructor() {
      this.ws = null;
      this.retryTimer = null;
      this.retryCount = 0;
      this.listeners = new Map();
      this.sessionId = showroomSessionId();
      this.slot = workstationSlot();
      this.status = "connecting";
      this.state = null;
      this.session = null;
      this.bootstrap = null;
      this.hermes = null;
      this.hermesLiveSessionId = "";
      this.hermesStoredSessionId = "";
      this.hermesStatus = "idle";
      this.hermesReconnectTimer = null;
      this.hermesReconnectCount = 0;
      this.hermesReconnectExhausted = false;
      this.hermesIntentionalClose = false;
      this.hermesConnectPromise = null;
      this.hermesServeToken = "";
      this.hermesAccessToken = accessToken();
      this.hermesSuspended = Boolean(global.document?.hidden) || !isConversationView();
      this.showroomIntentionalClose = false;
      this.lifecycleBound = false;
    }

    on(type, listener) {
      const listeners = this.listeners.get(type) || new Set();
      listeners.add(listener);
      this.listeners.set(type, listeners);
      return () => listeners.delete(listener);
    }

    emit(type, payload) {
      (this.listeners.get(type) || []).forEach((listener) => listener(payload));
    }

    setStatus(status, detail = "") {
      this.status = status;
      this.emit("status", { status, detail });
    }

    async request(path, options = {}) {
      const headers = new Headers(options.headers || {});
      headers.set("Accept", "application/json");
      const token = accessToken();
      if (token) headers.set("Authorization", `Bearer ${token}`);
      if (options.body !== undefined) headers.set("Content-Type", "application/json");
      const response = await fetch(path, {
        method: options.method || "GET",
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
      });
      if (!response.ok) {
        const message = await response.json().then((data) => data.detail).catch(() => response.statusText);
        const error = new Error(message || `HTTP ${response.status}`);
        error.status = response.status;
        throw error;
      }
      return response.status === 204 ? null : response.json();
    }

    async init(options = {}) {
      try {
        this.bindLifecycle();
        if (!options.force && isStaticDisplayView()) {
          this.setStatus("display", "纯展示页面，不连接业务后端");
          return;
        }
        this.setStatus("connecting", "正在连接业务后端");
        if (!accessToken()) {
          if (["localhost", "127.0.0.1"].includes(global.location.hostname)) {
            this.setStatus("demo", "本地演示模式");
            return;
          }
          this.setStatus("auth-required", "请先登录 AI Lab Platform");
          return;
        }
        await this.request("/health");
        const bootstrap = await this.request(
          `/api/showroom/bootstrap?session_id=${encodeURIComponent(this.sessionId)}&slot=${encodeURIComponent(this.slot)}`,
        );
        this.bootstrap = bootstrap;
        this.state = bootstrap.runtime;
        this.session = bootstrap.session;
        this.emit("bootstrap", bootstrap);
        this.connect();
        if (isConversationView()) this.resumeHermes();
      } catch (error) {
        this.setStatus(error.status === 401 ? "auth-required" : "offline", error.message);
      }
    }

    setHermesStatus(status, detail = "") {
      this.hermesStatus = status;
      this.emit("hermes-status", {
        status,
        detail,
        retryStopped: this.hermesReconnectExhausted,
      });
    }

    scheduleHermesReconnect() {
      if (
        this.hermesIntentionalClose
        || this.hermesSuspended
        || this.hermesReconnectTimer
        || this.hermesReconnectExhausted
        || !accessToken()
      ) return;
      if (this.hermesReconnectCount >= HERMES_RECONNECT_DELAYS.length) {
        this.hermesReconnectExhausted = true;
        this.setHermesStatus("error", "无法连接大架构师，已停止自动重试");
        return;
      }
      const delay = HERMES_RECONNECT_DELAYS[this.hermesReconnectCount];
      this.hermesReconnectCount += 1;
      this.setHermesStatus("reconnecting", `连接中断，${Math.ceil(delay / 1000)} 秒内恢复`);
      this.hermesReconnectTimer = global.setTimeout(() => {
        this.hermesReconnectTimer = null;
        this.ensureHermes().catch(() => {});
      }, delay);
    }

    async getHermesServeToken(options = {}) {
      const currentAccessToken = accessToken();
      if (currentAccessToken !== this.hermesAccessToken) {
        this.hermesAccessToken = currentAccessToken;
        this.hermesServeToken = "";
      }
      if (!options.refresh && this.hermesServeToken) return this.hermesServeToken;
      const { token } = await this.request("/api/v1/hermes/serve-token");
      if (!token) throw new Error("Hermes 会话令牌缺失");
      this.hermesServeToken = token;
      return token;
    }

    async ensureHermes(options = {}) {
      if (!global.HermesShared?.JsonRpcGatewayClient) {
        const error = new Error("Hermes Gateway 客户端未加载");
        this.setHermesStatus("error", error.message);
        throw error;
      }
      if (!accessToken()) {
        const error = new Error("请先登录 AI Lab Platform");
        this.setHermesStatus("auth-required", error.message);
        throw error;
      }
      if (this.hermesConnectPromise) return this.hermesConnectPromise;
      if (this.hermesSuspended || global.document?.hidden || !isConversationView()) {
        throw new Error("大架构师连接已暂停");
      }
      if (!options.force && this.hermes?.connectionState === "open" && this.hermesLiveSessionId) {
        return this.hermesLiveSessionId;
      }

      this.hermesConnectPromise = (async () => {
        global.clearTimeout(this.hermesReconnectTimer);
        this.hermesReconnectTimer = null;
        this.hermesIntentionalClose = false;
        this.setHermesStatus("connecting", "正在连接大架构师");

        if (this.hermes) {
          const previousGateway = this.hermes;
          this.hermes = null;
          this.hermesIntentionalClose = true;
          previousGateway.close();
          this.hermesIntentionalClose = false;
        }

        const token = await this.getHermesServeToken({ refresh: options.refreshToken });
        const gateway = new global.HermesShared.JsonRpcGatewayClient({
          closedErrorMessage: "大架构师连接已断开",
          connectErrorMessage: "无法连接大架构师",
          notConnectedErrorMessage: "大架构师尚未连接",
          requestIdPrefix: "showroom",
        });
        this.hermes = gateway;
        gateway.onEvent((event) => {
          if (event.session_id && event.session_id !== this.hermesLiveSessionId) return;
          this.emit("hermes-event", event);
        });
        gateway.onState((connectionState) => {
          if (gateway !== this.hermes) return;
          if (
            ["closed", "error"].includes(connectionState)
            && !this.hermesIntentionalClose
            && !this.hermesConnectPromise
          ) {
            this.scheduleHermesReconnect();
          }
        });

        const wsUrl = global.HermesShared.buildHermesWebSocketUrl({
          path: this.bootstrap?.capabilities?.hermes_gateway || "/api/ws",
          authParam: ["token", token],
        });
        await gateway.connect(wsUrl);
        if (this.hermesSuspended || global.document?.hidden || !isConversationView()) {
          gateway.close();
          throw new Error("大架构师连接已暂停");
        }

        const storedId = String(this.session?.data?.hermes_stored_session_id || "").trim();
        let result;
        if (storedId) {
          try {
            result = await gateway.request("session.resume", {
              session_id: storedId,
              source: "desktop",
              close_on_disconnect: false,
            });
          } catch {
            result = null;
          }
        }
        if (!result?.session_id) {
          result = await gateway.request("session.create", {
            source: "desktop",
            close_on_disconnect: false,
            title: `共创体验中心 · 需求问诊 · ${this.sessionId.slice(-8)}`,
          });
        }

        this.hermesLiveSessionId = String(result.session_id || "");
        this.hermesStoredSessionId = String(
          result.stored_session_id || result.session_key || result.resumed || storedId || "",
        );
        if (!this.hermesLiveSessionId || !this.hermesStoredSessionId) {
          throw new Error("Hermes 未返回可恢复的会话标识");
        }

        const resumedMessages = normalizeHermesMessages(result.messages);
        const shouldMarkInitialized = resumedMessages.length > 0 && !this.session?.data?.hermes_skill_initialized;
        if (this.hermesStoredSessionId !== storedId || shouldMarkInitialized) {
          this.session = await this.saveSession({
            data: {
              hermes_stored_session_id: this.hermesStoredSessionId,
              hermes_skill_initialized: shouldMarkInitialized,
            },
          });
        }
        this.hermesReconnectCount = 0;
        this.hermesReconnectExhausted = false;
        this.setHermesStatus(result.running ? "generating" : "online", result.running ? "正在恢复生成" : "大架构师已连接");
        this.emit("hermes-ready", {
          live_session_id: this.hermesLiveSessionId,
          stored_session_id: this.hermesStoredSessionId,
          messages: resumedMessages,
          running: Boolean(result.running),
        });
        return this.hermesLiveSessionId;
      })();

      try {
        return await this.hermesConnectPromise;
      } catch (error) {
        if (error.status === 401) this.hermesServeToken = "";
        if (this.hermesSuspended) {
          this.setHermesStatus("idle", "页面不可见，连接已暂停");
          throw error;
        }
        this.setHermesStatus(error.status === 401 ? "auth-required" : "error", error.message);
        this.scheduleHermesReconnect();
        throw error;
      } finally {
        this.hermesConnectPromise = null;
      }
    }

    retryHermes() {
      if (this.hermesConnectPromise) return this.hermesConnectPromise;
      global.clearTimeout(this.hermesReconnectTimer);
      this.hermesReconnectTimer = null;
      this.hermesReconnectCount = 0;
      this.hermesReconnectExhausted = false;
      this.hermesServeToken = "";
      this.hermesSuspended = Boolean(global.document?.hidden) || !isConversationView();
      if (this.hermesSuspended) return Promise.reject(new Error("当前页面不可见，暂不建立连接"));
      return this.ensureHermes({ force: true, refreshToken: true });
    }

    suspendHermes(options = {}) {
      this.hermesSuspended = true;
      global.clearTimeout(this.hermesReconnectTimer);
      this.hermesReconnectTimer = null;
      this.hermesIntentionalClose = true;
      const gateway = this.hermes;
      this.hermes = null;
      this.hermesLiveSessionId = "";
      gateway?.close();
      this.hermesIntentionalClose = false;
      if (options.suspendShowroom) {
        global.clearTimeout(this.retryTimer);
        this.retryTimer = null;
        this.showroomIntentionalClose = true;
        const showroomSocket = this.ws;
        this.ws = null;
        showroomSocket?.close();
      }
      this.setHermesStatus("idle", "页面不可见，连接已暂停");
    }

    resumeHermes() {
      if (global.document?.hidden || !isConversationView()) return;
      this.hermesSuspended = false;
      this.ensureHermes().catch(() => {});
    }

    bindLifecycle() {
      if (this.lifecycleBound) return;
      this.lifecycleBound = true;
      global.document?.addEventListener("visibilitychange", () => {
        if (global.document.hidden) {
          this.suspendHermes({ suspendShowroom: true });
          return;
        }
        this.showroomIntentionalClose = false;
        if (!isStaticDisplayView()) this.connect();
        this.resumeHermes();
      });
      global.addEventListener?.("pagehide", () => this.suspendHermes({ suspendShowroom: true }));
    }

    async submitHermesPrompt(question, options = {}) {
      const sessionId = await this.ensureHermes();
      let prompt = question;
      const skillInitialized = Boolean(this.session?.data?.hermes_skill_initialized);
      if (!skillInitialized) {
        const context = String(options.stationContext || "").trim();
        const arg = [context, `用户原始问题：${question}`].filter(Boolean).join("\n\n");
        const dispatched = await this.hermes.request("command.dispatch", {
          name: options.skillCommand || "solution-consultant-persona",
          arg,
          session_id: sessionId,
        });
        if (!dispatched || !["skill", "send"].includes(dispatched.type) || !dispatched.message) {
          throw new Error("大架构师技能加载失败");
        }
        prompt = dispatched.message;
      }
      this.setHermesStatus("generating", "大架构师正在理解需求");
      const response = await this.hermes.request("prompt.submit", {
        session_id: sessionId,
        text: prompt,
      });
      if (!skillInitialized) {
        this.saveSession({ data: { hermes_skill_initialized: true } }).catch(() => {});
      }
      return response;
    }

    async respondHermesClarify(requestId, answer) {
      if (!this.hermes || this.hermes.connectionState !== "open") await this.ensureHermes();
      this.setHermesStatus("generating", "已提交选择，继续收敛需求");
      return this.hermes.request("clarify.respond", {
        request_id: requestId,
        answer,
      });
    }

    async interruptHermes() {
      if (!this.hermesLiveSessionId || !this.hermes || this.hermes.connectionState !== "open") return;
      await this.hermes.request("session.interrupt", { session_id: this.hermesLiveSessionId });
      this.setHermesStatus("online", "本轮生成已停止");
    }

    connect() {
      const token = accessToken();
      if (!token || global.document?.hidden) return;
      if (this.ws && [WebSocket.CONNECTING, WebSocket.OPEN].includes(this.ws.readyState)) return;
      this.showroomIntentionalClose = false;
      global.clearTimeout(this.retryTimer);
      const protocol = global.location.protocol === "https:" ? "wss:" : "ws:";
      const url = `${protocol}//${global.location.host}/api/showroom/ws?token=${encodeURIComponent(token)}&session_id=${encodeURIComponent(this.sessionId)}`;
      const socket = new WebSocket(url);
      this.ws = socket;
      socket.addEventListener("open", () => {
        if (socket !== this.ws) return;
        this.retryCount = 0;
        this.setStatus("online");
      });
      socket.addEventListener("message", (event) => {
        if (socket !== this.ws) return;
        let message;
        try { message = JSON.parse(event.data); } catch { return; }
        if (message.type === "PING") {
          socket.send(JSON.stringify({ type: "PONG", at: Date.now() }));
          return;
        }
        if (message.type === "PREPARE") {
          socket.send(JSON.stringify({ type: "READY", epoch: message.epoch }));
        }
        if (message.state) this.state = message.state;
        this.emit("message", message);
      });
      socket.addEventListener("close", () => {
        if (socket !== this.ws || this.showroomIntentionalClose || global.document?.hidden) return;
        this.ws = null;
        this.setStatus("reconnecting");
        const delay = Math.min(10000, 800 * (2 ** this.retryCount++));
        this.retryTimer = global.setTimeout(() => this.connect(), delay);
      });
      socket.addEventListener("error", () => socket.close());
    }

    async commitStage(stage, payload = {}) {
      const epoch = Math.max(Date.now(), Number(this.state?.epoch || 0) + 1);
      await this.request("/api/showroom/commands", {
        method: "POST",
        body: { type: "PREPARE", epoch, stage, payload },
      });
      await new Promise((resolve) => global.setTimeout(resolve, 260));
      const state = await this.request("/api/showroom/commands", {
        method: "POST",
        body: { type: "COMMIT", epoch, stage, payload },
      });
      this.state = state;
      return state;
    }

    async submitReview(gate, decision, comment, phase) {
      const state = await this.request(`/api/showroom/reviews/${encodeURIComponent(gate)}`, {
        method: "POST",
        body: {
          decision,
          comment,
          phase,
          session_id: this.sessionId,
        },
      });
      this.state = state;
      return state;
    }

    async saveSession(patch) {
      const session = await this.request(`/api/showroom/sessions/${encodeURIComponent(this.sessionId)}`, {
        method: "PATCH",
        body: patch,
      });
      this.session = session;
      this.emit("session", session);
      return session;
    }

    async appendMessage(role, content) {
      const session = await this.request(`/api/showroom/sessions/${encodeURIComponent(this.sessionId)}/messages`, {
        method: "POST",
        body: { role, content },
      });
      this.session = session;
      this.emit("session", session);
      return session;
    }

    async confirmDemand(demand) {
      const session = await this.request(`/api/showroom/sessions/${encodeURIComponent(this.sessionId)}/demand/confirm`, {
        method: "POST",
        body: { demand },
      });
      this.session = session;
      this.emit("session", session);
      return session;
    }

    async generateInsight() {
      const session = await this.request(`/api/showroom/sessions/${encodeURIComponent(this.sessionId)}/insight/generate`, {
        method: "POST",
      });
      this.session = session;
      this.emit("session", session);
      return session;
    }

    async generateIpdArtifacts(phaseIndex = 0) {
      const session = await this.request(`/api/showroom/sessions/${encodeURIComponent(this.sessionId)}/ipd/${phaseIndex}/generate`, {
        method: "POST",
      });
      this.session = session;
      this.emit("session", session);
      return session;
    }

    async saveArtifact(key, title, content) {
      return this.request(`/api/showroom/sessions/${encodeURIComponent(this.sessionId)}/artifacts/${encodeURIComponent(key)}`, {
        method: "PUT",
        body: { title, content },
      });
    }

    async searchKnowledge(query, limit = 8) {
      return this.request(`/api/knowledge/search?q=${encodeURIComponent(query)}&limit=${limit}`);
    }

    async streamChat(question, options = {}) {
      const headers = new Headers({
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      });
      const token = accessToken();
      if (token) headers.set("Authorization", `Bearer ${token}`);
      const response = await fetch("/api/chat/stream", {
        method: "POST",
        headers,
        body: JSON.stringify({
          question,
          session_id: this.sessionId,
          agent_id: options.agentId || "main_agent",
          skill_id: options.skillId || undefined,
        }),
      });
      if (!response.ok || !response.body) {
        throw new Error(response.status === 401 ? "登录已过期" : `AI 服务不可用（${response.status}）`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let answer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() || "";
        for (const frame of frames) {
          const raw = frame.split("\n").find((line) => line.startsWith("data:"))?.slice(5).trim();
          if (!raw) continue;
          let data;
          try { data = JSON.parse(raw); } catch { continue; }
          await options.onEvent?.(data);
          this.emit("stream", data);
          if (data.type === "error") {
            throw new Error(data.message || "架构师服务暂不可用");
          }
          if (data.type === "delta") {
            const delta = data.delta || data.content || "";
            answer += delta;
            options.onDelta?.(answer, data);
          } else if (data.type === "answer") {
            answer = data.answer || data.content || answer;
            options.onDelta?.(answer, data);
          } else if (data.type === "done") {
            const finalAnswer = data.answer || data.content || "";
            if (!answer && finalAnswer) {
              answer = finalAnswer;
              options.onDelta?.(answer, data);
            }
          }
        }
      }
      return answer;
    }

    async submitClarify(response, clarifyId, agentId = "main_agent") {
      return this.request("/api/chat/stream/clarify", {
        method: "POST",
        body: {
          session_id: this.sessionId,
          response,
          clarify_id: clarifyId,
          agent_id: agentId,
        },
      });
    }
  }

  if (global.__SHOWROOM_TEST__) global.__ShowroomApi = ShowroomApi;
  global.showroomApi = new ShowroomApi();
})(window);
