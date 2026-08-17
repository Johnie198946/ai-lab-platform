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

    public init(
        isGenerating: Bool,
        title: String,
        onTitleTap: @escaping () -> Void,
        onNewSession: @escaping () -> Void,
        onHistoryTap: @escaping () -> Void
    ) {
        self.isGenerating = isGenerating
        self.title = title
        self.onTitleTap = onTitleTap
        self.onNewSession = onNewSession
        self.onHistoryTap = onHistoryTap
    }

    public var body: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            ZStack(alignment: .bottomTrailing) {
                QuantumAvatarView(size: 30)
                Circle()
                    .fill(isGenerating ? AppTheme.Colors.statusRunning : AppTheme.Colors.quantumCyan)
                    .frame(width: 9, height: 9)
                    .overlay(Circle().stroke(AppTheme.Colors.cardBackground, lineWidth: 1.5))
            }
            Button(action: onTitleTap) {
                HStack(spacing: 4) {
                    Text(title.isEmpty ? "新会话" : title)
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                        .lineLimit(1)
                    Image(systemName: "chevron.down")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(AppTheme.Colors.textTertiary)
                }
            }
            .buttonStyle(SoftButtonStyle())
            Spacer()
            Button(action: onNewSession) {
                Image(systemName: "square.and.pencil")
                    .font(.system(size: 15))
                    .foregroundColor(AppTheme.Colors.textSecondary)
            }
            .buttonStyle(SoftButtonStyle())
            Button(action: onHistoryTap) {
                Image(systemName: "clock.arrow.circlepath")
                    .font(.system(size: 15))
                    .foregroundColor(AppTheme.Colors.textSecondary)
            }
            .buttonStyle(SoftButtonStyle())
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.sm)
        .background(AppTheme.Colors.cardBackground)
    }
}
