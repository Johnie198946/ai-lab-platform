//
//  ReasoningCard.swift
//  AIPlatformApp
//
//  ChatGPT / Gemini Style Thinking Capsule & Timeline
//  - Streaming: Expands timeline with step reveal & breathing indicator.
//  - Completed: Auto-collapses to a compact capsule with duration (e.g. "已深度思考 4 秒 · 展开").
//  - User-Intent Aware: Preserves user's manual toggle choice.
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

    private var effectiveExpanded: Bool {
        if userToggled { return isExpanded }
        return isStreaming
    }

    public var body: some View {
        if steps.isEmpty {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 0) {
                // 折叠胶囊头部
                Button(action: {
                    withAnimation(.easeInOut(duration: 0.22)) {
                        userToggled = true
                        isExpanded = !effectiveExpanded
                    }
                }) {
                    HStack(spacing: AppTheme.Spacing.xs) {
                        Image(systemName: isStreaming ? "brain.head.profile" : "sparkles")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(AppTheme.Colors.quantumViolet)
                            .symbolEffect(.pulse, isActive: isStreaming)

                        Text(headerTitle)
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(AppTheme.Colors.textPrimary)

                        Spacer()

                        Text(effectiveExpanded ? "收起" : "展开")
                            .font(.system(size: 11))
                            .foregroundColor(AppTheme.Colors.textTertiary)

                        Image(systemName: effectiveExpanded ? "chevron.up" : "chevron.down")
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundColor(AppTheme.Colors.textTertiary)
                    }
                    .padding(.horizontal, AppTheme.Spacing.md)
                    .padding(.vertical, 7)
                    .contentShape(Rectangle())
                }
                .buttonStyle(SoftButtonStyle())

                // 展开时间线
                if effectiveExpanded {
                    Divider()
                        .background(AppTheme.Colors.border.opacity(0.4))

                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(Array(steps.enumerated()), id: \.element.id) { index, step in
                            ReasoningStepRow(step: step, isLast: index == steps.count - 1)
                        }
                    }
                    .padding(.horizontal, AppTheme.Spacing.md)
                    .padding(.vertical, AppTheme.Spacing.sm)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(AppTheme.Colors.quantumViolet.opacity(0.06))
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                    .stroke(AppTheme.Colors.quantumViolet.opacity(0.18), lineWidth: 0.5)
            )
        }
    }

    private var headerTitle: String {
        if isStreaming {
            return "深度思考中 (\(steps.count) 步)..."
        }
        if let sec = durationSeconds, sec > 0 {
            return "已深度思考 \(sec) 秒 (\(steps.count) 步)"
        }
        return "已深度思考 (\(steps.count) 步)"
    }
}

public struct ReasoningStepRow: View {
    public let step: ReasoningStep
    public let isLast: Bool

    public init(step: ReasoningStep, isLast: Bool) {
        self.step = step
        self.isLast = isLast
    }

    public var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            VStack(spacing: 0) {
                Circle()
                    .fill(dotColor)
                    .frame(width: 8, height: 8)
                    .padding(.top, 4)

                if !isLast {
                    Rectangle()
                        .fill(AppTheme.Colors.border.opacity(0.6))
                        .frame(width: 1)
                        .frame(minHeight: 18)
                }
            }
            .frame(width: 12)

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(step.title)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(AppTheme.Colors.textPrimary)

                    if step.status == "running" {
                        ProgressView()
                            .scaleEffect(0.6)
                            .frame(width: 12, height: 12)
                    }
                }

                if !step.detail.isEmpty {
                    Text(step.detail)
                        .font(.system(size: 11))
                        .foregroundColor(AppTheme.Colors.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(.bottom, isLast ? 0 : AppTheme.Spacing.xs)

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
