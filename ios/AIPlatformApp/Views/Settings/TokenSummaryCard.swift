//
//  TokenSummaryCard.swift
//  AIPlatformApp
//
//  Token 极简卡（④）：大数字（本月消耗，tabular-nums）+ 一句状态（预算剩余 %）
//  + 单条细进度线 + 一行泳道小字（数据不删，呈现简化）。
//

import SwiftUI

public struct TokenSummaryCard: View {
    @EnvironmentObject private var appState: AppState

    /// 月度 Token 预算（演示基线）
    private let totalBudget: Int = 4_200_000

    public init() {}

    public var body: some View {
        let profile = appState.currentProfile
        let used = Int(Double(totalBudget) * profile.tokenQuotaUsage)
        let remainingPct = Int((1 - profile.tokenQuotaUsage) * 100)

        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            // 标题行
            HStack(spacing: 6) {
                Image(systemName: "bolt.fill")
                    .font(.system(size: 13))
                    .foregroundColor(AppTheme.Colors.accent)
                Text("Token 消耗")
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(AppTheme.Colors.textPrimary)
                Spacer()
                Text("本月")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.textTertiary)
            }

            // 大数字
            Text(compact(used))
                .font(.system(size: 42, weight: .bold, design: .rounded))
                .monospacedDigit()
                .foregroundColor(AppTheme.Colors.textPrimary)

            // 一句状态
            Text("预算剩余 \(remainingPct)%")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(
                    remainingPct < 20 ? AppTheme.Colors.securityRed : AppTheme.Colors.textSecondary
                )

            // 单条细进度线
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(AppTheme.Colors.tertiaryBackground)
                    Capsule()
                        .fill(progressColor(remainingPct: remainingPct))
                        .frame(width: geo.size.width * profile.tokenQuotaUsage)
                }
            }
            .frame(height: 6)

            // 一行泳道小字
            HStack {
                Text(profile.isVipLane ? "VIP 泳道 · 0 延迟" : "抢占式池 · 并发 ≤ \(profile.concurrencyLimit)")
                Spacer()
                Text("\(grouped(used)) / \(grouped(totalBudget))")
            }
            .font(.system(size: 11))
            .foregroundColor(AppTheme.Colors.textTertiary)
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    private func progressColor(remainingPct: Int) -> Color {
        if remainingPct < 20 {
            return AppTheme.Colors.securityRed
        }
        return AppTheme.Colors.accent
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
