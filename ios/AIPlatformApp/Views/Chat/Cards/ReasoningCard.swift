//
//  ReasoningCard.swift
//  AIPlatformApp
//
//  真实思维链卡片：单实现（真实链）·折叠时间线。
//  默认收起「N 步推理」，点击平滑展开 4 类步骤（thought/tool_call/skill_load/agent_spawn）。
//  steps 为空时自动隐藏（不渲染占位，不伪造步骤）。
//

import SwiftUI

public struct ReasoningCard: View {
    public let steps: [ReasoningStep]
    @State private var isExpanded: Bool = false

    public init(steps: [ReasoningStep]) {
        self.steps = steps
    }

    public var body: some View {
        if steps.isEmpty {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 0) {
                // 折叠头部
                Button(action: {
                    withAnimation(.easeInOut(duration: 0.22)) {
                        isExpanded.toggle()
                    }
                }) {
                    HStack(spacing: AppTheme.Spacing.xs) {
                        Image(systemName: "brain.head.profile")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(AppTheme.Colors.quantumViolet)
                        Text("\(steps.count) 步推理")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(AppTheme.Colors.textPrimary)
                        Spacer()
                        Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(AppTheme.Colors.textTertiary)
                    }
                    .padding(.horizontal, AppTheme.Spacing.md)
                    .padding(.vertical, AppTheme.Spacing.sm)
                    .contentShape(Rectangle())
                }
                .buttonStyle(SoftButtonStyle())

                // 展开时间线
                if isExpanded {
                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(Array(steps.enumerated()), id: \.element.id) { index, step in
                            ReasoningStepRow(step: step, isLast: index == steps.count - 1)
                        }
                    }
                    .padding(.horizontal, AppTheme.Spacing.md)
                    .padding(.bottom, AppTheme.Spacing.sm)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(AppTheme.Colors.quantumViolet.opacity(0.06))
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                    .stroke(AppTheme.Colors.border, lineWidth: 0.5)
            )
        }
    }
}

// MARK: - 单步渲染（图标 / 标题 / 详情 / 状态）

private struct ReasoningStepRow: View {
    public let step: ReasoningStep
    public let isLast: Bool

    var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            // 时间线：图标节点 + 竖线
            VStack(spacing: 0) {
                ZStack {
                    stepIconBackground
                    stepIcon
                }
                if !isLast {
                    Rectangle()
                        .fill(AppTheme.Colors.border)
                        .frame(width: 1)
                        .frame(maxHeight: .infinity)
                }
            }

            // 标题 + 详情 + 状态
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: AppTheme.Spacing.xs) {
                    Text(step.title)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                    Spacer()
                    if step.status == "done" || step.status == "success" {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 11))
                            .foregroundColor(AppTheme.Colors.statusCompleted)
                    }
                }
                if !step.detail.isEmpty {
                    Text(step.detail)
                        .font(.system(size: 11))
                        .foregroundColor(AppTheme.Colors.textSecondary)
                        .lineLimit(3)
                }
            }
            .padding(.bottom, isLast ? 0 : AppTheme.Spacing.sm)
        }
        .padding(.top, AppTheme.Spacing.xs)
    }

    // MARK: - 图标节点（子代理步采用 Quantum 三色流光渐变点缀）
    @ViewBuilder
    private var stepIconBackground: some View {
        if step.type.usesGradient {
            Circle()
                .fill(AppTheme.Colors.quantumGradient)
                .frame(width: 22, height: 22)
                .opacity(0.16)
        } else {
            Circle()
                .fill(step.type.color.opacity(0.12))
                .frame(width: 22, height: 22)
        }
    }

    @ViewBuilder
    private var stepIcon: some View {
        if step.type.usesGradient {
            Image(systemName: step.type.iconName)
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(AppTheme.Colors.quantumGradient)
        } else {
            Image(systemName: step.type.iconName)
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(step.type.color)
        }
    }
}

public extension ReasoningStepType {
    /// 步骤类型 → SF Symbol 图标映射
    var iconName: String {
        switch self {
        case .thought: return "lightbulb.fill"
        case .toolCall: return "wrench.and.screwdriver.fill"
        case .skillLoad: return "books.vertical.fill"
        case .agentSpawn: return "point.3.connected.trianglepath.dotted"
        }
    }

    /// 步骤类型 → Quantum 真色谱映射（思考=Violet，工具=Blue，技能=Cyan；子代理=Gradient）
    var color: Color {
        switch self {
        case .thought: return AppTheme.Colors.quantumViolet
        case .toolCall: return AppTheme.Colors.quantumBlue
        case .skillLoad: return AppTheme.Colors.quantumCyan
        case .agentSpawn: return AppTheme.Colors.quantumViolet
        }
    }

    /// 子代理步采用 Quantum 三色流光渐变点缀（其余步骤为纯色圆点）
    var usesGradient: Bool {
        self == .agentSpawn
    }
}

// MARK: - Xcode #Preview

#Preview("ReasoningCard - Collapsed") {
    ReasoningCard(steps: MockData.demoReasoningSteps)
        .padding()
        .background(AppTheme.Colors.groupedBackground)
}
