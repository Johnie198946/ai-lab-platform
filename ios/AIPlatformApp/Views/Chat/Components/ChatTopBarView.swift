//
//  ChatTopBarView.swift
//  AIPlatformApp
//
//  Session Header Bar (Quantum Avatar, Status Dot, Title Drawer Trigger & Actions)
//  Extracted from ChatView for minimal footprint.
//

import SwiftUI

public struct ChatTopBarView: View {
    public let isGenerating: Bool
    public let title: String
    public let agentName: String
    public let onTitleTap: () -> Void
    public let onAgentTap: () -> Void
    public let onNewSession: () -> Void
    public let onHistoryTap: () -> Void
    public let onClearTap: () -> Void

    public init(
        isGenerating: Bool,
        title: String,
        agentName: String,
        onTitleTap: @escaping () -> Void,
        onAgentTap: @escaping () -> Void,
        onNewSession: @escaping () -> Void,
        onHistoryTap: @escaping () -> Void,
        onClearTap: @escaping () -> Void
    ) {
        self.isGenerating = isGenerating
        self.title = title
        self.agentName = agentName
        self.onTitleTap = onTitleTap
        self.onAgentTap = onAgentTap
        self.onNewSession = onNewSession
        self.onHistoryTap = onHistoryTap
        self.onClearTap = onClearTap
    }

    public var body: some View {
        HStack(spacing: AppTheme.Spacing.md) {
            QuantumAvatarView(size: 36)

            VStack(alignment: .leading, spacing: 3) {
                Button(action: onTitleTap) {
                    HStack(spacing: 6) {
                        Text(title.isEmpty ? "新会话" : title)
                            .font(AppTheme.Typography.cardTitle)
                            .foregroundColor(AppTheme.Colors.textPrimary)
                            .lineLimit(1)
                        Image(systemName: "chevron.down")
                            .font(.caption2.weight(.bold))
                            .foregroundColor(AppTheme.Icons.tertiary)
                    }
                }
                .buttonStyle(SoftButtonStyle())

                Button(action: onAgentTap) {
                    HStack(spacing: 5) {
                        Circle()
                            .fill(isGenerating ? AppTheme.Colors.statusRunning : AppTheme.Colors.statusCompleted)
                            .frame(width: 6, height: 6)
                        Text(agentName)
                            .font(AppTheme.Typography.micro)
                            .foregroundColor(AppTheme.Colors.textTertiary)
                            .lineLimit(1)
                        Image(systemName: "chevron.down")
                            .font(.system(size: 8, weight: .bold))
                            .foregroundColor(AppTheme.Icons.tertiary)
                    }
                }
                .buttonStyle(SoftButtonStyle())
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            Spacer()

            Button(action: onNewSession) {
                Image(systemName: "square.and.pencil")
                    .font(.body.weight(.semibold))
                        .foregroundColor(AppTheme.Icons.primary)
                    .minimumTouchTarget()
            }
            .buttonStyle(SoftButtonStyle())
            .accessibilityLabel("新建会话")

            Menu {
                Button(action: onHistoryTap) {
                    Label("会话历史", systemImage: "clock.arrow.circlepath")
                }
                Button(role: .destructive, action: onClearTap) {
                    Label("清空当前对话", systemImage: "trash")
                }
            } label: {
                Image(systemName: "ellipsis")
                    .font(.body.weight(.semibold))
                        .foregroundColor(AppTheme.Icons.secondary)
                    .minimumTouchTarget()
            }
            .buttonStyle(SoftButtonStyle())
            .accessibilityLabel("更多会话操作")
        }
        .padding(.horizontal, AppTheme.Metrics.contentGutter)
        .padding(.vertical, 10)
        .background(.thinMaterial)
        .background(AppTheme.Colors.cardBackground.opacity(0.90))
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(AppTheme.Colors.border.opacity(0.72))
                .frame(height: 0.5)
        }
    }
}
