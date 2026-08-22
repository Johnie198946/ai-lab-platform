//
//  ChatStatusCards.swift
//  AIPlatformApp
//
//  Status & Error Cards (Pending, Degraded, Interrupted, Orphan)
//  Extracted from ChatView for modularity and minimal footprint.
//

import SwiftUI

// MARK: - In-Flight & Queue Models

public struct PendingItem: Identifiable, Sendable {
    public let id: String
    public let text: String
    public let quote: QuotedContext?
    public let contextScope: ChatContextScopeDTO
    public let clientSessionContext: ClientSessionContextDTO?

    public init(id: String = UUID().uuidString, text: String, quote: QuotedContext? = nil, contextScope: ChatContextScopeDTO = ChatContextScopeDTO(), clientSessionContext: ClientSessionContextDTO? = nil) {
        self.id = id
        self.text = text
        self.quote = quote
        self.contextScope = contextScope
        self.clientSessionContext = clientSessionContext
    }
}

public struct InFlightRequest: Identifiable, Sendable {
    public let id: String
    public let sessionId: String
    public let text: String
    public let quote: QuotedContext?
    public let regenerate: Bool
    public let agentId: String?
    public let contextScope: ChatContextScopeDTO
    public let clientSessionContext: ClientSessionContextDTO?
    public var didRetry404: Bool = false
    public var phase: InFlightPhase = .thinking

    public init(
        id: String = UUID().uuidString,
        sessionId: String,
        text: String,
        quote: QuotedContext? = nil,
        regenerate: Bool = false,
        agentId: String? = nil,
        contextScope: ChatContextScopeDTO = ChatContextScopeDTO(),
        clientSessionContext: ClientSessionContextDTO? = nil,
        didRetry404: Bool = false,
        phase: InFlightPhase = .thinking
    ) {
        self.id = id
        self.sessionId = sessionId
        self.text = text
        self.quote = quote
        self.regenerate = regenerate
        self.agentId = agentId
        self.contextScope = contextScope
        self.clientSessionContext = clientSessionContext
        self.didRetry404 = didRetry404
        self.phase = phase
    }
}

public enum InFlightPhase: Equatable, Sendable {
    case thinking
    case timeout
    case networkError
    case serverError(String)
}

public struct NoteDraftCard: View {
    public let draft: NoteDraftBlock
    public let onSave: () -> Void
    public let onMerge: () -> Void
    public let onEdit: () -> Void
    public let onDiscard: () -> Void

    public var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Label("笔记草稿", systemImage: "note.text.badge.plus")
                .font(.headline)
                .foregroundStyle(AppTheme.Colors.quantumViolet)
            Text(draft.title).font(.subheadline.weight(.semibold))
            Text(draft.markdown)
                .font(.footnote)
                .foregroundStyle(AppTheme.Colors.textSecondary)
                .lineLimit(8)
            if let candidates = draft.mergeCandidates, !candidates.isEmpty {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                    Label("发现 \(candidates.count) 篇同类笔记", systemImage: "arrow.triangle.merge")
                        .font(.footnote.weight(.semibold))
                    ForEach(candidates.prefix(3)) { candidate in
                        Text("• \(candidate.title)")
                            .font(.caption)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                            .lineLimit(1)
                    }
                    Text("合并后会重新整理内容，旧笔记将移入归档并可恢复。")
                        .font(.caption)
                        .foregroundStyle(AppTheme.Colors.textTertiary)
                }
                .padding(AppTheme.Spacing.sm)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(AppTheme.Colors.surfaceTint)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
            }
            if draft.state == .awaitingConfirmation {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    if draft.mergeCandidates?.isEmpty == false {
                        Button("合并整理并归档旧笔记", action: onMerge)
                            .buttonStyle(.borderedProminent)
                            .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                        Button("仍保存为新笔记", action: onSave).buttonStyle(.bordered)
                    } else {
                        Button("保存到笔记", action: onSave).buttonStyle(.borderedProminent)
                    }
                    Button("编辑后保存", action: onEdit).buttonStyle(.bordered)
                    Button("放弃", role: .destructive, action: onDiscard).buttonStyle(.plain)
                }
            } else {
                Label(statusText, systemImage: statusIcon)
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(draft.state == .discarded ? AppTheme.Colors.textSecondary : Color.green)
            }
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: AppTheme.Radius.lg).stroke(AppTheme.Colors.border, lineWidth: 0.5))
    }

    private var statusText: String {
        switch draft.state {
        case .saved: return "已保存并同步"
        case .savedLocally: return "已保存到本地，等待同步"
        case .discarded: return "已放弃"
        case .awaitingConfirmation: return "等待确认"
        }
    }

    private var statusIcon: String {
        draft.state == .discarded ? "xmark.circle" : "checkmark.circle.fill"
    }
}

// MARK: - Placeholder Views

public struct PendingPlaceholderView: View {
    public let position: Int
    public let onCancel: () -> Void

    public init(position: Int, onCancel: @escaping () -> Void) {
        self.position = position
        self.onCancel = onCancel
    }

    public var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            QuantumAvatarView(size: 32).padding(.top, 2)
            HStack(spacing: AppTheme.Spacing.xs) {
                Image(systemName: "clock.arrow.circlepath")
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Icons.tertiary)
                Text("排队中 · 第 \(position) 位")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                Spacer()
                Button(action: onCancel) {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 13))
                        .foregroundColor(AppTheme.Icons.tertiary)
                }
                .buttonStyle(SoftButtonStyle())
            }
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.sm + 2)
            .background(AppTheme.Colors.cardBackground.opacity(0.7))
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(AppTheme.Colors.border, lineWidth: 0.5)
            )
            Spacer(minLength: 44)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
    }
}

public struct StatusCardView: View {
    public let icon: String
    public let iconColor: Color
    public let title: String
    public let message: String
    public let primary: (label: String, action: () -> Void)
    public let secondary: (label: String, action: () -> Void)?

    public init(
        icon: String,
        iconColor: Color,
        title: String,
        message: String,
        primary: (label: String, action: () -> Void),
        secondary: (label: String, action: () -> Void)? = nil
    ) {
        self.icon = icon
        self.iconColor = iconColor
        self.title = title
        self.message = message
        self.primary = primary
        self.secondary = secondary
    }

    public var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            QuantumAvatarView(size: 32).padding(.top, 2)
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                HStack(spacing: 6) {
                    Image(systemName: icon)
                        .font(.system(size: 12))
                        .foregroundColor(iconColor)
                    Text(title)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                }
                Text(message)
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                HStack(spacing: AppTheme.Spacing.sm) {
                    actionChip(primary.label, primary.action)
                    if let secondary {
                        actionChip(secondary.label, secondary.action)
                    }
                }
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(iconColor.opacity(0.25), lineWidth: 0.5)
            )
            Spacer(minLength: 44)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
    }

    private func actionChip(_ label: String, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(AppTheme.Colors.primary)
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, 6)
                .background(AppTheme.Colors.primary.opacity(0.08))
                .clipShape(Capsule())
        }
        .buttonStyle(SoftButtonStyle())
    }
}

public struct DegradedCardView: View {
    public let message: String
    public let onRetry: () -> Void

    public init(message: String, onRetry: @escaping () -> Void) {
        self.message = message
        self.onRetry = onRetry
    }

    public var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            QuantumAvatarView(size: 32).padding(.top, 2)
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                HStack(spacing: 6) {
                    Image(systemName: "wifi.exclamationmark")
                        .font(.system(size: 12))
                    .foregroundColor(AppTheme.Icons.warning)
                    Text("服务暂时不可用")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                }
                Text(message.isEmpty ? "服务暂时不可用，请稍后重试" : message)
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                retryChip
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(AppTheme.Colors.securityYellow.opacity(0.25), lineWidth: 0.5)
            )
            Spacer(minLength: 44)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
    }

    private var retryChip: some View {
        Button(action: onRetry) {
            HStack(spacing: 4) {
                Image(systemName: "arrow.clockwise")
                Text("重试")
            }
            .font(.system(size: 12, weight: .semibold))
            .foregroundColor(AppTheme.Icons.interactive)
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, 6)
            .background(AppTheme.Colors.primary.opacity(0.08))
            .clipShape(Capsule())
        }
        .buttonStyle(SoftButtonStyle())
    }
}

public struct InterruptedCardView: View {
    public let onRetry: () -> Void

    public init(onRetry: @escaping () -> Void) {
        self.onRetry = onRetry
    }

    public var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            QuantumAvatarView(size: 32).padding(.top, 2)
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                HStack(spacing: 6) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 12))
                    .foregroundColor(AppTheme.Icons.warning)
                    Text("响应已中断")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                }
                Text(SessionManager.interruptedText)
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                retryChip
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(AppTheme.Colors.securityYellow.opacity(0.25), lineWidth: 0.5)
            )
            Spacer(minLength: 44)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
    }

    private var retryChip: some View {
        Button(action: onRetry) {
            HStack(spacing: 4) {
                Image(systemName: "arrow.clockwise")
                Text("重试")
            }
            .font(.system(size: 12, weight: .semibold))
            .foregroundColor(AppTheme.Icons.interactive)
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, 6)
            .background(AppTheme.Colors.primary.opacity(0.08))
            .clipShape(Capsule())
        }
        .buttonStyle(SoftButtonStyle())
    }
}

public struct OrphanPendingCardView: View {
    public let onRetry: () -> Void

    public init(onRetry: @escaping () -> Void) {
        self.onRetry = onRetry
    }

    public var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            QuantumAvatarView(size: 32).padding(.top, 2)
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                HStack(spacing: 6) {
                    Image(systemName: "clock.badge.exclamationmark")
                        .font(.system(size: 12))
                    .foregroundColor(AppTheme.Icons.tertiary)
                    Text("未完成")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                }
                Text("该回复在上次中断前未完成，可继续重试。")
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                retryChip
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(AppTheme.Colors.border, lineWidth: 0.5)
            )
            Spacer(minLength: 44)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
    }

    private var retryChip: some View {
        Button(action: onRetry) {
            HStack(spacing: 4) {
                Image(systemName: "arrow.clockwise")
                Text("继续 / 重试")
            }
            .font(.system(size: 12, weight: .semibold))
            .foregroundColor(AppTheme.Icons.interactive)
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, 6)
            .background(AppTheme.Colors.primary.opacity(0.08))
            .clipShape(Capsule())
        }
        .buttonStyle(SoftButtonStyle())
    }
}
