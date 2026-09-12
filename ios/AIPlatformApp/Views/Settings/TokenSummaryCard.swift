//
//  TokenSummaryCard.swift
//  AIPlatformApp
//
//  服务端 Token 用量账本：GET /api/v1/usage/summary?days=7|30|90
//

import SwiftUI
import Charts

public struct TokenSummaryCard: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var selectedDays = 30
    @State private var selectedDate: String?
    @State private var summary: UsageSummaryDTO?
    @State private var isLoading = false
    @State private var loadError: String?
    private let loadsRemotely: Bool

    public init() {
        loadsRemotely = true
    }

    init(summary: UsageSummaryDTO, selectedDays: Int = 30, selectedDate: String? = nil) {
        _selectedDays = State(initialValue: selectedDays)
        _selectedDate = State(initialValue: selectedDate)
        _summary = State(initialValue: summary)
        loadsRemotely = false
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                    Label("Token 监控", systemImage: "chart.bar.fill")
                        .font(.subheadline.weight(.semibold))
                        .foregroundColor(AppTheme.Colors.textSecondary)

                    if let summary {
                        HStack(alignment: .firstTextBaseline, spacing: AppTheme.Spacing.xs) {
                            Text(compact(summary.totalTokens))
                                .font(.system(.largeTitle, design: .rounded, weight: .semibold))
                                .monospacedDigit()
                                .foregroundColor(AppTheme.Colors.textPrimary)
                                .contentTransition(.numericText())
                            Text("tokens")
                                .font(.caption)
                                .foregroundColor(AppTheme.Colors.textTertiary)
                        }
                    }
                }

                Spacer()

                Menu {
                    Picker("统计周期", selection: $selectedDays) {
                        Text("7 天").tag(7)
                        Text("30 天").tag(30)
                        Text("90 天").tag(90)
                    }
                } label: {
                    HStack(spacing: AppTheme.Spacing.xs) {
                        Text("\(selectedDays) 天")
                        Image(systemName: "chevron.up.chevron.down")
                            .font(.caption2.weight(.bold))
                    }
                    .font(.subheadline.weight(.semibold))
                    .foregroundColor(AppTheme.Colors.textPrimary)
                    .padding(.horizontal, AppTheme.Spacing.sm)
                    .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                    .background(AppTheme.Colors.secondaryBackground)
                    .clipShape(Capsule())
                }
                .accessibilityLabel("统计周期，\(selectedDays) 天")
            }

            if isLoading && summary == nil {
                HStack {
                    Spacer()
                    ProgressView("正在加载用量账本…")
                    Spacer()
                }
                .frame(minHeight: 180)
            } else if let loadError {
                ContentUnavailableView {
                    Label("用量读取失败", systemImage: "exclamationmark.triangle")
                } description: {
                    Text(loadError)
                } actions: {
                    Button("重试") { Task { await loadUsage() } }
                }
                .frame(minHeight: 180)
            } else if let summary {
                usageContent(summary)
            }
        }
        .padding(AppTheme.Spacing.xl)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Metrics.panelRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Metrics.panelRadius, style: .continuous)
                .stroke(AppTheme.Colors.border.opacity(0.7), lineWidth: 0.5)
        }
        .shadow(color: Color.black.opacity(0.05), radius: 18, y: 8)
        .task(id: selectedDays) {
            guard loadsRemotely else { return }
            await loadUsage()
        }
    }

    @ViewBuilder
    private func usageContent(_ summary: UsageSummaryDTO) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            if summary.daily.isEmpty {
                Label("近 \(selectedDays) 天暂无调用记录", systemImage: "chart.bar.xaxis")
                    .font(AppTheme.Typography.supporting)
                    .foregroundColor(AppTheme.Colors.textSecondary)
                    .frame(maxWidth: .infinity, minHeight: 72)
            } else {
                dailyChart(summary.daily)
            }
        }
    }

    private func dailyChart(_ daily: [UsageDailyDTO]) -> some View {
        let maximum = max(daily.map(\.totalTokens).max() ?? 0, 1)

        return Chart {
            ForEach(daily) { day in
                BarMark(
                    x: .value("日期", day.date),
                    y: .value("Token", Double(day.totalTokens)),
                    width: .fixed(selectedDays == 90 ? 3 : selectedDays == 30 ? 7 : 13)
                )
                .foregroundStyle(by: .value("指标", "Token"))
                .cornerRadius(1)

                LineMark(
                    x: .value("日期", day.date),
                    y: .value("缓存占比", cacheShare(day) * Double(maximum))
                )
                .foregroundStyle(by: .value("指标", "缓存占比"))
                .lineStyle(StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
            }

            if let selectedDate,
               let day = daily.first(where: { $0.date == selectedDate }) {
                RuleMark(x: .value("选中日期", selectedDate))
                    .foregroundStyle(AppTheme.Colors.textSecondary.opacity(0.65))
                    .lineStyle(StrokeStyle(lineWidth: 1.5, dash: [5, 4]))
                    .annotation(
                        position: .overlay,
                        spacing: 0,
                        overflowResolution: .init(x: .fit(to: .chart), y: .disabled)
                    ) {
                        tooltip(day)
                            .transition(.scale(scale: 0.96, anchor: .top).combined(with: .opacity))
                            .allowsHitTesting(false)
                    }

                PointMark(
                    x: .value("选中日期", selectedDate),
                    y: .value("缓存占比", cacheShare(day) * Double(maximum))
                )
                .symbolSize(38)
                .foregroundStyle(AppTheme.Colors.securityGreen)
            }
        }
        .chartForegroundStyleScale([
            "Token": AppTheme.Colors.quantumCyan,
            "缓存占比": AppTheme.Colors.securityGreen
        ])
        .chartLegend(position: .bottom, alignment: .leading, spacing: AppTheme.Spacing.lg)
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 4)) { value in
                AxisValueLabel {
                    if let date = value.as(String.self) {
                        Text(date.suffix(5).replacingOccurrences(of: "-", with: "/"))
                    }
                }
            }
        }
        .chartYAxis {
            AxisMarks(position: .leading, values: .automatic(desiredCount: 4)) { value in
                AxisGridLine()
                    .foregroundStyle(AppTheme.Colors.border.opacity(0.65))
                AxisValueLabel {
                    if let tokens = value.as(Double.self) {
                        Text(compact(Int(tokens.rounded())))
                    }
                }
            }
            AxisMarks(
                position: .trailing,
                values: [0, Double(maximum) / 2, Double(maximum)]
            ) { value in
                AxisValueLabel {
                    if let scaled = value.as(Double.self) {
                        Text("\(Int((scaled / Double(maximum) * 100).rounded()))%")
                    }
                }
            }
        }
        .chartYScale(domain: 0...Double(maximum))
        .chartXSelection(value: $selectedDate)
        .animation(reduceMotion ? nil : AppTheme.Motion.spring, value: selectedDate)
        .accessibilityLabel("Token 每日总量与缓存占比趋势")
        .sensoryFeedback(.selection, trigger: selectedDate)
        .frame(height: 240)
    }

    private func tooltip(_ day: UsageDailyDTO) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
            HStack {
                Text(day.date)
                Spacer()
                Text("\(grouped(day.totalTokens)) tokens")
            }
            .font(AppTheme.Typography.label)

            Grid(horizontalSpacing: AppTheme.Spacing.md, verticalSpacing: AppTheme.Spacing.xs) {
                GridRow {
                    tooltipMetric("输入", day.inputTokens)
                    tooltipMetric("输出", day.outputTokens)
                }
                GridRow {
                    tooltipMetric("缓存读取", day.cacheReadTokens)
                    tooltipMetric("缓存写入", day.cacheWriteTokens)
                }
            }

            HStack(spacing: AppTheme.Spacing.xs) {
                Circle()
                    .fill(AppTheme.Colors.securityGreen)
                    .frame(width: 7, height: 7)
                Text("缓存占比")
                Spacer()
                Text(String(format: "%.1f%%", cacheShare(day) * 100))
                    .monospacedDigit()
            }
            .font(AppTheme.Typography.micro)
        }
        .foregroundColor(.white)
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.sm)
        .frame(width: 220)
        .background(AppTheme.Colors.textPrimary.opacity(0.96))
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                .stroke(Color.white.opacity(0.12), lineWidth: 0.5)
        }
        .shadow(color: Color.black.opacity(0.1), radius: 14, y: 7)
    }

    private func tooltipMetric(_ name: String, _ value: Int?) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(name)
                .foregroundStyle(.white.opacity(0.6))
            Text(value.map(grouped) ?? "—")
                .monospacedDigit()
        }
        .font(AppTheme.Typography.micro)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func cacheShare(_ day: UsageDailyDTO) -> Double {
        guard day.totalTokens > 0 else { return 0 }
        let cached = (day.cacheReadTokens ?? 0) + (day.cacheWriteTokens ?? 0)
        return min(max(Double(cached) / Double(day.totalTokens), 0), 1)
    }

    @MainActor
    private func loadUsage() async {
        isLoading = true
        loadError = nil
        do {
            summary = try await APIClient.shared.fetchUsageSummary(days: selectedDays)
        } catch {
            summary = nil
            loadError = error.localizedDescription
        }
        isLoading = false
    }

    private func compact(_ n: Int) -> String {
        if n >= 1_000_000 {
            return String(format: "%.2fM", Double(n) / 1_000_000)
        }
        if n >= 1_000 {
            return String(format: "%.1fK", Double(n) / 1_000)
        }
        return "\(n)"
    }

    private func grouped(_ n: Int) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        return formatter.string(from: NSNumber(value: n)) ?? "\(n)"
    }

}

// MARK: - Xcode #Preview

#Preview("TokenSummaryCard - Light") {
    TokenSummaryCard()
        .environmentObject(AppState())
        .padding()
}

#Preview("TokenSummaryCard - Dark") {
    TokenSummaryCard()
        .environmentObject(AppState())
        .padding()
}
