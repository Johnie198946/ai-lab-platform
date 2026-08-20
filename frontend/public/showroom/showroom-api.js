(function showroomApiBootstrap(global) {
  "use strict";

  const AUTH_KEY = "ai-lab-platform.auth";
  const SESSION_KEY = "ai-lab-showroom.session";
  const HERMES_RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 15000];
  const DEMAND_ENVELOPE_PATTERNS = [
    /<!--\s*AI_LAB_DEMAND_V1\s*\{[\s\S]*?\}\s*AI_LAB_DEMAND_V1\s*-->/gi,
    /```(?:json\s+)?AI_LAB_DEMAND_V1\s*\{[\s\S]*?\}\s*```/gi,
    /```ya?ml\s*[\r\n]+\s*AI_LAB_DEMAND_V1\s*:[\s\S]*?```/gi,
  ];
  const DEMAND_STATE_ENVELOPE_PATTERNS = [
    /<!--\s*AI_LAB_DEMAND_STATE_V1\s*\{[\s\S]*?\}\s*AI_LAB_DEMAND_STATE_V1\s*-->/gi,
  ];
  const VISITOR_ENVELOPE_PATTERNS = [
    /<!--\s*AI_LAB_VISITOR_INSIGHT_V1\s*\{[\s\S]*?\}\s*AI_LAB_VISITOR_INSIGHT_V1\s*-->/gi,
    /```(?:json\s+)?AI_LAB_VISITOR_INSIGHT_V1\s*\{[\s\S]*?\}\s*```/gi,
  ];
  const INSIGHT_ENVELOPE_PATTERNS = [
    /<!--\s*AI_LAB_STAFFING_PLAN_V1\s*\{[\s\S]*?\}\s*AI_LAB_STAFFING_PLAN_V1\s*-->/gi,
    /<!--\s*AI_LAB_INSIGHT_STAGE_V1\s*\{[\s\S]*?\}\s*AI_LAB_INSIGHT_STAGE_V1\s*-->/gi,
    /<!--\s*AI_LAB_INSIGHT_SECTION_V1\s*\{[\s\S]*?\}\s*AI_LAB_INSIGHT_SECTION_V1\s*-->/gi,
    /<!--\s*AI_LAB_INSIGHT_V1\s*\{[\s\S]*?\}\s*AI_LAB_INSIGHT_V1\s*-->/gi,
    /<!--\s*AI_LAB_INSIGHT_REVISION_V[12]\s*\{[\s\S]*?\}\s*AI_LAB_INSIGHT_REVISION_V[12]\s*-->/gi,
    /<!--\s*AI_LAB_CONCEPT_REVIEW_V1\s*\{[\s\S]*?\}\s*AI_LAB_CONCEPT_REVIEW_V1\s*-->/gi,
  ];
  const CONTROL_PREFIX = "[AI_LAB_CONTROL]";

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

  function loginUrl() {
    const next = `${global.location.pathname}${global.location.search}${global.location.hash}`;
    return `/login?next=${encodeURIComponent(next)}`;
  }

  function requireLogin() {
    global.localStorage.removeItem(AUTH_KEY);
    global.location.replace(loginUrl());
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
    return ["controller", "screen-03", "screen-04"].includes(view)
      || /^experience-0?[1-5]$/.test(view);
  }

  function hermesLane() {
    const view = new URLSearchParams(global.location.search).get("view") || "controller";
    if (view === "screen-04") return "insight-review";
    return view === "controller" ? "backstage" : "frontstage";
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
        rawContent: message.role === "assistant"
          ? String(message.content ?? message.text ?? "")
          : "",
      }))
      .filter((message) => message.content.trim());
  }

  function visibleHermesMessage(role, content) {
    if (role === "assistant") {
      const withoutDemand = DEMAND_ENVELOPE_PATTERNS.reduce(
        (visible, pattern) => visible.replace(pattern, ""),
        content,
      );
      const withoutState = DEMAND_STATE_ENVELOPE_PATTERNS.reduce(
        (visible, pattern) => visible.replace(pattern, ""),
        withoutDemand,
      );
      const withoutVisitor = VISITOR_ENVELOPE_PATTERNS.reduce(
        (visible, pattern) => visible.replace(pattern, ""),
        withoutState,
      );
      return INSIGHT_ENVELOPE_PATTERNS.reduce(
        (visible, pattern) => visible.replace(pattern, ""),
        withoutVisitor,
      ).trim();
    }
    if (role !== "user") return content;
    if (content.includes("[AI_LAB_DEMAND_POLICY_V1]")) {
      const marker = "用户原始问题：";
      const markerIndex = content.lastIndexOf(marker);
      return markerIndex >= 0 ? content.slice(markerIndex + marker.length).trim() : "";
    }
    if (content.trim().startsWith(CONTROL_PREFIX)) return "";
    const invocation = global.HermesShared?.skillInvocationText?.(content);
    if (!invocation) return content;
    const marker = "用户原始问题：";
    const markerIndex = invocation.lastIndexOf(marker);
    const original = markerIndex >= 0 ? invocation.slice(markerIndex + marker.length).trim() : invocation;
    return original.startsWith(CONTROL_PREFIX) ? "" : original;
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
      this.hermesLane = "";
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
        // A showroom tab can stay open longer than the Authen JWT lifetime.
        // Redirect immediately so the operator can establish a fresh session
        // instead of seeing a misleading Hermes retry failure.
        if (response.status === 401) {
          requireLogin();
        }
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
          requireLogin();
          return;
        }
        await this.request("/health");
        const bootstrap = await this.request(
          `/api/showroom/bootstrap?session_id=${encodeURIComponent(this.sessionId)}&slot=${encodeURIComponent(this.slot)}`,
        );
        this.bootstrap = bootstrap;
        this.state = bootstrap.runtime;
        this.session = bootstrap.session;
        const authoritativeSessionId = this.slot === "main"
          ? bootstrap.active_main_session_id
          : bootstrap.session?.session_id;
        if (authoritativeSessionId) {
          this.sessionId = authoritativeSessionId;
          global.sessionStorage.setItem(SESSION_KEY, this.sessionId);
        }
        this.emit("bootstrap", bootstrap);
        // Some recovery flows need to refresh the authoritative Showroom
        // session before opening Hermes again.  Keep bootstrap side-effect
        // free when explicitly requested so an old in-memory Gateway cannot
        // resume a stale provider session in parallel.
        if (!options.skipHermes) {
          this.connect();
          if (isConversationView()) this.resumeHermes();
        }
      } catch (error) {
        if (error.status === 401) {
          this.setStatus("auth-required", "登录已过期，正在返回登录页");
          requireLogin();
          return;
        }
        this.setStatus("offline", error.message);
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
      const requestedLane = hermesLane();
      if (this.hermes?.connectionState === "open" && this.hermesLane !== requestedLane) {
        this.hermesIntentionalClose = true;
        this.hermes.close();
        this.hermesIntentionalClose = false;
        this.hermes = null;
        this.hermesLiveSessionId = "";
        this.hermesStoredSessionId = "";
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

        const lane = requestedLane;
        const laneSessions = this.session?.data?.hermes_sessions || {};
        const storedKey = `${lane}_stored_session_id`;
        const initializedKey = `${lane}_skill_initialized`;
        const storedId = String(
          laneSessions[storedKey]
          || (lane === "backstage" ? this.session?.data?.hermes_stored_session_id : "")
          || "",
        ).trim();
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
        this.hermesLane = lane;

        const view = new URLSearchParams(global.location.search).get("view") || "controller";
        const rawMessages = Array.isArray(result.messages) ? result.messages : [];
        const resumedMessages = normalizeHermesMessages(rawMessages);
        const laneInitialized = Boolean(laneSessions[initializedKey]);
        const shouldMarkInitialized = resumedMessages.length > 0 && !laneInitialized;
        if (this.hermesStoredSessionId !== storedId || shouldMarkInitialized) {
          this.session = await this.saveSession({
            data: {
              hermes_sessions: {
                [storedKey]: this.hermesStoredSessionId,
                [initializedKey]: laneInitialized || shouldMarkInitialized,
              },
              ...(lane === "backstage" ? {
                hermes_stored_session_id: this.hermesStoredSessionId,
                hermes_skill_initialized: laneInitialized || shouldMarkInitialized,
              } : {}),
            },
          });
        }
        this.hermesReconnectCount = 0;
        this.hermesReconnectExhausted = false;
        this.setHermesStatus(result.running ? "generating" : "online", result.running ? "正在恢复生成" : "大架构师已连接");
        this.emit("hermes-ready", {
          lane,
          live_session_id: this.hermesLiveSessionId,
          stored_session_id: this.hermesStoredSessionId,
          messages: resumedMessages,
          raw_message_count: rawMessages.length,
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
      const lane = this.hermesLane || hermesLane();
      const initializedKey = `${lane}_skill_initialized`;
      const skillInitialized = Boolean(
        this.session?.data?.hermes_sessions?.[initializedKey]
        || (lane === "backstage" && this.session?.data?.hermes_skill_initialized),
      );
      const forceDispatch = Boolean(options.forceDispatch);
      if (!skillInitialized || forceDispatch) {
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
      if (!skillInitialized && !forceDispatch) {
        const patch = { hermes_sessions: { [initializedKey]: true } };
        if (lane === "backstage") patch.hermes_skill_initialized = true;
        this.saveSession({ data: patch }).catch(() => {});
      }
      return response;
    }

    async submitHermesSkill(question, skillCommand, options = {}) {
      return this.submitHermesPrompt(question, {
        ...options,
        skillCommand,
        forceDispatch: true,
      });
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
        if (message.type === "SESSION_SWITCH_PREPARE" && message.session_id === this.sessionId) {
          this.interruptHermes().catch(() => {}).finally(() => {
            this.suspendHermes();
            if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({
              type: "SESSION_SWITCH_READY",
              session_id: this.sessionId,
              epoch: message.epoch,
            }));
          });
        }
        if (message.type === "SESSION_SWITCH_ABORT" && message.session_id === this.sessionId) {
          this.hermesSuspended = Boolean(global.document?.hidden) || !isConversationView();
          this.resumeHermes();
        }
        if (message.type === "SESSION_SWITCH_COMMIT" && message.session_id === this.sessionId) {
          this.sessionId = message.new_session_id;
          global.sessionStorage.setItem(SESSION_KEY, this.sessionId);
          this.session = null;
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

    async saveVisitor(visitor) {
      const session = await this.request(`/api/showroom/visits/${encodeURIComponent(this.sessionId)}/visitor`, {
        method: "PATCH",
        body: visitor,
      });
      this.session = session;
      this.emit("session", session);
      return session;
    }

    async extractVisitorInsight(content) {
      const backstageId = this.session?.data?.hermes_sessions?.backstage_stored_session_id;
      const result = await this.request(`/api/showroom/visits/${encodeURIComponent(this.sessionId)}/insight/extract`, {
        method: "POST",
        body: {
          content,
          hermes_stored_session_id: backstageId || this.hermesStoredSessionId || this.session?.data?.hermes_stored_session_id || "",
        },
      });
      if (result?.session) {
        this.session = result.session;
        this.emit("session", result.session);
      }
      return result;
    }

    async activateFrontstage(messageCount = 0) {
      const result = await this.request(`/api/showroom/visits/${encodeURIComponent(this.sessionId)}/frontstage`, {
        method: "POST",
        body: { message_count: messageCount },
      });
      this.session = result.session;
      this.emit("session", result.session);
      return result;
    }

    async completeVisit(source = "controller") {
      const session = await this.request(`/api/showroom/visits/${encodeURIComponent(this.sessionId)}/complete`, {
        method: "POST",
        body: { source },
      });
      this.session = session;
      this.emit("session", session);
      return session;
    }

    async rolloverVisit(source = "controller") {
      const result = await this.request(`/api/showroom/visits/${encodeURIComponent(this.sessionId)}/rollover`, {
        method: "POST",
        body: { epoch: Date.now(), source },
      });
      this.sessionId = result.session.session_id;
      global.sessionStorage.setItem(SESSION_KEY, this.sessionId);
      this.session = result.session;
      this.state = result.runtime;
      this.emit("session", result.session);
      this.emit("rollover", result);
      return result;
    }

    visibleAssistantMessage(content) {
      return visibleHermesMessage("assistant", String(content || ""));
    }

    async extractDemand(content) {
      const frontstageId = this.session?.data?.hermes_sessions?.frontstage_stored_session_id;
      const result = await this.request(
        `/api/showroom/sessions/${encodeURIComponent(this.sessionId)}/demand/extract`,
        {
          method: "POST",
          body: {
            content,
            hermes_stored_session_id: frontstageId
              || this.hermesStoredSessionId
              || "",
          },
        },
      );
      if (result?.session) {
        this.session = result.session;
        this.emit("session", result.session);
      }
      return result;
    }

    async saveDemandDraft(demand, manualFields) {
      const session = await this.request(
        `/api/showroom/sessions/${encodeURIComponent(this.sessionId)}/demand/draft`,
        {
          method: "PATCH",
          body: { demand, manual_fields: manualFields },
        },
      );
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

    async startInsightJob() {
      const result = await this.request(
        `/api/showroom/sessions/${encodeURIComponent(this.sessionId)}/insight/jobs`,
        { method: "POST" },
      );
      if (result?.session) {
        this.session = result.session;
        this.emit("session", result.session);
      }
      return result;
    }

    async getInsightJob(jobId) {
      const result = await this.request(
        `/api/showroom/sessions/${encodeURIComponent(this.sessionId)}/insight/jobs/${encodeURIComponent(jobId)}`,
      );
      if (result?.session) {
        this.session = result.session;
        this.emit("session", result.session);
      }
      return result;
    }

    async retryInsightJob(jobId) {
      const result = await this.request(
        `/api/showroom/sessions/${encodeURIComponent(this.sessionId)}/insight/jobs/${encodeURIComponent(jobId)}/retry`,
        { method: "POST" },
      );
      if (result?.session) {
        this.session = result.session;
        this.emit("session", result.session);
      }
      return result;
    }

    async saveStaffingPlan(jobId, plan) {
      const result = await this.request(
        `/api/showroom/sessions/${encodeURIComponent(this.sessionId)}/insight/jobs/${encodeURIComponent(jobId)}/plan`,
        { method: "PUT", body: { plan } },
      );
      if (result?.session) {
        this.session = result.session;
        this.emit("session", result.session);
      }
      return result;
    }

    async updateInsightProgress(jobId, progress) {
      const result = await this.request(
        `/api/showroom/sessions/${encodeURIComponent(this.sessionId)}/insight/jobs/${encodeURIComponent(jobId)}/progress`,
        { method: "POST", body: progress },
      );
      if (result?.session) {
        this.session = result.session;
        this.emit("session", result.session);
      }
      return result;
    }

    async completeInsightJob(jobId, content) {
      const result = await this.request(
        `/api/showroom/sessions/${encodeURIComponent(this.sessionId)}/insight/jobs/${encodeURIComponent(jobId)}/complete`,
        { method: "POST", body: { content } },
      );
      if (result?.session) {
        this.session = result.session;
        this.emit("session", result.session);
      }
      return result;
    }

    insightMutationBody(review = this.session?.data?.insight_review || {}) {
      const job = this.session?.data?.insight_job || {};
      return {
        epoch: Number(this.state?.epoch || 0),
        job_id: String(job.job_id || ""),
        demand_hash: String(review.demand_hash || job.source_hash || ""),
        base_version: String(review.version || "V0.1"),
      };
    }

    async extractInsightRevision(content, context = {}) {
      const body = this.insightMutationBody();
      const result = await this.request(
        `/api/showroom/sessions/${encodeURIComponent(this.sessionId)}/insight/revisions/extract`,
        {
          method: "POST",
          body: {
            ...body,
            content,
            user_instruction: String(context.userInstruction || ""),
            target_section: String(context.targetSection || ""),
            selected_text: String(context.selectedText || "").slice(0, 4000),
            expected_revision: Boolean(context.expectedRevision),
            request_id: String(context.requestId || ""),
          },
        },
      );
      if (result?.session) {
        this.session = result.session;
        this.emit("session", result.session);
      }
      return result;
    }

    async getInsightFieldCatalog() {
      return this.request(`/api/showroom/sessions/${encodeURIComponent(this.sessionId)}/insight/field-catalog`);
    }

    async registerInsightTbd(item) {
      const result = await this.request(
        `/api/showroom/sessions/${encodeURIComponent(this.sessionId)}/insight/tbds`,
        { method: "POST", body: { ...this.insightMutationBody(), ...item } },
      );
      if (result?.session) {
        this.session = result.session;
        this.emit("session", result.session);
      }
      return result;
    }

    async createInsightReviewTask() {
      return this.insightMutation("/insight/review-tasks");
    }

    async completeInsightReviewTask(taskId, content) {
      const result = await this.request(
        `/api/showroom/sessions/${encodeURIComponent(this.sessionId)}/insight/review-tasks/${encodeURIComponent(taskId)}/complete`,
        { method: "POST", body: { ...this.insightMutationBody(), content } },
      );
      if (result?.session) {
        this.session = result.session;
        this.emit("session", result.session);
      }
      return result;
    }

    async overrideInsightReviewTask(taskId, reason) {
      const result = await this.request(
        `/api/showroom/sessions/${encodeURIComponent(this.sessionId)}/insight/review-tasks/${encodeURIComponent(taskId)}/override`,
        { method: "POST", body: { ...this.insightMutationBody(), reason } },
      );
      if (result?.session) {
        this.session = result.session;
        this.emit("session", result.session);
      }
      return result;
    }

    async retryInsightReviewTask(taskId) {
      return this.insightMutation(`/insight/review-tasks/${encodeURIComponent(taskId)}/retry`);
    }

    async retryInsightReviewNotification(taskId) {
      return this.insightMutation(`/insight/review-tasks/${encodeURIComponent(taskId)}/notify`);
    }

    async applyInsightRevision(revisionId) {
      return this.insightMutation(`/insight/revisions/${encodeURIComponent(revisionId)}/apply`);
    }

    async discardInsightRevision(revisionId) {
      return this.insightMutation(`/insight/revisions/${encodeURIComponent(revisionId)}/discard`);
    }

    async confirmInsight() {
      return this.insightMutation("/insight/confirm");
    }

    async reopenInsight() {
      return this.insightMutation("/insight/reopen");
    }

    async reopenDemand() {
      return this.insightMutation("/demand/reopen");
    }

    async insightMutation(suffix) {
      const result = await this.request(
        `/api/showroom/sessions/${encodeURIComponent(this.sessionId)}${suffix}`,
        { method: "POST", body: this.insightMutationBody() },
      );
      if (result?.session) {
        this.session = result.session;
        this.emit("session", result.session);
      }
      return result;
    }

    async failInsightJob(jobId, message) {
      const result = await this.request(
        `/api/showroom/sessions/${encodeURIComponent(this.sessionId)}/insight/jobs/${encodeURIComponent(jobId)}/fail`,
        { method: "POST", body: { message } },
      );
      if (result?.session) {
        this.session = result.session;
        this.emit("session", result.session);
      }
      return result;
    }

    async interruptInsightJob(jobId, message = "用户已停止生成") {
      const result = await this.request(
        `/api/showroom/sessions/${encodeURIComponent(this.sessionId)}/insight/jobs/${encodeURIComponent(jobId)}/interrupt`,
        { method: "POST", body: { message } },
      );
      if (result?.session) {
        this.session = result.session;
        this.emit("session", result.session);
      }
      return result;
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
