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
    @Environment(\.colorScheme) private var colorScheme

    public let draft: NoteDraftBlock
    public let onSave: () -> Void
    public let onMerge: ([String]) -> Void
    public let onEdit: () -> Void
    public let onDiscard: () -> Void
    @State private var selectedCandidateIds: Set<String>

    public init(draft: NoteDraftBlock, onSave: @escaping () -> Void, onMerge: @escaping ([String]) -> Void, onEdit: @escaping () -> Void, onDiscard: @escaping () -> Void) {
        self.draft = draft
        self.onSave = onSave
        self.onMerge = onMerge
        self.onEdit = onEdit
        self.onDiscard = onDiscard
        let preferred = (draft.mergeCandidates ?? []).filter { $0.confidence >= 0.7 }.map(\.id)
        _selectedCandidateIds = State(initialValue: Set(preferred.isEmpty ? (draft.mergeCandidates ?? []).map(\.id) : preferred))
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            headerView
            previewView
            if hasMergeCandidates {
                mergeNoticeView
            }
            if draft.state == .awaitingConfirmation {
                actionView
            } else {
                statusView
            }
        }
        .padding(AppTheme.Spacing.xl)
        .quantumCard()
        .accessibilityElement(children: .contain)
    }

    private var hasMergeCandidates: Bool {
        !(draft.mergeCandidates ?? []).isEmpty
    }

    private var hasMergePreview: Bool {
        draft.selectedMergeCandidateIds != nil && draft.mergedMarkdown?.isEmpty == false
    }

    private var headerView: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
            ZStack {
                Circle()
                    .fill(AppTheme.Colors.quantumViolet.opacity(colorScheme == .dark ? 0.24 : 0.12))
                Image(systemName: hasMergeCandidates ? "arrow.triangle.merge" : "note.text.badge.plus")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(AppTheme.Icons.intelligence)
            }
            .frame(width: 40, height: 40)
            .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                HStack(spacing: AppTheme.Spacing.sm) {
                    Text(hasMergeCandidates ? "笔记整理建议" : "笔记草稿")
                        .font(AppTheme.Typography.cardTitle)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    Text("待确认")
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Icons.intelligence)
                        .padding(.horizontal, AppTheme.Spacing.sm)
                        .padding(.vertical, 5)
                        .background(AppTheme.Colors.surfaceTint)
                        .clipShape(Capsule())
                }
                Text(draft.title)
                    .font(AppTheme.Typography.supporting.weight(.semibold))
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                if let count = draft.sourceMessageCount {
                    Text("已归纳 \(count) 条来源\(draft.snapshotComplete == true ? " · 完整会话" : " · 会话不完整")")
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textTertiary)
                }
            }
            Spacer(minLength: 0)
        }
    }

    private var previewView: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            HStack {
                Text("内容预览")
                    .font(AppTheme.Typography.label)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                Spacer()
                if !draft.tags.isEmpty {
                    Text("\(draft.tags.count) 个标签")
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textTertiary)
                }
            }

            Text(hasMergePreview ? String((draft.mergedMarkdown ?? "").prefix(700)) : previewText)
                .font(AppTheme.Typography.supporting)
                .foregroundStyle(AppTheme.Colors.textSecondary)
                .lineSpacing(3)
                .lineLimit(5)
                .fixedSize(horizontal: false, vertical: true)

            if !draft.tags.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: AppTheme.Spacing.xs) {
                        ForEach(draft.tags.prefix(4), id: \.self) { tag in
                            Text("#\(tag)")
                                .font(AppTheme.Typography.micro)
                                .foregroundStyle(AppTheme.Icons.intelligence)
                                .padding(.horizontal, AppTheme.Spacing.sm)
                                .padding(.vertical, 6)
                                .background(AppTheme.Colors.cardBackground)
                                .clipShape(Capsule())
                        }
                    }
                }
            }
        }
        .padding(AppTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.Colors.surfaceTint)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    private var mergeNoticeView: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            HStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: "sparkles")
                    .foregroundStyle(AppTheme.Colors.emberOrange)
                Text("发现 \(draft.mergeCandidates?.count ?? 0) 篇相关笔记")
                    .font(AppTheme.Typography.supporting.weight(.semibold))
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Spacer(minLength: 0)
            }

            VStack(spacing: AppTheme.Spacing.xs) {
                ForEach(draft.mergeCandidates ?? []) { candidate in
                    Button {
                        if selectedCandidateIds.contains(candidate.id) {
                            selectedCandidateIds.remove(candidate.id)
                        } else {
                            selectedCandidateIds.insert(candidate.id)
                        }
                    } label: {
                        HStack(spacing: AppTheme.Spacing.sm) {
                            Image(systemName: selectedCandidateIds.contains(candidate.id) ? "checkmark.circle.fill" : "circle")
                                .foregroundStyle(selectedCandidateIds.contains(candidate.id) ? AppTheme.Icons.intelligence : AppTheme.Colors.textTertiary)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(candidate.title).font(AppTheme.Typography.micro.weight(.semibold)).lineLimit(1)
                                if let reason = candidate.matchReason, !reason.isEmpty {
                                    Text(reason).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textTertiary).lineLimit(1)
                                }
                            }
                            Spacer()
                        }
                    }
                    .buttonStyle(.plain)
                }
            }

            Text("合并会重新编排内容，旧笔记会移入可恢复的归档。")
                .font(AppTheme.Typography.micro)
                .foregroundStyle(AppTheme.Colors.textTertiary)
        }
        .padding(AppTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.Colors.warningSurface)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    private var actionView: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            if hasMergeCandidates {
                Button { onMerge(Array(selectedCandidateIds)) } label: {
                    Label(hasMergePreview ? "确认合并并归档" : "预览合并稿（\(selectedCandidateIds.count)）", systemImage: "arrow.triangle.merge")
                }
                .buttonStyle(QuantumPrimaryButtonStyle())
                .disabled(selectedCandidateIds.isEmpty)

                Button(action: onSave) {
                    Label("保存为新笔记", systemImage: "plus.circle")
                        .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget)
                }
                .buttonStyle(.bordered)
                .tint(AppTheme.Colors.primary)
            } else {
                Button(action: onSave) {
                    Label("保存到笔记", systemImage: "checkmark.circle")
                }
                .buttonStyle(QuantumPrimaryButtonStyle())
            }

            HStack(spacing: AppTheme.Spacing.md) {
                Button(action: onEdit) {
                    Label("编辑后保存", systemImage: "pencil")
                        .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget)
                }
                .buttonStyle(.borderless)
                .foregroundStyle(AppTheme.Colors.textSecondary)

                Button("放弃", role: .destructive, action: onDiscard)
                    .frame(minWidth: AppTheme.Metrics.minimumTouchTarget, minHeight: AppTheme.Metrics.minimumTouchTarget)
                    .buttonStyle(.borderless)
            }
            .font(AppTheme.Typography.supporting.weight(.medium))
        }
    }

    private var statusView: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: statusIcon)
                .foregroundStyle(draft.state == .discarded ? AppTheme.Colors.textTertiary : AppTheme.Icons.success)
            Text(statusText)
                .font(AppTheme.Typography.supporting.weight(.medium))
                .foregroundStyle(AppTheme.Colors.textSecondary)
            Spacer(minLength: 0)
        }
        .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
        .padding(.horizontal, AppTheme.Spacing.md)
        .background(draft.state == .discarded ? AppTheme.Colors.surfaceTint : AppTheme.Colors.successSurface)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    private var previewText: String {
        var value = draft.markdown
        value = value.replacingOccurrences(of: "(?m)^#{1,6}\\s*", with: "", options: .regularExpression)
        value = value.replacingOccurrences(of: "(?m)^\\s*[-*]\\s+", with: "• ", options: .regularExpression)
        return value.trimmingCharacters(in: .whitespacesAndNewlines)
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
