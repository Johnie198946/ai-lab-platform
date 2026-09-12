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
                Text("Token 监控")
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(AppTheme.Colors.textPrimary)
                Spacer()
                Text("服务端账本")
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
        .pressBorderGlow(cornerRadius: AppTheme.Radius.xl)
        .task(id: selectedDays) {
            await loadUsage()
        }
    }

    @ViewBuilder
    private func usageContent(_ summary: UsageSummaryDTO) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            quotaPanel(summary.quota)

            Divider()

            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(compact(summary.totalTokens))
                        .font(.system(size: 38, weight: .bold, design: .rounded))
                        .monospacedDigit()
                        .foregroundColor(AppTheme.Colors.textPrimary)
                    Text("近 \(selectedDays) 天实际消耗")
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

            if summary.totalCalls == 0 {
                Label("近 \(selectedDays) 天暂无调用记录", systemImage: "chart.bar.xaxis")
                    .font(AppTheme.Typography.supporting)
                    .foregroundColor(AppTheme.Colors.textSecondary)
                    .frame(maxWidth: .infinity, minHeight: 72)
            } else {
                dailyChart(summary.daily)
            }

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

    @ViewBuilder
    private func quotaPanel(_ quota: TokenQuotaDTO?) -> some View {
        if let quota {
            let progress = min(max(quota.percentUsed / 100, 0), 1)
            let accent = quotaColor(quota.percentUsed)
            VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(quota.isExhausted ? "本月额度已用尽" : "本月额度")
                            .font(.system(size: 16, weight: .bold))
                            .foregroundColor(AppTheme.Colors.textPrimary)
                        Text("每个自然月重置")
                            .font(AppTheme.Typography.micro)
                            .foregroundColor(AppTheme.Colors.textTertiary)
                    }
                    Spacer()
                    Text(percent(quota.percentUsed))
                        .font(.system(size: 22, weight: .bold, design: .rounded))
                        .monospacedDigit()
                        .foregroundColor(accent)
                }

                GeometryReader { proxy in
                    ZStack(alignment: .leading) {
                        Capsule()
                            .fill(AppTheme.Colors.secondaryBackground)
                        Capsule()
                            .fill(accent)
                            .frame(width: proxy.size.width * progress)
                    }
                }
                .frame(height: 12)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("本月 Token 额度")
                .accessibilityValue("已使用 \(percent(quota.percentUsed))，剩余 \(grouped(quota.remainingTokens)) Token")

                HStack(alignment: .top) {
                    quotaMetric("已用", quota.usedTokens, accent: accent)
                    Spacer()
                    quotaMetric("总额度", quota.limitTokens, accent: AppTheme.Colors.textPrimary)
                        .multilineTextAlignment(.trailing)
                }

                HStack(spacing: 5) {
                    Image(systemName: quota.isExhausted ? "exclamationmark.circle.fill" : "arrow.clockwise.circle")
                    Text(quota.isExhausted
                         ? "余额为 0，需等待下月重置"
                         : quota.percentUsed >= 75
                            ? "剩余 \(compact(quota.remainingTokens))；复杂请求可能因预留额度不足被拦截"
                            : "剩余 \(compact(quota.remainingTokens)) · \(resetCopy(quota.periodEnd)) 重置")
                }
                .font(AppTheme.Typography.micro)
                .foregroundColor(quota.isExhausted ? AppTheme.Colors.securityRed : AppTheme.Colors.textSecondary)
            }
            .padding(AppTheme.Spacing.lg)
            .background(accent.opacity(0.08))
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                    .stroke(accent.opacity(0.24), lineWidth: 0.75)
            }
        } else {
            Label("当前服务未返回额度信息，仅展示实际 Token 用量", systemImage: "info.circle")
                .font(AppTheme.Typography.supporting)
                .foregroundColor(AppTheme.Colors.textSecondary)
        }
    }

    private func quotaMetric(_ title: String, _ value: Int, accent: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(AppTheme.Typography.micro)
                .foregroundColor(AppTheme.Colors.textTertiary)
            Text(grouped(value))
                .font(.system(size: 15, weight: .semibold, design: .rounded))
                .monospacedDigit()
                .foregroundColor(accent)
        }
    }

    private func quotaColor(_ usedPercent: Double) -> Color {
        if usedPercent >= 90 { return AppTheme.Colors.securityRed }
        if usedPercent >= 75 { return AppTheme.Colors.securityYellow }
        return AppTheme.Colors.securityGreen
    }

    private func percent(_ value: Double) -> String {
        String(format: value < 10 ? "%.1f%%" : "%.0f%%", value)
    }

    private func resetCopy(_ isoDate: String) -> String {
        let formatter = ISO8601DateFormatter()
        guard let date = formatter.date(from: isoDate) else { return "下月" }
        let display = DateFormatter()
        display.locale = Locale(identifier: "zh_CN")
        display.dateFormat = "M 月 d 日"
        return display.string(from: date)
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
        .padding()
}
