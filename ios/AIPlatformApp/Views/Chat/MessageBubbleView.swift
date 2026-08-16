//
//  MessageBubbleView.swift
//  AIPlatformApp
//
//  Markdown Message Bubble with Syntax-Highlighted Code Cards, Math Formulas & Context Menu
//  统一 blocks 数组序渲染 7 类块 + 真实思维链卡片 + 富媒体引用上下文（剔除 reasoning）
//  SwiftUI Native 60fps Rendering (Zero WebView Dependency)
//

import SwiftUI

public struct MessageBubbleView: View {
    public let message: ChatMessage
    public var onQuoteFollowUp: ((QuotedContext) -> Void)? = nil
    public var onRegenerate: ((String) -> Void)? = nil

    @State private var isCopied: Bool = false

    public init(
        message: ChatMessage,
        onQuoteFollowUp: ((QuotedContext) -> Void)? = nil,
        onRegenerate: ((String) -> Void)? = nil
    ) {
        self.message = message
        self.onQuoteFollowUp = onQuoteFollowUp
        self.onRegenerate = onRegenerate
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
                .font(.system(size: 15, weight: .regular))
                .foregroundColor(AppTheme.Colors.onPrimary)
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, AppTheme.Spacing.sm + 2)
                .background(AppTheme.Colors.userBubbleGradient)
                .clipShape(
                    RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                )
                .shadow(color: AppTheme.Colors.quantumBlue.opacity(0.35), radius: 8, x: 2, y: 4)
                .contextMenu {
                    contextMenuActions
                }
        }
    }

    // MARK: - Assistant Bubble
    private var assistantAvatarView: some View {
        // Quantum 品牌头像（自适应托盘 + 原色球体 + 暗色微光描边）
        QuantumAvatarView(size: 32)
            .padding(.top, 2)
    }

    private var assistantBubbleContent: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            // 演示样例标注
            if message.isDemoSample {
                demoSampleBadge
            }

            // Markdown 卡片流：解析 message.content 为 8 类块，逐块卡片化呈现（彻底消除原始横线/符号堆砌）
            if !markdownBlocks.isEmpty || message.isStreaming {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                    ForEach(markdownBlocks) { block in
                        MarkdownBlockCard(block: block)
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
            }

            // 富媒体块（单 ForEach 按 blocks 数组序）
            ForEach(message.blocks) { block in
                blockCard(block)
            }
        }
        .contextMenu {
            contextMenuActions
        }
    }

    /// 解析后的 Markdown 卡片块（NSCache 按 messageId + contentHash 缓存，避免长列表重复解析）。
    private var markdownBlocks: [MarkdownBlock] {
        MarkdownBlockParser.shared.parse(message.content, messageId: message.id)
    }

    // MARK: - 演示样例标注
    private var demoSampleBadge: some View {
        HStack(spacing: 4) {
            Image(systemName: "sparkles")
                .font(.system(size: 10, weight: .bold))
            Text("演示样例")
                .font(.system(size: 10, weight: .bold))
        }
        .foregroundColor(AppTheme.Colors.primary)
        .padding(.horizontal, AppTheme.Spacing.sm)
        .padding(.vertical, 3)
        .background(AppTheme.Colors.primary.opacity(0.08))
        .clipShape(Capsule())
    }

    // MARK: - 块分发（8 case 统一渲染）
    @ViewBuilder
    private func blockCard(_ block: MessageBlock) -> some View {
        switch block {
        case .code(let snippet): CodeBlockCard(snippet: snippet)
        case .formula(let formula): FormulaCard(formula: formula)
        case .chart(let chart): ChartCard(block: chart)
        case .image(let image): ImageCard(block: image)
        case .table(let table): TableCard(block: table)
        case .attachment(let attachment): AttachmentCard(block: attachment)
        case .reasoning(let steps): ReasoningCard(steps: steps)
        case .clarify(let clarify): ClarifyCard(block: clarify, onSubmit: nil)
        }
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
            if let summary = quote.blockSummary, !summary.isEmpty {
                Text(summary)
                    .font(.system(size: 10))
                    .foregroundColor(AppTheme.Colors.textTertiary)
                    .lineLimit(1)
                    .padding(.leading, AppTheme.Spacing.xs + 3)
            }
        }
        .padding(AppTheme.Spacing.xs)
        .background(AppTheme.Colors.secondaryBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xs))
    }

    private var streamingCursorView: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(AppTheme.Colors.primary)
                .frame(width: 6, height: 6)
            Circle()
                .fill(AppTheme.Colors.primary.opacity(0.6))
                .frame(width: 6, height: 6)
            Circle()
                .fill(AppTheme.Colors.primary.opacity(0.3))
                .frame(width: 6, height: 6)
        }
        .padding(.top, 2)
    }

    // MARK: - Context Menu
    @ViewBuilder
    private var contextMenuActions: some View {
        Button(action: {
            #if os(iOS)
            UIPasteboard.general.string = message.content
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            #endif
        }) {
            Label("复制全文", systemImage: "doc.on.doc")
        }

        Button(action: {
            onQuoteFollowUp?(message.quoteContext)
        }) {
            Label("引用此消息追问", systemImage: "quote.bubble")
        }

        if message.role == .assistant {
            Button(action: {
                onRegenerate?(message.id)
            }) {
                Label("重新生成", systemImage: "arrow.clockwise")
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
                    .foregroundColor(isCopied ? AppTheme.Colors.securityGreen : Color.white.opacity(0.8))
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
                    // Line numbers
                    let lines = snippet.code.components(separatedBy: "\n")
                    VStack(alignment: .trailing, spacing: 3) {
                        ForEach(0..<lines.count, id: \.self) { idx in
                            Text("\(idx + 1)")
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundColor(Color.gray.opacity(0.6))
                        }
                    }

                    // Code Text
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
                .foregroundColor(AppTheme.Colors.accent)

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
    }
}

// MARK: - Xcode #Preview

#Preview("MessageBubbleView - Light") {
    VStack(spacing: 16) {
        MessageBubbleView(message: MockData.messages[0])
        MessageBubbleView(message: MockData.messages[1])
    }
    .background(AppTheme.Colors.groupedBackground)
}

#Preview("MessageBubbleView - Dark") {
    VStack(spacing: 16) {
        MessageBubbleView(message: MockData.messages[0])
        MessageBubbleView(message: MockData.messages[1])
    }
    .background(AppTheme.Colors.groupedBackground)
    .preferredColorScheme(.dark)
}
