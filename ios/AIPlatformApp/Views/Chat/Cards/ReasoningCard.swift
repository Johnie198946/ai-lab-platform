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

    @State private var isExpanded: Bool = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init(
        steps: [ReasoningStep],
        durationSeconds: Int? = nil,
        isStreaming: Bool = false,
        initiallyExpanded: Bool = false
    ) {
        self.steps = steps
        self.durationSeconds = durationSeconds
        self.isStreaming = isStreaming
        _isExpanded = State(initialValue: initiallyExpanded)
    }

    public var body: some View {
        if steps.isEmpty {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 0) {
                // ChatGPT 风格单行极简胶囊
                Button(action: {
                    if reduceMotion {
                        isExpanded.toggle()
                    } else {
                        withAnimation(.spring(response: 0.28, dampingFraction: 0.82)) {
                            isExpanded.toggle()
                        }
                    }
                }) {
                    HStack(spacing: 6) {
                        Image(systemName: isStreaming ? "brain.head.profile" : "sparkles")
                            .font(.caption.weight(.medium))
                            .foregroundColor(AppTheme.Icons.intelligence)
                            .symbolEffect(.pulse, isActive: isStreaming && !reduceMotion)

                        // 胶囊内的单行流式文本切换
                        Text(capsuleText)
                            .font(.caption.weight(.medium))
                            .foregroundColor(AppTheme.Colors.textSecondary)
                            .lineLimit(1)
                            .id(capsuleText)
                            .transition(reduceMotion ? .opacity : .opacity.combined(with: .move(edge: .bottom)))

                        Spacer(minLength: 0)

                        if isStreaming {
                            ProgressView()
                                .scaleEffect(0.5)
                                .frame(width: 10, height: 10)
                                .padding(.trailing, 2)
                        }

                        Image(systemName: "chevron.right")
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(AppTheme.Icons.tertiary)
                            .rotationEffect(.degrees(isExpanded ? 90 : 0))
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .frame(minHeight: 44)
                    .contentShape(Rectangle())
                }
                .buttonStyle(SoftButtonStyle())

                // 仅当用户主动点击时才展开的精简编号步骤抽屉
                if isExpanded {
                    VStack(alignment: .leading, spacing: 0) {
                        Divider()
                            .overlay(AppTheme.Colors.border.opacity(0.4))
                            .padding(.bottom, 6)

                        ForEach(Array(steps.enumerated()), id: \.element.id) { index, step in
                            ReasoningStepRow(
                                index: index + 1,
                                step: step,
                                isLast: index == steps.count - 1
                            )
                        }
                    }
                    .padding(.horizontal, 10)
                    .padding(.bottom, 6)
                    .transition(reduceMotion ? .opacity : .opacity.combined(with: .move(edge: .top)))
                }
            }
            .background(AppTheme.Colors.cardBackground.opacity(0.55))
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(AppTheme.Colors.border.opacity(0.5), lineWidth: 0.5)
            )
            .pressBorderGlow(cornerRadius: 10)
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
