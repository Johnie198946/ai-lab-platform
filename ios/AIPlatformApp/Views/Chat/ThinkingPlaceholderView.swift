//
//  ThinkingPlaceholderView.swift
//  AIPlatformApp
//
//  Single, truthful execution card for an in-flight assistant response.
//

import SwiftUI

struct ChatRunningPresentation: Equatable {
    static let fallbackAssistantName = "Quantumn 助手"

    let assistantName: String
    let title: String
    let detail: String?

    init(
        assistantName: String?,
        phase: String?,
        phaseDetail: String?,
        progress: String?,
        steps: [ReasoningStep]
    ) {
        let trimmedName = assistantName?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        self.assistantName = trimmedName.isEmpty ? Self.fallbackAssistantName : trimmedName

        let runningTool = steps.last { $0.type != .thought && $0.status == "running" }
        let latestTool = steps.last { $0.type != .thought }
        if runningTool != nil {
            title = "正在查阅资料"
        } else if phase == "boot" {
            title = "正在准备"
        } else {
            title = "正在处理请求"
        }

        detail = [phaseDetail, progress, runningTool?.detail, runningTool?.title, latestTool?.detail, latestTool?.title]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .first { !$0.isEmpty }
    }
}

public struct ThinkingPlaceholderView: View {
    public let progress: String?
    public let phase: String?
    public let phaseDetail: String?
    public let steps: [ReasoningStep]
    public let assistantName: String?
    public let onCancel: () -> Void

    public init(
        seconds: Int,
        progress: String? = nil,
        phase: String? = nil,
        phaseDetail: String? = nil,
        steps: [ReasoningStep] = [],
        assistantName: String? = nil,
        onCancel: @escaping () -> Void
    ) {
        self.progress = progress
        self.phase = phase
        self.phaseDetail = phaseDetail
        self.steps = steps
        self.assistantName = assistantName
        self.onCancel = onCancel
    }

    private var presentation: ChatRunningPresentation {
        ChatRunningPresentation(
            assistantName: assistantName,
            phase: phase,
            phaseDetail: phaseDetail,
            progress: progress,
            steps: steps
        )
    }

    public var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            QuantumAvatarView(size: 28)
                .padding(.top, AppTheme.Spacing.xs)
                .accessibilityHidden(true)

            ChatRunningStatusCard(
                presentation: presentation,
                steps: steps,
                onCancel: onCancel
            )

            Spacer(minLength: 44)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
        .accessibilityElement(children: .contain)
    }
}

struct ChatRunningStatusCard: View {
    let presentation: ChatRunningPresentation
    let steps: [ReasoningStep]
    var onCancel: (() -> Void)? = nil

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var isExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            ReasoningStatusStrip(
                title: presentation.title,
                detail: presentation.detail,
                isStreaming: true,
                isExpanded: isExpanded,
                onToggle: steps.isEmpty ? nil : toggleExpanded,
                onCancel: onCancel
            )

            if isExpanded, !steps.isEmpty {
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
                .transition(.opacity)
            }
        }
    }

    private func toggleExpanded() {
        if reduceMotion {
            isExpanded.toggle()
        } else {
            withAnimation(AppTheme.Motion.spring) {
                isExpanded.toggle()
            }
        }
    }
}

#Preview("ThinkingPlaceholderView - Actual Steps") {
    ThinkingPlaceholderView(
        seconds: 30,
        phase: "reasoning",
        phaseDetail: "正在比对公开时间线",
        steps: [
            ReasoningStep(type: .thought, title: "整理问题范围"),
            ReasoningStep(type: .toolCall, title: "查阅公开资料", detail: "正在比对公开时间线", status: "running")
        ],
        onCancel: {}
    )
    .padding()
    .background(AppTheme.Colors.groupedBackground)
}
