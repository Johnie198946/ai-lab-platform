//
//  MessageBubbleView.swift
//  AIPlatformApp
//
//  Markdown Message Bubble with Syntax-Highlighted Code Cards, Math Formulas & Context Menu
//  统一 blocks 数组序渲染 7 类块 + 真实思维链卡片 + 富媒体引用上下文
//  ChatGPT / Claude 规范：思维链胶囊置顶 -> 正文卡片居中 -> 操作条在底部（有正文时才展示）
//

import SwiftUI

public struct MessageBubbleView: View {
    public let message: ChatMessage
    public var context: PluginRenderContext? = nil
    public var onQuoteFollowUp: ((QuotedContext) -> Void)? = nil
    public var onRegenerate: ((String) -> Void)? = nil
    public var onStartTopic: ((ChatMessage) -> Void)? = nil

    @State private var isCopied: Bool = false

    public init(
        message: ChatMessage,
        context: PluginRenderContext? = nil,
        onQuoteFollowUp: ((QuotedContext) -> Void)? = nil,
        onRegenerate: ((String) -> Void)? = nil,
        onStartTopic: ((ChatMessage) -> Void)? = nil
    ) {
        self.message = message
        self.context = context
        self.onQuoteFollowUp = onQuoteFollowUp
        self.onRegenerate = onRegenerate
        self.onStartTopic = onStartTopic
    }

    public var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            if message.role == .user {
                Spacer(minLength: 44)
                userBubbleContent
            } else {
                assistantAvatarView
                assistantBubbleContent
                Spacer(minLength: 44)
            }
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
    }

    // MARK: - User Bubble
    private var userBubbleContent: some View {
        VStack(alignment: .trailing, spacing: AppTheme.Spacing.xs) {
            if let quoted = message.quotedContext {
                quotedHeaderView(quoted)
            }

            Text(message.content)
                .font(AppTheme.Typography.body)
                .foregroundColor(AppTheme.Colors.onPrimary)
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, AppTheme.Spacing.sm + 2)
                .background(AppTheme.Colors.userBubbleGradient)
                .clipShape(
                    RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                )
                .pressBorderGlow(cornerRadius: AppTheme.Radius.lg)
                .shadow(color: Color.black.opacity(0.06), radius: 5, x: 0, y: 2)
                .contextMenu {
                    contextMenuActions
                }
        }
    }

    // MARK: - Assistant Bubble
    private var assistantAvatarView: some View {
        QuantumAvatarView(size: 28)
            .padding(.top, 4)
    }

    private var assistantBubbleContent: some View {
        let trimmed = message.content.trimmingCharacters(in: .whitespacesAndNewlines)
        return VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            if let name = message.executingAgentName,
               message.executingAgentId != "main_agent" {
                HStack(spacing: 5) {
                    Image(systemName: "person.crop.circle.badge.checkmark")
                    Text(message.delegatedBy == nil ? "(name)" : "由 (name) 完成")
                }
                .font(AppTheme.Typography.micro.weight(.semibold))
                .foregroundColor(AppTheme.Colors.quantumBlue)
                .padding(.horizontal, AppTheme.Spacing.sm)
                .padding(.vertical, 4)
                .background(AppTheme.Colors.surfaceTint, in: Capsule())
                .accessibilityLabel("执行 Agent：\(name)")
            }

            // 演示样例标注
            if message.isDemoSample {
                demoSampleBadge
            }

            // 1. 思维链胶囊（置顶展示，对标 ChatGPT）
            if let reasoningBlock = message.blocks.first(where: { if case .reasoning = $0 { return true }; return false }) {
                blockCard(reasoningBlock)
            }

            // 2. Markdown 正文卡片（正文非空 或 流式中）
            if !trimmed.isEmpty || message.isStreaming {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                    if !markdownBlocks.isEmpty {
                        // MarkdownBlock.id 基于内容；重复段落/分隔线会产生相同 id。
                        // 使用解析顺序作为局部身份，避免 SwiftUI 在长列表布局时合并重复节点。
                        ForEach(Array(markdownBlocks.enumerated()), id: \.offset) { _, block in
                            MarkdownBlockCard(block: block)
                        }
                    } else if !trimmed.isEmpty {
                        Text(message.content)
                            .font(AppTheme.Typography.body)
                            .foregroundColor(AppTheme.Colors.textPrimary)
                    }

                    if message.isStreaming {
                        streamingCursorView
                    }
                }
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, AppTheme.Spacing.md)
                .background(AppTheme.Colors.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                        .stroke(AppTheme.Colors.assistantBubbleBorder.opacity(0.18), lineWidth: 0.5)
                )
                .pressBorderGlow(cornerRadius: AppTheme.Radius.lg)
            }

            // 3. 其他富媒体块（非 reasoning，如表格、图表、代码、澄清卡等）
            ForEach(message.blocks.filter { if case .reasoning = $0 { return false }; return true }) { block in
                blockCard(block)
            }

            // 4. 空气泡兜底（正文为空且非流式非待办且无澄清卡）：显式给出异常提示 + 重新生成（绝不只露底部操作条）
            if trimmed.isEmpty && !message.isStreaming && !message.pending && message.clarifyBlock == nil {
                HStack(spacing: AppTheme.Spacing.sm) {
                    Image(systemName: "exclamationmark.circle.fill")
                        .font(.system(size: 14))
                    .foregroundColor(AppTheme.Icons.warning)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("未能生成有效回答")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(AppTheme.Colors.textPrimary)
                        Text("大模型未返回完整响应，请点击重新生成")
                            .font(.system(size: 11))
                            .foregroundColor(AppTheme.Colors.textSecondary)
                    }
                    Spacer()
                    Button(action: { onRegenerate?(message.id) }) {
                        HStack(spacing: 4) {
                            Image(systemName: "arrow.clockwise")
                            Text("重新生成")
                        }
                        .font(.system(size: 12, weight: .semibold))
            .foregroundColor(AppTheme.Icons.interactive)
                        .padding(.horizontal, AppTheme.Spacing.sm + 2)
                        .padding(.vertical, 6)
                        .background(AppTheme.Colors.primary.opacity(0.08))
                        .clipShape(Capsule())
                    }
                    .buttonStyle(SoftButtonStyle())
                }
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, AppTheme.Spacing.sm + 2)
                .background(AppTheme.Colors.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                        .stroke(AppTheme.Colors.border, lineWidth: 0.5)
                )
                .pressBorderGlow(cornerRadius: AppTheme.Radius.md)
            }

            // 5. ChatGPT 风格气泡操作条（仅在正文非空且已完成时展示，绝不单独裸露）
            if message.role == .assistant && !trimmed.isEmpty && !message.isStreaming && !message.pending {
                BubbleActionBar(
                    messageId: message.id,
                    content: message.content,
                    onRegenerate: { onRegenerate?(message.id) }
                )
                .padding(.leading, 4)
            }
        }
        .contextMenu {
            contextMenuActions
        }
    }

    /// 解析后的 Markdown 卡片块（流式期间缓存 key = messageId + isStreaming，剔除 content hash，
    /// 流式期不重解析；done 时以完整内容解析一次——Supervision 条件 5）。
    private var markdownBlocks: [MarkdownBlock] {
        guard !message.content.isEmpty else { return [] }
        let cacheKey = message.isStreaming ? "\(message.id)_streaming" : "\(message.id)_done_\(message.content.hashValue)"
        return MarkdownBlockParser.shared.parse(message.content, messageId: cacheKey)
    }

    // MARK: - 演示样例标注
    private var demoSampleBadge: some View {
        HStack(spacing: 4) {
            Image(systemName: "sparkles")
                .font(.system(size: 10, weight: .bold))
            Text("演示样例")
                .font(.system(size: 10, weight: .bold))
        }
            .foregroundColor(AppTheme.Icons.intelligence)
        .padding(.horizontal, AppTheme.Spacing.sm)
        .padding(.vertical, 3)
        .background(AppTheme.Colors.primary.opacity(0.08))
        .clipShape(Capsule())
    }

    // MARK: - 块分发（委托 BlockCardDispatcher 静态分发）
    @ViewBuilder
    private func blockCard(_ block: MessageBlock) -> some View {
        BlockCardDispatcher(
            block: block,
            isStreaming: message.isStreaming,
            onClarifySubmit: { selection in
                context?.onClarifySubmit?(selection)
            },
            onNoteDraftAction: { draftId, action in
                context?.onNoteDraftAction?(draftId, action)
            },
            onKnowledgeAction: { actionId, action in
                context?.onKnowledgeAction?(actionId, action)
            }
        )
    }

    // MARK: - Subcomponents

    private func quotedHeaderView(_ quote: QuotedContext) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: AppTheme.Spacing.xs) {
                Rectangle()
                    .fill(AppTheme.Colors.accent)
                    .frame(width: 3)

                Text(quote.text)
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                    .lineLimit(2)
            }
            .padding(.horizontal, AppTheme.Spacing.sm)
            .padding(.vertical, 4)
            .background(AppTheme.Colors.primary.opacity(0.06))
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xs))
        }
    }

    private var streamingCursorView: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(AppTheme.Colors.quantumCyan)
                .frame(width: 6, height: 6)
                .opacity(0.85)
        }
        .padding(.vertical, 2)
    }

    @ViewBuilder
    private var contextMenuActions: some View {
        Button(action: copyToClipboard) {
            Label(isCopied ? "已复制" : "复制全文", systemImage: isCopied ? "checkmark" : "doc.on.doc")
        }

        if let quoteAction = onQuoteFollowUp, !message.content.isEmpty {
            Button(action: {
                quoteAction(QuotedContext(text: message.content))
            }) {
                Label("引用追问", systemImage: "quote.bubble")
            }
        }

        if let onStartTopic, !message.content.isEmpty, !message.isStreaming {
            Button(action: { onStartTopic(message) }) {
                Label("开启针对性话题", systemImage: "bubble.left.and.bubble.right")
            }
        }

        if message.role == .assistant, let regenAction = onRegenerate {
            Button(action: { regenAction(message.id) }) {
                Label("重新生成", systemImage: "arrow.clockwise")
            }
        }
    }

    private func copyToClipboard() {
        #if os(iOS)
        UIPasteboard.general.string = message.content
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        #endif
        isCopied = true
        Task {
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            isCopied = false
        }
    }
}

// MARK: - Syntax-Highlighted Code Block Card
public struct CodeBlockCard: View {
    public let snippet: CodeSnippet
    @State private var isCopied: Bool = false

    public init(snippet: CodeSnippet) {
        self.snippet = snippet
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header Bar
            HStack {
                HStack(spacing: 6) {
                    Circle().fill(AppTheme.Colors.codeWindowRed).frame(width: 10, height: 10)
                    Circle().fill(AppTheme.Colors.codeWindowYellow).frame(width: 10, height: 10)
                    Circle().fill(AppTheme.Colors.codeWindowGreen).frame(width: 10, height: 10)

                    Text(snippet.language.uppercased())
                        .font(.system(size: 11, weight: .bold, design: .monospaced))
                        .foregroundColor(Color.white.opacity(0.8))
                        .padding(.leading, 6)
                }

                Spacer()

                Button(action: copyCode) {
                    HStack(spacing: 4) {
                        Image(systemName: isCopied ? "checkmark" : "doc.on.doc")
                            .font(.system(size: 11, weight: .semibold))
                        Text(isCopied ? "已复制" : "复制")
                            .font(.system(size: 11, weight: .medium))
                    }
            .foregroundColor(isCopied ? AppTheme.Icons.success : Color.white.opacity(0.8))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.white.opacity(0.12))
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xs))
                }
            }
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.sm)
            .background(AppTheme.Colors.codeBlockHeader)

            Divider()
                .background(Color.white.opacity(0.1))

            // Code Lines Content
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                    let lines = snippet.code.components(separatedBy: "\n")
                    VStack(alignment: .trailing, spacing: 3) {
                        ForEach(0..<lines.count, id: \.self) { idx in
                            Text("\(idx + 1)")
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundColor(Color.gray.opacity(0.6))
                        }
                    }

                    VStack(alignment: .leading, spacing: 3) {
                        ForEach(0..<lines.count, id: \.self) { idx in
                            Text(lines[idx])
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundColor(AppTheme.Colors.codeSyntaxForeground)
                        }
                    }
                }
                .padding(AppTheme.Spacing.md)
            }
            .background(AppTheme.Colors.codeBlockBackground)
        }
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        .pressBorderGlow(cornerRadius: AppTheme.Radius.md)
    }

    private func copyCode() {
        #if os(iOS)
        UIPasteboard.general.string = snippet.code
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        #endif
        isCopied = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            isCopied = false
        }
    }
}

// MARK: - Mathematical Formula Card
public struct FormulaCard: View {
    public let formula: String

    public init(formula: String) {
        self.formula = formula
    }

    public var body: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: "function")
                .font(.system(size: 14, weight: .bold))
                    .foregroundColor(AppTheme.Icons.intelligence)

            ScrollView(.horizontal, showsIndicators: false) {
                Text(formula)
                    .font(.system(size: 13, weight: .medium, design: .serif))
                    .italic()
                    .foregroundColor(AppTheme.Colors.textPrimary)
            }
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.accent.opacity(0.08))
        .overlay(
            RoundedRectangle(cornerRadius: AppTheme.Radius.md)
                .stroke(AppTheme.Colors.accent.opacity(0.2), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
        .pressBorderGlow(cornerRadius: AppTheme.Radius.md)
    }
}
