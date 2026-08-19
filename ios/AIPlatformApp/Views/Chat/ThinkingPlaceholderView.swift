//
//  ThinkingPlaceholderView.swift
//  AIPlatformApp
//
//  等待期动态阶段提示：告别单一枯燥的「已等待 N 秒」。
//  真实 status 分相直显（bridge boot→reasoning）：首帧 boot「正在初始化推理引擎…」→
//  agent 构建完成 reasoning「正在理解需求…」→ 真实 thought 到达后占位让位（ChatView 解除 pending）。
//  phase/phaseDetail 为空时回退本地等待秒数伪文案（非 bridge 流场景兜底），配呼吸光点。
//

import SwiftUI

public struct ThinkingPlaceholderView: View {
    public let seconds: Int
    public let progress: String?
    public let phase: String?
    public let phaseDetail: String?
    public let onCancel: () -> Void

    @State private var isBreathing: Bool = false

    public init(
        seconds: Int,
        progress: String? = nil,
        phase: String? = nil,
        phaseDetail: String? = nil,
        onCancel: @escaping () -> Void
    ) {
        self.seconds = seconds
        self.progress = progress
        self.phase = phase
        self.phaseDetail = phaseDetail
        self.onCancel = onCancel
    }

    /// 真实 status 分相直显：phaseDetail 优先（bridge 下发即真文案）→ 分相兜底 → 本地秒数伪文案回退
    private var stageText: String {
        if let detail = phaseDetail, !detail.isEmpty {
            return detail
        }
        switch phase {
        case "boot": return "正在初始化推理引擎…"
        case "reasoning": return "正在理解需求…"
        default: break
        }
        switch seconds {
        case ..<15: return "正在理解任务需求…"
        case ..<60: return "正在检索知识星海 / 调用工具链…"
        default: return "深度协同推理进行中 (已等待 \(seconds) 秒)"
        }
    }

    private var stageIcon: String {
        switch phase {
        case "boot": return "bolt.horizontal.circle.fill"
        case "reasoning": return "brain.head.profile"
        default: break
        }
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

                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 5) {
                        Image(systemName: stageIcon)
                            .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(AppTheme.Icons.intelligence)
                        Text(stageText)
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(AppTheme.Colors.textSecondary)
                    }

                    // 长任务状态回读：轮询拉取的最新工具步骤（2s→4s→6s→8s 退避）
                    if let progress, !progress.isEmpty {
                        HStack(spacing: 5) {
                            Image(systemName: "arrow.triangle.2.circlepath")
                                .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(AppTheme.Icons.live)
                            Text(progress)
                                .font(.system(size: 11))
            .foregroundColor(AppTheme.Icons.tertiary)
                                .lineLimit(1)
                        }
                    }
                }

                Spacer()

            Button(action: onCancel) {
                HStack(spacing: 4) {
                    Image(systemName: "xmark.circle.fill")
                    Text("取消")
                }
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(AppTheme.Icons.tertiary)
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
