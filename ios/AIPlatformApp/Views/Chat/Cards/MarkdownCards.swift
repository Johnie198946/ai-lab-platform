//
//  MarkdownCards.swift
//  AIPlatformApp
//
//  Markdown 卡片渲染组件：极简 SwiftUI 原生流式卡片容器。
//  零自定义字符串拼接，利用 SwiftUI 原生 LocalizedStringKey 零开销高帧率渲染。
//

import SwiftUI

// MARK: - 极简 Markdown 文本（利用原生 LocalizedStringKey 零开销渲染加粗/斜体/代码）

public struct MarkdownText: View {
    public let text: String
    public var font: Font = .system(size: 15)
    public var color: Color = AppTheme.Colors.textPrimary

    public init(_ text: String, font: Font = .system(size: 15), color: Color = AppTheme.Colors.textPrimary) {
        self.text = text
        self.font = font
        self.color = color
    }

    public var body: some View {
        Text(LocalizedStringKey(text))
            .font(font)
            .foregroundColor(color)
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
            MarkdownText(text)
                .fixedSize(horizontal: false, vertical: true)
                .lineSpacing(3)
        case .bulletList(let items):
            MarkdownBulletListCard(items: items)
        case .numberedList(let items):
            MarkdownNumberedListCard(items: items)
        case .codeBlock(let language, let code):
            CodeBlockCard(snippet: CodeSnippet(language: language ?? "text", code: code))
        case .quote(let text):
            MarkdownQuoteCard(text: text)
        case .divider:
            Rectangle()
                .fill(AppTheme.Colors.border.opacity(0.5))
                .frame(height: 0.5)
                .padding(.vertical, AppTheme.Spacing.xs)
        case .table(let tableBlock):
            TableCard(block: tableBlock)
        case .chart(let chartBlock):
            ChartCard(block: chartBlock)
        case .sourceCitations(let items):
            SourceCitationsCard(items: items)
        }
    }
}

// MARK: - 标题卡（分级视觉：L1 大标题渐变条 + L2 中文序号蓝条 + L3 青色点）

private struct MarkdownHeadingCard: View {
    let level: Int
    let text: String

    var body: some View {
        HStack(alignment: .center, spacing: 8) {
            if level == 1 {
                RoundedRectangle(cornerRadius: 2)
                    .fill(AppTheme.Colors.quantumGradient)
                    .frame(width: 4, height: 18)
            } else {
                RoundedRectangle(cornerRadius: 2)
                    .fill(AppTheme.Colors.quantumBlue)
                    .frame(width: 3.5, height: 16)
            }

            MarkdownText(
                text,
                font: .system(size: level == 1 ? 19 : (level == 2 ? 17 : 15.5), weight: .bold),
                color: AppTheme.Colors.textPrimary
            )
        }
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
                MarkdownText(text, font: .system(size: 14, weight: .medium))
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

// MARK: - 列表卡

private struct MarkdownBulletListCard: View {
    let items: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                    Circle()
                        .fill(AppTheme.Colors.quantumCyan)
                        .frame(width: 5, height: 5)
                        .padding(.top, 7)
                    MarkdownText(item, font: .system(size: 14.5))
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }
}

private struct MarkdownNumberedListCard: View {
    let items: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                    Text("\(index + 1).")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(AppTheme.Colors.quantumBlue)
                        .frame(minWidth: 22, alignment: .leading)
                    MarkdownText(item, font: .system(size: 14.5))
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
            MarkdownText(text, font: .system(size: 14), color: AppTheme.Colors.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(AppTheme.Spacing.sm)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.Colors.quantumViolet.opacity(0.04))
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
    }
}

// MARK: - 知识库来源条目卡（视觉区分：图书图标 + 次级色 + 紧凑单项）

public struct SourceCitationsCard: View {
    public let items: [String]

    public init(items: [String]) {
        self.items = items
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 5) {
                Image(systemName: "books.vertical.fill")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.quantumCyan)
                Text("来源条目")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundColor(AppTheme.Colors.quantumCyan)
            }

            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                HStack(alignment: .top, spacing: 6) {
                    Image(systemName: "doc.text.magnifyingglass")
                        .font(.system(size: 10))
                        .foregroundColor(AppTheme.Colors.textTertiary)
                        .padding(.top, 2)
                    Text(item.trimmingCharacters(in: CharacterSet(charactersIn: "`*- ")))
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundColor(AppTheme.Colors.textSecondary)
                        .lineLimit(2)
                }
            }
        }
        .padding(AppTheme.Spacing.sm)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.Colors.quantumCyan.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                .stroke(AppTheme.Colors.quantumCyan.opacity(0.25), lineWidth: 0.5)
        )
    }
}
