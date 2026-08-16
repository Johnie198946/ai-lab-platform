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
    @State private var selectedAgentId: String = "main_agent"
    @State private var quotedContext: QuotedContext? = nil
    @State private var isShowingClearAlert: Bool = false
    @State private var isGenerating: Bool = false
    @State private var showingVoiceInput: Bool = false
    @State private var showingPlusMenu: Bool = false
    @StateObject private var speechService = SpeechRecognizerService()

    // MARK: - 状态机字段（真实后端对接）
    @State private var inflight: InFlightRequest? = nil       // 当前 in-flight（思考/超时/错误占位）
    @State private var pendingQueue: [PendingItem] = []       // 排队消息（上限 3）
    @State private var waitingSeconds: Int = 0                // 「已等待 N 秒」本地计时
    @State private var currentChatTask: Task<Void, Never>? = nil
    @State private var toastMessage: String? = nil
    @State private var demoMode: Bool = false                 // 网络错误后「切换演示模式」

    private let waitingTimer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    private let availableAgents = [
        ("main_agent", "Main 智能编排", "sparkles"),
        ("supervision", "Supervision 架构审查", "shield.checkerboard"),
        ("coder", "Coder 独立开发", "chevron.left.forwardslash.chevron.right")
    ]

    private let suggestionChips = [
        "🔍 诊断 SMT 贴片机气压告警",
        "📐 调整 DAG 拓扑串联质检",
        "🔒 申请受限知识库订阅",
        "✨ 提炼结构化 Prompt"
    ]

    public init() {}

    public var body: some View {
        NavigationStack {
            ZStack {
                AppTheme.Colors.groupedBackground
                    .ignoresSafeArea()

                VStack(spacing: 0) {
                    // MARK: - 1. Top Agent Selector & Status
                    topAgentSelectorBar

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
            .navigationTitle("协同对话")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    agentHeaderBadge
                }

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
            .onAppear { handlePendingPrompt() }
            .onChange(of: appState.pendingChatPrompt) { _, _ in handlePendingPrompt() }
            .onReceive(waitingTimer) { _ in tickWaitingTimer() }
            .sheet(isPresented: $showingVoiceInput) { voiceSheet }
            .sheet(isPresented: $showingPlusMenu) { plusSheet }
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
                        MessageBubbleView(
                            message: message,
                            onQuoteFollowUp: { quote in
                                withAnimation(.spring()) { self.quotedContext = quote }
                            },
                            onRegenerate: { messageId in regenerate(messageId: messageId) }
                        )
                        .id(message.id)
                    }

                    // 当前 in-flight 占位（思考 / 超时 / 错误）
                    if let current = inflight {
                        inflightPlaceholder(current)
                            .id("inflight_\(current.id)")
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
        messages.removeAll()
    }

    // MARK: - Subviews

    private var agentHeaderBadge: some View {
        HStack(spacing: 6) {
            QuantumAvatarView(size: 18)
            Text(currentAgentTitle)
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(AppTheme.Colors.textPrimary)
            Circle()
                .fill(AppTheme.Colors.quantumCyan)
                .frame(width: 6, height: 6)
        }
    }

    private var currentAgentTitle: String {
        availableAgents.first(where: { $0.0 == selectedAgentId })?.1 ?? "AI Agent"
    }

    private var topAgentSelectorBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: AppTheme.Spacing.sm) {
                ForEach(availableAgents, id: \.0) { agent in
                    let isSelected = selectedAgentId == agent.0
                    Button(action: {
                        #if os(iOS)
                        UIImpactFeedbackGenerator(style: .light).impactOccurred()
                        #endif
                        selectedAgentId = agent.0
                    }) {
                        HStack(spacing: 6) {
                            Image(systemName: agent.2)
                                .font(.system(size: 12))
                            Text(agent.1)
                                .font(.system(size: 12, weight: isSelected ? .bold : .medium))
                        }
                        .padding(.horizontal, AppTheme.Spacing.md)
                        .padding(.vertical, 6)
                        .foregroundColor(isSelected ? AppTheme.Colors.onPrimary : AppTheme.Colors.textSecondary)
                        .background(
                            isSelected ?
                            AnyShapeStyle(AppTheme.Colors.quantumGradient) :
                            AnyShapeStyle(AppTheme.Colors.cardBackground)
                        )
                        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                                .stroke(isSelected ? Color.clear : AppTheme.Colors.border, lineWidth: 1)
                        )
                    }
                    .buttonStyle(SoftButtonStyle())
                }
            }
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.sm)
        }
        .background(AppTheme.Colors.cardBackground)
    }

    private var suggestionChipsBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: AppTheme.Spacing.xs) {
                ForEach(suggestionChips, id: \.self) { chip in
                    Button(action: {
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
            ThinkingPlaceholderView(seconds: waitingSeconds, onCancel: { cancelInFlight() })
        case .timeout:
            StatusCardView(
                icon: "exclamationmark.triangle.fill",
                iconColor: AppTheme.Colors.securityYellow,
                title: "响应超时(180s)",
                message: "后端 180 秒内未返回，可能仍在处理中。",
                primary: ("继续等待", { retryCurrentInFlight() }),
                secondary: ("重试", { retryCurrentInFlight() })
            )
        case .networkError:
            StatusCardView(
                icon: "wifi.exclamationmark",
                iconColor: AppTheme.Colors.securityRed,
                title: "后端不可达",
                message: "无法连接到后端服务，请检查网络或稍后重试。",
                primary: ("重试", { retryCurrentInFlight() }),
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
            anchor = "inflight_\(inf.id)"
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

        messages.append(ChatMessage(role: .user, content: text, quotedContext: quote))
        inputText = ""
        quotedContext = nil
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
        let req = InFlightRequest(id: UUID().uuidString, text: text, quote: quote)
        inflight = req
        currentChatTask = Task {
            await runInFlight(req)
        }
    }

    private func runInFlight(_ req: InFlightRequest) async {
        if demoMode {
            await appendDemoReply(req: req)
            return
        }
        do {
            let resp = try await APIClient.shared.chat(
                question: req.text,
                sessionId: appState.chatSessionId,
                quotedContext: req.quote?.text
            )
            if let sid = resp.sessionId, !sid.isEmpty {
                appState.chatSessionId = sid
            }
            await handleSuccess(req: req, response: resp)
        } catch {
            await handleError(req: req, error: error)
        }
    }

    private func handleSuccess(req: InFlightRequest, response: ChatResponseDTO) async {
        guard inflight?.id == req.id else { return }

        // 先挂载真实 reasoning（折叠 ReasoningCard，空 reasoning 自动隐藏）
        let steps = (response.reasoning ?? []).map { $0.toReasoningStep() }
        var blocks: [MessageBlock] = []
        if !steps.isEmpty {
            blocks.append(.reasoning(steps))
        }

        let messageId = UUID().uuidString
        messages.append(
            ChatMessage(id: messageId, role: .assistant, content: "", isStreaming: true, blocks: blocks)
        )

        // 移除思考占位
        inflight = nil

        // 再打字机渲染 answer
        await typewriter(messageId: messageId, answer: response.answer)

        finishGeneration()
    }

    private func handleError(req: InFlightRequest, error: Error) async {
        guard inflight?.id == req.id else { return }

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
                quotedContext: updated.quote?.text
            )
            if let sid = resp.sessionId, !sid.isEmpty {
                appState.chatSessionId = sid
            }
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
        // 占位改「已取消」
        messages.append(ChatMessage(role: .assistant, content: "已取消", isStreaming: false))
        finishGeneration()
    }

    private func finishGeneration() {
        isGenerating = false
        inflight = nil
        currentChatTask = nil
        waitingSeconds = 0
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
        let messageId = UUID().uuidString
        messages.append(
            ChatMessage(id: messageId, role: .assistant, content: "", isStreaming: true, isDemoSample: true)
        )
        await typewriter(messageId: messageId, answer: demoReply(for: req.text))
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

private struct ThinkingPlaceholderView: View {
    let seconds: Int
    let onCancel: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            QuantumAvatarView(size: 32).padding(.top, 2)
            HStack(spacing: AppTheme.Spacing.xs) {
                Circle().fill(AppTheme.Colors.primary).frame(width: 6, height: 6)
                Circle().fill(AppTheme.Colors.primary.opacity(0.6)).frame(width: 6, height: 6)
                Circle().fill(AppTheme.Colors.primary.opacity(0.3)).frame(width: 6, height: 6)
                Text("思考中 · 已等待 \(seconds) 秒")
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                Spacer()
                Button(action: onCancel) {
                    HStack(spacing: 4) {
                        Image(systemName: "xmark.circle.fill")
                        Text("取消")
                    }
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.textTertiary)
                }
                .buttonStyle(SoftButtonStyle())
            }
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.sm + 2)
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(AppTheme.Colors.assistantBubbleBorder.opacity(0.18), lineWidth: 0.5)
            )
            Spacer(minLength: 44)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
    }
}

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
