//
//  TableCard.swift
//  AIPlatformApp
//
//  表格卡片：标题 + Semibold 表头 + 发丝线 + 数据行 + 横向滚动。
//

import SwiftUI

public struct TableCard: View {
    public let block: TableBlock

    public init(block: TableBlock) {
        self.block = block
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            // 标题行
            HStack(spacing: AppTheme.Spacing.xs) {
                Image(systemName: "tablecells")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.primary)
                Text(block.title)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.textPrimary)
                Spacer()
            }

            // 横向滚动表格
            ScrollView(.horizontal, showsIndicators: false) {
                VStack(spacing: 0) {
                    // 表头（Semibold）
                    headerRow
                    Divider().background(AppTheme.Colors.border)
                    // 数据行
                    ForEach(Array(block.rows.enumerated()), id: \.offset) { _, row in
                        dataRow(row)
                        Divider().background(AppTheme.Colors.border)
                    }
                }
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
            }
        }
        .padding(AppTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                .stroke(AppTheme.Colors.border, lineWidth: 0.5)
        )
    }

    private var headerRow: some View {
        HStack(spacing: 0) {
            ForEach(Array(block.headers.enumerated()), id: \.offset) { index, header in
                Text(header)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.brandPrimary)
                    .frame(minWidth: 90, alignment: .leading)
                    .padding(.horizontal, AppTheme.Spacing.sm)
                    .padding(.vertical, AppTheme.Spacing.sm)
                    .background(AppTheme.Colors.brandPrimary.opacity(0.06))
                if index < block.headers.count - 1 {
                    Divider().background(AppTheme.Colors.border)
                }
            }
        }
    }

    private func dataRow(_ row: [String]) -> some View {
        HStack(spacing: 0) {
            ForEach(Array(row.enumerated()), id: \.offset) { index, cell in
                Text(cell)
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                    .frame(minWidth: 90, alignment: .leading)
                    .padding(.horizontal, AppTheme.Spacing.sm)
                    .padding(.vertical, AppTheme.Spacing.sm)
                if index < row.count - 1 {
                    Divider().background(AppTheme.Colors.border)
                }
            }
        }
    }
}

// MARK: - Xcode #Preview

#Preview("TableCard - Light") {
    TableCard(
        block: TableBlock(
            title: "竞品动态一览",
            headers: ["竞品", "动向", "影响"],
            rows: [
                ["OpenAI", "发布新模型", "成本下降"],
                ["Anthropic", "开放长上下文", "落地提速"]
            ]
        )
    )
    .padding()
    .background(AppTheme.Colors.groupedBackground)
}
