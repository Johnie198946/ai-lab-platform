//
//  ReasoningCard.swift
//  AIPlatformApp
//
//  ChatGPT / Gemini Style Thinking Capsule & Timeline (v2)
//  - Reasoning: subtle pulsing pill "思考中…" with live step chain streaming below.
//  - Completed: collapses into a minimal pill "已深度思考 N 秒" (no step count noise,
//    no "展开" text — just icon + duration + chevron), tap to expand.
//  - Expanded: numbered step timeline with per-type accent dot.
//

import SwiftUI

public struct ReasoningCard: View {
    public let steps: [ReasoningStep]
    public var durationSeconds: Int? = nil
    public var isStreaming: Bool = false

    @State private var isExpanded: Bool = false
    @State private var userToggled: Bool = false

    public init(steps: [ReasoningStep], durationSeconds: Int? = nil, isStreaming: Bool = false) {
        self.steps = steps
        self.durationSeconds = durationSeconds
        self.isStreaming = isStreaming
    }

    /// 流式进行中默认展开（实时链可见）；完成后收起为胶囊；用户手动切换后尊重用户
    private var effectiveExpanded: Bool {
        if userToggled { return isExpanded }
        return isStreaming
    }

    public var body: some View {
        if steps.isEmpty {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 0) {
                // ChatGPT 风格胶囊头部（极简：图标 + 文案 + 纯 chevron，无多余文字）
                Button(action: {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.85)) {
                        userToggled = true
                        isExpanded = !effectiveExpanded
                    }
                }) {
                    HStack(spacing: 6) {
                        Image(systemName: isStreaming ? "brain.head.profile" : "sparkles")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(AppTheme.Colors.quantumViolet)
                            .symbolEffect(.pulse, isActive: isStreaming)

                        Text(headerTitle)
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(AppTheme.Colors.textSecondary)
                            .lineLimit(1)

                        Spacer(minLength: 0)

                        Image(systemName: "chevron.right")
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(AppTheme.Colors.textTertiary)
                            .rotationEffect(.degrees(effectiveExpanded ? 90 : 0))
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 7)
                    .contentShape(Rectangle())
                }
                .buttonStyle(SoftButtonStyle())

                // 展开时间线（编号步骤 + 类型色点）
                if effectiveExpanded {
                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(Array(steps.enumerated()), id: \.element.id) { index, step in
                            ReasoningStepRow(index: index + 1, step: step, isLast: index == steps.count - 1)
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .transition(.opacity.combined(with: .move(edge: .top)))
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(AppTheme.Colors.cardBackground.opacity(0.65))
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(AppTheme.Colors.border.opacity(0.6), lineWidth: 0.5)
            )
        }
    }

    private var headerTitle: String {
        if isStreaming {
            return "思考中…"
        }
        if let sec = durationSeconds, sec > 0 {
            return "已深度思考 \(sec) 秒"
        }
        return "已深度思考"
    }
}

public struct ReasoningStepRow: View {
    public let index: Int
    public let step: ReasoningStep
    public let isLast: Bool

    public init(index: Int, step: ReasoningStep, isLast: Bool) {
        self.index = index
        self.step = step
        self.isLast = isLast
    }

    public var body: some View {
        HStack(alignment: .top, spacing: 8) {
            // 编号徽标
            ZStack {
                Circle()
                    .fill(dotColor.opacity(0.12))
                    .frame(width: 20, height: 20)
                Text("\(index)")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(dotColor)
            }
            .padding(.top, 2)

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 5) {
                    Text(step.title)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(AppTheme.Colors.textPrimary)

                    if step.status == "running" {
                        ProgressView()
                            .scaleEffect(0.55)
                            .frame(width: 10, height: 10)
                    }
                }

                if !step.detail.isEmpty {
                    Text(step.detail)
                        .font(.system(size: 11))
                        .foregroundColor(AppTheme.Colors.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .lineLimit(3)
                }
            }
            .padding(.bottom, isLast ? 0 : 8)

            Spacer(minLength: 0)
        }
    }

    private var dotColor: Color {
        switch step.type {
        case .thought: return AppTheme.Colors.quantumViolet
        case .toolCall: return AppTheme.Colors.quantumBlue
        case .skillLoad: return AppTheme.Colors.quantumCyan
        case .agentSpawn: return AppTheme.Colors.statusRunning
        }
    }
}
