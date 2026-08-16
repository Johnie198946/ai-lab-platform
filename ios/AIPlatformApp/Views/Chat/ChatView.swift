//
//  ChatView.swift
//  AIPlatformApp
//
//  Streaming Agent Conversation View with TextKit2-Style Markdown Bubbles & Quoted Follow-Ups
//  真实后端对接：POST /api/chat + 真实思维链折叠卡 + 排队/取消/超时/404 幂等自愈完整状态机
//

import SwiftUI

public struct ChatView: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.scenePhase) private var scenePhase

    @State private var messages: [ChatMessage] = []
    @State private var inputText: String = ""
    @State private var quickCommands: [String] = []
    @State private var quotedContext: QuotedContext? = nil
    @State private var isShowingClearAlert: Bool = false
    @State private var isGenerating: Bool = false
    @State private var showingVoiceInput: Bool = false
    @State private var showingPlusMenu: Bool = false
    @State private var showingSessionDrawer: Bool = false
    @StateObject private var speechService = SpeechRecognizerService()
    @ObservedObject private var sessionManager = SessionManager.shared

    // MARK: - 状态机字段（真实后端对接）
    @State private var inflight: InFlightRequest? = nil       // 当前 in-flight（思考/超时/错误占位）
    @State private var pendingQueue: [PendingItem] = []       // 排队消息（上限 3）
    @State private var waitingSeconds: Int = 0                // 「已等待 N 秒」本地计时
    @State private var currentChatTask: Task<Void, Never>? = nil
    /// 思维链逐步揭示动画任务表（按消息 ID 隔离，defer 自清理，切换会话安全取消）
    @State private var animationTasks: [String: Task<Void, Never>] = [:]
    @State private var toastMessage: String? = nil
    @State private var demoMode: Bool = false                 // 网络错误后「切换演示模式」
    @State private var liveProgress: String? = nil            // 长任务轮询拉取的最新步骤
    @State private var statusPollTask: Task<Void, Never>? = nil  // 320s 指数退避轮询任务
    /// 真实 status 分相（bridge boot/reasoning）：只驱动 ThinkingPlaceholder 文案，不解除 pending（R-3 铁律）
    @State private var thinkingPhase: String? = nil
    @State private var thinkingDetail: String? = nil

    private let waitingTimer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    public init() {}

    public var body: some View {
        NavigationStack {
            ZStack {
                AppTheme.Colors.groupedBackground
                    .ignoresSafeArea()

                VStack(spacing: 0) {
                    // MARK: - 1. Session Top Bar（Quantum 球体 + 会话标题 + 新建/历史）
                    sessionTopBar

                    Divider()
                        .background(AppTheme.Colors.border)

                    // MARK: - 2. Scrollable Messages Stream
                    messagesList

                    // MARK: - 3. Suggestion Chips Bar
                    suggestionChipsBar

                    // MARK: - 4. Quoted Context Banner (if active)
                    if let quote = quotedContext {
                        quotedFollowUpBanner(quote: quote)
                    }

                    // MARK: - 5. Bottom Input Bar
                    bottomInputBar
                }
            }
            .navigationTitle("")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: { isShowingClearAlert = true }) {
                        Image(systemName: "trash")
                            .font(.system(size: 14))
                            .foregroundColor(AppTheme.Colors.textSecondary)
                    }
                }
            }
            .alert("清空当前对话？", isPresented: $isShowingClearAlert) {
                Button("取消", role: .cancel) {}
                Button("清空", role: .destructive) { clearMessages() }
            } message: {
                Text("此操作将清空当前会话所有消息记录。")
            }
            .overlay(alignment: .bottom) { toastOverlay }
            .animation(.easeInOut(duration: 0.2), value: toastMessage)
            .onAppear {
                restoreActiveSession()
                refreshQuickCommands()
                handlePendingPrompt()
            }
            .onChange(of: appState.pendingChatPrompt) { _, _ in handlePendingPrompt() }
            .onReceive(waitingTimer) { _ in tickWaitingTimer() }
            .sheet(isPresented: $showingVoiceInput) { voiceSheet }
            .sheet(isPresented: $showingPlusMenu) { plusSheet }
            .sheet(isPresented: $showingSessionDrawer) { sessionDrawerSheet }
            .onChange(of: scenePhase) { _, phase in
                if phase == .active {
                    InboxFileManager.shared.cleanupStaleInboxFiles()
                }
            }
        }
    }

    private var messagesList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: AppTheme.Spacing.md) {
                    ForEach(messages) { message in
                        messageRow(message)
                            .id(message.id)
                    }

                    // 排队占位（实时序号）
                    ForEach(Array(pendingQueue.enumerated()), id: \.element.id) { index, item in
                        PendingPlaceholderView(
                            position: index + 1,
                            onCancel: { cancelQueued(item.id) }
                        )
                        .id("pending_\(item.id)")
                    }
                }
                .padding(.vertical, AppTheme.Spacing.md)
            }
            .onChange(of: messages.count) { _, _ in scrollToLatest(proxy) }
            .onChange(of: pendingQueue.count) { _, _ in scrollToLatest(proxy) }
            .onChange(of: inflight?.id) { _, _ in scrollToLatest(proxy) }
        }
    }

    /// 单条消息分发渲染：.interrupted / degraded / pending 占位 / 常规气泡四态。
    @ViewBuilder
    private func messageRow(_ message: ChatMessage) -> some View {
        if message.role == .interrupted {
            InterruptedCardView(onRetry: { retryMessage(message.id) })
        } else if message.degraded {
            DegradedCardView(onRetry: { retryMessage(message.id) })
        } else if message.pending && message.role == .assistant {
            if let req = inflight, req.id == message.id {
                inflightPlaceholder(req)
            } else {
                OrphanPendingCardView(onRetry: { retryMessage(message.id) })
            }
        } else if let clarify = message.clarifyBlock {
            // 澄清选项卡片：点选后回调 sendClarifySelection 提交
            ClarifyCard(
                block: clarify,
                onSubmit: { selection in
                    sendClarifySelection(messageId: message.id, selection: selection)
                }
            )
        } else {
            MessageBubbleView(
                message: message,
                onQuoteFollowUp: { quote in
                    withAnimation(.spring()) { self.quotedContext = quote }
                },
                onRegenerate: { messageId in regenerate(messageId: messageId) }
            )
        }
    }

    /// 澄清卡片提交：按来源分流——
    /// - bridge 澄清（Hermes clarify 工具）：submitClarify 解锁阻塞中的 agent 线程；
    /// - preclassified 澄清（本地规则预分诊卡片）：无 agent 在等，直接发起新一轮对话推进。
    private func sendClarifySelection(messageId: String, selection: String) {
        guard let idx = messages.firstIndex(where: { $0.id == messageId }) else { return }
        let sessionId = sessionManager.activeSessionID()
        var source = "bridge"
        // 1) 原卡片置为已提交（禁用重复点选）——直接改 blocks 数组内的关联值
        if let blockIdx = messages[idx].blocks.firstIndex(where: {
            if case .clarify = $0 { return true }
            return false
        }) {
            if case .clarify(var c) = messages[idx].blocks[blockIdx] {
                source = c.source
                c.markSubmitted(selection: selection)
                messages[idx].blocks[blockIdx] = .clarify(c)
            }
        }
        commitSession()
        // 2) 回填用户选择消息（视觉一致）
        messages.append(ChatMessage(
            sessionId: sessionId,
            role: .user,
            content: selection
        ))
        commitSession()

        // 3) 按来源分流
        if source == "preclassified" {
            // 本地预分诊卡片：没有 agent 在等 → 把选择作为新消息发起真实对话（agent 接手 Gate-by-Gate）
            if !isGenerating {
                startGeneration(text: selection, quote: nil)
            } else {
                // 理论不会发生（预分诊流已结束 isGenerating=false），兜底直接排队
                pendingQueue.append(PendingItem(id: UUID().uuidString, text: selection, quote: nil))
            }
            return
        }

        // bridge 澄清：使用当前活动会话 ID 提交到澄清端点解锁 agent（严禁使用未初始化的 nil）
        // 会话单源：req.inflight.sessionId → activeSessionID()（appState.chatSessionId 已废除）
        let resolvedSessionId = inflight?.sessionId ?? sessionId

        Task {
            var submitSuccess = false
            // 带 3 次轻量重试机制（防偶发网络抖动）
            for attempt in 0..<3 {
                do {
                    let ok = try await APIClient.shared.submitClarify(sessionId: resolvedSessionId, response: selection)
                    if ok {
                        submitSuccess = true
                        break
                    }
                } catch {
                    // 稍作等待后重试
                    try? await Task.sleep(nanoseconds: UInt64((attempt + 1) * 300_000_000))
                }
            }

            if !submitSuccess {
                // 解锁失败兜底：卡片恢复可交互态，绝不假死锁入队
                await MainActor.run {
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
                    showToast("选项提交失败，请点击重试")
                }
            }
        }
    }

    @ViewBuilder
    private var toastOverlay: some View {
        if let toast = toastMessage {
            toastView(toast)
                .transition(.move(edge: .bottom).combined(with: .opacity))
                .padding(.bottom, 90)
        }
    }

    private var voiceSheet: some View {
        VoiceInputView(
            service: speechService,
            onTranscript: { text in inputText = text },
            onDismiss: { showingVoiceInput = false }
        )
    }

    private var plusSheet: some View {
        PlusMenuSheet(
            onPhotoPicked: { data in attachPhoto(data) },
            onDocumentPicked: { url in attachDocument(url) },
            onWeChatImported: { link in importWeChatLink(link) },
            onKnowledgeReferenced: { item in referenceKnowledge(item) }
        )
    }

    private func tickWaitingTimer() {
        if let inf = inflight, inf.phase == .thinking {
            waitingSeconds += 1
        }
    }

    private func clearMessages() {
        cancelAllReveals()
        messages.removeAll()
        commitSession()
    }

    // MARK: - Subviews

    // MARK: - Session 顶栏（Quantum 球体 + 会话标题 + 新建/历史）

    private var sessionTopBar: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            // 左侧 Quantum 球体 + 状态点
            ZStack(alignment: .bottomTrailing) {
                QuantumAvatarView(size: 30)
                Circle()
                    .fill(statusDotColor)
                    .frame(width: 9, height: 9)
                    .overlay(Circle().stroke(AppTheme.Colors.cardBackground, lineWidth: 1.5))
            }

            // 中间：当前会话标题 + chevron.down（触发会话抽屉）
            Button(action: { showingSessionDrawer = true }) {
                HStack(spacing: 4) {
                    Text(currentSessionTitle)
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                        .lineLimit(1)
                    Image(systemName: "chevron.down")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(AppTheme.Colors.textTertiary)
                }
            }
            .buttonStyle(SoftButtonStyle())

            Spacer()

            // 右侧：新建会话 + 历史会话
            Button(action: newSession) {
                Image(systemName: "square.and.pencil")
                    .font(.system(size: 15))
                    .foregroundColor(AppTheme.Colors.textSecondary)
            }
            .buttonStyle(SoftButtonStyle())

            Button(action: { showingSessionDrawer = true }) {
                Image(systemName: "clock.arrow.circlepath")
                    .font(.system(size: 15))
                    .foregroundColor(AppTheme.Colors.textSecondary)
            }
            .buttonStyle(SoftButtonStyle())
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.sm)
        .background(AppTheme.Colors.cardBackground)
    }

    private var statusDotColor: Color {
        isGenerating ? AppTheme.Colors.statusRunning : AppTheme.Colors.quantumCyan
    }

    private var currentSessionTitle: String {
        sessionManager.title(for: sessionManager.activeSessionID())
    }

    /// 会话抽屉：多会话切换（updatedAt 倒序）+ 新建 + 删除（本地级联清理）。
    private var sessionDrawerSheet: some View {
        SessionDrawerSheet(
            sessionManager: sessionManager,
            onSelect: { id in switchSession(to: id) },
            onNew: { newSession() },
            onDelete: { id in deleteSessionAndMaybeSwitch(id) }
        )
    }

    /// 按所选 Agent 动态生成的默认预设 Chip（冷启动兜底，点击填入输入框）。
    private var defaultChips: [String] {
        switch appState.selectedAgentId {
        case "supervision":
            return ["🔍 审查这份架构方案的风险点", "📋 出具执行硬锁批复", "🧪 核对后端契约测试"]
        case "coder":
            return ["💻 实现一个 FastAPI 路由", "🔧 修复网络超时与降级", "✅ 跑通后端 pytest"]
        case "knowledge":
            return ["📚 检索最新竞品动态", "🧠 知识入库并打三标签", "🔒 订阅受限知识分类"]
        default:
            return ["📝 撰写一份问题报告", "🤝 分诊任务并派发执行", "📊 生成周度总结"]
        }
    }

    // MARK: - 会话动作（持久化 / 切换 / 屏障 / 重试）

    private func restoreActiveSession() {
        let sid = sessionManager.activeSessionID()
        messages = sessionManager.messages(for: sid)
    }

    /// 将当前视图 messages 写回 SessionManager（消息级原子落盘）。
    private func commitSession() {
        let sid = sessionManager.activeSessionID()
        sessionManager.setMessages(messages, for: sid)
    }

    /// 新建会话：新 UUID + 保留后台在途（Hermes 式：任务继续跑完写归属会话）+ 清当前视图状态。
    private func newSession() {
        commitSession()
        // 不中断在途任务：Hermes 式后台完成，结果落盘到原会话；切回可看
        stopStatusPolling()
        sessionManager.createSession()
        messages = []
        pendingQueue.removeAll()
        isGenerating = false
        // 保留 inflight/currentChatTask 引用让后台任务跑完（回调按 sessionId 归属写盘）
        waitingSeconds = 0
        inputText = ""
        quotedContext = nil
        showingSessionDrawer = false
    }

    private func switchSession(to id: String) {
        guard id != sessionManager.activeSessionId else {
            showingSessionDrawer = false
            return
        }
        commitSession()
        // 不中断在途任务（Hermes 式后台完成）；进度轮询仅对活跃会话有意义，先停
        stopStatusPolling()
        sessionManager.switchTo(id)
        messages = sessionManager.messages(for: id)
        pendingQueue.removeAll()
        isGenerating = false
        waitingSeconds = 0
        inputText = ""
        quotedContext = nil
        showingSessionDrawer = false
        // 切回原会话时：若该会话仍有在途任务（pending 占位），恢复生成态与进度轮询
        if let inflight,
           inflight.sessionId == id,
           messages.contains(where: { $0.id == inflight.id && $0.pending }) {
            isGenerating = true
            startStatusPolling(req: inflight)
        }
    }

    /// 删除会话：本地级联清理；若删除的是 active，切到剩余最新会话。
    private func deleteSessionAndMaybeSwitch(_ id: String) {
        sessionManager.deleteSession(id)
        if sessionManager.activeSessionId != nil {
            messages = sessionManager.messages(for: sessionManager.activeSessionID())
        }
        // 若被删的是当前活跃会话且已有新 active，重置视图状态
        if !isGenerating || inflight == nil {
            pendingQueue.removeAll()
            inputText = ""
            quotedContext = nil
        }
    }

    /// 取消在途请求并在其原会话（req.sessionId）落盘 .interrupted 标记（不静默丢弃）。
    private func abandonInFlight() {
        // 无论 inflight 是否已清空（响应已到、思维链揭示中），都先取消在途揭示动画
        cancelAllReveals()
        stopStatusPolling()
        guard let req = inflight else { return }
        currentChatTask?.cancel()
        sessionManager.markInterrupted(sessionId: req.sessionId)
        inflight = nil
        isGenerating = false
        currentChatTask = nil
        waitingSeconds = 0
    }

    /// 重试：重发 preceding user 提问，成功原地替换（不追加）degraded/interrupted 卡。
    private func retryMessage(_ messageId: String) {
        guard !isGenerating else { return }
        guard let idx = messages.firstIndex(where: { $0.id == messageId }) else { return }
        guard let userIdx = messages[..<idx].lastIndex(where: { $0.role == .user }) else { return }
        let prompt = messages[userIdx].content
        let quote = messages[userIdx].quotedContext
        // 移除降级/中断卡，重发（startGeneration 会追加新 pending 占位，成功替换不重复）
        messages.remove(at: idx)
        commitSession()
        startGeneration(text: prompt, quote: quote)
    }

    // MARK: - 快捷指令（本地滑动窗口 Top3 + 冷启动兜底，需求1）

    private func computeQuickCommands() -> [String] {
        let defaults = defaultChips
        let ranked = QuickCommandTracker.shared.rankedCommands()
        var result: [String] = []
        for (cmd, _) in ranked where !result.contains(cmd) && result.count < 3 {
            result.append(cmd)
        }
        for d in defaults where !result.contains(d) && result.count < 3 {
            result.append(d)
        }
        return result
    }

    private func refreshQuickCommands() {
        quickCommands = computeQuickCommands()
    }

    private var suggestionChipsBar: some View {
        VStack(spacing: 2) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: AppTheme.Spacing.xs) {
                    ForEach(quickCommands, id: \.self) { chip in
                        Button(action: {
                            // 本地记录使用频次（滑动窗口），再填充并发送（需求1）
                            QuickCommandTracker.shared.record(chip)
                            refreshQuickCommands()
                            inputText = chip
                            sendMessage()
                        }) {
                            Text(chip)
                                .font(.system(size: 12))
                                .foregroundColor(AppTheme.Colors.textSecondary)
                                .padding(.horizontal, AppTheme.Spacing.sm + 2)
                                .padding(.vertical, 4)
                                .background(AppTheme.Colors.cardBackground)
                                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
                                .overlay(
                                    RoundedRectangle(cornerRadius: AppTheme.Radius.sm)
                                        .stroke(AppTheme.Colors.border, lineWidth: 0.5)
                                )
                        }
                        .buttonStyle(SoftButtonStyle())
                    }
                }
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, AppTheme.Spacing.xs)
            }
            // 隐私标注：快捷指令仅本地计算（需求1）
            HStack(spacing: 4) {
                Image(systemName: "lock.fill")
                    .font(.system(size: 9))
                Text("仅本地计算 · 保护隐私")
                    .font(.system(size: 10))
            }
            .foregroundColor(AppTheme.Colors.textTertiary)
            .padding(.bottom, 2)
        }
    }

    private func quotedFollowUpBanner(quote: QuotedContext) -> some View {
        HStack {
            Image(systemName: "quote.bubble.fill")
                .foregroundColor(AppTheme.Colors.primary)
                .font(.system(size: 14))

            VStack(alignment: .leading, spacing: 2) {
                Text("引用追问中")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(AppTheme.Colors.primary)
                Text(quote.text)
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                    .lineLimit(1)
            }

            Spacer()

            Button(action: {
                withAnimation(.spring()) {
                    quotedContext = nil
                }
            }) {
                Image(systemName: "xmark.circle.fill")
                    .foregroundColor(AppTheme.Colors.textTertiary)
                    .font(.system(size: 16))
            }
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, 6)
        .background(AppTheme.Colors.primary.opacity(0.08))
        .transition(.move(edge: .bottom).combined(with: .opacity))
    }

    private var bottomInputBar: some View {
        HStack(alignment: .bottom, spacing: AppTheme.Spacing.sm) {
            Button(action: {
                #if os(iOS)
                UIImpactFeedbackGenerator(style: .light).impactOccurred()
                #endif
                InboxFileManager.shared.cleanupStaleInboxFiles()
                showingPlusMenu = true
            }) {
                Image(systemName: "plus.circle.fill")
                    .font(.system(size: 24))
                    .foregroundColor(AppTheme.Colors.textSecondary)
            }
            .padding(.bottom, 6)

            HStack {
                TextField("发送指令或提出问题...", text: $inputText, axis: .vertical)
                    .lineLimit(1...5)
                    .font(.system(size: 15))
                    .padding(.horizontal, AppTheme.Spacing.sm)
                    .padding(.vertical, 8)

                if !inputText.isEmpty {
                    Button(action: { inputText = "" }) {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 14))
                            .foregroundColor(AppTheme.Colors.textTertiary)
                    }
                    .padding(.trailing, 6)
                }
            }
            .background(AppTheme.Colors.secondaryBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))

            if inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Button(action: {
                    #if os(iOS)
                    UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                    #endif
                    showingVoiceInput = true
                }) {
                    Image(systemName: "mic.fill")
                        .font(.system(size: 18))
                        .foregroundColor(AppTheme.Colors.onPrimary)
                        .frame(width: 36, height: 36)
                        .background(AppTheme.Colors.accent)
                        .clipShape(Circle())
                        .overlay(
                            Circle()
                                .stroke(AppTheme.Colors.quantumCyan.opacity(0.6), lineWidth: 1.5)
                        )
                        .shadow(color: AppTheme.Colors.quantumCyan.opacity(0.55), radius: 8, x: 0, y: 0)
                }
                .buttonStyle(SoftButtonStyle())
                .padding(.bottom, 2)
            } else {
                Button(action: sendMessage) {
                    Image(systemName: "arrow.up")
                        .font(.system(size: 16, weight: .bold))
                        .foregroundColor(AppTheme.Colors.onPrimary)
                        .frame(width: 36, height: 36)
                        .background(AppTheme.Colors.quantumGradient)
                        .clipShape(Circle())
                }
                .buttonStyle(SoftButtonStyle())
                .padding(.bottom, 2)
            }
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.sm)
        .background(AppTheme.Colors.cardBackground)
    }

    // MARK: - In-flight / Pending 占位渲染

    @ViewBuilder
    private func inflightPlaceholder(_ req: InFlightRequest) -> some View {
        switch req.phase {
        case .thinking:
            ThinkingPlaceholderView(
                seconds: waitingSeconds,
                progress: liveProgress,
                phase: thinkingPhase,
                phaseDetail: thinkingDetail,
                onCancel: { cancelInFlight() }
            )
        case .timeout:
            StatusCardView(
                icon: "exclamationmark.triangle.fill",
                iconColor: AppTheme.Colors.securityYellow,
                title: "长任务超时(300s)",
                message: "任务可能仍在后台处理中，已轮询最新进度。可一键断点续接或继续等待。",
                primary: ("断点续接", { probeAndResumeCurrentInFlight() }),
                secondary: ("继续等待", { retryCurrentInFlight() })
            )
        case .networkError:
            StatusCardView(
                icon: "wifi.exclamationmark",
                iconColor: AppTheme.Colors.securityRed,
                title: "后端不可达",
                message: "无法连接到后端服务，请检查网络或稍后重试。",
                primary: ("重试", { probeAndResumeCurrentInFlight() }),
                secondary: ("切换演示模式", { switchToDemoMode() })
            )
        case .serverError(let msg):
            StatusCardView(
                icon: "xmark.octagon.fill",
                iconColor: AppTheme.Colors.securityRed,
                title: "请求失败",
                message: msg,
                primary: ("重试", { retryCurrentInFlight() }),
                secondary: nil
            )
        }
    }

    private func toastView(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 13, weight: .semibold))
            .foregroundColor(AppTheme.Colors.onPrimary)
            .padding(.horizontal, AppTheme.Spacing.lg)
            .padding(.vertical, AppTheme.Spacing.sm + 2)
            .background(AppTheme.Colors.quantumBlue.opacity(0.95))
            .clipShape(Capsule())
            .shadow(color: Color.black.opacity(0.15), radius: 8, y: 2)
    }

    private func scrollToLatest(_ proxy: ScrollViewProxy) {
        let anchor: String?
        if let last = pendingQueue.last {
            anchor = "pending_\(last.id)"
        } else if let inf = inflight {
            anchor = inf.id
        } else {
            anchor = messages.last?.id
        }
        if let anchor {
            withAnimation(.easeOut(duration: 0.25)) {
                proxy.scrollTo(anchor, anchor: .bottom)
            }
        }
    }

    // MARK: - Actions

    private func handlePendingPrompt() {
        if let prompt = appState.pendingChatPrompt {
            self.inputText = prompt
            appState.pendingChatPrompt = nil
        }
    }

    // MARK: - 发送 / 状态机

    private func sendMessage() {
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

        messages.append(ChatMessage(sessionId: sessionManager.activeSessionID(), role: .user, content: text, quotedContext: quote))
        inputText = ""
        quotedContext = nil
        commitSession()
        dispatchAssistantReply(to: text, quote: quote)
    }

    /// 排队或立即开始（isGenerating 为 true 时入队；否则直接发起真实请求）
    private func dispatchAssistantReply(to text: String, quote: QuotedContext? = nil) {
        if isGenerating {
            pendingQueue.append(PendingItem(id: UUID().uuidString, text: text, quote: quote))
        } else {
            startGeneration(text: text, quote: quote)
        }
    }

    private func startGeneration(text: String, quote: QuotedContext?) {
        isGenerating = true
        waitingSeconds = 0
        thinkingPhase = nil   // 新请求重置真实分相（等待首帧 status 到达）
        thinkingDetail = nil
        let sessionId = sessionManager.activeSessionID()
        let req = InFlightRequest(id: UUID().uuidString, sessionId: sessionId, text: text, quote: quote)
        inflight = req
        // pending 占位消息（响应前 true；成功/降级/中断后 false）
        messages.append(
            ChatMessage(id: req.id, sessionId: sessionId, role: .assistant, content: "", isStreaming: true, pending: true)
        )
        commitSession()
        currentChatTask = Task {
            await runInFlightStreamed(req)
        }
        startStatusPolling(req: req)
    }

    private func runInFlight(_ req: InFlightRequest) async {
        if demoMode {
            await appendDemoReply(req: req)
            return
        }
        do {
            let resp = try await APIClient.shared.chat(
                question: req.text,
                sessionId: req.sessionId,
                quotedContext: req.quote?.text,
                agentId: appState.selectedAgentId
            )
            await handleSuccess(req: req, response: resp)
        } catch {
            await handleError(req: req, error: error)
        }
    }

    /// v7 真实流式入口：SSE 事件逐条驱动 UI（delta 实时追加 / tool 实时卡片 / clarify 实时卡片）。
    /// 流式失败时降级为 runInFlight 非流式路径（体验不劣化）。
    private func runInFlightStreamed(_ req: InFlightRequest) async {
        if demoMode {
            await appendDemoReply(req: req)
            return
        }
        let stream = APIClient.shared.chatStream(
            question: req.text,
            sessionId: req.sessionId,
            agentId: appState.selectedAgentId
        )
        do {
            for try await event in stream {
                guard inflight?.id == req.id else { return }
                guard req.sessionId == sessionManager.activeSessionID() else {
                    sessionManager.markInterrupted(sessionId: req.sessionId)
                    finishGeneration()
                    return
                }
                switch event {
                case .delta(let content):
                    if let idx = messages.firstIndex(where: { $0.id == req.id }) {
                        // 铁律：首个流式事件到达立即解除 pending 占位（防 ThinkingPlaceholder 遮蔽真流式）
                        messages[idx].pending = false
                        messages[idx].content += content
                        messages[idx].isStreaming = true
                        // 收到正文时，将进行中的思考步骤状态置为 done
                        updateReasoningSteps(for: idx) { steps in
                            if let tIdx = steps.firstIndex(where: { $0.type == .thought && $0.status == "running" }) {
                                steps[tIdx].status = "done"
                            }
                        }
                    }
                case .thought(let content):
                    // 实时思考流：累加到唯一的 thought 步骤中（绝不能按 token 产生新步骤）
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
                            // 前序思考步骤置为 done
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
                case .clarify(let question, let choices, let multiSelect, let source):
                    let block = ClarifyBlock(
                        question: question,
                        choices: choices,
                        multiSelect: multiSelect,
                        submitLabel: "确认选择",
                        source: source
                    )
                    if let idx = messages.firstIndex(where: { $0.id == req.id }) {
                        // 思考步骤全部置为 done
                        updateReasoningSteps(for: idx) { steps in
                            for i in steps.indices { steps[i].status = "done" }
                        }
                        var blocks = messages[idx].blocks
                        // 避免重复挂载澄清卡片
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
                    // R-3 铁律：status 仅更新 ThinkingPlaceholder 阶段文案，绝不解除 pending
                    // （占位解除仍以首个 thought/delta 为准，否则 boot 首帧即解除、分相提示失去展示期）
                    thinkingPhase = phase.isEmpty ? nil : phase
                    thinkingDetail = detail.isEmpty ? nil : detail
                case .done(let sid, let answer):
                    if let idx = messages.firstIndex(where: { $0.id == req.id }) {
                        // 完成时所有步骤置为 done
                        updateReasoningSteps(for: idx) { steps in
                            for i in steps.indices { steps[i].status = "done" }
                        }
                        messages[idx].pending = false
                        messages[idx].isStreaming = false
                    }
                case .error(let code, let message):
                    if let idx = messages.firstIndex(where: { $0.id == req.id }) {
                        messages[idx].content = message.isEmpty ? "流式响应异常（\(code)）" : message
                        messages[idx].pending = false
                        messages[idx].isStreaming = false
                        messages[idx].degraded = true
                    }
                }
            }
            commitSession()
            finishGeneration()
        } catch {
            // 流式失败 → 降级非流式（保留既有 502/404 自愈路径）
            if let idx = messages.firstIndex(where: { $0.id == req.id }) {
                messages[idx].content = ""
                messages[idx].blocks = []
            }
            await runInFlight(req)
        }
    }

    /// 取消息当前已挂载的推理步骤（无则空数组）
    private func reasoningSteps(for index: Int) -> [ReasoningStep] {
        guard index < messages.count else { return [] }
        for block in messages[index].blocks {
            if case .reasoning(let steps) = block {
                return steps
            }
        }
        return []
    }

    /// 就地更新消息中的推理步骤（保持 blocks 结构稳定）
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

    private func handleSuccess(req: InFlightRequest, response: ChatResponseDTO) async {
        // 后台任务兜底：inflight 槽已被更新的任务占用（用户在别的会话又发了消息）——
        // 本响应仍按归属会话落盘，绝不丢弃（Hermes 式后台完成）。
        if inflight?.id != req.id {
            sessionManager.applyResponse(sessionId: req.sessionId, requestId: req.id, response: response)
            return
        }

        // 会话感知：响应回来时已切到别的会话 → 结果写原会话（不中断、不丢）
        guard req.sessionId == sessionManager.activeSessionID() else {
            sessionManager.applyResponse(sessionId: req.sessionId, requestId: req.id, response: response)
            finishGeneration()
            return
        }

        // 502 降级：跳过 ReasoningCard，pending 占位原地替换为降级卡（不入正常历史）
        if response.degraded == true {
            if let idx = messages.firstIndex(where: { $0.id == req.id }) {
                messages[idx].content = response.answer.isEmpty ? "服务暂时不可用，请稍后重试" : response.answer
                messages[idx].degraded = true
                messages[idx].pending = false
                messages[idx].isStreaming = false
                messages[idx].blocks = []
            }
            inflight = nil
            commitSession()
            finishGeneration()
            return
        }

        // 对话式创建 Agent 成功信号 → 广播通知，触发拓扑页租户切片列表静默刷新
        if response.answer.contains("已为您创建专属 Agent 切片") {
            NotificationCenter.default.post(name: .tenantAgentsDidUpdate, object: nil)
        }

        // 正常：先挂载真实 reasoning（折叠 ReasoningCard，空 reasoning 自动隐藏）
        let steps = (response.reasoning ?? []).map { $0.toReasoningStep() }
        if let idx = messages.firstIndex(where: { $0.id == req.id }) {
            // 先挂空 reasoning（逐步揭示任务逐条填充），无步骤时 ReasoningCard 自动隐藏
            messages[idx].blocks = steps.isEmpty ? [] : [.reasoning([])]
        }

        // 移除思考占位
        inflight = nil

        // 澄清卡片优先：后端返回 clarify 载荷 → 直接挂载 ClarifyBlock，
        // answer 仅作为极简引导语（禁止正文废话），跳过思维链揭示与打字机渲染。
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
                // 正文只保留极简引导（≤40 字），杜绝流程说教
                messages[idx].content = response.answer.isEmpty ? "" : String(response.answer.prefix(40))
                messages[idx].blocks = blocks
                messages[idx].pending = false
                messages[idx].isStreaming = false
            }
            commitSession()
            finishGeneration()
            return
        }

        // 思维链逐步揭示（每步约 300ms），揭示完毕后再打字机渲染正文
        if !steps.isEmpty {
            await revealReasoning(messageId: req.id, steps: steps)
        }

        // 再打字机渲染 answer（原地填充 pending 占位）
        await typewriter(messageId: req.id, answer: response.answer)

        if let idx = messages.firstIndex(where: { $0.id == req.id }) {
            messages[idx].pending = false
        }
        commitSession()
        finishGeneration()
    }

    /// 思维链逐步揭示动画：四类步骤按序以 300ms 间隔展开。
    /// 任务注册进 `animationTasks`（按消息 ID 隔离），Task 执行体内 `defer` 自清理，
    /// 会话切换 / 清空 / 取消在途时由 `cancelAllReveals()` 统一 cancel。
    private func revealReasoning(messageId: String, steps: [ReasoningStep]) async {
        animationTasks[messageId]?.cancel()
        let task = Task { @MainActor in
            defer { animationTasks.removeValue(forKey: messageId) }
            for k in 1...steps.count {
                try? await Task.sleep(nanoseconds: 300_000_000)
                if Task.isCancelled { return }
                guard let idx = messages.firstIndex(where: { $0.id == messageId }) else { return }
                withAnimation(.easeInOut(duration: 0.25)) {
                    messages[idx].blocks = [.reasoning(Array(steps[0..<k]))]
                }
            }
        }
        animationTasks[messageId] = task
        await task.value
    }

    /// 统一取消所有在途思维链揭示动画（会话切换 / 新建 / 清空 / 取消在途）。
    private func cancelAllReveals() {
        for task in animationTasks.values { task.cancel() }
        animationTasks.removeAll()
    }

    private func handleError(req: InFlightRequest, error: Error) async {
        // 后台任务兜底：inflight 槽已被更新的任务占用 → 降级卡写归属会话。
        if inflight?.id != req.id {
            let text: String
            if let urlError = error as? URLError, urlError.code == .cancelled {
                sessionManager.applyDegraded(sessionId: req.sessionId, requestId: req.id, text: "已取消")
                return
            }
            if error is CancellationError {
                sessionManager.applyDegraded(sessionId: req.sessionId, requestId: req.id, text: "已取消")
                return
            }
            if let apiErr = error as? APIError, case .timeout = apiErr {
                text = "响应超时，请重试"
            } else {
                text = "服务暂时不可用，请稍后重试"
            }
            sessionManager.applyDegraded(sessionId: req.sessionId, requestId: req.id, text: text)
            return
        }

        // 切走后任务失败：degraded 卡写原会话（不中断、不静默）。
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

        if let urlError = error as? URLError, urlError.code == .cancelled {
            markCancelled(req: req)
            return
        }
        if error is CancellationError {
            markCancelled(req: req)
            return
        }

        switch error {
        case APIError.unauthorized:
            // 401 → needsReauth（APIClient 已置位，AppRoot 协调器负责登出）；不推进队列
            isGenerating = false
            inflight = nil
            currentChatTask = nil
            waitingSeconds = 0
        case APIError.timeout:
            inflight?.phase = .timeout
        case APIError.server(let code, _) where code == 404:
            await handleNotFound(req: req)
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

    /// 404：清 session_id 无感知重发一次；再 404 → toast 不循环
    private func handleNotFound(req: InFlightRequest) async {
        if req.didRetry404 {
            showToast("会话失效，已开启新会话")
            finishGeneration()
            return
        }
        appState.chatSessionId = nil
        var updated = req
        updated.didRetry404 = true
        inflight = updated

        do {
            let resp = try await APIClient.shared.chat(
                question: updated.text,
                sessionId: nil,
                quotedContext: updated.quote?.text,
                agentId: appState.selectedAgentId
            )
            await handleSuccess(req: updated, response: resp)
        } catch {
            if let apiErr = error as? APIError, case .server(let code, _) = apiErr, code == 404 {
                showToast("会话失效，已开启新会话")
                finishGeneration()
            } else {
                await handleError(req: updated, error: error)
            }
        }
    }

    private func markCancelled(req: InFlightRequest) {
        guard inflight?.id == req.id else { return }
        // 占位改「已取消」（用户主动取消；会话切换的取消已由 markInterrupted 处理）
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
        stopStatusPolling()
        advanceQueue()
    }

    private func advanceQueue() {
        guard !pendingQueue.isEmpty else { return }
        let next = pendingQueue.removeFirst()
        startGeneration(text: next.text, quote: next.quote)
    }

    private func cancelInFlight() {
        currentChatTask?.cancel()
    }

    private func cancelQueued(_ id: String) {
        pendingQueue.removeAll { $0.id == id }
        // 后续占位序号由 enumerated 实时重排
    }

    private func retryCurrentInFlight() {
        guard var req = inflight else { return }
        req.phase = .thinking
        req.didRetry404 = false
        inflight = req
        waitingSeconds = 0
        currentChatTask = Task {
            await runInFlight(req)
        }
        startStatusPolling(req: req)
    }

    // MARK: - 长任务状态回读 / 断点重续（320s 指数退避轮询 + 状态探测）

    /// 320s 指数退避轮询：2s→4s→6s→8s（上限 8s），最多 50 次。
    /// 拉取 status=running 时的 latest_step，实时回填 ThinkingPlaceholder 进度行。
    private func startStatusPolling(req: InFlightRequest) {
        statusPollTask?.cancel()
        liveProgress = nil
        // 会话单源：轮询绑定本次请求的会话 ID（appState.chatSessionId 已废除）
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
                if Task.isCancelled { return }
                guard isGenerating,
                      inflight?.id == req.id,
                      inflight?.phase == .thinking else { return }
                do {
                    let status = try await APIClient.shared.fetchChatStatus(sessionId: sid)
                    if status.status == "running" {
                        liveProgress = status.latestStep
                    }
                } catch {
                    // 轮询失败忽略，不干扰主 POST 请求
                }
                polls += 1
            }
        }
    }

    private func stopStatusPolling() {
        statusPollTask?.cancel()
        statusPollTask = nil
        liveProgress = nil
    }

    /// 断点续接入口：先探测 status 端点（completed 秒级装载 / 未完成断点续接）。
    private func probeAndResumeCurrentInFlight() {
        guard var req = inflight else { return }
        req.phase = .thinking
        inflight = req
        waitingSeconds = 0
        currentChatTask = Task {
            await probeAndResume(req)
        }
    }

    private func probeAndResume(_ req: InFlightRequest) async {
        // 先探测 status：已完成 → 秒级装载；未完成/探测失败 → 断点续接（重发 POST，桥接层 --resume）
        // 会话单源：探测绑定本次请求会话 ID（appState.chatSessionId 已废除）
        let sid = req.sessionId
        if !sid.isEmpty, !demoMode {
            do {
                let status = try await APIClient.shared.fetchChatStatus(sessionId: sid, consume: true)
                if status.status == "completed",
                   let answer = status.answer, !answer.isEmpty {
                    await applyCompletedStatus(req: req, status: status)
                    return
                }
            } catch {
                // 探测失败 → 落入重发
            }
        }
        retryCurrentInFlight()
    }

    /// 秒级装载已完成的断点结果（不重复调用 Hermes）。
    private func applyCompletedStatus(req: InFlightRequest, status: ChatStatusDTO) async {
        guard inflight?.id == req.id else { return }
        // 切走后探测到 completed：结果写原会话（断点续接成果不丢）
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
        commitSession()
        finishGeneration()
    }

    private func switchToDemoMode() {
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
            await typewriter(messageId: req.id, answer: demoReply(for: req.text))
            messages[idx].pending = false
        }
        commitSession()
        finishGeneration()
    }

    private func demoReply(for question: String) -> String {
        "演示模式：后端暂不可达，已切换到本地演示。你提出的「\(question)」将在接入真实后端后获得答复。"
    }

    /// 打字机渲染 answer（先挂载 reasoning 卡后再逐字推进正文）
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

    private func showToast(_ text: String) {
        toastMessage = text
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.2) {
            if toastMessage == text {
                toastMessage = nil
            }
        }
    }

    // MARK: - regenerate（统一走真实 API，共享 isGenerating 互斥锁）

    private func regenerate(messageId: String) {
        guard !isGenerating else { return }
        guard let targetIdx = messages.firstIndex(where: { $0.id == messageId }) else { return }
        guard messages[targetIdx].role == .assistant else { return }
        guard let userIdx = messages[..<targetIdx].lastIndex(where: { $0.role == .user }) else { return }

        let userPrompt = messages[userIdx].content
        let quote = messages[userIdx].quotedContext
        // 移除目标及其后所有消息，走真实 API 重发
        messages.removeSubrange(targetIdx...)
        startGeneration(text: userPrompt, quote: quote)
    }

    // MARK: - PlusMenuSheet 回填处理

    private func attachPhoto(_ data: Data) {
        let block = ImageBlock(assetName: "imported_photo", imageData: data, caption: "已导入照片（2048px 降采样）")
        let msg = ChatMessage(
            role: .user,
            content: "📸 已从照片图库导入一张图片（客户端 2048px 等比降采样 · JPEG 0.85）",
            blocks: [.image(block)]
        )
        messages.append(msg)
        dispatchAssistantReply(to: "照片导入")
    }

    private func attachDocument(_ url: URL) {
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

    private func importWeChatLink(_ link: String) {
        let msg = ChatMessage(
            role: .user,
            content: "💬 微信文章导入请求：\(link)\n（已通过 mp.weixin.qq.com 白名单校验，内容抓取由后端引擎后续轮次承接）"
        )
        messages.append(msg)
        dispatchAssistantReply(to: "微信文章导入")
    }

    private func referenceKnowledge(_ item: KnowledgeItem) {
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

// MARK: - 状态机数据结构

private struct PendingItem: Identifiable {
    let id: String
    let text: String
    let quote: QuotedContext?
}

private struct InFlightRequest {
    let id: String
    let sessionId: String    // 会话屏障：响应回来时校验是否仍为 active 会话
    let text: String
    let quote: QuotedContext?
    var didRetry404: Bool = false
    var phase: InFlightPhase = .thinking
}

private enum InFlightPhase: Equatable {
    case thinking
    case timeout
    case networkError
    case serverError(String)
}

// MARK: - 占位视图

private struct PendingPlaceholderView: View {
    let position: Int
    let onCancel: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            QuantumAvatarView(size: 32).padding(.top, 2)
            HStack(spacing: AppTheme.Spacing.xs) {
                Image(systemName: "clock.arrow.circlepath")
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textTertiary)
                Text("排队中 · 第 \(position) 位")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                Spacer()
                Button(action: onCancel) {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 13))
                        .foregroundColor(AppTheme.Colors.textTertiary)
                }
                .buttonStyle(SoftButtonStyle())
            }
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.sm + 2)
            .background(AppTheme.Colors.cardBackground.opacity(0.7))
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(AppTheme.Colors.border, lineWidth: 0.5)
            )
            Spacer(minLength: 44)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
    }
}

private struct StatusCardView: View {
    let icon: String
    let iconColor: Color
    let title: String
    let message: String
    let primary: (label: String, action: () -> Void)
    let secondary: (label: String, action: () -> Void)?

    var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            QuantumAvatarView(size: 32).padding(.top, 2)
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                HStack(spacing: 6) {
                    Image(systemName: icon)
                        .font(.system(size: 12))
                        .foregroundColor(iconColor)
                    Text(title)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                }
                Text(message)
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                HStack(spacing: AppTheme.Spacing.sm) {
                    actionChip(primary.label, primary.action)
                    if let secondary {
                        actionChip(secondary.label, secondary.action)
                    }
                }
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(iconColor.opacity(0.25), lineWidth: 0.5)
            )
            Spacer(minLength: 44)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
    }

    private func actionChip(_ label: String, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(AppTheme.Colors.primary)
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, 6)
                .background(AppTheme.Colors.primary.opacity(0.08))
                .clipShape(Capsule())
        }
        .buttonStyle(SoftButtonStyle())
    }
}

// MARK: - 会话抽屉（多会话切换 + 新建 + 删除）

private struct SessionDrawerSheet: View {
    @ObservedObject var sessionManager: SessionManager
    let onSelect: (String) -> Void
    let onNew: () -> Void
    let onDelete: (String) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Button(action: onNew) {
                        Label("新建会话", systemImage: "square.and.pencil")
                    }
                }

                Section("历史会话") {
                    ForEach(sessionManager.sortedSessionIDs(), id: \.self) { id in
                        Button {
                            onSelect(id)
                        } label: {
                            SessionRow(
                                title: sessionManager.title(for: id),
                                messageCount: sessionManager.messages(for: id).count,
                                updatedAt: sessionManager.sessionUpdatedAt[id] ?? .distantPast,
                                isActive: sessionManager.activeSessionId == id
                            )
                        }
                        .buttonStyle(SoftButtonStyle())
                        .swipeActions {
                            Button(role: .destructive) {
                                onDelete(id)
                            } label: {
                                Label("删除", systemImage: "trash")
                            }
                        }
                    }
                }
            }
            .navigationTitle("会话")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("完成") { dismiss() }
                }
            }
        }
    }
}

private struct SessionRow: View {
    let title: String
    let messageCount: Int
    let updatedAt: Date
    let isActive: Bool

    var body: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            VStack(alignment: .leading, spacing: 3) {
                Text(title.isEmpty ? "新会话" : title)
                    .font(.system(size: 14, weight: isActive ? .bold : .medium))
                    .foregroundColor(isActive ? AppTheme.Colors.primary : AppTheme.Colors.textPrimary)
                    .lineLimit(1)
                Text("\(messageCount) 条消息 · \(relativeTime(updatedAt))")
                    .font(.system(size: 11))
                    .foregroundColor(AppTheme.Colors.textTertiary)
            }
            Spacer()
            if isActive {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 14))
                    .foregroundColor(AppTheme.Colors.primary)
            }
        }
        .padding(.vertical, 2)
    }

    private func relativeTime(_ date: Date) -> String {
        let s = Int(Date().timeIntervalSince(date))
        if s < 60 { return "刚刚" }
        if s < 3600 { return "\(s / 60) 分钟前" }
        if s < 86400 { return "\(s / 3600) 小时前" }
        let f = DateFormatter()
        f.dateFormat = "MM-dd HH:mm"
        return f.string(from: date)
    }
}

// MARK: - 降级卡 / 中断卡 / 未完成孤儿卡

/// 502 降级卡（跳过 ReasoningCard，不入正常历史，重试成功原地替换）。
private struct DegradedCardView: View {
    let onRetry: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            QuantumAvatarView(size: 32).padding(.top, 2)
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                HStack(spacing: 6) {
                    Image(systemName: "wifi.exclamationmark")
                        .font(.system(size: 12))
                        .foregroundColor(AppTheme.Colors.securityYellow)
                    Text("服务暂时不可用")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                }
                Text("服务暂时不可用，请稍后重试")
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                retryChip
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(AppTheme.Colors.securityYellow.opacity(0.25), lineWidth: 0.5)
            )
            Spacer(minLength: 44)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
    }

    private var retryChip: some View {
        Button(action: onRetry) {
            HStack(spacing: 4) {
                Image(systemName: "arrow.clockwise")
                Text("重试")
            }
            .font(.system(size: 12, weight: .semibold))
            .foregroundColor(AppTheme.Colors.primary)
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, 6)
            .background(AppTheme.Colors.primary.opacity(0.08))
            .clipShape(Capsule())
        }
        .buttonStyle(SoftButtonStyle())
    }
}

/// 会话切换中断卡（在原会话落盘，携带重试入口，不污染 API 上下文）。
private struct InterruptedCardView: View {
    let onRetry: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            QuantumAvatarView(size: 32).padding(.top, 2)
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                HStack(spacing: 6) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 12))
                        .foregroundColor(AppTheme.Colors.securityYellow)
                    Text("响应已中断")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                }
                Text(SessionManager.interruptedText)
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                retryChip
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(AppTheme.Colors.securityYellow.opacity(0.25), lineWidth: 0.5)
            )
            Spacer(minLength: 44)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
    }

    private var retryChip: some View {
        Button(action: onRetry) {
            HStack(spacing: 4) {
                Image(systemName: "arrow.clockwise")
                Text("重试")
            }
            .font(.system(size: 12, weight: .semibold))
            .foregroundColor(AppTheme.Colors.primary)
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, 6)
            .background(AppTheme.Colors.primary.opacity(0.08))
            .clipShape(Capsule())
        }
        .buttonStyle(SoftButtonStyle())
    }
}

/// 冷启动孤儿 pending 卡（上次中断未完成的会话恢复，提供继续/重试入口）。
private struct OrphanPendingCardView: View {
    let onRetry: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            QuantumAvatarView(size: 32).padding(.top, 2)
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                HStack(spacing: 6) {
                    Image(systemName: "clock.badge.exclamationmark")
                        .font(.system(size: 12))
                        .foregroundColor(AppTheme.Colors.textTertiary)
                    Text("未完成")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                }
                Text("该回复在上次中断前未完成，可继续重试。")
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                retryChip
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(AppTheme.Colors.border, lineWidth: 0.5)
            )
            Spacer(minLength: 44)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
    }

    private var retryChip: some View {
        Button(action: onRetry) {
            HStack(spacing: 4) {
                Image(systemName: "arrow.clockwise")
                Text("继续 / 重试")
            }
            .font(.system(size: 12, weight: .semibold))
            .foregroundColor(AppTheme.Colors.primary)
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, 6)
            .background(AppTheme.Colors.primary.opacity(0.08))
            .clipShape(Capsule())
        }
        .buttonStyle(SoftButtonStyle())
    }
}

// MARK: - Xcode #Preview

#Preview("ChatView - Light") {
    ChatView()
        .environmentObject(AppState())
}

#Preview("ChatView - Dark") {
    ChatView()
        .environmentObject(AppState())
        .preferredColorScheme(.dark)
}
