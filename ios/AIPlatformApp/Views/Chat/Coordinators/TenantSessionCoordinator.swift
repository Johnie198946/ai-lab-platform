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
    public static let shared = TenantSessionCoordinator()

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
    @Published public private(set) var hasOlderMessages: Bool = false
    @Published public private(set) var hasNewerMessages: Bool = false
    @Published public private(set) var isLatestPage: Bool = true
    @Published public private(set) var historyPageIdentity = UUID()
    @Published public private(set) var historyPageStartsAtBottom: Bool = true

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
    /// Detached server Runs continue independently of the currently visible chat.
    /// One monitor per logical session writes the terminal answer back to that session.
    private var backgroundRunMonitors: [String: Task<Void, Never>] = [:]
    private var backgroundRunRequests: [String: InFlightRequest] = [:]
    private var sessionPendingQueues: [String: [PendingItem]] = [:]
    private let maximumConcurrentRuns = 2
    private var lastStreamCheckpoint = Date.distantPast
    private var lastCheckpointCharacterCount = 0
    private var nextContextScope: ChatContextScopeDTO? = nil
    private var nextClientSessionContext: ClientSessionContextDTO? = nil
    @Published public var pendingOrganizationDisposition: [String] = []
    private var accountCancellable: AnyCancellable?
    /// Avoid synchronous SQLite rehydration every time SwiftUI merely presents the same Tab again.
    private var loadedSessionId: String? = nil

    public init(sessionManager: SessionManager? = nil, appState: AppState? = nil) {
        self.sessionManager = sessionManager ?? SessionManager.shared
        self.appState = appState
        restoreActiveSession()
        refreshQuickCommands()
        accountCancellable = NotificationCenter.default.publisher(for: .localAccountDidChange)
            .sink { [weak self] _ in
                Task { @MainActor in self?.handleLocalAccountChange() }
            }
    }

    private func handleLocalAccountChange() {
        // Standalone coordinators used by previews and focused UI tests have no
        // account lifecycle to follow. Ignore process-wide account notifications
        // until ChatView binds the real AppState on appear.
        guard appState != nil else { return }
        tenantEpoch += 1
        cancelAllTasksAndAnimations()
        for task in backgroundRunMonitors.values { task.cancel() }
        backgroundRunMonitors.removeAll()
        backgroundRunRequests.removeAll()
        isGenerating = false
        inflight = nil
        pendingQueue.removeAll()
        messages.removeAll()
        loadedSessionId = nil
        if appState?.isLoggedIn == true {
            restoreActiveSession(force: true)
        }
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
            },
            onNoteDraftAction: { [weak self] draftId, action in
                self?.handleNoteDraftAction(messageId: message?.id, draftId: draftId, action: action)
            },
            onKnowledgeAction: { [weak self] actionId, verb in
                self?.handleKnowledgeAction(messageId: message?.id, actionId: actionId, verb: verb)
            }
        )
    }

    public func restoreActiveSession(force: Bool = false) {
        let sid = sessionManager.activeSessionID()
        guard force || loadedSessionId != sid else { return }
        applyHistoryPage(sessionManager.latestPage(for: sid), isLatest: true, startsAtBottom: true)
        loadedSessionId = sid
        self.quotedContext = nil
        appState?.selectedAgentId = sessionManager.agentId(for: sid)
        appState?.selectedAgentName = sessionManager.agentName(for: sid)
    }

    public func updateClarifyDraft(messageId: String, selectionIDs: [String], customText: String) {
        updateClarify(messageId: messageId) { block in
            block.draftSelectionIDs = selectionIDs
            block.draftCustomText = customText
        }
    }

    public func setClarifyCollapsed(messageId: String, collapsed: Bool) {
        updateClarify(messageId: messageId) { $0.isCollapsed = collapsed }
    }

    public func collapseActiveClarify() {
        guard let message = messages.last(where: { $0.clarifyBlock?.isSubmitted == false }),
              message.clarifyBlock?.isCollapsed == false else { return }
        setClarifyCollapsed(messageId: message.id, collapsed: true)
    }

    private func updateClarify(messageId: String, mutate: (inout ClarifyBlock) -> Void) {
        guard let messageIndex = messages.firstIndex(where: { $0.id == messageId }),
              let blockIndex = messages[messageIndex].blocks.firstIndex(where: {
                  if case .clarify = $0 { return true }; return false
              }), case .clarify(var block) = messages[messageIndex].blocks[blockIndex] else { return }
        mutate(&block)
        messages[messageIndex].blocks[blockIndex] = .clarify(block)
        commitSession()
    }

    /// 回前台、重建 ChatView 或切回会话时，仅对账既有 server-side Run。
    /// 不重发原问题；running 进入 status monitor，只有明确 not_found/timeout 才允许用户重跑。
    public func reconcileActiveRun() {
        guard !isGenerating, APIClient.shared.currentToken() != nil else { return }
        let sid = sessionManager.activeSessionID()
        guard let outputIndex = messages.lastIndex(where: {
            $0.clarifyBlock == nil && ($0.role == .interrupted || $0.pending || $0.isStreaming)
        }) else { return }
        let outputId = messages[outputIndex].id
        guard let userMessage = messages[..<outputIndex].last(where: { $0.role == .user })
            ?? sessionManager.previousUserMessage(before: outputId, sessionId: sid) else { return }
        let agentId = sessionManager.agentId(for: sid)
        let taskEpoch = tenantEpoch
        statusPollTask?.cancel()
        statusPollTask = Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                let status = try await APIClient.shared.fetchChatStatus(
                    sessionId: sid, consume: true, agentId: agentId
                )
                guard self.tenantEpoch == taskEpoch,
                      self.sessionManager.activeSessionID() == sid else { return }
                if status.status == "completed", let answer = status.answer, !answer.isEmpty {
                    self.applyRecoveredAnswer(answer, outputMessageId: outputId)
                    self.backgroundRunMonitors[sid]?.cancel()
                    self.backgroundRunMonitors.removeValue(forKey: sid)
                    self.backgroundRunRequests.removeValue(forKey: sid)
                    self.finishGeneration()
                    return
                }
                if status.status == "running" {
                    let req = InFlightRequest(
                        id: outputId, sessionId: sid, text: userMessage.content,
                        quote: userMessage.quotedContext, agentId: agentId
                    )
                    self.inflight = req
                    self.isGenerating = true
                    self.streamOutputMessageIds[req.id] = outputId
                    if let idx = self.messages.firstIndex(where: { $0.id == outputId }) {
                        self.messages[idx].role = .assistant
                        self.messages[idx].pending = true
                        self.messages[idx].isStreaming = true
                    }
                    self.commitSession()
                    self.startRecoveredRunMonitor(
                        requestId: req.id, sessionId: sid,
                        agentId: agentId, outputMessageId: outputId
                    )
                }
            } catch {
                // 网络不确定时保持可恢复标记，绝不创建第二个 Run。
            }
        }
    }

    /// 冷启动/回前台时以服务端为准恢复 Clarify；不启动新推理。
    public func reconcileRestoredClarify() {
        guard let idx = messages.lastIndex(where: {
            guard let block = $0.clarifyBlock else { return false }
            return block.source == "bridge" && !block.isSubmitted
        }), let block = messages[idx].clarifyBlock else { return }
        let messageId = messages[idx].id
        let sid = block.sessionId ?? sessionManager.activeSessionID()
        let requestId = block.requestId ?? messageId
        let agentId = block.agentId ?? appState?.selectedAgentId
        let selection = block.submittedSelection
        clarifySubmissionTask?.cancel()
        clarifySubmissionTask = Task { [weak self] in
            guard let self else { return }
            if [.submitting, .reconciling].contains(block.submissionState), !selection.isEmpty {
                await self.reconcileClarifySubmission(
                    messageId: messageId,
                    selection: selection,
                    requestId: requestId,
                    sessionId: sid,
                    agentId: agentId,
                    serverState: "restore"
                )
                return
            }
            do {
                let status = try await APIClient.shared.fetchChatStatus(
                    sessionId: sid, agentId: agentId
                )
                guard let currentIdx = self.messages.firstIndex(where: { $0.id == messageId }) else { return }
                if let pending = status.clarify, pending.clarifyId == block.clarifyId {
                    if let blockIdx = self.messages[currentIdx].blocks.firstIndex(where: {
                        if case .clarify = $0 { return true }; return false
                    }), case .clarify(var restored) = self.messages[currentIdx].blocks[blockIdx] {
                        restored.requestId = pending.requestId ?? requestId
                        restored.sessionId = sid
                        restored.agentId = agentId
                        restored.expiresInSeconds = pending.expiresInSeconds
                        restored.submissionState = .pending
                        self.messages[currentIdx].blocks[blockIdx] = .clarify(restored)
                        self.commitSession()
                    }
                } else if status.status == "completed", let answer = status.answer, !answer.isEmpty {
                    self.messages.append(ChatMessage(sessionId: sid, role: .assistant, content: answer))
                    self.setClarifyState(messageIndex: currentIdx, state: .expired)
                    self.commitSession()
                } else if status.status == "running" {
                    self.isGenerating = true
                    self.inflight = InFlightRequest(
                        id: requestId, sessionId: sid, text: "", agentId: agentId
                    )
                    self.startRecoveredRunMonitor(
                        requestId: requestId,
                        sessionId: sid,
                        agentId: agentId,
                        outputMessageId: messageId
                    )
                } else {
                    self.setClarifyState(messageIndex: currentIdx, state: .expired)
                    self.commitSession()
                }
            } catch {
                // 离线时保留本地卡片；用户点击后仍会走精确 clarify_id 提交与对账。
            }
        }
    }

    public func commitSession() {
        let sid = sessionManager.activeSessionID()
        sessionManager.setMessages(messages, for: sid)
        guard isLatestPage else { return }
        trimVisibleMessageWindow()
        sessionManager.cacheVisibleMessages(messages, for: sid)
    }

    public func switchSession(to sessionId: String) {
        let previousSessionId = sessionManager.activeSessionID()
        guard sessionId != previousSessionId else { return }

        sessionPendingQueues[previousSessionId] = pendingQueue
        detachCurrentRunForNavigation()
        tenantEpoch += 1
        cancelAllTasksAndAnimations()

        isGenerating = false
        inflight = nil
        pendingQueue = sessionPendingQueues[sessionId] ?? []
        waitingSeconds = 0
        thinkingPhase = nil
        thinkingDetail = nil
        liveProgress = nil

        sessionManager.switchTo(sessionId)
        restoreActiveSession(force: true)
        refreshQuickCommands()
    }

    public func startTargetedTopic(from message: ChatMessage) {
        let parentId = sessionManager.activeSessionID()
        let topic = sessionManager.startTopic(parentSessionId: parentId, sourceMessage: message)
        if topic.state == .queued {
            showToast("并行话题已满（最多 3 个），已加入队列")
            return
        }
        switchSession(to: topic.sessionId)
        quotedContext = sessionManager.topicQuote(for: topic.sessionId)
        showToast("已开启针对性话题，引用上下文已保留")
    }

    public func openTopic(_ topic: TopicSessionMetadata) {
        guard topic.state != .queued else {
            showToast("该话题仍在队列中")
            return
        }
        switchSession(to: topic.sessionId)
        if messages.isEmpty { quotedContext = sessionManager.topicQuote(for: topic.sessionId) }
    }

    public func endCurrentTopic() {
        let sessionId = sessionManager.activeSessionID()
        guard sessionManager.topicSessions[sessionId]?.state == .active else { return }
        sessionManager.markTopicEnding(sessionId)
        sendMessage(text: "请结束当前针对性话题：基于本话题完整上下文生成可确认的 knowledge_action_v1 知识操作草案。必须返回 knowledge_action_draft，由用户确认后再通过 /me/knowledge-notes 同步；不要直接写入知识库。")
    }

    public func newSession(agentId: String? = nil, agentName: String? = nil) {
        let previousSessionId = sessionManager.activeSessionID()
        sessionPendingQueues[previousSessionId] = pendingQueue
        detachCurrentRunForNavigation()
        tenantEpoch += 1
        cancelAllTasksAndAnimations()

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
        restoreActiveSession(force: true)
        refreshQuickCommands()
    }

    public func deleteSession(_ sessionId: String) {
        backgroundRunMonitors[sessionId]?.cancel()
        backgroundRunMonitors.removeValue(forKey: sessionId)
        backgroundRunRequests.removeValue(forKey: sessionId)
        sessionPendingQueues.removeValue(forKey: sessionId)
        if sessionId == sessionManager.activeSessionID() {
            newSession()
        }
        sessionManager.deleteSession(sessionId)
    }

    public func clearCurrentSession() {
        cancelAllTasksAndAnimations()
        let sid = sessionManager.activeSessionID()
        sessionManager.clearSession(sid)
        messages.removeAll()
        hasOlderMessages = false
        hasNewerMessages = false
        isLatestPage = true
        historyPageStartsAtBottom = true
        historyPageIdentity = UUID()
    }

    public func loadOlderMessagePage() {
        guard !isGenerating, let first = messages.first else { return }
        let sid = sessionManager.activeSessionID()
        applyHistoryPage(sessionManager.pageBefore(first.id, sessionId: sid), isLatest: false, startsAtBottom: true)
    }

    public func loadNewerMessagePage() {
        guard !isGenerating, let last = messages.last else { return }
        let sid = sessionManager.activeSessionID()
        let page = sessionManager.pageAfter(last.id, sessionId: sid)
        applyHistoryPage(page, isLatest: !page.hasNewer, startsAtBottom: false)
    }

    public func returnToLatestMessages() {
        guard !isGenerating else { return }
        let sid = sessionManager.activeSessionID()
        applyHistoryPage(sessionManager.latestPage(for: sid), isLatest: true, startsAtBottom: true)
    }

    private func applyHistoryPage(_ page: StoredMessagePage, isLatest: Bool, startsAtBottom: Bool) {
        messages = page.messages
        hasOlderMessages = page.hasOlder
        hasNewerMessages = page.hasNewer
        isLatestPage = isLatest && !page.hasNewer
        historyPageStartsAtBottom = startsAtBottom
        historyPageIdentity = UUID()
    }

    private func trimVisibleMessageWindow() {
        var totalCharacters = messages.reduce(0) { $0 + $1.content.count }
        while messages.count > 1 && (messages.count > ChatHistoryStore.pageMessageLimit || totalCharacters > ChatHistoryStore.pageCharacterLimit) {
            totalCharacters -= messages.removeFirst().content.count
            hasOlderMessages = true
        }
        hasNewerMessages = false
        isLatestPage = true
    }

    /// Locking the screen suspends iOS networking. Checkpoint and detach the client
    /// subscription while preserving the server Run, then reconcile it on foreground.
    public func prepareForBackground() {
        guard let req = inflight else {
            commitSession()
            return
        }
        let outputId = outputMessageId(for: req)
        drainDeltaBuffer(messageId: outputId)
        commitSession()
        startBackgroundRunMonitor(req: req, outputMessageId: outputId)
        currentChatTask?.cancel()
        currentChatTask = nil
        stopStatusPolling()
        isGenerating = false
        inflight = nil
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

    /// Navigation detaches the transport but never cancels the server Run.
    /// The partial answer is checkpointed and a session-keyed monitor owns
    /// completion while another tab or conversation is visible.
    private func detachCurrentRunForNavigation() {
        guard let req = inflight else { return }
        let outputId = outputMessageId(for: req)
        drainDeltaBuffer(messageId: outputId)
        commitSession()
        startBackgroundRunMonitor(req: req, outputMessageId: outputId)
        currentChatTask?.cancel()
        currentChatTask = nil
        stopStatusPolling()
    }

    private func startBackgroundRunMonitor(req: InFlightRequest, outputMessageId: String) {
        guard backgroundRunMonitors[req.sessionId] == nil else { return }
        backgroundRunRequests[req.sessionId] = req
        backgroundRunMonitors[req.sessionId] = Task { @MainActor [weak self] in
            guard let self else { return }
            defer {
                self.backgroundRunMonitors.removeValue(forKey: req.sessionId)
                self.backgroundRunRequests.removeValue(forKey: req.sessionId)
            }
            var attempts = 0
            while attempts < 360, !Task.isCancelled {
                do {
                    let status = try await APIClient.shared.fetchChatStatus(
                        sessionId: req.sessionId, agentId: req.agentId
                    )
                    if status.status == "completed", let answer = status.answer, !answer.isEmpty {
                        self.sessionManager.applyCompletedStatus(
                            sessionId: req.sessionId,
                            requestId: outputMessageId,
                            answer: answer
                        )
                        return
                    }
                    if ["timeout", "not_found"].contains(status.status) {
                        self.sessionManager.applyDegraded(
                            sessionId: req.sessionId,
                            requestId: outputMessageId,
                            text: "任务未能完成，可返回会话后重试"
                        )
                        return
                    }
                } catch {
                    // A transient status failure must not create a second Run.
                }
                attempts += 1
                try? await Task.sleep(nanoseconds: 2_000_000_000)
            }
        }
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
            self.nextContextScope = appState?.pendingChatContextScope
            self.nextClientSessionContext = appState?.pendingChatSessionContext
            appState?.pendingChatPrompt = nil
            appState?.pendingChatContextScope = nil
            appState?.pendingChatSessionContext = nil
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

        if !isLatestPage { returnToLatestMessages() }

        #if os(iOS)
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        #endif

        let quote = quotedContext
        let contextScope = nextContextScope ?? ChatContextScopeDTO()
        nextContextScope = nil
        let sid = sessionManager.activeSessionID()
        if backgroundRunMonitors[sid] != nil {
            showToast("当前会话仍有任务在后台执行，请等待完成")
            return
        }
        if !isGenerating && backgroundRunMonitors.count >= maximumConcurrentRuns {
            showToast("已有 \(maximumConcurrentRuns) 个会话任务在执行，请稍后再试")
            return
        }
        if isGenerating && pendingQueue.count >= 3 && !regenerate {
            showToast("最多排队 3 条，请等待")
            return
        }

        let clientSessionContext = nextClientSessionContext ?? sessionManager.clientSessionContext(for: sid)
        nextClientSessionContext = nil
        var localNoteSnapshot: [ChatLocalNoteDTO] = []
        var localNoteCharacters = 0
        // Ordinary web/general questions must not upload every local note. Only
        // explicit local/combined knowledge requests receive a bounded snapshot.
        if contextScope.mode == .localOnly || contextScope.mode == .combined {
            for note in (KnowledgeNoteStore.shared.notes + KnowledgeNoteStore.shared.archivedNotes).prefix(12) {
                let markdown = String(KnowledgeNoteStore.shared.markdown(for: note).prefix(8_000))
                guard localNoteCharacters + markdown.count <= 40_000 else { break }
                localNoteSnapshot.append(ChatLocalNoteDTO(
                    id: note.id,
                    title: note.title,
                    markdown: markdown,
                    updatedAt: ISO8601DateFormatter().string(from: note.updatedAt),
                    contentHash: KnowledgeNoteStore.shared.contentHash(for: note),
                    tags: note.tags,
                    aliases: note.aliases,
                    isPinned: note.isPinned,
                    archived: note.archivedAt != nil
                ))
                localNoteCharacters += markdown.count
            }
        }
        let enrichedClientSessionContext = ClientSessionContextDTO(
            sessionId: clientSessionContext.sessionId,
            messages: clientSessionContext.messages,
            truncated: clientSessionContext.truncated,
            sourceSessions: clientSessionContext.sourceSessions,
            localNotes: localNoteSnapshot
        )
        messages.append(ChatMessage(sessionId: sid, role: .user, content: text, quotedContext: quote))
        inputText = ""
        quotedContext = nil
        commitSession()

        if isGenerating && !regenerate {
            pendingQueue.append(PendingItem(id: UUID().uuidString, text: text, quote: quote, contextScope: contextScope, clientSessionContext: enrichedClientSessionContext))
        } else {
            startGeneration(text: text, quote: quote, regenerate: regenerate, contextScope: contextScope, clientSessionContext: enrichedClientSessionContext)
        }
    }

    public func dispatchAssistantReply(to text: String, quote: QuotedContext? = nil) {
        if isGenerating {
            pendingQueue.append(PendingItem(id: UUID().uuidString, text: text, quote: quote))
        } else {
            startGeneration(text: text, quote: quote)
        }
    }

    public func startGeneration(text: String, quote: QuotedContext?, regenerate: Bool = false, contextScope: ChatContextScopeDTO = ChatContextScopeDTO(), clientSessionContext: ClientSessionContextDTO? = nil) {
        isGenerating = true
        waitingSeconds = 0
        thinkingPhase = nil
        thinkingDetail = nil
        generationStartDate = Date()
        lastStreamCheckpoint = .distantPast
        lastCheckpointCharacterCount = 0
        let sid = sessionManager.activeSessionID()
        let req = InFlightRequest(
            id: UUID().uuidString, sessionId: sid, text: text, quote: quote,
            regenerate: regenerate, agentId: appState?.selectedAgentId,
            contextScope: contextScope, clientSessionContext: clientSessionContext
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

    // MARK: - 流式批量节流
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
        let publishedCount = messages.first(where: { $0.id == messageId })?.content.utf8.count ?? 0
        let delay = ChatStreamingPerformancePolicy.flushDelayNanoseconds(
            currentUTF8Count: publishedCount + deltaBuffer.utf8.count
        )
        flushTask = Task { @MainActor [weak self] in
            // Increase coalescing as the answer grows. Combined with the bounded
            // streaming tail this leaves a predictable main-thread scroll budget.
            try? await Task.sleep(nanoseconds: delay)
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
                let count = self.messages[idx].content.count
                if Date().timeIntervalSince(self.lastStreamCheckpoint) >= 0.75
                    || count - self.lastCheckpointCharacterCount >= 2_048 {
                    self.lastStreamCheckpoint = Date()
                    self.lastCheckpointCharacterCount = count
                    self.commitSession()
                }
            }
        }
    }

    private func runInFlightStreamed(_ req: InFlightRequest, taskEpoch: Int) async {
        var handedOffToStatusRecovery = false
        var receivedTerminalEvent = false
        defer {
            if self.tenantEpoch == taskEpoch,
               self.sessionManager.activeSessionID() == req.sessionId {
                let outputId = self.outputMessageId(for: req)
                self.drainDeltaBuffer(messageId: outputId)
                self.finalizeReasoningDuration(for: outputId)
                self.commitSession()
            } else {
                self.flushTask?.cancel()
                self.flushTask = nil
                self.flushScheduled = false
                self.deltaBuffer = ""
            }
            // Once handed to a status monitor, this remains the same active Run.
            if !handedOffToStatusRecovery,
               self.inflight?.id == req.id && self.tenantEpoch == taskEpoch {
                self.isGenerating = false
            }
            if !handedOffToStatusRecovery {
                self.streamOutputMessageIds.removeValue(forKey: req.id)
            }
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
            agentId: req.agentId,
            contextScope: req.contextScope,
            clientSessionContext: req.clientSessionContext
        )
        do {
            eventLoop: for try await event in stream {
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
                            if let tIdx = steps.firstIndex(where: { $0.type == .thought }) {
                                steps[tIdx].title = "正在生成回答…"
                                steps[tIdx].status = "running"
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

                case .clarify(let question, let choices, let multiSelect, let source, let clarifyId, let requestId, let expiresInSeconds):
                    drainDeltaBuffer(messageId: outputId)
                    let block = ClarifyBlock(
                        clarifyId: clarifyId,
                        requestId: requestId ?? req.id,
                        sessionId: req.sessionId,
                        agentId: req.agentId,
                        expiresInSeconds: expiresInSeconds,
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

                case .clarifyExpired(let clarifyId, _):
                    markClarifyExpired(clarifyId: clarifyId)

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

                case .feedbackReceipt(_, _, let message, _):
                    showToast(message)

                case .agentRoute(let id, let name, _, let delegatedBy):
                    if let idx = messages.firstIndex(where: { $0.id == outputId }) {
                        messages[idx].executingAgentId = id
                        messages[idx].executingAgentName = name
                        messages[idx].delegatedBy = delegatedBy
                    }

                case .noteDraft(let id, let title, let markdown, let tags, let sourceSessionId, let sourceMessageIds, let accountScope, let mergeCandidates, let mergedTitle, let mergedMarkdown, let mergedTags, let operation, let targetNoteId, let targetNoteTitle, let targetContentHash):
                    drainDeltaBuffer(messageId: outputId)
                    guard sourceSessionId == nil || sourceSessionId == req.sessionId else { continue }
                    let draft = NoteDraftBlock(
                        id: id,
                        title: title,
                        markdown: markdown,
                        tags: tags,
                        sourceSessionId: sourceSessionId,
                        sourceMessageIds: sourceMessageIds,
                        accountScope: accountScope,
                        mergeCandidates: mergeCandidates.isEmpty ? nil : mergeCandidates,
                        mergedTitle: mergedTitle,
                        mergedMarkdown: mergedMarkdown,
                        mergedTags: mergedTags.isEmpty ? nil : mergedTags,
                        operation: operation,
                        targetNoteId: targetNoteId,
                        targetNoteTitle: targetNoteTitle,
                        targetContentHash: targetContentHash
                    )
                    if let idx = messages.firstIndex(where: { $0.id == outputId }),
                       !messages[idx].blocks.contains(where: {
                           if case .noteDraft(let existing) = $0 { return existing.id == id }
                           return false
                       }) {
                        messages[idx].blocks.append(.noteDraft(draft))
                        messages[idx].pending = false
                    }

                case .knowledgeActionDraft(let action):
                    drainDeltaBuffer(messageId: outputId)
                    if let idx = messages.firstIndex(where: { $0.id == outputId }),
                       !messages[idx].blocks.contains(where: {
                           if case .knowledgeAction(let existing) = $0 { return existing.id == action.id }
                           return false
                       }) {
                        messages[idx].blocks.append(.knowledgeAction(action))
                        messages[idx].pending = false
                    }

                case .knowledgeNavigation(let target):
                    appState?.pendingKnowledgeNavigation = target
                    appState?.activeTab = 2

                case .done(_, let answer):
                    drainDeltaBuffer(messageId: outputId)
                    if let idx = messages.firstIndex(where: { $0.id == outputId }) {
                        updateReasoningSteps(for: idx) { steps in
                            for i in steps.indices { steps[i].status = "done" }
                        }
                        // The terminal answer is authoritative. Replacing the
                        // accumulated transport snapshot prevents truncated or
                        // stale deltas from winning the final persistence race.
                        if let answer, !answer.isEmpty {
                            messages[idx].content = answer
                        }
                        messages[idx].pending = false
                        messages[idx].isStreaming = false
                        receivedTerminalEvent = !messages[idx].content.isEmpty
                    }

                case .error(let code, let message):
                    drainDeltaBuffer(messageId: outputId)
                    if let idx = messages.firstIndex(where: { $0.id == outputId }) {
                        if code == "knowledge_scope_denied" {
                            messages[idx].content = "套餐或知识权限已变化，请刷新知识权限后重试"
                            showToast("套餐或知识权限已变化，请刷新知识权限后重试")
                            NotificationCenter.default.post(name: .knowledgeAccessDidChange, object: nil)
                        } else {
                            messages[idx].content = message.isEmpty ? "流式响应异常（\(code)）" : message
                        }
                        messages[idx].pending = false
                        messages[idx].isStreaming = false
                        messages[idx].degraded = true
                        receivedTerminalEvent = true
                    }
                }
                if receivedTerminalEvent { break eventLoop }
            }
            guard self.tenantEpoch == taskEpoch else { return }
            let outputId = outputMessageId(for: req)
            drainDeltaBuffer(messageId: outputId)
            if receivedTerminalEvent {
                commitSession()
                finishGeneration()
                return
            }

            // A stream that ended without a terminal frame (including busy)
            // reconciles the same server Run instead of starting a duplicate.
            handedOffToStatusRecovery = await recoverAfterStreamEnd(req, outputMessageId: outputId)
            if !handedOffToStatusRecovery { finishGeneration() }
        } catch {
            guard self.tenantEpoch == taskEpoch else { return }
            let outputId = outputMessageId(for: req)
            drainDeltaBuffer(messageId: outputId)
            // 网络断开只 detach。running 必须恢复 monitor，绝不能以 regenerate 覆盖旧 user key。
            handedOffToStatusRecovery = await recoverAfterStreamEnd(req, outputMessageId: outputId)
            if !handedOffToStatusRecovery { finishGeneration() }
        }
    }

    /// SSE 结束后的唯一恢复路径：completed 回填；running 追踪；不确定状态保留恢复入口。
    @discardableResult
    private func recoverAfterStreamEnd(_ req: InFlightRequest, outputMessageId: String) async -> Bool {
        do {
            let status = try await APIClient.shared.fetchChatStatus(
                sessionId: req.sessionId, consume: true, agentId: req.agentId
            )
            if status.status == "completed", let answer = status.answer, !answer.isEmpty {
                applyRecoveredAnswer(answer, outputMessageId: outputMessageId)
                return false
            }
            if status.status == "running" {
                if let idx = messages.firstIndex(where: { $0.id == outputMessageId }) {
                    if messages[idx].content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        messages[idx].content = "连接暂时中断，正在后台继续。返回本页后会恢复同一任务。"
                    }
                    messages[idx].pending = true
                    messages[idx].isStreaming = true
                    messages[idx].degraded = false
                }
                streamOutputMessageIds[req.id] = outputMessageId
                startRecoveredRunMonitor(
                    requestId: req.id, sessionId: req.sessionId,
                    agentId: req.agentId, outputMessageId: outputMessageId
                )
                commitSession()
                return true
            }
        } catch {
            // 状态查询也断网：持久化 interrupted，回前台后 reconcileActiveRun 再对账。
        }
        if let idx = messages.firstIndex(where: { $0.id == outputMessageId }) {
            if messages[idx].content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                messages[idx].content = "连接暂时中断，已保留当前任务。请稍后返回本页恢复。"
            }
            messages[idx].role = .interrupted
            messages[idx].pending = false
            messages[idx].isStreaming = false
            messages[idx].degraded = false
        }
        commitSession()
        return false
    }

    private func applyRecoveredAnswer(_ answer: String, outputMessageId: String) {
        guard let idx = messages.firstIndex(where: { $0.id == outputMessageId }) else { return }
        messages[idx].role = .assistant
        messages[idx].content = answer
        messages[idx].pending = false
        messages[idx].isStreaming = false
        messages[idx].degraded = false
        messages[idx].blocks = []
        finalizeReasoningDuration(for: outputMessageId)
        commitSession()
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
                clarifyId: payload.clarifyId,
                requestId: req.id,
                sessionId: req.sessionId,
                agentId: req.agentId,
                expiresInSeconds: payload.expiresInSeconds,
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
        case APIError.knowledgeScopeChanged:
            inflight?.phase = .serverError("套餐或知识权限已变化，请刷新知识权限后重试")
            showToast("套餐或知识权限已变化，请刷新知识权限后重试")
            NotificationCenter.default.post(name: .knowledgeAccessDidChange, object: nil)
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
        guard clarify.submissionState != .submitting else { return }
        let sid = clarify.sessionId ?? sessionManager.activeSessionID()
        let clarifyId = clarify.clarifyId
        let agentId = clarify.agentId ?? appState?.selectedAgentId

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

        // 服务端 clarify_id 是唯一真值。requestId 仅用于把同一 Run 的续写定位到 UI，
        // 不再以易失的 inflight/streamOutputMessageIds/isGenerating 作为提交门禁。
        let requestId = clarify.requestId
            ?? streamOutputMessageIds.first(where: { $0.value == messageId })?.key
            ?? inflight?.id
            ?? messageId
        setClarifyState(messageIndex: idx, state: .submitting, selection: selection)
        commitSession()
        print("[Clarify] submit-start message=\(messageId) clarify=\(clarifyId ?? "legacy") request=\(requestId)")

        clarifySubmissionTask?.cancel()
        clarifySubmissionTask = Task { [weak self] in
            guard let self else { return }
            do {
                let result = try await APIClient.shared.submitClarify(
                    sessionId: sid,
                    response: selection,
                    clarifyId: clarifyId,
                    agentId: agentId
                )
                guard !Task.isCancelled else { return }
                print("[Clarify] submit-result clarify=\(clarifyId ?? "legacy") state=\(result.state)")
                if result.ok && ["accepted", "replayed"].contains(result.state) {
                    self.acceptClarifySubmission(
                        messageId: messageId,
                        requestId: requestId,
                        sessionId: sid,
                        agentId: agentId,
                        selection: selection
                    )
                    return
                }
                await self.reconcileClarifySubmission(
                    messageId: messageId,
                    selection: selection,
                    requestId: requestId,
                    sessionId: sid,
                    agentId: agentId,
                    serverState: result.state
                )
            } catch is CancellationError {
                return
            } catch {
                guard !Task.isCancelled else { return }
                print("[Clarify] failed message=\(messageId) clarify=\(clarifyId ?? "nil") error=\(error.localizedDescription)")
                await self.reconcileClarifySubmission(
                    messageId: messageId,
                    selection: selection,
                    requestId: requestId,
                    sessionId: sid,
                    agentId: agentId,
                    serverState: "network_unknown"
                )
            }
        }
    }

    private func setClarifyState(
        messageIndex: Int,
        state: ClarifySubmissionState,
        selection: String? = nil
    ) {
        guard let blockIdx = messages[messageIndex].blocks.firstIndex(where: {
            if case .clarify = $0 { return true }; return false
        }), case .clarify(var block) = messages[messageIndex].blocks[blockIdx] else { return }
        block.submissionState = state
        if let selection { block.submittedSelection = selection }
        messages[messageIndex].blocks[blockIdx] = .clarify(block)
    }

    private func acceptClarifySubmission(
        messageId: String,
        requestId: String,
        sessionId: String,
        agentId: String?,
        selection: String
    ) {
        guard let idx = messages.firstIndex(where: { $0.id == messageId }) else { return }
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
            sessionId: sessionId,
            role: .assistant,
            content: "",
            isStreaming: true,
            blocks: [.reasoning([continuationStep])]
        ))
        if inflight?.id == requestId {
            streamOutputMessageIds[requestId] = continuationMessageId
        } else {
            let original = messages[..<idx].last(where: { $0.role == .user })?.content ?? ""
            inflight = InFlightRequest(
                id: requestId, sessionId: sessionId, text: original, agentId: agentId
            )
            startRecoveredRunMonitor(
                requestId: requestId,
                sessionId: sessionId,
                agentId: agentId,
                outputMessageId: continuationMessageId
            )
        }
        isGenerating = true
        thinkingPhase = "reasoning"
        thinkingDetail = "已收到选择，正在继续处理…"
        commitSession()
    }

    private func reconcileClarifySubmission(
        messageId: String,
        selection: String,
        requestId: String,
        sessionId: String,
        agentId: String?,
        serverState: String
    ) async {
        guard let idx = messages.firstIndex(where: { $0.id == messageId }),
              let local = messages[idx].clarifyBlock else { return }
        setClarifyState(messageIndex: idx, state: .reconciling, selection: selection)
        commitSession()
        do {
            let status = try await APIClient.shared.fetchChatStatus(
                sessionId: sessionId, agentId: agentId
            )
            print("[Clarify] reconcile clarify=\(local.clarifyId ?? "legacy") phase=\(status.phase ?? status.status)")
            if status.status == "completed", let answer = status.answer, !answer.isEmpty {
                markClarifySubmitted(messageIndex: idx, selection: selection)
                messages.append(ChatMessage(sessionId: sessionId, role: .assistant, content: answer))
                commitSession()
                finishGeneration()
                return
            }
            if let pending = status.clarify {
                if pending.clarifyId == local.clarifyId {
                    setClarifyState(
                        messageIndex: idx,
                        state: serverState == "rejected" ? .rejected : .pending,
                        selection: selection
                    )
                    commitSession()
                    showToast(serverState == "rejected" ? "该选择未通过校验，请修改后重试" : "连接已恢复，请再次确认")
                } else {
                    setClarifyState(messageIndex: idx, state: .expired, selection: selection)
                    let next = ClarifyBlock(
                        clarifyId: pending.clarifyId,
                        requestId: pending.requestId ?? requestId,
                        sessionId: sessionId,
                        agentId: agentId,
                        expiresInSeconds: pending.expiresInSeconds,
                        question: pending.question,
                        choices: pending.choices,
                        multiSelect: pending.multiSelect,
                        source: "bridge"
                    )
                    messages.append(ChatMessage(
                        sessionId: sessionId, role: .assistant, content: "", blocks: [.clarify(next)]
                    ))
                    commitSession()
                    showToast("旧确认已过期，已恢复到当前问题")
                }
                return
            }
            if status.status == "running" {
                // POST 可能已成功但响应丢失；无 pending clarify 表示 Run 已继续。
                acceptClarifySubmission(
                    messageId: messageId,
                    requestId: requestId,
                    sessionId: sessionId,
                    agentId: agentId,
                    selection: selection
                )
                return
            }
            setClarifyState(messageIndex: idx, state: .expired, selection: selection)
            commitSession()
            showToast("确认已过期，请确认后恢复任务")
        } catch {
            setClarifyState(messageIndex: idx, state: .pending, selection: selection)
            commitSession()
            showToast("网络状态不确定，未重复执行；请重试确认")
        }
    }

    private func startRecoveredRunMonitor(
        requestId: String,
        sessionId: String,
        agentId: String?,
        outputMessageId: String
    ) {
        statusPollTask?.cancel()
        statusPollTask = Task { @MainActor [weak self] in
            guard let self else { return }
            var attempts = 0
            // Bridge watchdog 的服务端上限为 720s；monitor 覆盖完整窗口，避免长调研在 3 分钟处假中断。
            while attempts < 360 && !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                guard !Task.isCancelled else { return }
                do {
                    let status = try await APIClient.shared.fetchChatStatus(
                        sessionId: sessionId, agentId: agentId
                    )
                    if status.status == "completed", let answer = status.answer, !answer.isEmpty {
                        if let idx = self.messages.firstIndex(where: { $0.id == outputMessageId }) {
                            self.messages[idx].content = answer
                            self.messages[idx].pending = false
                            self.messages[idx].isStreaming = false
                            self.messages[idx].blocks = []
                        }
                        self.commitSession()
                        if self.inflight?.id == requestId { self.finishGeneration() }
                        return
                    }
                    if let pending = status.clarify {
                        let block = ClarifyBlock(
                            clarifyId: pending.clarifyId,
                            requestId: pending.requestId ?? requestId,
                            sessionId: sessionId,
                            agentId: agentId,
                            expiresInSeconds: pending.expiresInSeconds,
                            question: pending.question,
                            choices: pending.choices,
                            multiSelect: pending.multiSelect,
                            source: "bridge"
                        )
                        if let idx = self.messages.firstIndex(where: { $0.id == outputMessageId }) {
                            if !self.messages[idx].blocks.contains(where: {
                                if case .clarify(let existing) = $0 { return existing.id == block.id }
                                return false
                            }) {
                                self.messages[idx].blocks.append(.clarify(block))
                            }
                            self.messages[idx].pending = false
                            self.messages[idx].isStreaming = false
                        }
                        self.streamOutputMessageIds[requestId] = outputMessageId
                        self.commitSession()
                        return
                    }
                    if ["timeout", "not_found"].contains(status.status) {
                        if let idx = self.messages.firstIndex(where: { $0.id == outputMessageId }) {
                            self.messages[idx].role = .interrupted
                            self.messages[idx].content = "任务已中断，可确认后恢复"
                            self.messages[idx].isStreaming = false
                        }
                        self.commitSession()
                        if self.inflight?.id == requestId { self.finishGeneration() }
                        return
                    }
                } catch {
                    // 短暂网络错误继续对账，不启动第二个 Run。
                }
                attempts += 1
            }
        }
    }

    private func markClarifyExpired(clarifyId: String?) {
        guard let idx = messages.lastIndex(where: { message in
            guard let block = message.clarifyBlock else { return false }
            return clarifyId == nil || block.clarifyId == clarifyId
        }) else { return }
        setClarifyState(messageIndex: idx, state: .expired)
        commitSession()
        showToast("确认等待已超时，可确认后恢复任务")
    }

    public func recoverExpiredClarify(messageId: String) {
        guard let idx = messages.firstIndex(where: { $0.id == messageId }),
              let block = messages[idx].clarifyBlock,
              block.submissionState == .expired,
              let userIdx = messages[..<idx].lastIndex(where: { $0.role == .user }) else { return }
        let prompt = messages[userIdx].content
        let quote = messages[userIdx].quotedContext
        let sid = block.sessionId ?? sessionManager.activeSessionID()
        let agentId = block.agentId ?? appState?.selectedAgentId
        let requestId = block.requestId ?? messageId
        clarifySubmissionTask?.cancel()
        clarifySubmissionTask = Task { [weak self] in
            guard let self else { return }
            do {
                let status = try await APIClient.shared.fetchChatStatus(
                    sessionId: sid, agentId: agentId
                )
                if status.status == "completed", let answer = status.answer, !answer.isEmpty {
                    self.messages.append(ChatMessage(sessionId: sid, role: .assistant, content: answer))
                    self.commitSession()
                    self.finishGeneration()
                    return
                }
                if let pending = status.clarify, pending.clarifyId == block.clarifyId {
                    self.setClarifyState(messageIndex: idx, state: .pending)
                    self.commitSession()
                    self.showToast("服务端仍在等待，请再次确认")
                    return
                }
                if status.status == "running" {
                    self.isGenerating = true
                    self.inflight = InFlightRequest(
                        id: requestId, sessionId: sid, text: prompt, quote: quote, agentId: agentId
                    )
                    self.startRecoveredRunMonitor(
                        requestId: requestId,
                        sessionId: sid,
                        agentId: agentId,
                        outputMessageId: messageId
                    )
                    self.showToast("原任务仍在后台运行，已恢复跟踪")
                    return
                }
                guard Self.statusAllowsRegenerate(status.status) else {
                    self.showToast("服务端状态尚未收敛，未重复执行")
                    return
                }
            } catch {
                // 网络不确定时绝不能创建第二个 Run；让用户稍后再次对账。
                self.showToast("无法确认服务器状态，未重复执行")
                return
            }
            // 只有服务端明确无可恢复 Run 时才由用户这次点击触发 regenerate。
            // 不 cancel 旧 SSE，避免其延迟 cancel 请求跨代杀死刚创建的新 Run。
            self.statusPollTask?.cancel()
            self.isGenerating = false
            self.inflight = nil
            if let currentIdx = self.messages.firstIndex(where: { $0.id == messageId }) {
                self.messages.removeSubrange(currentIdx...)
            }
            self.commitSession()
            self.startGeneration(text: prompt, quote: quote, regenerate: true)
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
        let totalCount = answer.count
        guard totalCount > 0 else {
            messages[idx].isStreaming = false
            return
        }
        let batchSize = ChatStreamingPerformancePolicy.typewriterBatchSize(
            totalCharacterCount: totalCount
        )
        var shown = 0
        while shown < totalCount {
            shown = min(shown + batchSize, totalCount)
            let end = answer.index(answer.startIndex, offsetBy: shown)
            messages[idx].content = String(answer[..<end])
            if shown < totalCount {
                try? await Task.sleep(
                    nanoseconds: ChatStreamingPerformancePolicy.typewriterDelayNanoseconds
                )
            }
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
        guard let req = inflight else { return }
        // 显式停止是唯一会触发 Bridge cancel/interrupt 的客户端路径。
        tenantEpoch += 1
        currentChatTask?.cancel()
        currentChatTask = nil
        stopStatusPolling()
        markCancelled(req: req)
        Task {
            try? await APIClient.shared.cancelStream(
                sessionId: req.sessionId, agentId: req.agentId
            )
        }
    }

    public func cancelQueued(_ id: String) {
        pendingQueue.removeAll { $0.id == id }
    }

    nonisolated static func statusAllowsRegenerate(_ status: String) -> Bool {
        ["timeout", "not_found"].contains(status)
    }

    /// 重新生成先对账 server-side Run：completed 回填，running 恢复同一 request 的 monitor；
    /// 只有 Bridge 明确返回 timeout/not_found 时才携带 regenerate=true 创建新 Run。
    public func retryMessage(_ messageId: String) {
        guard !isGenerating else { return }
        guard let idx = messages.firstIndex(where: { $0.id == messageId }) else { return }
        let sid = sessionManager.activeSessionID()
        let visibleUser = messages[..<idx].last(where: { $0.role == .user })
        guard let userMessage = visibleUser
            ?? sessionManager.previousUserMessage(before: messageId, sessionId: sid) else { return }
        let agentId = sessionManager.agentId(for: sid)

        guard APIClient.shared.currentToken() != nil else {
            showToast("需要登录后继续会话，请先登录")
            return
        }

        isGenerating = true // 防止重复点击并发探测/重跑
        statusPollTask?.cancel()
        statusPollTask = Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                let status = try await APIClient.shared.fetchChatStatus(
                    sessionId: sid, consume: true, agentId: agentId
                )
                guard !Task.isCancelled else { return }
                if status.status == "completed", let answer = status.answer, !answer.isEmpty {
                    self.applyRecoveredAnswer(answer, outputMessageId: messageId)
                    self.isGenerating = false
                    return
                }
                if status.status == "running" {
                    let req = InFlightRequest(
                        id: messageId, sessionId: sid, text: userMessage.content,
                        quote: userMessage.quotedContext, agentId: agentId
                    )
                    self.inflight = req
                    self.streamOutputMessageIds[req.id] = messageId
                    if let currentIdx = self.messages.firstIndex(where: { $0.id == messageId }) {
                        self.messages[currentIdx].role = .assistant
                        self.messages[currentIdx].pending = true
                        self.messages[currentIdx].isStreaming = true
                        self.messages[currentIdx].degraded = false
                    }
                    self.commitSession()
                    self.startRecoveredRunMonitor(
                        requestId: req.id, sessionId: sid,
                        agentId: agentId, outputMessageId: messageId
                    )
                    self.showToast("原任务仍在后台运行，已恢复跟踪")
                    return
                }
                guard Self.statusAllowsRegenerate(status.status) else {
                    self.isGenerating = false
                    self.showToast("服务端状态尚未收敛，未重复执行")
                    return
                }
            } catch {
                self.isGenerating = false
                self.showToast("无法确认服务器状态，未重复执行")
                return
            }

            // 仅服务端明确无可恢复 Run 时才重跑，避免覆盖 detached run 的 user key。
            self.isGenerating = false
            self.sessionManager.truncateMessages(from: messageId, sessionId: sid)
            if let currentIdx = self.messages.firstIndex(where: { $0.id == messageId }) {
                self.messages.removeSubrange(currentIdx...)
            }
            self.hasNewerMessages = false
            self.isLatestPage = true
            self.startGeneration(
                text: userMessage.content, quote: userMessage.quotedContext, regenerate: true
            )
        }
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
        startGeneration(
            text: next.text,
            quote: next.quote,
            contextScope: next.contextScope,
            clientSessionContext: next.clientSessionContext
        )
    }

    public func handleNoteDraftAction(
        messageId: String?, draftId: String, action: String
    ) {
        guard let messageIndex = messages.firstIndex(where: { $0.id == messageId }),
              let blockIndex = messages[messageIndex].blocks.firstIndex(where: {
                  if case .noteDraft(let draft) = $0 { return draft.id == draftId }
                  return false
              }), case .noteDraft(var draft) = messages[messageIndex].blocks[blockIndex],
              draft.state == .awaitingConfirmation else { return }
        if action == "discard" {
            draft.state = .discarded
            messages[messageIndex].blocks[blockIndex] = .noteDraft(draft)
            commitSession()
            return
        }
        guard draft.accountScope == nil || draft.accountScope == KnowledgeNoteStore.shared.accountFingerprint else {
            showToast("账号已切换，不能保存其他账号的笔记草稿")
            return
        }
        let shouldMerge = action == "merge"
        let noteTitle = shouldMerge ? (draft.mergedTitle ?? draft.title) : draft.title
        let noteMarkdown = shouldMerge ? (draft.mergedMarkdown ?? draft.markdown) : draft.markdown
        let noteTags = shouldMerge ? (draft.mergedTags ?? draft.tags) : draft.tags
        guard !shouldMerge || (draft.mergeCandidates?.isEmpty == false && draft.mergedMarkdown?.isEmpty == false) else {
            showToast("合并稿不可用，请保存为新笔记")
            return
        }
        guard appState?.isLoggedIn == true else {
            showToast("请先登录后再保存笔记")
            return
        }
        let note: KnowledgeNote?
        if draft.isUpdate, let targetId = draft.targetNoteId {
            guard let existing = KnowledgeNoteStore.shared.note(id: targetId) else {
                showToast("目标笔记已不存在，无法应用修改")
                return
            }
            if let expectedHash = draft.targetContentHash,
               KnowledgeNoteStore.shared.contentHash(for: existing) != expectedHash {
                showToast("笔记内容已变化，请重新生成完善方案")
                return
            }
            note = KnowledgeNoteStore.shared.save(
                id: targetId,
                title: noteTitle,
                body: noteMarkdown,
                tags: noteTags,
                isPinned: existing.isPinned
            )
        } else {
            note = KnowledgeNoteStore.shared.createNote(
                title: noteTitle, body: noteMarkdown, tags: noteTags
            )
        }
        guard let note else {
            showToast("无法保存笔记，请检查本地存储")
            return
        }
        draft.state = .savedLocally
        draft.savedNoteId = note.id
        messages[messageIndex].blocks[blockIndex] = .noteDraft(draft)
        commitSession()
        let archivedNotes: [KnowledgeNote]
        if shouldMerge {
            archivedNotes = (draft.mergeCandidates ?? []).compactMap { candidate in
                KnowledgeNoteStore.shared.archive(id: candidate.id, mergedInto: note.id)
            }
            showToast("已合并，并将 \(archivedNotes.count) 篇旧笔记归档")
        } else {
            archivedNotes = []
        }
        if draft.isUpdate {
            showToast("已更新原笔记")
        } else if action == "edit" {
            appState?.activeTab = 2
            showToast("已保存到本地，可在笔记页继续编辑")
        }
        let expectedEpoch = tenantEpoch
        Task { [weak self] in
            do {
                try await APIClient.shared.syncKnowledgeNote(
                    id: note.id,
                    markdown: KnowledgeNoteStore.shared.markdown(for: note),
                    updatedAt: note.updatedAt
                )
                for archived in archivedNotes {
                    try await APIClient.shared.syncKnowledgeNote(
                        id: archived.id,
                        markdown: KnowledgeNoteStore.shared.markdown(for: archived),
                        updatedAt: archived.updatedAt
                    )
                    try await APIClient.shared.archiveKnowledgeNote(
                        id: archived.id, mergedIntoNoteId: note.id
                    )
                }
                guard let self, self.tenantEpoch == expectedEpoch,
                      let currentMessageIndex = self.messages.firstIndex(where: { $0.id == messageId }),
                      let currentBlockIndex = self.messages[currentMessageIndex].blocks.firstIndex(where: {
                          if case .noteDraft(let value) = $0 { return value.id == draftId }
                          return false
                      }), case .noteDraft(var currentDraft) = self.messages[currentMessageIndex].blocks[currentBlockIndex] else { return }
                currentDraft.state = .saved
                self.messages[currentMessageIndex].blocks[currentBlockIndex] = .noteDraft(currentDraft)
                self.commitSession()
            } catch {
                self?.showToast("笔记已保存到本地，稍后可重试同步")
            }
        }
    }

    public func handleKnowledgeAction(messageId: String?, actionId: String, verb: String) {
        guard let messageIndex = messages.firstIndex(where: { $0.id == messageId }),
              let blockIndex = messages[messageIndex].blocks.firstIndex(where: {
                  if case .knowledgeAction(let item) = $0 { return item.id == actionId }
                  return false
              }), case .knowledgeAction(var action) = messages[messageIndex].blocks[blockIndex]
        else { return }
        if verb == "open" {
            if var target = action.suggestedNavigation, target.noteId == nil {
                target = KnowledgeNavigationTarget(
                    destination: target.destination,
                    noteId: action.resultNoteIds.first,
                    query: target.query
                )
                appState?.pendingKnowledgeNavigation = target
            } else {
                appState?.pendingKnowledgeNavigation = action.suggestedNavigation
            }
            appState?.activeTab = 2
            return
        }
        let retryableStates: Set<KnowledgeActionState> = [.proposed, .localApplied, .syncPending]
        guard retryableStates.contains(action.state) else { return }
        if verb == "discard", action.state != .proposed { return }
        action.state = verb == "discard" ? .proposed : .applying
        messages[messageIndex].blocks[blockIndex] = .knowledgeAction(action)
        commitSession()
        let expectedEpoch = tenantEpoch
        Task { [weak self] in
            let result = verb == "discard"
                ? await KnowledgeActionExecutor.shared.discard(action)
                : await KnowledgeActionExecutor.shared.execute(action)
            guard let self, self.tenantEpoch == expectedEpoch,
                  let currentMessageIndex = self.messages.firstIndex(where: { $0.id == messageId }),
                  let currentBlockIndex = self.messages[currentMessageIndex].blocks.firstIndex(where: {
                      if case .knowledgeAction(let item) = $0 { return item.id == actionId }
                      return false
                  }), case .knowledgeAction(var current) = self.messages[currentMessageIndex].blocks[currentBlockIndex]
            else { return }
            current.state = result.state
            current.resultNoteIds = result.noteIds
            current.errorMessage = result.message
            self.messages[currentMessageIndex].blocks[currentBlockIndex] = .knowledgeAction(current)
            self.commitSession()
            if let message = result.message { self.showToast(message) }
            else if result.state == .synced { self.showToast("知识操作已应用并同步") }
            if result.state == .synced {
                let organizerId = self.sessionManager.activeSessionID()
                let sources = self.sessionManager.organizationSources(for: organizerId)
                if !sources.isEmpty {
                    self.sessionManager.markOrganized(sources)
                    self.pendingOrganizationDisposition = sources
                }
            }
            if result.state == .synced,
               self.sessionManager.topicSessions[self.sessionManager.activeSessionID()]?.state == .ending {
                self.sessionManager.finishTopic(self.sessionManager.activeSessionID())
            }
        }
    }

    public func applyOrganizationDisposition(_ status: SessionLifecycleStatus?) {
        let sources = pendingOrganizationDisposition
        pendingOrganizationDisposition = []
        guard let status else {
            showToast("来源会话已保留")
            return
        }
        for id in sources { sessionManager.setLifecycle(status, for: id) }
        showToast(status == .archived ? "来源会话已归档" : "来源会话已移入回收站")
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
