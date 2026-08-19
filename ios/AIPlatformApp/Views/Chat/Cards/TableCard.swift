//
//  TableCard.swift
//  AIPlatformApp
//
//  表格插件：通用数据表 + 移动端需求确认单双列自适应布局。
//

import SwiftUI

public struct TableCard: View {
    public let block: TableBlock
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    public init(block: TableBlock) {
        self.block = block
    }

    public var body: some View {
        Group {
            if isRequirementConfirmation {
                requirementConfirmationCard
            } else {
                genericTableCard
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(isRequirementConfirmation ? "需求确认单" : block.title)
    }

    private var isRequirementConfirmation: Bool {
        block.title.contains("需求确认")
            || block.headers.first?.contains("确认维度") == true
            || block.headers.contains(where: { $0.contains("已确认需求") })
    }

    private var requirementConfirmationCard: some View {
        VStack(alignment: .leading, spacing: 0) {
            requirementHeader
            if !dynamicTypeSize.isAccessibilitySize {
                requirementColumnHeader
            }

            ForEach(Array(block.rows.enumerated()), id: \.offset) { index, row in
                requirementRow(row, index: index)
            }

            HStack(spacing: AppTheme.Spacing.xs) {
                Image(systemName: "info.circle")
                    .font(.caption.weight(.semibold))
                Text("确认后进入方案设计；如有偏差，可选择“需要修改”。")
                    .font(.caption)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .foregroundColor(AppTheme.Icons.secondary)
            .padding(.horizontal, AppTheme.Spacing.xl)
            .padding(.vertical, AppTheme.Spacing.md)
            .background(AppTheme.Colors.secondaryBackground.opacity(0.55))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                .stroke(AppTheme.Colors.quantumBlue.opacity(colorScheme == .dark ? 0.42 : 0.24), lineWidth: 1)
        )
        .shadow(
            color: Color.black.opacity(colorScheme == .dark ? 0.20 : 0.08),
            radius: 22,
            x: 0,
            y: 6
        )
    }

    private var requirementHeader: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            ZStack {
                RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous)
                    .fill(AppTheme.Colors.quantumGradient)
                    .frame(width: 36, height: 36)
                Image(systemName: "checklist.checked")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(AppTheme.Icons.onAccent)
            }

            VStack(alignment: .leading, spacing: 2) {
                Text("需求确认单")
                    .font(.headline.weight(.semibold))
                    .foregroundColor(AppTheme.Colors.textPrimary)
                Text("Drill-me 已完成多轮需求收敛")
                    .font(.caption)
                    .foregroundColor(AppTheme.Colors.textSecondary)
            }

            Spacer(minLength: AppTheme.Spacing.sm)

            Label("待确认", systemImage: "checkmark.seal")
                .font(.caption2.weight(.semibold))
                .foregroundColor(AppTheme.Icons.interactive)
                .padding(.horizontal, AppTheme.Spacing.sm)
                .padding(.vertical, 5)
                .background(AppTheme.Colors.quantumBlue.opacity(0.09))
                .clipShape(Capsule())
        }
        .padding(AppTheme.Spacing.xl)
        .background(
            LinearGradient(
                colors: [
                    AppTheme.Colors.quantumBlue.opacity(colorScheme == .dark ? 0.13 : 0.08),
                    AppTheme.Colors.quantumViolet.opacity(colorScheme == .dark ? 0.08 : 0.04),
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
    }

    private var requirementColumnHeader: some View {
        HStack(spacing: 0) {
            Text(block.headers.first ?? "确认维度")
                .frame(width: 96, alignment: .leading)
            Text(block.headers.dropFirst().first ?? "已确认需求")
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .font(.caption.weight(.semibold))
        .foregroundColor(AppTheme.Colors.textSecondary)
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.sm)
        .background(AppTheme.Colors.secondaryBackground.opacity(0.72))
    }

    private func requirementRow(_ row: [String], index: Int) -> some View {
        let dimension = row.first ?? "—"
        let detail = row.dropFirst().joined(separator: " · ")
        return Group {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    requirementKey(dimension)
                    requirementValue(detail)
                }
            } else {
                HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                    requirementKey(dimension)
                        .frame(width: 104, alignment: .leading)
                    requirementValue(detail)
                }
            }
        }
        .padding(.horizontal, AppTheme.Spacing.xl)
        .padding(.vertical, AppTheme.Spacing.md)
        .background(index.isMultiple(of: 2) ? Color.clear : AppTheme.Colors.secondaryBackground.opacity(0.32))
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(AppTheme.Colors.border.opacity(0.75))
                .frame(height: 0.5)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(dimension)：\(detail)")
    }

    private func requirementKey(_ dimension: String) -> some View {
        HStack(alignment: .top, spacing: 6) {
            Image(systemName: "checkmark.circle.fill")
                .font(.caption)
                .foregroundColor(AppTheme.Icons.success)
                .padding(.top, 2)
            Text(dimension)
                .font(AppTheme.Typography.label)
                .foregroundColor(AppTheme.Colors.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func requirementValue(_ detail: String) -> some View {
        Text(LocalizedStringKey(detail.isEmpty ? "—" : detail))
            .font(AppTheme.Typography.body)
            .foregroundColor(AppTheme.Colors.textPrimary)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var genericTableCard: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            // 标题行
            HStack(spacing: AppTheme.Spacing.xs) {
                Image(systemName: "tablecells")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(AppTheme.Icons.interactive)
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
    ScrollView {
        VStack(spacing: 20) {
            TableCard(
                block: TableBlock(
                    title: "需求确认单",
                    headers: ["确认维度", "已确认需求"],
                    rows: [
                        ["产品形态", "酒店电视端 WebApp"],
                        ["核心场景", "迎宾、客房服务、点餐购物"],
                        ["MVP 范围", "核心三件套 + 多语言与周边推荐"],
                        ["技术路线", "HTML5 + 遥控器焦点导航 + WebView"],
                        ["验收标准", "电视端可完整演示主流程"],
                    ]
                )
            )
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
        }
        .padding()
        .background(AppTheme.Colors.groupedBackground)
    }
}
