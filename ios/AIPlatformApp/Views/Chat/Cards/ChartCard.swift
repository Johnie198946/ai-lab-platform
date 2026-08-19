//
//  ChartCard.swift
//  AIPlatformApp
//
//  图表卡片：Swift Charts 原生渲染，仅支持 line / bar，
//  Quantum Spectrum 序列（Cyan → Blue → Violet），不挪用红黄绿警示色。
//

import SwiftUI
import Charts

public struct ChartCard: View {
    public let block: ChartBlock

    public init(block: ChartBlock) {
        self.block = block
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            // 标题行
            HStack(spacing: AppTheme.Spacing.xs) {
                Image(systemName: block.chartType == .line ? "chart.xyaxis.line" : "chart.bar.fill")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(AppTheme.Icons.interactive)
                Text(block.title)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.textPrimary)
                Spacer()
            }

            // Swift Charts 画布
            chartContent
                .frame(height: 150)

            // 摘要行
            if !block.summary.isEmpty {
                Text(block.summary)
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                    .lineSpacing(2)
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

    @ViewBuilder
    private var chartContent: some View {
        Chart {
            ForEach(Array(block.series.enumerated()), id: \.element.id) { index, series in
                ForEach(series.points) { point in
                    if block.chartType == .line {
                        LineMark(
                            x: .value("时间", point.label),
                            y: .value("数值", point.value)
                        )
                        .foregroundStyle(seriesColor(index))
                        .symbol(Circle().strokeBorder(lineWidth: 2))
                        .interpolationMethod(.catmullRom)
                    } else {
                        BarMark(
                            x: .value("时间", point.label),
                            y: .value("数值", point.value)
                        )
                        .foregroundStyle(seriesColor(index))
                        .cornerRadius(AppTheme.Radius.xs)
                    }
                }
            }
        }
        .chartYScale(domain: 0...maxValue(block.series) * 1.2)
    }

    /// Quantum Spectrum 序列：Cyan → Blue → Violet（严禁红黄绿警示色）
    private func seriesColor(_ index: Int) -> Color {
        switch index {
        case 0: return AppTheme.Colors.quantumCyan
        case 1: return AppTheme.Colors.quantumBlue
        default: return AppTheme.Colors.quantumViolet
        }
    }

    private func maxValue(_ series: [ChartSeries]) -> Double {
        let all = series.flatMap(\.points).map(\.value)
        return all.max() ?? 100
    }
}

// MARK: - Xcode #Preview

#Preview("ChartCard - Light") {
    ChartCard(
        block: ChartBlock(
            title: "近 6 月热度",
            chartType: .line,
            series: [
                ChartSeries(name: "A", points: [
                    ChartPoint(label: "1月", value: 10),
                    ChartPoint(label: "2月", value: 20),
                    ChartPoint(label: "3月", value: 30)
                ]),
                ChartSeries(name: "B", points: [
                    ChartPoint(label: "1月", value: 5),
                    ChartPoint(label: "2月", value: 15),
                    ChartPoint(label: "3月", value: 25)
                ])
            ],
            summary: "摘要行"
        )
    )
    .padding()
    .background(AppTheme.Colors.groupedBackground)
}
