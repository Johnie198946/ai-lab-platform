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
    /// 澄清提交后的断点续接轮询（原 SSE 流已断时兜底：completed 后回填最终答复，绝不无声等待）
    private var resumePollTask: Task<Void, Never>? = nil
    private var animationTasks: [String: Task<Void, Never>] = [:]
    private var clarifyWatchdogs: [String: Task<Void, Never>] = [:]
    private var submittingQuestionIds: Set<String> = []
    private var activeAttemptIds: [String: String] = [:]

    public init(sessionManager: SessionManager? = nil, appState: AppState? = nil) {
        self.sessionManager = sessionManager ?? SessionManager.shared
        self.appState = appState
        restoreActiveSession()
        refreshQuickCommands()
    }

    // MARK: - 会话恢复与持久化

    public func restoreActiveSession() {
        let sid = sessionManager.activeSessionID()
        self.messages = sessionManager.messages(for: sid)
        self.quotedContext = nil
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

    public func newSession() {
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

        let newId = sessionManager.createSession()
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
        stopStatusPolling()
        for task in animationTasks.values { task.cancel() }
        animationTasks.removeAll()
        for watchdog in clarifyWatchdogs.values { watchdog.cancel() }
        clarifyWatchdogs.removeAll()
        submittingQuestionIds.removeAll()
        activeAttemptIds.removeAll()
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

    public func selectCommand(_ chip: String) {
        QuickCommandTracker.shared.record(chip)
        refreshQuickCommands()
        inputText = chip
        sendMessage()
    }

    // MARK: - 发送 / 状态机

    public func sendMessage() {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }

        #if os(iOS)
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        #endif

        let quote = quotedContext
        if isGenerating && pendingQueue.count >= 3 {
            showToast("最多排队 3 条，请等待")
            return
        }

        let sid = sessionManager.activeSessionID()
        messages.append(ChatMessage(sessionId: sid, role: .user, content: text, quotedContext: quote))
        inputText = ""
        quotedContext = nil
        commitSession()
        dispatchAssistantReply(to: text, quote: quote)
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
        let req = InFlightRequest(id: UUID().uuidString, sessionId: sid, text: text, quote: quote, regenerate: regenerate)
        inflight = req

        messages.append(
            ChatMessage(id: req.id, sessionId: sid, role: .assistant, content: "", isStreaming: true, pending: true)
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
        if demoMode {
            await appendDemoReply(req: req)
            return
        }
        deltaBuffer = ""
        flushScheduled = false
        let stream = APIClient.shared.chatStream(
            question: req.text,
            sessionId: req.sessionId,
            quotedContext: req.quote?.text,   // 引用历史消息上下文（若有），对齐后端 quoted_context 注入
            regenerate: req.regenerate,        // 重新生成：服务端作废旧 run 后全新执行
            agentId: appState?.selectedAgentId
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
                    drainDeltaBuffer(messageId: req.id)
                    sessionManager.markInterrupted(sessionId: req.sessionId)
                    finishGeneration()
                    return
                }

                switch event {
                case .delta(let content):
                    deltaBuffer += content
                    scheduleContentFlush(messageId: req.id, taskEpoch: taskEpoch)
                    if let idx = messages.firstIndex(where: { $0.id == req.id }) {
                        updateReasoningSteps(for: idx) { steps in
                            if let tIdx = steps.firstIndex(where: { $0.type == .thought && $0.status == "running" }) {
                                steps[tIdx].status = "done"
                            }
                        }
                    }

                case .thought(let content):
                    if let idx = messages.firstIndex(where: { $0.id == req.id }) {
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
                    if let idx = messages.firstIndex(where: { $0.id == req.id }) {
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
                    if let idx = messages.firstIndex(where: { $0.id == req.id }) {
                        messages[idx].pending = false
                        updateReasoningSteps(for: idx) { steps in
                            if let matchIdx = steps.lastIndex(where: { $0.id == id || ($0.status == "running" && $0.title.contains(tool)) }) {
                                steps[matchIdx].status = "done"
                            }
                        }
                    }

                case .clarify(let question, let choices, let multiSelect, let source, let clarifyId):
                    drainDeltaBuffer(messageId: req.id)
                    let block = ClarifyBlock(
                        clarifyId: clarifyId,
                        question: question,
                        choices: choices,
                        multiSelect: multiSelect,
                        submitLabel: "确认选择",
                        source: source
                    )
                    if let idx = messages.firstIndex(where: { $0.id == req.id }) {
                        updateReasoningSteps(for: idx) { steps in
                            for i in steps.indices { steps[i].status = "done" }
                        }
                        var blocks = messages[idx].blocks
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

                case .done(_, let answer):
                    drainDeltaBuffer(messageId: req.id)
                    if let idx = messages.firstIndex(where: { $0.id == req.id }) {
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

                case .error(let code, let message):
                    drainDeltaBuffer(messageId: req.id)
                    if let idx = messages.firstIndex(where: { $0.id == req.id }) {
                        messages[idx].content = message.isEmpty ? "流式响应异常（\(code)）" : message
                        messages[idx].pending = false
                        messages[idx].isStreaming = false
                        messages[idx].degraded = true
                    }
                }
            }
            guard self.tenantEpoch == taskEpoch else { return }
            drainDeltaBuffer(messageId: req.id)

            // 兜底补全：若流式连接提前断开或未收到 delta/done.answer，从 status 端点或 non-stream 接口补全，确保绝不遗留空气泡
            if let idx = messages.firstIndex(where: { $0.id == req.id }) {
                if messages[idx].content.isEmpty && messages[idx].clarifyBlock == nil {
                    if let status = try? await APIClient.shared.fetchChatStatus(sessionId: req.sessionId, consume: true),
                       let ans = status.answer, !ans.isEmpty {
                        messages[idx].content = ans
                    } else if let chatResp = try? await APIClient.shared.chat(
                        question: req.text,
                        sessionId: req.sessionId,
                        quotedContext: req.quote?.text,
                        agentId: appState?.selectedAgentId
                    ), !chatResp.answer.isEmpty {
                        messages[idx].content = chatResp.answer
                    }
                }
                messages[idx].pending = false
                messages[idx].isStreaming = false
            }

            finalizeReasoningDuration(for: req.id)
            commitSession()
            finishGeneration()
        } catch {
            guard self.tenantEpoch == taskEpoch else { return }
            if let idx = messages.firstIndex(where: { $0.id == req.id }) {
                messages[idx].content = ""
                messages[idx].blocks = []
            }
            await runInFlight(req, taskEpoch: taskEpoch)
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
                agentId: appState?.selectedAgentId
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

        if inflight?.id != req.id {
            sessionManager.applyResponse(sessionId: req.sessionId, requestId: req.id, response: response)
            return
        }

        guard req.sessionId == sessionManager.activeSessionID() else {
            sessionManager.applyResponse(sessionId: req.sessionId, requestId: req.id, response: response)
            finishGeneration()
            return
        }

        if response.degraded == true {
            if let idx = messages.firstIndex(where: { $0.id == req.id }) {
                messages[idx].content = response.answer.isEmpty ? "服务暂时不可用，请稍后重试" : response.answer
                messages[idx].degraded = true
                messages[idx].pending = false
                messages[idx].isStreaming = false
                messages[idx].blocks = []
            }
            inflight = nil
            finalizeReasoningDuration(for: req.id)
            commitSession()
            finishGeneration()
            return
        }

        if response.answer.contains("已为您创建专属 Agent 切片") {
            NotificationCenter.default.post(name: .tenantAgentsDidUpdate, object: nil)
        }

        let steps = (response.reasoning ?? []).map { $0.toReasoningStep() }
        if let idx = messages.firstIndex(where: { $0.id == req.id }) {
            messages[idx].blocks = steps.isEmpty ? [] : [.reasoning([])]
        }
        inflight = nil

        if let payload = response.clarify, !payload.question.isEmpty {
            let clarify = ClarifyBlock(
                question: payload.question,
                choices: payload.choices.isEmpty ? [] : payload.choices,
                multiSelect: payload.multiSelect,
                submitLabel: "确认选择"
            )
            if let idx = messages.firstIndex(where: { $0.id == req.id }) {
                var blocks = messages[idx].blocks
                blocks.append(.clarify(clarify))
                messages[idx].content = response.answer.isEmpty ? "" : String(response.answer.prefix(40))
                messages[idx].blocks = blocks
                messages[idx].pending = false
                messages[idx].isStreaming = false
            }
            finalizeReasoningDuration(for: req.id)
            commitSession()
            finishGeneration()
            return
        }

        if !steps.isEmpty {
            await revealReasoning(messageId: req.id, steps: steps)
        }

        await typewriter(messageId: req.id, answer: response.answer)

        if let idx = messages.firstIndex(where: { $0.id == req.id }) {
            messages[idx].pending = false
        }
        finalizeReasoningDuration(for: req.id)
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
                sessionId: nil,
                quotedContext: updated.quote?.text,
                agentId: appState?.selectedAgentId
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

    // MARK: - Clarify 5态沙箱与 Watchdog 守护

    public func sendClarifySelection(messageId: String, selection: String) {
        guard let idx = messages.firstIndex(where: { $0.id == messageId }) else { return }
        let sid = sessionManager.activeSessionID()
        var source = "bridge"
        var clarifyId: String? = nil

        if let blockIdx = messages[idx].blocks.firstIndex(where: {
            if case .clarify = $0 { return true }
            return false
        }) {
            if case .clarify(var c) = messages[idx].blocks[blockIdx] {
                source = c.source
                clarifyId = c.clarifyId
                c.markSubmitted(selection: selection)
                messages[idx].blocks[blockIdx] = .clarify(c)
            }
        }
        commitSession()

        messages.append(ChatMessage(
            sessionId: sid,
            role: .user,
            content: selection
        ))
        commitSession()

        if source == "preclassified" {
            if !isGenerating {
                startGeneration(text: selection, quote: nil)
            } else {
                pendingQueue.append(PendingItem(id: UUID().uuidString, text: selection, quote: nil))
            }
            return
        }

        let resolvedSessionId = inflight?.sessionId ?? sid
        let attemptId = UUID().uuidString
        activeAttemptIds[messageId] = attemptId
        submittingQuestionIds.insert(messageId)

        // 启动 15s 客户端 Watchdog 守护
        clarifyWatchdogs[messageId]?.cancel()
        let watchdogTask = Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: 15_000_000_000)
            guard let self = self, !Task.isCancelled else { return }
            if self.activeAttemptIds[messageId] == attemptId {
                self.submittingQuestionIds.remove(messageId)
                self.resetClarifyCard(messageId: messageId)
                self.showToast("提交超时，已解锁可重试")
            }
        }
        clarifyWatchdogs[messageId] = watchdogTask

        Task { [weak self] in
            guard let self = self else { return }
            var submitSuccess = false
            for attempt in 0..<3 {
                do {
                    let ok = try await APIClient.shared.submitClarify(
                        sessionId: resolvedSessionId,
                        response: selection,
                        clarifyId: clarifyId
                    )
                    if ok {
                        submitSuccess = true
                        break
                    }
                } catch {
                    try? await Task.sleep(nanoseconds: UInt64((attempt + 1) * 300_000_000))
                }
            }

            await MainActor.run {
                guard self.activeAttemptIds[messageId] == attemptId else { return }
                self.clarifyWatchdogs[messageId]?.cancel()
                self.clarifyWatchdogs.removeValue(forKey: messageId)
                self.submittingQuestionIds.remove(messageId)

                if !submitSuccess {
                    self.resetClarifyCard(messageId: messageId)
                    self.showToast("选项提交失败，请点击重试")
                } else if !self.isGenerating {
                    // 原 SSE 流已断（断连/detach）：启动断点续接轮询，
                    // 确保澄清提交后必然有下文（completed 回填最终答复，绝不无声等待）
                    self.startClarifyResumePolling(sessionId: resolvedSessionId)
                }
            }
        }
    }

    private func resetClarifyCard(messageId: String) {
        if let idx = messages.firstIndex(where: { $0.id == messageId }) {
            if let blockIdx = messages[idx].blocks.firstIndex(where: {
                if case .clarify = $0 { return true }
                return false
            }) {
                if case .clarify(var c) = messages[idx].blocks[blockIdx] {
                    c.isSubmitted = false
                    c.submittedSelection = ""
                    messages[idx].blocks[blockIdx] = .clarify(c)
                }
            }
        }
    }

    /// 澄清提交后的断点续接轮询（原 SSE 流已断时兜底）：
    /// 2s 间隔回读 status，completed 后把最终答复追加为新 assistant 消息；running 持续给
    /// 「执行中」反馈；120s 未完成则诚实提示可稍后重试。顶设铁律：下一步在干嘛不允许空着。
    private func startClarifyResumePolling(sessionId: String) {
        resumePollTask?.cancel()
        let taskEpoch = tenantEpoch
        resumePollTask = Task { @MainActor [weak self] in
            guard let self else { return }
            var polls = 0
            while polls < 60 && !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                if Task.isCancelled || self.tenantEpoch != taskEpoch { return }
                do {
                    let status = try await APIClient.shared.fetchChatStatus(sessionId: sessionId)
                    if status.status == "completed", let answer = status.answer, !answer.isEmpty {
                        // 完成：追加 assistant 消息（澄清后的最终答复）
                        self.messages.append(ChatMessage(
                            sessionId: sessionId,
                            role: .assistant,
                            content: answer,
                            isStreaming: false,
                            pending: false
                        ))
                        self.commitSession()
                        self.showToast("已完成")
                        return
                    }
                    if status.status == "error" {
                        self.showToast("任务执行出错，请点击重试")
                        return
                    }
                    // running/pending：ClarifyCard 已展示「Agent 继续执行中…」，继续轮询
                } catch {
                    // 网络抖动：继续轮询
                }
                polls += 1
            }
            if !Task.isCancelled && self.tenantEpoch == taskEpoch {
                self.showToast("任务仍在后台执行，可稍后进入会话查看")
            }
        }
    }

    // MARK: - 辅助方法与操作

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
                    let status = try await APIClient.shared.fetchChatStatus(sessionId: sid)
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
                if let status = try? await APIClient.shared.fetchChatStatus(sessionId: sid, consume: true),
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
                let status = try await APIClient.shared.fetchChatStatus(sessionId: sid, consume: true)
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
