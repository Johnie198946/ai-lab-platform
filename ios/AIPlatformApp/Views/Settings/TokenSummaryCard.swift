//
//  TokenSummaryCard.swift
//  AIPlatformApp
//
//  Token 消耗卡：真实对接 GET /api/v1/me/usage（chat_calls + token_used）
//  离线/失败时回退本地配额演示，UI 显式标注「演示数据」防误解。
//

import SwiftUI

public struct TokenSummaryCard: View {
    @EnvironmentObject private var appState: AppState

    /// 月度 Token 预算（仅作展示配额上限与离线回退基线）
    private let totalBudget: Int = 4_200_000

    @State private var chatCalls: Int? = nil
    @State private var tokenUsed: Int? = nil
    @State private var offline: Bool = false

    public init() {}

    public var body: some View {
        let profile = appState.currentProfile
        let used = tokenUsed ?? Int(Double(totalBudget) * profile.tokenQuotaUsage)
        let calls = chatCalls ?? 0
        let progress = min(1.0, max(0.0, Double(used) / Double(totalBudget)))

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
                Text(offline ? "演示数据" : "实时用量")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(offline ? AppTheme.Colors.textTertiary : AppTheme.Colors.securityGreen)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background((offline ? AppTheme.Colors.textTertiary : AppTheme.Colors.securityGreen).opacity(0.12))
                    .clipShape(Capsule())
            }

            // 大数字（token_used）
            Text(compact(used))
                .font(.system(size: 42, weight: .bold, design: .rounded))
                .monospacedDigit()
                .foregroundColor(AppTheme.Colors.textPrimary)

            // 累计对话次数（chat_calls）
            Text("累计对话 \(grouped(calls)) 次")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(AppTheme.Colors.textSecondary)

            // 单条细进度线
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(AppTheme.Colors.tertiaryBackground)
                    Capsule()
                        .fill(offline ? AnyShapeStyle(AppTheme.Colors.accent) : AnyShapeStyle(AppTheme.Colors.quantumGradient))
                        .frame(width: geo.size.width * progress)
                }
            }
            .frame(height: 6)

            // 一行泳道小字
            HStack {
                Text("Token 用量 \(grouped(used))")
                Spacer()
                Text("调用 \(grouped(calls)) 次")
            }
            .font(.system(size: 11))
            .foregroundColor(AppTheme.Colors.textTertiary)
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        .task {
            await loadUsage()
        }
    }

    private func loadUsage() async {
        do {
            let usage = try await APIClient.shared.fetchUsage()
            chatCalls = usage.chatCalls
            tokenUsed = usage.tokenUsed
            offline = false
        } catch {
            offline = true
        }
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
