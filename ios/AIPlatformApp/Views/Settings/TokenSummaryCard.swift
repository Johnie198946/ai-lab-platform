//
//  TokenSummaryCard.swift
//  AIPlatformApp
//
//  真实 Token 用量：GET /api/v1/usage/summary?days=7|30|90
//

import SwiftUI

public struct TokenSummaryCard: View {
    @State private var selectedDays = 30
    @State private var summary: UsageSummaryDTO?
    @State private var isLoading = false
    @State private var loadError: String?

    public init() {}

    public var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            HStack(spacing: 6) {
                Image(systemName: "bolt.fill")
                    .font(.system(size: 13))
                    .foregroundColor(AppTheme.Icons.intelligence)
                Text("真实用量")
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(AppTheme.Colors.textPrimary)
                Spacer()
                Text("真实记录")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(AppTheme.Colors.securityGreen)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(AppTheme.Colors.securityGreen.opacity(0.12))
                    .clipShape(Capsule())
            }

            Picker("统计周期", selection: $selectedDays) {
                Text("7 天").tag(7)
                Text("30 天").tag(30)
                Text("90 天").tag(90)
            }
            .pickerStyle(.segmented)

            if isLoading && summary == nil {
                HStack {
                    Spacer()
                    ProgressView("正在加载真实用量…")
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
            } else if let summary, summary.totalCalls == 0 {
                ContentUnavailableView(
                    "暂无真实用量记录",
                    systemImage: "chart.bar.xaxis",
                    description: Text("只统计功能上线后的模型调用，不使用本地估算。")
                )
                .frame(minHeight: 180)
            } else if let summary {
                usageContent(summary)
            }
        }
        .padding(AppTheme.Spacing.xl)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous)
                .stroke(AppTheme.Colors.border, lineWidth: 0.75)
        }
        .task(id: selectedDays) {
            await loadUsage()
        }
    }

    @ViewBuilder
    private func usageContent(_ summary: UsageSummaryDTO) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(compact(summary.totalTokens))
                        .font(.system(size: 38, weight: .bold, design: .rounded))
                        .monospacedDigit()
                        .foregroundColor(AppTheme.Colors.textPrimary)
                    Text("总 Token")
                        .font(AppTheme.Typography.micro)
                        .foregroundColor(AppTheme.Colors.textTertiary)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 3) {
                    Text("\(grouped(summary.totalCalls)) 次调用")
                    Text("成功 \(grouped(summary.successCalls)) · 失败 \(grouped(summary.failedCalls))")
                }
                .font(AppTheme.Typography.micro)
                .foregroundColor(AppTheme.Colors.textSecondary)
            }

            HStack(spacing: AppTheme.Spacing.sm) {
                tokenMetric("输入", summary.inputTokens)
                tokenMetric("输出", summary.outputTokens)
            }

            dailyChart(summary.daily)

            if summary.missingUsageCalls > 0 {
                Label(
                    "\(summary.missingUsageCalls) 次调用未返回 Token usage，未计入 Token 总量",
                    systemImage: "info.circle"
                )
                .font(AppTheme.Typography.micro)
                .foregroundColor(AppTheme.Colors.textSecondary)
            }

            if !summary.models.isEmpty {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    Text("模型分布")
                        .font(AppTheme.Typography.supporting.weight(.semibold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                    ForEach(Array(summary.models.prefix(5))) { item in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(item.model)
                                    .font(AppTheme.Typography.supporting.weight(.semibold))
                                Text(item.provider)
                                    .font(AppTheme.Typography.micro)
                                    .foregroundColor(AppTheme.Colors.textTertiary)
                            }
                            Spacer()
                            Text("\(compact(item.totalTokens)) · \(item.calls) 次")
                                .font(AppTheme.Typography.micro)
                                .monospacedDigit()
                                .foregroundColor(AppTheme.Colors.textSecondary)
                        }
                    }
                }
            }
        }
    }

    private func tokenMetric(_ title: String, _ value: Int) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title)
                .font(AppTheme.Typography.micro)
                .foregroundColor(AppTheme.Colors.textTertiary)
            Text(grouped(value))
                .font(AppTheme.Typography.supporting.weight(.semibold))
                .monospacedDigit()
                .foregroundColor(AppTheme.Colors.textPrimary)
        }
        .padding(AppTheme.Spacing.sm)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.Colors.secondaryBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
    }

    private func dailyChart(_ daily: [UsageDailyDTO]) -> some View {
        let maximum = max(daily.map(\.totalTokens).max() ?? 0, 1)
        return VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Text("每日趋势")
                .font(AppTheme.Typography.supporting.weight(.semibold))
                .foregroundColor(AppTheme.Colors.textPrimary)
            ScrollView(.horizontal) {
                LazyHStack(alignment: .bottom, spacing: selectedDays == 90 ? 3 : 6) {
                    ForEach(daily) { day in
                        RoundedRectangle(cornerRadius: 3, style: .continuous)
                            .fill(AppTheme.Colors.quantumGradient)
                            .frame(
                                width: selectedDays == 90 ? 4 : 8,
                                height: max(2, 88 * CGFloat(day.totalTokens) / CGFloat(maximum))
                            )
                            .accessibilityLabel("\(day.date)，\(day.totalTokens) Token")
                    }
                }
                .frame(minHeight: 88, alignment: .bottom)
            }
            .scrollIndicators(.hidden)
        }
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
        .preferredColorScheme(.dark)
        .padding()
}
