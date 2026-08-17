//
//  MarkdownCards.swift
//  AIPlatformApp
//
//  Markdown 卡片渲染组件：将 MarkdownBlockParser 解析出的 10 类块，
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
        case .table(let tableBlock):
            TableCard(block: tableBlock)
        case .chart(let chartBlock):
            ChartCard(block: chartBlock)
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
                MarkdownInlineText(
                    segments: MarkdownBlockParser.parseInline(text),
                    baseFont: .system(size: 14, weight: .medium),
                    baseColor: AppTheme.Colors.textPrimary
                )
                .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(AppTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            LinearGradient(
                colors: [
                    AppTheme.Colors.quantumBlue.opacity(0.10),
                    AppTheme.Colors.quantumViolet.opacity(0.04)
                ],
                startPoint: .leading,
                endPoint: .trailing
            )
        )
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                .stroke(AppTheme.Colors.quantumBlue.opacity(0.25), lineWidth: 0.5)
        )
    }
}

// MARK: - 段落卡

private struct MarkdownParagraphCard: View {
    let text: String

    var body: some View {
        MarkdownInlineText(
            segments: MarkdownBlockParser.parseInline(text),
            baseFont: .system(size: 15),
            baseColor: AppTheme.Colors.textPrimary
        )
        .fixedSize(horizontal: false, vertical: true)
        .lineSpacing(3)
    }
}

// MARK: - 列表卡

private struct MarkdownBulletListCard: View {
    let items: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                    Circle()
                        .fill(AppTheme.Colors.quantumCyan)
                        .frame(width: 5, height: 5)
                        .padding(.top, 7)
                    MarkdownInlineText(
                        segments: MarkdownBlockParser.parseInline(item),
                        baseFont: .system(size: 14),
                        baseColor: AppTheme.Colors.textPrimary
                    )
                    .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }
}

private struct MarkdownNumberedListCard: View {
    let items: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                    Text("\(index + 1).")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(AppTheme.Colors.quantumBlue)
                        .frame(minWidth: 22, alignment: .leading)
                    MarkdownInlineText(
                        segments: MarkdownBlockParser.parseInline(item),
                        baseFont: .system(size: 14),
                        baseColor: AppTheme.Colors.textPrimary
                    )
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
                .fill(AppTheme.Colors.quantumViolet.opacity(0.4))
                .frame(width: 3)
            MarkdownInlineText(
                segments: MarkdownBlockParser.parseInline(text),
                baseFont: .system(size: 14),
                baseColor: AppTheme.Colors.textSecondary
            )
            .fixedSize(horizontal: false, vertical: true)
        }
        .padding(AppTheme.Spacing.sm)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.Colors.quantumViolet.opacity(0.04))
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
    }
}

// MARK: - 分隔卡

private struct MarkdownDividerCard: View {
    var body: some View {
        HStack(spacing: 8) {
            Rectangle()
                .fill(AppTheme.Colors.border.opacity(0.5))
                .frame(height: 0.5)
        }
        .padding(.vertical, AppTheme.Spacing.xs)
    }
}
