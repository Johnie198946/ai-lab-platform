//
//  ReasoningCard.swift
//  AIPlatformApp
//
//  ChatGPT / Claude Style Minimal Thinking Capsule (v4 - Pure Capsule Streaming)
//  - Streaming: 仅胶囊内单行文本流式滚动（如「思考中…」「检索知识库: 华为.md」），绝不在页面铺开长文。
//  - Completed: 收起为极简胶囊「已深度思考 N 秒」，点击展开优雅的编号步骤抽屉。
//

import SwiftUI

public struct ReasoningCard: View {
    public let steps: [ReasoningStep]
    public var durationSeconds: Int? = nil
    public var isStreaming: Bool = false
    public var onCancel: (() -> Void)? = nil

    @State private var isExpanded: Bool = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init(
        steps: [ReasoningStep],
        durationSeconds: Int? = nil,
        isStreaming: Bool = false,
        initiallyExpanded: Bool = false,
        onCancel: (() -> Void)? = nil
    ) {
        self.steps = steps
        self.durationSeconds = durationSeconds
        self.isStreaming = isStreaming
        self.onCancel = onCancel
        _isExpanded = State(initialValue: initiallyExpanded)
    }

    public var body: some View {
        if steps.isEmpty {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 0) {
                ReasoningStatusStrip(
                    title: capsuleText,
                    isStreaming: isStreaming,
                    isExpanded: isExpanded,
                    onToggle: toggleExpanded,
                    onCancel: isStreaming ? onCancel : nil
                )

                // 仅当用户主动点击时才展开的精简编号步骤抽屉
                if isExpanded {
                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(Array(steps.enumerated()), id: \.element.id) { index, step in
                            ReasoningStepRow(
                                index: index + 1,
                                step: step,
                                isLast: index == steps.count - 1
                            )
                        }
                    }
                    .padding(.horizontal, AppTheme.Spacing.md)
                    .padding(.top, AppTheme.Spacing.sm)
                    .transition(reduceMotion ? .opacity : .opacity.combined(with: .move(edge: .top)))
                }
            }
            .onChange(of: isStreaming) { wasStreaming, streaming in
                guard wasStreaming && !streaming else { return }
                if reduceMotion {
                    isExpanded = false
                } else {
                    withAnimation(.easeOut(duration: 0.2)) { isExpanded = false }
                }
            }
        }
    }

    private func toggleExpanded() {
        if reduceMotion {
            isExpanded.toggle()
        } else {
            withAnimation(AppTheme.Motion.spring) { isExpanded.toggle() }
        }
    }

    /// 胶囊单行文本：流式期间动态呈现当前正在执行的动作（胶囊内单行流式），完成后显示思考耗时
    private var capsuleText: String {
        if isStreaming {
            // 优先展示当前正在 running 的工具/步骤（如 "调用工具: search_files"）
            if let running = steps.last(where: { $0.status == "running" && $0.type != .thought }), !running.title.isEmpty {
                return running.title
            }
            // 其次展示最近完成的有意义步骤
            if let lastTool = steps.last(where: { $0.type != .thought }), !lastTool.title.isEmpty {
                return lastTool.title
            }
            return "思考中…"
        }
        if let sec = durationSeconds, sec > 0 {
            return "已深度思考 \(sec) 秒"
        }
        return "已深度思考"
    }
}

/// 等待期与真实推理期共用的 Quantum Pearl 状态条。
struct ReasoningStatusStrip: View {
    let title: String
    var detail: String? = nil
    var isStreaming: Bool = true
    var isExpanded: Bool = false
    var onToggle: (() -> Void)? = nil
    var onCancel: (() -> Void)? = nil

    @State private var isBreathing = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    init(
        title: String,
        detail: String? = nil,
        isStreaming: Bool = true,
        isExpanded: Bool = false,
        onToggle: (() -> Void)? = nil,
        onCancel: (() -> Void)? = nil
    ) {
        self.title = title
        self.detail = detail
        self.isStreaming = isStreaming
        self.isExpanded = isExpanded
        self.onToggle = onToggle
        self.onCancel = onCancel
    }

    var body: some View {
        HStack(spacing: 0) {
            if let onToggle {
                Button(action: onToggle) { statusLabel(showsDisclosure: true) }
                    .buttonStyle(SoftButtonStyle())
            } else {
                statusLabel(showsDisclosure: false)
            }

            if let onCancel {
                Button(action: onCancel) {
                    Image(systemName: "xmark")
                        .font(.caption.weight(.semibold))
                        .foregroundColor(AppTheme.Icons.tertiary)
                        .minimumTouchTarget()
                }
                .buttonStyle(SoftButtonStyle())
                .accessibilityLabel("取消当前任务")
            }
        }
        .background(AppTheme.Colors.cardBackground.opacity(0.70))
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xs, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.xs, style: .continuous)
                .stroke(AppTheme.Colors.border.opacity(0.50), lineWidth: 0.5)
        }
        .pressBorderGlow(cornerRadius: AppTheme.Radius.xs)
        .onAppear { isBreathing = true }
    }

    private func statusLabel(showsDisclosure: Bool) -> some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            intelligenceDots

            VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
                Text(title)
                    .font(AppTheme.Typography.label)
                    .foregroundColor(AppTheme.Colors.textSecondary)
                    .lineLimit(1)
                    .id(title)
                    .transition(reduceMotion ? .opacity : .opacity.combined(with: .move(edge: .bottom)))

                if let detail, !detail.isEmpty {
                    Text(detail)
                        .font(AppTheme.Typography.micro)
                        .foregroundColor(AppTheme.Colors.textTertiary)
                        .lineLimit(1)
                }
            }

            Spacer(minLength: 0)

            if showsDisclosure {
                Image(systemName: "chevron.right")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(AppTheme.Icons.tertiary)
                    .rotationEffect(.degrees(isExpanded ? 90 : 0))
                    .accessibilityHidden(true)
            }
        }
        .padding(.leading, AppTheme.Spacing.md)
        .padding(.trailing, showsDisclosure ? AppTheme.Spacing.md : 0)
        .padding(.vertical, 6)
        .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget, alignment: .leading)
        .contentShape(Rectangle())
    }

    private var intelligenceDots: some View {
        HStack(spacing: 3) {
            ForEach(Array([AppTheme.Colors.quantumCyan, AppTheme.Colors.quantumBlue, AppTheme.Colors.quantumViolet].enumerated()), id: \.offset) { index, color in
                Circle()
                    .fill(color)
                    .frame(width: 5, height: 5)
                    .opacity(isStreaming && isBreathing ? 1 : 0.42)
                    .scaleEffect(isStreaming && isBreathing ? 1 : 0.72)
                    .animation(
                        reduceMotion || !isStreaming
                            ? nil
                            : .easeInOut(duration: 0.9).delay(Double(index) * 0.14).repeatForever(autoreverses: true),
                        value: isBreathing
                    )
            }
        }
        .frame(width: 22)
        .accessibilityHidden(true)
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
        HStack(alignment: .top, spacing: 7) {
            ZStack {
                Circle()
                    .fill(dotColor.opacity(0.12))
                    .frame(width: 16, height: 16)
                Text("\(index)")
                    .font(.caption2.weight(.bold))
                    .foregroundColor(dotColor)
            }
            .padding(.top, 2)

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 4) {
                    Text(step.title)
                        .font(.caption.weight(.medium))
                        .foregroundColor(AppTheme.Colors.textPrimary)

                    if step.status == "running" {
                        ProgressView()
                            .scaleEffect(0.45)
                            .frame(width: 8, height: 8)
                    }
                }

                if !step.detail.isEmpty && step.type != .thought {
                    Text(step.detail)
                        .font(.caption2)
                        .foregroundColor(AppTheme.Colors.textTertiary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(.bottom, isLast ? 0 : 6)

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

enum ReasoningStepMutation {
    /// Returns nil when an update is a no-op, allowing streaming callers to
    /// avoid publishing an identical message tree for every SSE token.
    static func applying(
        _ update: (inout [ReasoningStep]) -> Void,
        to steps: [ReasoningStep]
    ) -> [ReasoningStep]? {
        var updated = steps
        update(&updated)
        return updated == steps ? nil : updated
    }
}

extension ChatMessage {
    /// A terminal answer and a running reasoning row must never coexist.
    /// Stream recovery can finish without delivering the SSE `done` frame, so
    /// completion paths normalize the persisted reasoning block as an invariant.
    mutating func settleReasoningForCompletion() {
        blocks = blocks.map { block in
            guard case .reasoning(var steps) = block else { return block }
            for index in steps.indices where steps[index].status == "running" {
                steps[index].status = "done"
                if steps[index].title == "正在生成回答…"
                    || steps[index].title == "正在生成回答..." {
                    steps[index].title = "回答已生成"
                }
            }
            return .reasoning(steps)
        }
    }
}
