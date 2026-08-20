//
//  TenantSessionCoordinator.swift
//  AIPlatformApp
//
//  Coordinator for iOS Agent Chat (DeepSeek Harness / Cordis Pattern)
//  Manages SSE streaming, Bridge status polling, session switching barriers,
//  Clarify 5-state watchdog, and multi-tenant scoped lifecycle.
//

import SwiftUI
import Combine

@MainActor
public final class TenantSessionCoordinator: ObservableObject {
    @Published public var messages: [ChatMessage] = []
    @Published public var inputText: String = ""
    @Published public var quickCommands: [String] = []
    @Published public var quotedContext: QuotedContext? = nil
    @Published public var isGenerating: Bool = false
    @Published public var inflight: InFlightRequest? = nil
    @Published public var pendingQueue: [PendingItem] = []
    @Published public var waitingSeconds: Int = 0
    @Published public var thinkingPhase: String? = nil
    @Published public var thinkingDetail: String? = nil
    @Published public var liveProgress: String? = nil
    @Published public var toastMessage: String? = nil
    @Published public var demoMode: Bool = false

    public let sessionManager: SessionManager
    public weak var appState: AppState?

    /// 租户与会话隔离 Epoch 屏障（递增令牌）
    private var tenantEpoch: Int = 0
    private var generationStartDate: Date? = nil
    private var currentChatTask: Task<Void, Never>? = nil
    private var statusPollTask: Task<Void, Never>? = nil
    private var clarifySubmissionTask: Task<Void, Never>? = nil
    /// Agent 请求 ID -> 当前 UI 输出消息 ID。Clarify 后仍消费同一 SSE，但把续写放到用户选择之后。
    private var streamOutputMessageIds: [String: String] = [:]
    private var animationTasks: [String: Task<Void, Never>] = [:]

    public init(sessionManager: SessionManager? = nil, appState: AppState? = nil) {
        self.sessionManager = sessionManager ?? SessionManager.shared
        self.appState = appState
        restoreActiveSession()
        refreshQuickCommands()
    }

    // MARK: - 会话恢复与持久化

    public func makeRenderContext(for message: ChatMessage? = nil) -> PluginRenderContext {
        PluginRenderContext(
            messageId: message?.id ?? "active",
            isStreaming: message?.isStreaming ?? isGenerating,
            onClarifySubmit: { [weak self] selection in
                if let messageId = message?.id {
                    self?.sendClarifySelection(messageId: messageId, selection: selection)
                } else if let lastClarify = self?.messages.last(where: { $0.clarifyBlock != nil }) {
                    self?.sendClarifySelection(messageId: lastClarify.id, selection: selection)
                }
            },
            onQuoteFollowUp: { [weak self] quote in
                self?.quotedContext = quote
            },
            onRegenerate: { [weak self] mid in
                self?.retryMessage(mid)
            }
        )
    }

    public func restoreActiveSession() {
        let sid = sessionManager.activeSessionID()
        self.messages = sessionManager.messages(for: sid)
        self.quotedContext = nil
        appState?.selectedAgentId = sessionManager.agentId(for: sid)
        appState?.selectedAgentName = sessionManager.agentName(for: sid)
    }

    public func commitSession() {
        let sid = sessionManager.activeSessionID()
        sessionManager.setMessages(messages, for: sid)
    }

    public func switchSession(to sessionId: String) {
        guard sessionId != sessionManager.activeSessionID() else { return }

        // 双重物理阻断：递增 Epoch + 取消所有在途 Task
        tenantEpoch += 1
        cancelAllTasksAndAnimations()

        if let inf = inflight {
            sessionManager.markInterrupted(sessionId: inf.sessionId)
        }

        isGenerating = false
        inflight = nil
        pendingQueue.removeAll()
        waitingSeconds = 0
        thinkingPhase = nil
        thinkingDetail = nil
        liveProgress = nil

        sessionManager.switchTo(sessionId)
        restoreActiveSession()
        refreshQuickCommands()
    }

    public func newSession(agentId: String? = nil, agentName: String? = nil) {
        tenantEpoch += 1
        cancelAllTasksAndAnimations()

        if let inf = inflight {
            sessionManager.markInterrupted(sessionId: inf.sessionId)
        }

        isGenerating = false
        inflight = nil
        pendingQueue.removeAll()
        waitingSeconds = 0
        thinkingPhase = nil
        thinkingDetail = nil
        liveProgress = nil

        let resolvedAgentId = agentId ?? appState?.selectedAgentId ?? "main_agent"
        let resolvedAgentName = agentName ?? appState?.selectedAgentName ?? "Main 智能编排"
        let newId = sessionManager.createSession(
            agentId: resolvedAgentId, agentName: resolvedAgentName
        )
        sessionManager.switchTo(newId)
        restoreActiveSession()
        refreshQuickCommands()
    }

    public func deleteSession(_ sessionId: String) {
        if sessionId == sessionManager.activeSessionID() {
            newSession()
        }
        sessionManager.deleteSession(sessionId)
    }

    public func clearCurrentSession() {
        cancelAllTasksAndAnimations()
        messages.removeAll()
        commitSession()
    }

    public func cancelAllTasksAndAnimations() {
        currentChatTask?.cancel()
        currentChatTask = nil
        clarifySubmissionTask?.cancel()
        clarifySubmissionTask = nil
        streamOutputMessageIds.removeAll()
        stopStatusPolling()
        for task in animationTasks.values { task.cancel() }
        animationTasks.removeAll()
    }

    // MARK: - 快捷指令与计时器

    public func tickWaitingTimer() {
        if let inf = inflight, inf.phase == .thinking {
            waitingSeconds += 1
        }
    }

    public func refreshQuickCommands() {
        let defaults = [
            "分析当前行业竞争格局",
            "根据知识库生成汇报摘要",
            "规划多智能体协同流水线"
        ]
        let ranked = QuickCommandTracker.shared.rankedCommands().map(\.command)
        var result: [String] = []
        for cmd in ranked where result.count < 3 {
            result.append(cmd)
        }
        for cmd in defaults where result.count < 3 && !result.contains(cmd) {
            result.append(cmd)
        }
        quickCommands = result
    }

    public func handlePendingPrompt() {
        if let prompt = appState?.pendingChatPrompt {
            self.inputText = prompt
            appState?.pendingChatPrompt = nil
        }
    }

    public func handlePendingAgent() {
        guard let selection = appState?.pendingChatAgent else { return }
        appState?.pendingChatAgent = nil
        appState?.selectedAgentId = selection.agentId
        appState?.selectedAgentName = selection.agentName
        newSession(agentId: selection.agentId, agentName: selection.agentName)
        if let prompt = selection.prompt, !prompt.isEmpty {
            inputText = prompt
        }
    }

    public func selectCommand(_ chip: String) {
        QuickCommandTracker.shared.record(chip)
        refreshQuickCommands()
        inputText = chip
        sendMessage()
    }

    // MARK: - 发送 / 状态机

    public func sendMessage() {
        sendMessage(text: nil, regenerate: false)
    }

    /// 发送消息核心：regenerate=true 时对 bridge 语义为「作废旧 run 全新执行」
    /// （用于 clarify 解锁失败兜底——选项文本必达后端，不被并发防护拦截）
    public func sendMessage(text explicitText: String? = nil, regenerate: Bool = false) {
        let text = (explicitText ?? inputText).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }

        #if os(iOS)
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        #endif

        let quote = quotedContext
        if isGenerating && pendingQueue.count >= 3 && !regenerate {
            showToast("最多排队 3 条，请等待")
            return
        }

        let sid = sessionManager.activeSessionID()
        messages.append(ChatMessage(sessionId: sid, role: .user, content: text, quotedContext: quote))
        inputText = ""
        quotedContext = nil
        commitSession()

        if isGenerating && !regenerate {
            pendingQueue.append(PendingItem(id: UUID().uuidString, text: text, quote: quote))
        } else {
            startGeneration(text: text, quote: quote, regenerate: regenerate)
        }
    }

    public func dispatchAssistantReply(to text: String, quote: QuotedContext? = nil) {
        if isGenerating {
            pendingQueue.append(PendingItem(id: UUID().uuidString, text: text, quote: quote))
        } else {
            startGeneration(text: text, quote: quote)
        }
    }

    public func startGeneration(text: String, quote: QuotedContext?, regenerate: Bool = false) {
        isGenerating = true
        waitingSeconds = 0
        thinkingPhase = nil
        thinkingDetail = nil
        generationStartDate = Date()
        let sid = sessionManager.activeSessionID()
        let req = InFlightRequest(
            id: UUID().uuidString, sessionId: sid, text: text, quote: quote,
            regenerate: regenerate, agentId: appState?.selectedAgentId
        )
        inflight = req
        streamOutputMessageIds[req.id] = req.id

        let initialStep = ReasoningStep(
            type: .thought,
            title: "正在根据需求规划与执行…",
            detail: text,
            status: "running"
        )
        messages.append(
            ChatMessage(
                id: req.id,
                sessionId: sid,
                role: .assistant,
                content: "",
                isStreaming: true,
                blocks: [.reasoning([initialStep])],
                pending: true
            )
        )
        commitSession()

        let taskEpoch = self.tenantEpoch
        currentChatTask = Task {
            await runInFlightStreamed(req, taskEpoch: taskEpoch)
        }
        startStatusPolling(req: req, taskEpoch: taskEpoch)
    }

    // MARK: - 流式 80ms 批量节流（Supervision 批复）
    private var deltaBuffer: String = ""
    private var flushScheduled: Bool = false
    private var flushTask: Task<Void, Never>? = nil

    private func drainDeltaBuffer(messageId: String) {
        flushTask?.cancel()
        flushTask = nil
        flushScheduled = false
        guard !deltaBuffer.isEmpty else { return }
        if let idx = messages.firstIndex(where: { $0.id == messageId }) {
            messages[idx].content += deltaBuffer
            messages[idx].pending = false
            messages[idx].isStreaming = true
        }
        deltaBuffer = ""
    }

    private func scheduleContentFlush(messageId: String, taskEpoch: Int) {
        guard !flushScheduled else { return }
        flushScheduled = true
        flushTask = Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: 80_000_000)
            guard let self = self, !Task.isCancelled, self.tenantEpoch == taskEpoch else {
                self?.flushScheduled = false
                self?.deltaBuffer = ""
                return
            }
            self.flushScheduled = false
            guard let idx = self.messages.firstIndex(where: { $0.id == messageId }) else {
                self.deltaBuffer = ""
                return
            }
            if !self.deltaBuffer.isEmpty {
                self.messages[idx].content += self.deltaBuffer
                self.deltaBuffer = ""
                self.messages[idx].pending = false
                self.messages[idx].isStreaming = true
            }
        }
    }

    private func runInFlightStreamed(_ req: InFlightRequest, taskEpoch: Int) async {
        defer {
            let outputId = self.outputMessageId(for: req)
            self.drainDeltaBuffer(messageId: outputId)
            self.finalizeReasoningDuration(for: outputId)
            self.commitSession()
            // 💡 仅当当前请求仍为活跃请求时复位 isGenerating，避免异步延迟派发误杀新流
            if self.inflight?.id == req.id && self.tenantEpoch == taskEpoch {
                self.isGenerating = false
            }
            self.streamOutputMessageIds.removeValue(forKey: req.id)
        }
        if demoMode {
            await appendDemoReply(req: req)
            return
        }
        deltaBuffer = ""
        flushScheduled = false
        let stream = APIClient.shared.chatStream(
            question: req.text,
            requestId: req.id,
            sessionId: req.sessionId,
            quotedContext: req.quote?.text,   // 引用历史消息上下文（若有），对齐后端 quoted_context 注入
            regenerate: req.regenerate,        // 重新生成：服务端作废旧 run 后全新执行
            agentId: req.agentId
        )
        do {
            for try await event in stream {
                guard self.tenantEpoch == taskEpoch else {
                    drainDeltaBuffer(messageId: req.id)
                    return
                }
                guard inflight?.id == req.id else {
                    drainDeltaBuffer(messageId: req.id)
                    return
                }
                guard req.sessionId == sessionManager.activeSessionID() else {
                    drainDeltaBuffer(messageId: outputMessageId(for: req))
                    sessionManager.markInterrupted(sessionId: req.sessionId)
                    finishGeneration()
                    return
                }

                let outputId = outputMessageId(for: req)
                switch event {
                case .delta(let content):
                    deltaBuffer += content
                    scheduleContentFlush(messageId: outputId, taskEpoch: taskEpoch)
                    if let idx = messages.firstIndex(where: { $0.id == outputId }) {
                        updateReasoningSteps(for: idx) { steps in
                            if let tIdx = steps.firstIndex(where: { $0.type == .thought && $0.status == "running" }) {
                                steps[tIdx].status = "done"
                            }
                        }
                    }

                case .thought(let content):
                    if let idx = messages.firstIndex(where: { $0.id == outputId }) {
                        messages[idx].pending = false
                        updateReasoningSteps(for: idx) { steps in
                            if let tIdx = steps.firstIndex(where: { $0.type == .thought }) {
                                steps[tIdx].detail += content
                                steps[tIdx].status = "running"
                            } else {
                                steps.insert(
                                    ReasoningStep(
                                        type: .thought,
                                        title: "思考过程",
                                        detail: content,
                                        status: "running"
                                    ),
                                    at: 0
                                )
                            }
                        }
                    }

                case .toolStart(let id, let tool, let label):
                    if let idx = messages.firstIndex(where: { $0.id == outputId }) {
                        messages[idx].pending = false
                        updateReasoningSteps(for: idx) { steps in
                            if let tIdx = steps.firstIndex(where: { $0.type == .thought && $0.status == "running" }) {
                                steps[tIdx].status = "done"
                            }
                            let stepType: ReasoningStepType = (tool == "skill_view" || tool == "skills_list") ? .skillLoad : (tool == "delegate_task" ? .agentSpawn : .toolCall)
                            let title = tool == "skill_view" ? "加载技能: \(label)" : (tool == "delegate_task" ? "派发子智能体" : "调用工具: \(tool)")
                            steps.append(ReasoningStep(id: id, type: stepType, title: title, detail: label, status: "running"))
                        }
                    }

                case .toolComplete(let id, let tool):
                    if let idx = messages.firstIndex(where: { $0.id == outputId }) {
                        messages[idx].pending = false
                        updateReasoningSteps(for: idx) { steps in
                            if let matchIdx = steps.lastIndex(where: { $0.id == id || ($0.status == "running" && $0.title.contains(tool)) }) {
                                steps[matchIdx].status = "done"
                            }
                        }
                    }

                case .clarify(let question, let choices, let multiSelect, let source, let clarifyId):
                    drainDeltaBuffer(messageId: outputId)
                    let block = ClarifyBlock(
                        clarifyId: clarifyId,
                        question: question,
                        choices: choices,
                        multiSelect: multiSelect,
                        submitLabel: "确认选择",
                        source: source
                    )
                    if let idx = messages.firstIndex(where: { $0.id == outputId }) {
                        updateReasoningSteps(for: idx) { steps in
                            for i in steps.indices { steps[i].status = "done" }
                        }
                        var blocks = messages[idx].blocks
                        if isRequirementConfirmationQuestion(question),
                           !containsRequirementTable(message: messages[idx]) {
                            blocks.append(.table(makeRequirementConfirmationTable()))
                        }
                        if !blocks.contains(where: { if case .clarify = $0 { return true }; return false }) {
                            blocks.append(.clarify(block))
                            messages[idx].blocks = blocks
                        }
                        messages[idx].pending = false
                        messages[idx].isStreaming = false
                    }

                case .clarifyRejected:
                    showToast("选择未通过校验，请从选项中选择或输入有效内容")

                case .status(let phase, let detail):
                    thinkingPhase = phase.isEmpty ? nil : phase
                    thinkingDetail = detail.isEmpty ? nil : detail
                    if let idx = messages.firstIndex(where: { $0.id == outputId }) {
                        updateReasoningSteps(for: idx) { steps in
                            if let tIdx = steps.firstIndex(where: { $0.type == .thought }) {
                                if !detail.isEmpty {
                                    steps[tIdx].title = detail
                                }
                            } else {
                                steps.insert(
                                    ReasoningStep(
                                        type: .thought,
                                        title: detail.isEmpty ? "正在理解需求…" : detail,
                                        status: "running"
                                    ),
                                    at: 0
                                )
                            }
                        }
                    }

                case .agentRoute(let id, let name, _, let delegatedBy):
                    if let idx = messages.firstIndex(where: { $0.id == outputId }) {
                        messages[idx].executingAgentId = id
                        messages[idx].executingAgentName = name
                        messages[idx].delegatedBy = delegatedBy
                    }

                case .done(_, let answer):
                    drainDeltaBuffer(messageId: outputId)
                    if let idx = messages.firstIndex(where: { $0.id == outputId }) {
                        updateReasoningSteps(for: idx) { steps in
                            for i in steps.indices { steps[i].status = "done" }
                        }
                        // 兜底：若流式 delta 偶发丢失或仅收到 done 帧，以 answer 补全正文（防空气泡）
                        if messages[idx].content.isEmpty, let answer, !answer.isEmpty {
                            messages[idx].content = answer
                        }
                        messages[idx].pending = false
                        messages[idx].isStreaming = false
                    }

                case .error(let code, _):
                    drainDeltaBuffer(messageId: outputId)
                    if let idx = messages.firstIndex(where: { $0.id == outputId }) {
                        messages[idx].content = "流式响应异常（\(code)）"
                        messages[idx].pending = false
                        messages[idx].isStreaming = false
                        messages[idx].degraded = true
                    }
                }
            }
            guard self.tenantEpoch == taskEpoch else { return }
            let outputId = outputMessageId(for: req)
            drainDeltaBuffer(messageId: outputId)

            // 断流只回读同一个 Hermes Run，绝不以原始问题发起第二次完整推理。
            if let idx = messages.firstIndex(where: { $0.id == outputId }) {
                if messages[idx].content.isEmpty && messages[idx].clarifyBlock == nil {
                    if let status = try? await APIClient.shared.fetchChatStatus(sessionId: req.sessionId, consume: true, agentId: req.agentId),
                       let ans = status.answer, !ans.isEmpty {
                        messages[idx].content = ans
                    } else {
                        messages[idx].content = "连接暂时中断，正在后台继续。返回本页后会恢复同一任务。"
                        messages[idx].degraded = true
                    }
                }
                messages[idx].pending = false
                messages[idx].isStreaming = false
            }

            finalizeReasoningDuration(for: outputId)
            commitSession()
            finishGeneration()
        } catch {
            guard self.tenantEpoch == taskEpoch else { return }
            let outputId = outputMessageId(for: req)
            drainDeltaBuffer(messageId: outputId)

            // SSE 异常不能清空已生成内容，更不能用原始需求另起一个非流式 Agent。
            // 先回读后台结果；未完成时保留现有上下文并给出明确恢复入口。
            if let status = try? await APIClient.shared.fetchChatStatus(
                sessionId: req.sessionId,
                consume: true,
                agentId: req.agentId
            ), status.status == "completed", let answer = status.answer, !answer.isEmpty {
                if let idx = messages.firstIndex(where: { $0.id == outputId }) {
                    messages[idx].content = answer
                    messages[idx].pending = false
                    messages[idx].isStreaming = false
                    messages[idx].degraded = false
                }
            } else if let idx = messages.firstIndex(where: { $0.id == outputId }) {
                if messages[idx].content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    messages[idx].content = "连接暂时中断，已保留当前需求确认进度。请点击重新生成继续。"
                }
                messages[idx].pending = false
                messages[idx].isStreaming = false
                messages[idx].degraded = false
            }
            commitSession()
            finishGeneration()
        }
    }

    private func runInFlight(_ req: InFlightRequest, taskEpoch: Int) async {
        if demoMode {
            await appendDemoReply(req: req)
            return
        }
        do {
            let resp = try await APIClient.shared.chat(
                question: req.text,
                sessionId: req.sessionId,
                quotedContext: req.quote?.text,
                agentId: req.agentId
            )
            guard self.tenantEpoch == taskEpoch else { return }
            await handleSuccess(req: req, response: resp, taskEpoch: taskEpoch)
        } catch {
            guard self.tenantEpoch == taskEpoch else { return }
            await handleError(req: req, error: error, taskEpoch: taskEpoch)
        }
    }

    private func handleSuccess(req: InFlightRequest, response: ChatResponseDTO, taskEpoch: Int) async {
        guard self.tenantEpoch == taskEpoch else { return }
        let outputId = outputMessageId(for: req)

        if inflight?.id != req.id {
            sessionManager.applyResponse(sessionId: req.sessionId, requestId: req.id, response: response)
            return
        }

        guard req.sessionId == sessionManager.activeSessionID() else {
            sessionManager.applyResponse(sessionId: req.sessionId, requestId: req.id, response: response)
            finishGeneration()
            return
        }

        if let route = response.resolvedAgent,
           let idx = messages.firstIndex(where: { $0.id == outputId }) {
            messages[idx].executingAgentId = route.id
            messages[idx].executingAgentName = route.name
            messages[idx].delegatedBy = response.delegatedBy
        }

        if response.degraded == true {
            if let idx = messages.firstIndex(where: { $0.id == outputId }) {
                messages[idx].content = response.answer.isEmpty ? "服务暂时不可用，请稍后重试" : response.answer
                messages[idx].degraded = true
                messages[idx].pending = false
                messages[idx].isStreaming = false
                messages[idx].blocks = []
            }
            inflight = nil
            finalizeReasoningDuration(for: outputId)
            commitSession()
            finishGeneration()
            return
        }

        if response.answer.contains("已为您创建专属 Agent 切片") {
            NotificationCenter.default.post(name: .tenantAgentsDidUpdate, object: nil)
        }

        let steps = (response.reasoning ?? []).map { $0.toReasoningStep() }
        if let idx = messages.firstIndex(where: { $0.id == outputId }) {
            messages[idx].blocks = steps.isEmpty ? [] : [.reasoning([])]
        }
        inflight = nil

        if let payload = response.clarify, !payload.question.isEmpty {
            let clarify = ClarifyBlock(
                question: payload.question,
                choices: payload.choices.isEmpty ? [] : payload.choices,
                multiSelect: payload.multiSelect,
                submitLabel: "确认选择",
                source: payload.source ?? "bridge"
            )
            if let idx = messages.firstIndex(where: { $0.id == outputId }) {
                var blocks = messages[idx].blocks
                blocks.append(.clarify(clarify))
                messages[idx].content = response.answer.isEmpty ? "" : String(response.answer.prefix(40))
                messages[idx].blocks = blocks
                messages[idx].pending = false
                messages[idx].isStreaming = false
            }
            finalizeReasoningDuration(for: outputId)
            commitSession()
            finishGeneration()
            return
        }

        if !steps.isEmpty {
            await revealReasoning(messageId: outputId, steps: steps)
        }

        await typewriter(messageId: outputId, answer: response.answer)

        if let idx = messages.firstIndex(where: { $0.id == outputId }) {
            messages[idx].pending = false
        }
        finalizeReasoningDuration(for: outputId)
        commitSession()
        finishGeneration()
    }

    private func handleError(req: InFlightRequest, error: Error, taskEpoch: Int) async {
        guard self.tenantEpoch == taskEpoch else { return }

        if inflight?.id != req.id {
            let text: String
            if let apiErr = error as? APIError, case .timeout = apiErr {
                text = "响应超时，请重试"
            } else {
                text = "服务暂时不可用，请稍后重试"
            }
            sessionManager.applyDegraded(sessionId: req.sessionId, requestId: req.id, text: text)
            return
        }

        guard req.sessionId == sessionManager.activeSessionID() else {
            let text: String
            if let apiErr = error as? APIError, case .timeout = apiErr {
                text = "响应超时，请重试"
            } else {
                text = "服务暂时不可用，请稍后重试"
            }
            sessionManager.applyDegraded(sessionId: req.sessionId, requestId: req.id, text: text)
            finishGeneration()
            return
        }

        if (error as? URLError)?.code == .cancelled || error is CancellationError {
            markCancelled(req: req)
            return
        }

        switch error {
        case APIError.unauthorized:
            isGenerating = false
            inflight = nil
            currentChatTask = nil
            waitingSeconds = 0
        case APIError.timeout:
            inflight?.phase = .timeout
        case APIError.server(let code, _) where code == 404:
            await handleNotFound(req: req, taskEpoch: taskEpoch)
        case APIError.server(let code, _):
            inflight?.phase = .serverError("服务端错误 \(code)")
        case APIError.network:
            inflight?.phase = .networkError
        case APIError.decoding, APIError.invalidURL:
            inflight?.phase = .serverError("数据解析失败")
        default:
            inflight?.phase = .serverError(error.localizedDescription)
        }
    }

    private func handleNotFound(req: InFlightRequest, taskEpoch: Int) async {
        if req.didRetry404 {
            showToast("会话失效，已开启新会话")
            finishGeneration()
            return
        }
        appState?.chatSessionId = nil
        var updated = req
        updated.didRetry404 = true
        inflight = updated

        do {
            let resp = try await APIClient.shared.chat(
                question: updated.text,
                requestId: updated.id,
                sessionId: nil,
                quotedContext: updated.quote?.text,
                agentId: updated.agentId
            )
            guard self.tenantEpoch == taskEpoch else { return }
            await handleSuccess(req: updated, response: resp, taskEpoch: taskEpoch)
        } catch {
            guard self.tenantEpoch == taskEpoch else { return }
            if let apiErr = error as? APIError, case .server(let code, _) = apiErr, code == 404 {
                showToast("会话失效，已开启新会话")
                finishGeneration()
            } else {
                await handleError(req: updated, error: error, taskEpoch: taskEpoch)
            }
        }
    }

    // MARK: - Clarify 选项卡会话推进（原 SSE 解锁续跑）

    public func sendClarifySelection(messageId: String, selection: String) {
        guard let idx = messages.firstIndex(where: { $0.id == messageId }) else { return }
        guard let clarify = messages[idx].clarifyBlock, !clarify.isSubmitted else { return }
        let sid = sessionManager.activeSessionID()
        let clarifyId = clarify.clarifyId

        // 本地预分类卡没有正在等待解锁的 Agent，按普通新问题处理。
        if clarify.source != "bridge" {
            markClarifySubmitted(messageIndex: idx, selection: selection)
            messages.append(ChatMessage(sessionId: sid, role: .user, content: selection))
            commitSession()
            if isGenerating {
                pendingQueue.append(PendingItem(id: UUID().uuidString, text: selection, quote: nil))
            } else {
                startGeneration(text: selection, quote: nil)
            }
            return
        }

        // Bridge clarify 必须仍归属于当前 SSE。绝不能 finishGeneration/startGeneration：
        // regenerate 会在服务端 interrupt 掉正在 wait_for_response 的旧 Agent。
        // 多轮 Drill-me 中，第二张及后续卡片位于 continuation message；反查它所属的原始 run ID，
        // 确保每次选择都只是解锁同一个 Agent，而不是被当作一条新 prompt。
        let requestId = streamOutputMessageIds.first(where: { $0.value == messageId })?.key ?? messageId
        guard let req = inflight, req.id == requestId, req.sessionId == sid, isGenerating else {
            showToast("该确认请求已失效，请重新生成")
            return
        }

        markClarifySubmitted(messageIndex: idx, selection: selection)
        let continuationMessageId = UUID().uuidString
        let continuationStep = ReasoningStep(
            type: .thought,
            title: "已收到选择，正在继续处理…",
            detail: selection,
            status: "running"
        )
        messages.append(ChatMessage(
            id: continuationMessageId,
            sessionId: sid,
            role: .assistant,
            content: "",
            isStreaming: true,
            blocks: [.reasoning([continuationStep])]
        ))
        streamOutputMessageIds[req.id] = continuationMessageId
        thinkingPhase = "reasoning"
        thinkingDetail = "已收到选择，正在继续处理…"
        commitSession()

        clarifySubmissionTask?.cancel()
        clarifySubmissionTask = Task { [weak self] in
            guard let self else { return }
            do {
                let accepted = try await APIClient.shared.submitClarify(
                    sessionId: sid,
                    response: selection,
                    clarifyId: clarifyId,
                    agentId: self.appState?.selectedAgentId
                )
                guard !Task.isCancelled else { return }
                guard accepted else {
                    self.rollbackClarifySubmission(
                        messageId: messageId,
                        requestId: requestId,
                        continuationMessageId: continuationMessageId,
                        toast: "选项未被服务端接受，请重试"
                    )
                    return
                }
                print("[Clarify] accepted message=\(messageId) clarify=\(clarifyId ?? "nil") session=\(sid)")
            } catch is CancellationError {
                return
            } catch {
                guard !Task.isCancelled else { return }
                print("[Clarify] failed message=\(messageId) clarify=\(clarifyId ?? "nil") error=\(error.localizedDescription)")
                self.rollbackClarifySubmission(
                    messageId: messageId,
                    requestId: requestId,
                    continuationMessageId: continuationMessageId,
                    toast: error.localizedDescription
                )
            }
        }
    }

    private func markClarifySubmitted(messageIndex: Int, selection: String) {
        if let blockIdx = messages[messageIndex].blocks.firstIndex(where: {
            if case .clarify = $0 { return true }
            return false
        }) {
            if case .clarify(var c) = messages[messageIndex].blocks[blockIdx] {
                c.markSubmitted(selection: selection)
                messages[messageIndex].blocks[blockIdx] = .clarify(c)
            }
        }
    }

    private func rollbackClarifySubmission(
        messageId: String,
        requestId: String,
        continuationMessageId: String,
        toast: String
    ) {
        guard let idx = messages.firstIndex(where: { $0.id == messageId }) else { return }
        if let blockIdx = messages[idx].blocks.firstIndex(where: {
            if case .clarify = $0 { return true }
            return false
        }), case .clarify(var c) = messages[idx].blocks[blockIdx] {
            c.isSubmitted = false
            c.submittedSelection = ""
            messages[idx].blocks[blockIdx] = .clarify(c)
        }
        messages.removeAll { $0.id == continuationMessageId }
        streamOutputMessageIds[requestId] = messageId
        thinkingPhase = nil
        thinkingDetail = nil
        commitSession()
        showToast(toast)
    }

    public func submitClarifyAction(messageId: String, selection: String) {
        sendClarifySelection(messageId: messageId, selection: selection)
    }

    // MARK: - 辅助方法与操作

    private func outputMessageId(for req: InFlightRequest) -> String {
        streamOutputMessageIds[req.id] ?? req.id
    }

    private func isRequirementConfirmationQuestion(_ question: String) -> Bool {
        question.contains("需求确认单")
            || question.contains("以上需求") && question.contains("准确")
    }

    private func containsRequirementTable(message: ChatMessage) -> Bool {
        if message.content.contains("确认维度") && message.content.contains("已确认需求") {
            return true
        }
        return message.blocks.contains { block in
            if case .table(let table) = block {
                return table.title.contains("需求确认")
            }
            return false
        }
    }

    /// 从本次 Drill-me 已提交卡片确定性组装确认单。模型已输出 Markdown 表格时不会调用此兜底。
    private func makeRequirementConfirmationTable() -> TableBlock {
        var rows: [[String]] = []
        var usedDimensions: Set<String> = []

        for message in messages {
            guard let clarify = message.clarifyBlock,
                  clarify.isSubmitted,
                  !clarify.submittedSelection.isEmpty else { continue }
            let dimension = requirementDimension(for: clarify.question, fallbackIndex: rows.count + 1)
            guard !usedDimensions.contains(dimension) else { continue }
            usedDimensions.insert(dimension)
            rows.append([dimension, clarify.submittedSelection])
        }

        return TableBlock(
            title: "需求确认单",
            headers: ["确认维度", "已确认需求"],
            rows: rows
        )
    }

    private func requirementDimension(for question: String, fallbackIndex: Int) -> String {
        let rules: [(keywords: [String], label: String)] = [
            (["交付形态", "产品形态", "哪一种形态"], "产品形态"),
            (["核心场景", "故事线", "目标用户", "解决什么问题"], "目标用户与场景"),
            (["MVP", "功能边界", "范围"], "MVP 范围"),
            (["技术路线", "技术栈"], "技术路线"),
            (["数据", "集成", "对接"], "数据与集成"),
            (["验收", "成功标准"], "验收标准"),
        ]
        for rule in rules where rule.keywords.contains(where: question.contains) {
            return rule.label
        }
        return "确认项 \(fallbackIndex)"
    }

    private func updateReasoningSteps(for idx: Int, update: (inout [ReasoningStep]) -> Void) {
        guard idx < messages.count else { return }
        var blocks = messages[idx].blocks
        var steps: [ReasoningStep] = []
        var reasoningBlockIdx: Int? = nil
        for (i, block) in blocks.enumerated() {
            if case .reasoning(let s) = block {
                steps = s
                reasoningBlockIdx = i
                break
            }
        }
        update(&steps)
        if let rIdx = reasoningBlockIdx {
            blocks[rIdx] = .reasoning(steps)
        } else if !steps.isEmpty {
            blocks.insert(.reasoning(steps), at: 0)
        }
        messages[idx].blocks = blocks
    }

    private func revealReasoning(messageId: String, steps: [ReasoningStep]) async {
        animationTasks[messageId]?.cancel()
        let task = Task { @MainActor in
            defer { self.animationTasks.removeValue(forKey: messageId) }
            for k in 1...steps.count {
                try? await Task.sleep(nanoseconds: 300_000_000)
                if Task.isCancelled { return }
                guard let idx = self.messages.firstIndex(where: { $0.id == messageId }) else { return }
                withAnimation(.easeInOut(duration: 0.25)) {
                    self.messages[idx].blocks = [.reasoning(Array(steps[0..<k]))]
                }
            }
        }
        animationTasks[messageId] = task
        await task.value
    }

    private func typewriter(messageId: String, answer: String) async {
        guard let idx = messages.firstIndex(where: { $0.id == messageId }) else { return }
        let chars = Array(answer)
        guard !chars.isEmpty else {
            messages[idx].isStreaming = false
            return
        }
        var shown = 0
        while shown < chars.count {
            shown = min(shown + 3, chars.count)
            messages[idx].content = String(chars[0..<shown])
            try? await Task.sleep(nanoseconds: 16_000_000)
        }
        messages[idx].isStreaming = false
    }

    private func startStatusPolling(req: InFlightRequest, taskEpoch: Int) {
        statusPollTask?.cancel()
        liveProgress = nil
        let sid = req.sessionId
        guard !sid.isEmpty, !demoMode else { return }
        statusPollTask = Task { @MainActor in
            let delays = [2, 4, 6, 8]
            var step = 0
            var polls = 0
            while polls < 50 && !Task.isCancelled {
                let delay = delays[min(step, delays.count - 1)]
                step += 1
                try? await Task.sleep(nanoseconds: UInt64(delay) * 1_000_000_000)
                if Task.isCancelled || self.tenantEpoch != taskEpoch { return }
                guard self.isGenerating,
                      self.inflight?.id == req.id,
                      self.inflight?.phase == .thinking else { return }
                do {
                    let status = try await APIClient.shared.fetchChatStatus(sessionId: sid, agentId: req.agentId)
                    if status.status == "running" {
                        self.liveProgress = status.latestStep
                    }
                } catch {}
                polls += 1
            }
        }
    }

    public func stopStatusPolling() {
        statusPollTask?.cancel()
        statusPollTask = nil
        liveProgress = nil
    }

    public func cancelInFlight() {
        currentChatTask?.cancel()
    }

    public func cancelQueued(_ id: String) {
        pendingQueue.removeAll { $0.id == id }
    }

    /// 重新生成（完整工作流 v2）：
    /// 1) 先从服务器探测该会话是否已产生完整答案（断点重续语义：会话可能已在后台完成，
    ///    status 端点 consume 模式可直接取回最终正文，无需重新烧 token）
    /// 2) 若确实未完成/无答案 → 携带用户原句 + 引用上下文全量重跑
    public func retryMessage(_ messageId: String) {
        guard !isGenerating else { return }
        guard let idx = messages.firstIndex(where: { $0.id == messageId }) else { return }
        guard let userIdx = messages[..<idx].lastIndex(where: { $0.role == .user }) else { return }

        let userPrompt = messages[userIdx].content
        let quote = messages[userIdx].quotedContext
        let sid = sessionManager.activeSessionID()

        // 未登录/无有效 token：断点探测与重跑均需认证，先给出明确提示（不无声硬跳登录页）
        guard APIClient.shared.currentToken() != nil else {
            showToast("需要登录后继续会话，请先登录")
            return
        }

        // 先探测服务器：断点重续优先（避免重复烧 token + 完整上下文回显）
        let probeTask = Task { @MainActor in
            if !sid.isEmpty {
                if let status = try? await APIClient.shared.fetchChatStatus(sessionId: sid, consume: true, agentId: appState?.selectedAgentId),
                   status.status == "completed",
                   let answer = status.answer, !answer.isEmpty {
                    // 断点续接命中：直接用服务器已完成的答案回填（保留全部上下文）
                    messages[idx].content = answer
                    messages[idx].pending = false
                    messages[idx].isStreaming = false
                    messages[idx].degraded = false
                    finalizeReasoningDuration(for: messageId)
                    commitSession()
                    return
                }
            }
            // 未命中断点 → 全量重跑（携带上下文 + regenerate 标志，服务端作废旧 run 后全新执行）
            messages.removeSubrange(idx...)
            startGeneration(text: userPrompt, quote: quote, regenerate: true)
        }
        _ = probeTask
    }

    public func retryCurrentInFlight() {
        guard var req = inflight else { return }
        req.phase = .thinking
        req.didRetry404 = false
        inflight = req
        waitingSeconds = 0
        let taskEpoch = self.tenantEpoch
        currentChatTask = Task {
            await runInFlight(req, taskEpoch: taskEpoch)
        }
        startStatusPolling(req: req, taskEpoch: taskEpoch)
    }

    public func probeAndResumeCurrentInFlight() {
        guard var req = inflight else { return }
        req.phase = .thinking
        inflight = req
        waitingSeconds = 0
        currentChatTask = Task {
            await probeAndResume(req)
        }
    }

    private func probeAndResume(_ req: InFlightRequest) async {
        let sid = req.sessionId
        if !sid.isEmpty, !demoMode {
            do {
                let status = try await APIClient.shared.fetchChatStatus(sessionId: sid, consume: true, agentId: req.agentId)
                if status.status == "completed",
                   let answer = status.answer, !answer.isEmpty {
                    await applyCompletedStatus(req: req, status: status)
                    return
                }
            } catch {}
        }
        retryCurrentInFlight()
    }

    private func applyCompletedStatus(req: InFlightRequest, status: ChatStatusDTO) async {
        guard inflight?.id == req.id else { return }
        guard req.sessionId == sessionManager.activeSessionID() else {
            sessionManager.applyCompletedStatus(
                sessionId: req.sessionId, requestId: req.id,
                answer: status.answer ?? "服务暂时不可用，请稍后重试"
            )
            finishGeneration()
            return
        }
        let steps = (status.reasoning ?? []).map { $0.toReasoningStep() }
        if let idx = messages.firstIndex(where: { $0.id == req.id }) {
            messages[idx].blocks = steps.isEmpty ? [] : [.reasoning([])]
        }
        inflight = nil
        stopStatusPolling()
        if !steps.isEmpty {
            await revealReasoning(messageId: req.id, steps: steps)
        }
        await typewriter(messageId: req.id, answer: status.answer ?? "")
        if let idx = messages.firstIndex(where: { $0.id == req.id }) {
            messages[idx].pending = false
        }
        finalizeReasoningDuration(for: req.id)
        commitSession()
        finishGeneration()
    }

    public func switchToDemoMode() {
        demoMode = true
        currentChatTask?.cancel()
        guard let req = inflight else { return }
        inflight = nil
        Task {
            await appendDemoReply(req: req)
        }
    }

    private func appendDemoReply(req: InFlightRequest) async {
        if let idx = messages.firstIndex(where: { $0.id == req.id }) {
            messages[idx].isDemoSample = true
            await typewriter(messageId: req.id, answer: "演示模式：后端暂不可达，已切换到本地演示。你提出的「\(req.text)」将在接入真实后端后获得答复。")
            messages[idx].pending = false
        }
        finalizeReasoningDuration(for: req.id)
        commitSession()
        finishGeneration()
    }

    private func markCancelled(req: InFlightRequest) {
        guard inflight?.id == req.id else { return }
        if let idx = messages.firstIndex(where: { $0.id == req.id }) {
            messages[idx].content = "已取消"
            messages[idx].pending = false
            messages[idx].isStreaming = false
            messages[idx].degraded = false
        } else {
            messages.append(ChatMessage(role: .assistant, content: "已取消", isStreaming: false))
        }
        commitSession()
        finishGeneration()
    }

    private func finishGeneration() {
        isGenerating = false
        inflight = nil
        currentChatTask = nil
        waitingSeconds = 0
        generationStartDate = nil
        stopStatusPolling()
        advanceQueue()
    }

    /// 流式/非流式完成时，为消息落盘真实思考耗时（无记录时不伪造）。
    private func finalizeReasoningDuration(for messageId: String) {
        guard let start = generationStartDate,
              let idx = messages.firstIndex(where: { $0.id == messageId }) else { return }
        let seconds = Int(Date().timeIntervalSince(start))
        if seconds >= 0, messages[idx].reasoningDuration == nil {
            messages[idx].reasoningDuration = seconds
        }
    }

    private func advanceQueue() {
        guard !pendingQueue.isEmpty else { return }
        let next = pendingQueue.removeFirst()
        startGeneration(text: next.text, quote: next.quote)
    }

    public func showToast(_ text: String) {
        toastMessage = text
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.2) { [weak self] in
            if self?.toastMessage == text {
                self?.toastMessage = nil
            }
        }
    }

    public func attachPhoto(_ data: Data) {
        let block = ImageBlock(assetName: "imported_photo", imageData: data, caption: "已导入照片（2048px 降采样）")
        let msg = ChatMessage(
            role: .user,
            content: "📸 已从照片图库导入一张图片（客户端 2048px 等比降采样 · JPEG 0.85）",
            blocks: [.image(block)]
        )
        messages.append(msg)
        dispatchAssistantReply(to: "照片导入")
    }

    public func attachDocument(_ url: URL) {
        let name = url.lastPathComponent
        let sizeBytes = InboxFileManager.shared.fileSizeBytes(at: url) ?? 0
        let sizeText = ByteCountFormatter.string(fromByteCount: sizeBytes, countStyle: .file)
        let attachment = AttachmentBlock(fileName: name, fileType: attachmentFileType(for: url), fileSize: sizeText)
        let msg = ChatMessage(
            role: .user,
            content: "📄 已导入文档：\(name)（\(sizeText)）",
            blocks: [.attachment(attachment)]
        )
        messages.append(msg)
        dispatchAssistantReply(to: "文档导入")
    }

    public func importWeChatLink(_ link: String) {
        let msg = ChatMessage(
            role: .user,
            content: "💬 微信文章导入请求：\(link)\n（已通过 mp.weixin.qq.com 白名单校验，内容抓取由后端引擎后续轮次承接）"
        )
        messages.append(msg)
        dispatchAssistantReply(to: "微信文章导入")
    }

    public func referenceKnowledge(_ item: KnowledgeItem) {
        let quote = QuotedContext(text: "《\(item.title)》", blockSummary: item.summary)
        let msg = ChatMessage(
            role: .user,
            content: "引用知识条目：\(item.title)",
            quotedContext: quote
        )
        messages.append(msg)
        dispatchAssistantReply(to: "知识引用")
    }

    private func attachmentFileType(for url: URL) -> AttachmentFileType {
        switch url.pathExtension.lowercased() {
        case "pdf": return .pdf
        case "doc", "docx": return .word
        case "ppt", "pptx", "key": return .ppt
        case "xls", "xlsx", "csv": return .excel
        default: return .generic
        }
    }
}
