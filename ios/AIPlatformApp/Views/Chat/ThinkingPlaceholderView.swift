//
//  ThinkingPlaceholderView.swift
//  AIPlatformApp
//
//  等待期动态阶段提示：告别单一枯燥的「已等待 N 秒」。
//  本地单 Timer 派生 waitingSeconds，映射三阶段文案（配呼吸光点）：
//    - 0 ~ 15 秒：正在理解任务需求…
//    - 15 ~ 60 秒：正在检索知识星海 / 调用工具链…
//    - 60 秒以上：深度协同推理进行中 (已等待 N 秒)
//

import SwiftUI

public struct ThinkingPlaceholderView: View {
    public let seconds: Int
    public let onCancel: () -> Void

    @State private var isBreathing: Bool = false

    public init(seconds: Int, onCancel: @escaping () -> Void) {
        self.seconds = seconds
        self.onCancel = onCancel
    }

    private var stageText: String {
        switch seconds {
        case ..<15: return "正在理解任务需求…"
        case ..<60: return "正在检索知识星海 / 调用工具链…"
        default: return "深度协同推理进行中 (已等待 \(seconds) 秒)"
        }
    }

    private var stageIcon: String {
        switch seconds {
        case ..<15: return "text.book.closed.fill"
        case ..<60: return "sparkle.magnifyingglass"
        default: return "brain.head.profile"
        }
    }

    public var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            QuantumAvatarView(size: 32).padding(.top, 2)

            HStack(spacing: AppTheme.Spacing.sm) {
                breathingDots

                HStack(spacing: 5) {
                    Image(systemName: stageIcon)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(AppTheme.Colors.quantumBlue)
                    Text(stageText)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(AppTheme.Colors.textSecondary)
                }

                Spacer()

                Button(action: onCancel) {
                    HStack(spacing: 4) {
                        Image(systemName: "xmark.circle.fill")
                        Text("取消")
                    }
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.textTertiary)
                }
                .buttonStyle(SoftButtonStyle())
            }
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.sm + 2)
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(AppTheme.Colors.assistantBubbleBorder.opacity(0.18), lineWidth: 0.5)
            )
            Spacer(minLength: 44)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
        .onAppear { isBreathing = true }
    }

    /// 呼吸光点：三色量子光点脉动（Cyan / Blue / Violet）。
    private var breathingDots: some View {
        HStack(spacing: 4) {
            ForEach(Array([AppTheme.Colors.quantumCyan, AppTheme.Colors.quantumBlue, AppTheme.Colors.quantumViolet].enumerated()), id: \.offset) { _, color in
                Circle()
                    .fill(color)
                    .frame(width: 6, height: 6)
                    .opacity(isBreathing ? 1.0 : 0.25)
                    .scaleEffect(isBreathing ? 1.0 : 0.7)
                    .animation(
                        .easeInOut(duration: 0.9).repeatForever(autoreverses: true),
                        value: isBreathing
                    )
            }
        }
    }
}

// MARK: - Xcode #Preview

#Preview("ThinkingPlaceholderView - Stages") {
    VStack(spacing: 12) {
        ThinkingPlaceholderView(seconds: 5, onCancel: {})
        ThinkingPlaceholderView(seconds: 30, onCancel: {})
        ThinkingPlaceholderView(seconds: 75, onCancel: {})
    }
    .padding()
    .background(AppTheme.Colors.groupedBackground)
}
