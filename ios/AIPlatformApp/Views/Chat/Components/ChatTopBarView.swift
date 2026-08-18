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
    public let onTitleTap: () -> Void
    public let onNewSession: () -> Void
    public let onHistoryTap: () -> Void
    public let onClearTap: () -> Void

    public init(
        isGenerating: Bool,
        title: String,
        onTitleTap: @escaping () -> Void,
        onNewSession: @escaping () -> Void,
        onHistoryTap: @escaping () -> Void,
        onClearTap: @escaping () -> Void
    ) {
        self.isGenerating = isGenerating
        self.title = title
        self.onTitleTap = onTitleTap
        self.onNewSession = onNewSession
        self.onHistoryTap = onHistoryTap
        self.onClearTap = onClearTap
    }

    public var body: some View {
        HStack(spacing: AppTheme.Spacing.md) {
            ZStack(alignment: .bottomTrailing) {
                QuantumAvatarView(size: 36)
                Circle()
                    .fill(isGenerating ? AppTheme.Colors.statusRunning : AppTheme.Colors.quantumCyan)
                    .frame(width: 10, height: 10)
                    .overlay(Circle().stroke(AppTheme.Colors.surfaceElevated, lineWidth: 2))
            }

            Button(action: onTitleTap) {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 5) {
                        Text(title.isEmpty ? "新会话" : title)
                            .font(AppTheme.Typography.cardTitle)
                            .foregroundColor(AppTheme.Colors.textPrimary)
                            .lineLimit(1)
                        Image(systemName: "chevron.down")
                            .font(.caption2.weight(.bold))
                            .foregroundColor(AppTheme.Colors.textTertiary)
                    }

                    Text(isGenerating ? "正在执行任务" : "Quantum 助手 · 已就绪")
                        .font(AppTheme.Typography.micro)
                        .foregroundColor(isGenerating ? AppTheme.Colors.statusRunning : AppTheme.Colors.textSecondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(SoftButtonStyle())
            .accessibilityHint("打开历史会话")

            Spacer()

            Button(action: onNewSession) {
                Image(systemName: "square.and.pencil")
                    .font(.body.weight(.semibold))
                    .foregroundColor(AppTheme.Colors.onPrimary)
                    .minimumTouchTarget()
                    .background(AppTheme.Colors.quantumGradient)
                    .clipShape(Circle())
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
                    .foregroundColor(AppTheme.Colors.textSecondary)
                    .minimumTouchTarget()
                    .background(AppTheme.Colors.secondaryBackground)
                    .clipShape(Circle())
            }
            .buttonStyle(SoftButtonStyle())
            .accessibilityLabel("更多会话操作")
        }
        .padding(.horizontal, AppTheme.Metrics.contentGutter)
        .padding(.vertical, AppTheme.Spacing.sm)
        .background(.ultraThinMaterial)
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(AppTheme.Colors.border.opacity(0.7))
                .frame(height: 0.5)
        }
    }
}
