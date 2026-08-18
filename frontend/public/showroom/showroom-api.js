(function showroomApiBootstrap(global) {
  "use strict";

  const AUTH_KEY = "ai-lab-platform.auth";
  const SESSION_KEY = "ai-lab-showroom.session";

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

    async init() {
      try {
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
      } catch (error) {
        this.setStatus(error.status === 401 ? "auth-required" : "offline", error.message);
      }
    }

    connect() {
      const token = accessToken();
      if (!token) return;
      global.clearTimeout(this.retryTimer);
      const protocol = global.location.protocol === "https:" ? "wss:" : "ws:";
      const url = `${protocol}//${global.location.host}/api/showroom/ws?token=${encodeURIComponent(token)}&session_id=${encodeURIComponent(this.sessionId)}`;
      this.ws = new WebSocket(url);
      this.ws.addEventListener("open", () => {
        this.retryCount = 0;
        this.setStatus("online");
      });
      this.ws.addEventListener("message", (event) => {
        let message;
        try { message = JSON.parse(event.data); } catch { return; }
        if (message.type === "PING") {
          this.ws?.send(JSON.stringify({ type: "PONG", at: Date.now() }));
          return;
        }
        if (message.type === "PREPARE") {
          this.ws?.send(JSON.stringify({ type: "READY", epoch: message.epoch }));
        }
        if (message.state) this.state = message.state;
        this.emit("message", message);
      });
      this.ws.addEventListener("close", () => {
        this.setStatus("reconnecting");
        const delay = Math.min(10000, 800 * (2 ** this.retryCount++));
        this.retryTimer = global.setTimeout(() => this.connect(), delay);
      });
      this.ws.addEventListener("error", () => this.ws?.close());
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
          options.onEvent?.(data);
          this.emit("stream", data);
          const delta = data.delta || data.content || data.answer || "";
          if (["delta", "answer", "done"].includes(data.type) && delta) {
            answer += delta;
            options.onDelta?.(answer, data);
          }
        }
      }
      return answer;
    }
  }

  global.showroomApi = new ShowroomApi();
})(window);
