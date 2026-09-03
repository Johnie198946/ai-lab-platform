//
//  MessageBubbleView.swift
//  AIPlatformApp
//
//  Markdown Message Bubble with Syntax-Highlighted Code Cards, Math Formulas & Context Menu
//  统一 blocks 数组序渲染 7 类块 + 真实思维链卡片 + 富媒体引用上下文
//  ChatGPT / Claude 规范：思维链胶囊置顶 -> 正文卡片居中 -> 操作条在底部（有正文时才展示）
//

import SwiftUI

enum StreamTextChunker {
    static func chunks(_ text: String, size: Int = 1_600) -> [String] {
        guard !text.isEmpty, size > 0 else { return [] }
        var result: [String] = []
        var start = text.startIndex
        while start < text.endIndex {
            let end = text.index(start, offsetBy: size, limitedBy: text.endIndex)
                ?? text.endIndex
            result.append(String(text[start..<end]))
            start = end
        }
        return result
    }
}

struct BoundedTextPreview: Equatable {
    let content: String
    let omittedPrefix: Bool
}

enum LongMessagePresentation {
    static let longAnswerCharacterThreshold = 4_000
    static let streamingCharacterLimit = 2_400
    static let streamingExpansionStep = 2_400
    static let collapsedCharacterLimit = 800

    static func isLong(_ text: String, limit: Int = longAnswerCharacterThreshold) -> Bool {
        guard limit >= 0 else { return true }
        guard let boundary = text.index(
            text.startIndex,
            offsetBy: limit,
            limitedBy: text.endIndex
        ) else { return false }
        return boundary != text.endIndex
    }

    static func streamingPreview(_ text: String, limit: Int = streamingCharacterLimit) -> BoundedTextPreview {
        guard limit > 0 else {
            return BoundedTextPreview(content: "", omittedPrefix: !text.isEmpty)
        }
        guard isLong(text, limit: limit) else {
            return BoundedTextPreview(content: text, omittedPrefix: false)
        }
        let start = text.index(text.endIndex, offsetBy: -limit)
        return BoundedTextPreview(content: String(text[start...]), omittedPrefix: true)
    }

    static func collapsedPreview(_ text: String, limit: Int = collapsedCharacterLimit) -> String {
        guard limit > 0 else { return "" }
        guard isLong(text, limit: limit) else { return text }
        let boundary = text.index(text.startIndex, offsetBy: limit)
        let rawPrefix = String(text[..<boundary])
        let minimumBoundary = rawPrefix.index(
            rawPrefix.startIndex,
            offsetBy: max(0, limit / 2),
            limitedBy: rawPrefix.endIndex
        ) ?? rawPrefix.startIndex
        if let paragraphBreak = rawPrefix.range(of: "\n\n", options: .backwards),
           paragraphBreak.lowerBound >= minimumBoundary {
            return String(rawPrefix[..<paragraphBreak.lowerBound])
        }
        return rawPrefix
    }

    static func nextStreamingLimit(current: Int, contentCount: Int) -> Int {
        guard current < contentCount else { return max(0, contentCount) }
        return current + min(streamingExpansionStep, contentCount - current)
    }
}

enum ChatStreamingPerformancePolicy {
    static func flushDelayNanoseconds(currentUTF8Count: Int) -> UInt64 {
        switch currentUTF8Count {
        case ..<4_000: return 160_000_000
        case ..<12_000: return 250_000_000
        default: return 400_000_000
        }
    }

    static func typewriterBatchSize(totalCharacterCount: Int) -> Int {
        guard totalCharacterCount > 0 else { return 1 }
        return max(3, (totalCharacterCount + 23) / 24)
    }

    static let typewriterDelayNanoseconds: UInt64 = 50_000_000
}

public struct MessageBubbleView: View {
    public let message: ChatMessage
    public var context: PluginRenderContext? = nil
    public var onQuoteFollowUp: ((QuotedContext) -> Void)? = nil
    public var onRegenerate: ((String) -> Void)? = nil
    public var onStartTopic: ((ChatMessage) -> Void)? = nil

    @State private var isCopied: Bool = false
    @State private var quoteFragmentDraft = ""
    @State private var isChoosingQuoteFragment = false
    @State private var isShowingFullAnswer = false
    @State private var streamingCharacterLimit = LongMessagePresentation.streamingCharacterLimit

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
        .sheet(isPresented: $isChoosingQuoteFragment) {
            QuoteFragmentPicker(sourceText: message.content, text: $quoteFragmentDraft) {
                let fragment = quoteFragmentDraft.trimmingCharacters(in: .whitespacesAndNewlines)
                if !fragment.isEmpty { onQuoteFollowUp?(QuotedContext(text: fragment)) }
                isChoosingQuoteFragment = false
            }
            .presentationDetents([.medium, .large])
            .presentationDragIndicator(.visible)
        }
        .sheet(isPresented: $isShowingFullAnswer) {
            LongAnswerSheet(messageId: message.id, content: message.content)
        }
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
                    if message.isStreaming, !trimmed.isEmpty {
                        // Stable chunks keep old layout nodes unchanged while only
                        // a bounded tail grows. Keeping the rendered subtree capped
                        // prevents a very long answer from monopolizing layout.
                        if streamingPreview.omittedPrefix {
                            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                                Label("前文已折叠，Hermes 仍在后台生成", systemImage: "text.append")
                                    .font(AppTheme.Typography.supporting.weight(.medium))
                                    .foregroundStyle(AppTheme.Colors.textSecondary)
                                Button {
                                    streamingCharacterLimit = LongMessagePresentation.nextStreamingLimit(
                                        current: streamingCharacterLimit,
                                        contentCount: message.content.count
                                    )
                                } label: {
                                    Label("向前展开一部分", systemImage: "chevron.up")
                                        .font(AppTheme.Typography.supporting.weight(.semibold))
                                }
                                .buttonStyle(SoftButtonStyle())
                                .accessibilityHint("每次多显示一段已收到的内容，不影响 Hermes 继续生成")
                            }
                        }
                        ForEach(Array(streamingTextChunks.enumerated()), id: \.offset) { _, chunk in
                            Text(chunk)
                                .font(AppTheme.Typography.body)
                                .foregroundColor(AppTheme.Colors.textPrimary)
                        }
                    } else if !completedMarkdownBlocks.isEmpty {
                        // MarkdownBlock.id is content-derived; use parse order as
                        // local identity so repeated paragraphs stay distinct.
                        ForEach(Array(completedMarkdownBlocks.enumerated()), id: \.offset) { _, block in
                            MarkdownBlockCard(block: block)
                        }
                    } else if !trimmed.isEmpty {
                        Text(completedDisplayContent)
                            .font(AppTheme.Typography.body)
                            .foregroundColor(AppTheme.Colors.textPrimary)
                    }

                    if isLongCompletedAnswer {
                        Button {
                            isShowingFullAnswer = true
                        } label: {
                            HStack(spacing: AppTheme.Spacing.xs) {
                                Text("展开全文")
                                Image(systemName: "arrow.up.left.and.arrow.down.right")
                            }
                            .font(AppTheme.Typography.supporting.weight(.semibold))
                            .foregroundStyle(AppTheme.Colors.quantumBlue)
                            .frame(maxWidth: .infinity, minHeight: 44)
                            .background(AppTheme.Colors.surfaceTint, in: Capsule())
                        }
                        .buttonStyle(SoftButtonStyle())
                        .accessibilityHint("在独立页面中查看完整回答")
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

    /// 流式期不解析 Markdown；完成态短回答解析全文，长回答只解析有界预览。
    private var isLongCompletedAnswer: Bool {
        !message.isStreaming && LongMessagePresentation.isLong(message.content)
    }

    private var completedDisplayContent: String {
        isLongCompletedAnswer
            ? LongMessagePresentation.collapsedPreview(message.content)
            : message.content
    }

    private var completedMarkdownBlocks: [MarkdownBlock] {
        guard !message.isStreaming, !message.content.isEmpty else { return [] }
        let suffix = isLongCompletedAnswer
            ? "collapsed_\(completedDisplayContent.hashValue)"
            : "done_\(message.content.hashValue)"
        return MarkdownBlockParser.shared.parse(completedDisplayContent, messageId: "\(message.id)_\(suffix)")
    }

    private var streamingPreview: BoundedTextPreview {
        LongMessagePresentation.streamingPreview(
            message.content,
            limit: streamingCharacterLimit
        )
    }

    private var streamingTextChunks: [String] {
        StreamTextChunker.chunks(streamingPreview.content)
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
                Label("引用全文追问", systemImage: "quote.bubble")
            }
            Button {
                quoteFragmentDraft = ""
                isChoosingQuoteFragment = true
            } label: {
                Label("选择片段引用", systemImage: "selection.pin.in.out")
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

private struct LongAnswerSheet: View {
    let messageId: String
    let content: String
    let cacheKey: String
    @Environment(\.dismiss) private var dismiss
    @State private var isCopied = false

    init(messageId: String, content: String) {
        self.messageId = messageId
        self.content = content
        self.cacheKey = "\(messageId)_full_\(content.hashValue)"
    }

    private var blocks: [MarkdownBlock] {
        MarkdownBlockParser.shared.parse(content, messageId: cacheKey)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                    // Parse once into semantic blocks, then instantiate each Markdown
                    // view lazily. Tables, headings, lists and links keep their meaning
                    // without building one monolithic Markdown layout tree.
                    ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                        MarkdownBlockCard(block: block)
                    }
                }
                .textSelection(.enabled)
                .frame(maxWidth: AppTheme.Metrics.readableContentWidth, alignment: .leading)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(AppTheme.Spacing.md)
            }
            .background(AppTheme.Colors.background)
            .navigationTitle("回答全文")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("关闭") { dismiss() }
                }
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        #if os(iOS)
                        UIPasteboard.general.string = content
                        UIImpactFeedbackGenerator(style: .light).impactOccurred()
                        #endif
                        isCopied = true
                    } label: {
                        Label(isCopied ? "已复制" : "复制全文", systemImage: isCopied ? "checkmark" : "doc.on.doc")
                    }
                    .accessibilityHint("复制完整回答到剪贴板")
                }
            }
        }
    }
}

private struct QuoteFragmentPicker: View {
    let sourceText: String
    @Binding var text: String
    let onConfirm: () -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                Text("原文（长按选择并复制需要的词、句或段落）")
                    .font(.footnote)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                ScrollView {
                    Text(sourceText)
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(maxHeight: 210)
                .padding(AppTheme.Spacing.sm)
                .background(AppTheme.Colors.surfaceTint)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))

                Text("引用内容")
                    .font(.footnote.weight(.semibold))
                TextEditor(text: $text)
                    .font(AppTheme.Typography.body)
                    .frame(minHeight: 80, maxHeight: 150)
                    .overlay(alignment: .topLeading) {
                        if text.isEmpty {
                            Text("粘贴或输入要引用的片段")
                                .foregroundStyle(AppTheme.Colors.textTertiary)
                                .padding(.horizontal, 5)
                                .padding(.vertical, 8)
                                .allowsHitTesting(false)
                        }
                    }
                    .padding(AppTheme.Spacing.sm)
                    .background(AppTheme.Colors.surfaceTint)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
            }
            .padding(AppTheme.Spacing.md)
            .navigationTitle("选择引用片段")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("引用") { onConfirm() }
                        .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
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
