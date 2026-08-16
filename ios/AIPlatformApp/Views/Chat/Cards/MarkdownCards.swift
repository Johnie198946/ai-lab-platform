//
//  MarkdownCards.swift
//  AIPlatformApp
//
//  Markdown 卡片渲染组件：将 MarkdownBlockParser 解析出的 8 类块，
//  渲染为精致的流式卡片容器（彻底消除原始 Markdown 横线与文本堆砌）。
//

import SwiftUI

// MARK: - 行内富文本（Code Span 优先 + 粗体/斜体）

public struct MarkdownInlineText: View {
    public let segments: [InlineSegment]
    public var baseFont: Font = .system(size: 15)
    public var baseColor: Color = AppTheme.Colors.textPrimary

    public init(segments: [InlineSegment], baseFont: Font = .system(size: 15), baseColor: Color = AppTheme.Colors.textPrimary) {
        self.segments = segments
        self.baseFont = baseFont
        self.baseColor = baseColor
    }

    public var body: some View {
        segments.reduce(Text("")) { acc, seg in
            acc + segmentText(seg)
        }
        .font(baseFont)
        .foregroundColor(baseColor)
    }

    private func segmentText(_ seg: InlineSegment) -> Text {
        switch seg {
        case .text(let s): return Text(s)
        case .code(let s):
            return Text(s)
                .font(.system(size: 13, design: .monospaced))
                .foregroundColor(AppTheme.Colors.quantumViolet)
        case .bold(let s): return Text(s).bold()
        case .italic(let s): return Text(s).italic()
        }
    }
}

// MARK: - 块级卡片分发器

public struct MarkdownBlockCard: View {
    public let block: MarkdownBlock

    public init(block: MarkdownBlock) {
        self.block = block
    }

    public var body: some View {
        switch block {
        case .heading(let level, let text):
            MarkdownHeadingCard(level: level, text: text)
        case .callout(let label, let text):
            MarkdownCalloutCard(label: label, text: text)
        case .paragraph(let text):
            MarkdownParagraphCard(text: text)
        case .bulletList(let items):
            MarkdownBulletListCard(items: items)
        case .numberedList(let items):
            MarkdownNumberedListCard(items: items)
        case .codeBlock(let language, let code):
            CodeBlockCard(snippet: CodeSnippet(language: language ?? "text", code: code))
        case .quote(let text):
            MarkdownQuoteCard(text: text)
        case .divider:
            MarkdownDividerCard()
        }
    }
}

// MARK: - 标题卡

private struct MarkdownHeadingCard: View {
    let level: Int
    let text: String

    private var fontSize: CGFloat {
        switch level {
        case 1: return 20
        case 2: return 18
        case 3: return 16
        default: return 15
        }
    }

    private var fontWeight: Font.Weight {
        level <= 2 ? .bold : .semibold
    }

    var body: some View {
        MarkdownInlineText(
            segments: MarkdownBlockParser.parseInline(text),
            baseFont: .system(size: fontSize, weight: fontWeight),
            baseColor: AppTheme.Colors.textPrimary
        )
        .padding(.top, level <= 2 ? AppTheme.Spacing.xs : 2)
    }
}

// MARK: - 语义结论卡（Callout）

private struct MarkdownCalloutCard: View {
    let label: String
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            Image(systemName: "sparkles")
                .font(.system(size: 13, weight: .bold))
                .foregroundColor(AppTheme.Colors.quantumBlue)
                .padding(.top, 2)

            VStack(alignment: .leading, spacing: 3) {
                Text(label)
                    .font(.system(size: 11, weight: .bold))
                    .foregroundColor(AppTheme.Colors.quantumBlue)
                if !text.isEmpty {
                    MarkdownInlineText(
                        segments: MarkdownBlockParser.parseInline(text),
                        baseFont: .system(size: 13, weight: .medium),
                        baseColor: AppTheme.Colors.textPrimary
                    )
                }
            }
            Spacer(minLength: 0)
        }
        .padding(AppTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.Colors.quantumBlue.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                .stroke(AppTheme.Colors.quantumBlue.opacity(0.28), lineWidth: 0.8)
        )
    }
}

// MARK: - 段落卡

private struct MarkdownParagraphCard: View {
    let text: String

    var body: some View {
        MarkdownInlineText(segments: MarkdownBlockParser.parseInline(text))
            .lineSpacing(4)
            .fixedSize(horizontal: false, vertical: true)
    }
}

// MARK: - 无序列表卡

private struct MarkdownBulletListCard: View {
    let items: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                    Circle()
                        .fill(AppTheme.Colors.quantumBlue)
                        .frame(width: 5, height: 5)
                        .padding(.top, 7)
                    MarkdownInlineText(segments: MarkdownBlockParser.parseInline(item))
                        .lineSpacing(3)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }
}

// MARK: - 有序列表卡

private struct MarkdownNumberedListCard: View {
    let items: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(items.enumerated()), id: \.offset) { idx, item in
                HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                    Text("\(idx + 1).")
                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                        .foregroundColor(AppTheme.Colors.quantumBlue)
                        .frame(minWidth: 18, alignment: .trailing)
                    MarkdownInlineText(segments: MarkdownBlockParser.parseInline(item))
                        .lineSpacing(3)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }
}

// MARK: - 引用卡

private struct MarkdownQuoteCard: View {
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            Rectangle()
                .fill(AppTheme.Colors.quantumCyan.opacity(0.6))
                .frame(width: 3)
            MarkdownInlineText(
                segments: MarkdownBlockParser.parseInline(text),
                baseFont: .system(size: 13),
                baseColor: AppTheme.Colors.textSecondary
            )
            .italic()
            .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, 2)
    }
}

// MARK: - 分隔线卡（优雅间距）

private struct MarkdownDividerCard: View {
    var body: some View {
        Rectangle()
            .fill(AppTheme.Colors.border)
            .frame(height: 1)
            .padding(.vertical, AppTheme.Spacing.xs)
    }
}
