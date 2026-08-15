//
//  ChatView.swift
//  AIPlatformApp
//
//  Streaming Agent Conversation View with TextKit2-Style Markdown Bubbles & Quoted Follow-Ups
//  首条主动发送注入富媒体演示剧本 + 真实思维链折叠卡 + regenerate 混合态
//

import SwiftUI

public struct ChatView: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.scenePhase) private var scenePhase

    @State private var messages: [ChatMessage] = MockData.messages
    @State private var inputText: String = ""
    @State private var selectedAgentId: String = "main_agent"
    @State private var quotedContext: QuotedContext? = nil
    @State private var isShowingClearAlert: Bool = false
    @State private var isGenerating: Bool = false
    @State private var showingVoiceInput: Bool = false
    @State private var showingPlusMenu: Bool = false
    @State private var hasShownRichMediaDemo: Bool = false
    @StateObject private var speechService = SpeechRecognizerService()

    /// 预置消息 id 集合（用于 regenerate 混合态判定：预置=保留 blocks+附真实链，运行时=全量替换）
    private let presetMessageIds: Set<String> = Set(MockData.messages.map(\.id))

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
                    ScrollViewReader { proxy in
                        ScrollView {
                            LazyVStack(spacing: AppTheme.Spacing.md) {
                                ForEach(messages) { message in
                                    MessageBubbleView(
                                        message: message,
                                        onQuoteFollowUp: { quote in
                                            withAnimation(.spring()) {
                                                self.quotedContext = quote
                                            }
                                        },
                                        onRegenerate: { messageId in
                                            regenerate(messageId: messageId)
                                        }
                                    )
                                    .id(message.id)
                                }
                            }
                            .padding(.vertical, AppTheme.Spacing.md)
                        }
                        .onChange(of: messages.count) { _, _ in
                            if let lastId = messages.last?.id {
                                withAnimation(.easeOut(duration: 0.25)) {
                                    proxy.scrollTo(lastId, anchor: .bottom)
                                }
                            }
                        }
                    }

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
                Button("清空", role: .destructive) {
                    messages.removeAll()
                    hasShownRichMediaDemo = false
                }
            } message: {
                Text("此操作将清空当前会话所有消息记录。")
            }
            .onAppear {
                handlePendingPrompt()
            }
            .onChange(of: appState.pendingChatPrompt) { _, _ in
                handlePendingPrompt()
            }
            .sheet(isPresented: $showingVoiceInput) {
                VoiceInputView(
                    service: speechService,
                    onTranscript: { text in
                        inputText = text
                    },
                    onDismiss: {
                        showingVoiceInput = false
                    }
                )
            }
            .sheet(isPresented: $showingPlusMenu) {
                PlusMenuSheet(
                    onPhotoPicked: { data in attachPhoto(data) },
                    onDocumentPicked: { url in attachDocument(url) },
                    onWeChatImported: { link in importWeChatLink(link) },
                    onKnowledgeReferenced: { item in referenceKnowledge(item) }
                )
            }
            .onChange(of: scenePhase) { _, phase in
                if phase == .active {
                    InboxFileManager.shared.cleanupStaleInboxFiles()
                }
            }
        }
    }

    // MARK: - Subviews

    private var agentHeaderBadge: some View {
        HStack(spacing: 6) {
            // Quantum 品牌微标（自适应托盘球体图标）+ 状态点缀色
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
            // Attachment Plus Button（四入口扩展面板 + 进入面板触发清理节流）
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

            // Multiline Text Editor
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

            // Send / Voice Button
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

    // MARK: - Actions

    private func handlePendingPrompt() {
        if let prompt = appState.pendingChatPrompt {
            self.inputText = prompt
            appState.pendingChatPrompt = nil
        }
    }

    private func sendMessage() {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }

        #if os(iOS)
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        #endif

        let userMsg = ChatMessage(
            role: .user,
            content: text,
            quotedContext: quotedContext
        )
        messages.append(userMsg)
        inputText = ""
        quotedContext = nil

        // 首条主动发送 → 注入 4 卡剧本回复；之后走普通流式
        if !hasShownRichMediaDemo {
            hasShownRichMediaDemo = true
            injectRichMediaDemo(to: text)
        } else {
            simulateAssistantResponse(to: text)
        }
    }

    /// 首条主动消息触发 4 卡剧本（Chart/Image/Table/Attachment + 真实链），本地打字机动画。
    private func injectRichMediaDemo(to userPrompt: String) {
        isGenerating = true

        let streamId = UUID().uuidString
        let initial = ChatMessage(
            id: streamId,
            role: .assistant,
            content: "思考中...",
            isStreaming: true
        )
        messages.append(initial)

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) {
            if let idx = messages.firstIndex(where: { $0.id == streamId }) {
                let demo = MockData.richMediaDemoReply(for: userPrompt)
                messages[idx] = ChatMessage(
                    id: streamId,
                    role: .assistant,
                    content: demo.content,
                    isStreaming: false,
                    blocks: demo.blocks,
                    isDemoSample: true
                )
            }
            self.isGenerating = false
        }
    }

    /// 普通流式回复（本地打字机动画·非网络流式）；期间 blocks 为空，完成一次性注入。
    private func simulateAssistantResponse(to userPrompt: String) {
        isGenerating = true

        let streamId = UUID().uuidString
        let initialAssistantMsg = ChatMessage(
            id: streamId,
            role: .assistant,
            content: "思考中...",
            isStreaming: true
        )
        messages.append(initialAssistantMsg)

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
            if let idx = messages.firstIndex(where: { $0.id == streamId }) {
                messages[idx].content = "已收到关于「\(userPrompt)」的协同请求。正在调用多租户 Agent 编排流水线与知识库检索..."
            }
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
            if let idx = messages.firstIndex(where: { $0.id == streamId }) {
                messages[idx].content = "根据分析，当前任务已自动调度至最优智能体处理。输出如下："
                messages[idx].isStreaming = false
                messages[idx].blocks = [
                    .code(
                        CodeSnippet(
                            language: "swift",
                            code: "// Swift 6 异步协同调用示例\nlet response = await orchestrator.execute(intent: \"\(userPrompt)\")"
                        )
                    )
                ]
            }
            self.isGenerating = false
        }
    }

    /// regenerate(messageId:)：定位 assistant → 最近 user → 替换。
    /// 预置消息=保留原 blocks+附真实链（混合态·演示样例标注）；运行时=全量替换；isGenerating 互斥。
    private func regenerate(messageId: String) {
        guard !isGenerating else { return }
        guard let targetIdx = messages.firstIndex(where: { $0.id == messageId }) else { return }
        guard messages[targetIdx].role == .assistant else { return }
        guard let userIdx = messages[..<targetIdx].lastIndex(where: { $0.role == .user }) else { return }

        let userPrompt = messages[userIdx].content
        let isPreset = presetMessageIds.contains(messageId)

        if isPreset {
            // 预置消息混合态：保留原富媒体 blocks + 附真实 reasoning，标注演示样例
            var updated = messages[targetIdx]
            updated.content = "关于「\(userPrompt)」——已重新生成（演示样例）。"
            updated.blocks = messages[targetIdx].blocks.filter { block in
                if case .reasoning = block { return false }
                return true
            }
            updated.blocks.append(.reasoning(MockData.demoReasoningSteps))
            updated.isStreaming = false
            updated.isDemoSample = true
            messages[targetIdx] = updated
        } else {
            // 运行时全量替换：移除目标及其后所有消息，流式重发
            messages.removeSubrange(targetIdx...)
            simulateAssistantResponse(to: userPrompt)
        }
    }

    // MARK: - PlusMenuSheet 回填处理

    /// 照片导入：降采样后 JPEG 数据 → 用户消息 + 图片卡
    private func attachPhoto(_ data: Data) {
        let block = ImageBlock(assetName: "imported_photo", imageData: data, caption: "已导入照片（2048px 降采样）")
        let msg = ChatMessage(
            role: .user,
            content: "📸 已从照片图库导入一张图片（客户端 2048px 等比降采样 · JPEG 0.85）",
            blocks: [.image(block)]
        )
        messages.append(msg)
        simulateAssistantResponse(to: "照片导入")
    }

    /// 文档导入：前置 50MB 预检已通过，读取文件名/体积 → 用户消息 + 附件卡
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
        simulateAssistantResponse(to: "文档导入")
    }

    /// 微信文章导入：白名单校验通过后的链接回填（抓取由后端后续轮承接）
    private func importWeChatLink(_ link: String) {
        let msg = ChatMessage(
            role: .user,
            content: "💬 微信文章导入请求：\(link)\n（已通过 mp.weixin.qq.com 白名单校验，内容抓取由后端引擎后续轮次承接）"
        )
        messages.append(msg)
        simulateAssistantResponse(to: "微信文章导入")
    }

    /// 引用知识：已订阅条目 → 带引用上下文的用户消息
    private func referenceKnowledge(_ item: KnowledgeItem) {
        let quote = QuotedContext(text: "《\(item.title)》", blockSummary: item.summary)
        let msg = ChatMessage(
            role: .user,
            content: "引用知识条目：\(item.title)",
            quotedContext: quote
        )
        messages.append(msg)
        simulateAssistantResponse(to: "知识引用")
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
