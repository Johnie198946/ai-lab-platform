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
    @State private var showingDetails = false

    public let draft: NoteDraftBlock
    public let onSave: () -> Void
    public let onMerge: () -> Void
    public let onEdit: () -> Void
    public let onDiscard: () -> Void

    public var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                headerView
                previewView
                if hasMergeCandidates {
                    mergeNoticeView
                }
            }
            .contentShape(Rectangle())
            .onTapGesture { showingDetails = true }
            .accessibilityAddTraits(.isButton)
            .accessibilityHint("打开完整笔记草稿")
            if draft.state == .awaitingConfirmation {
                actionView
            } else {
                statusView
            }
        }
        .padding(AppTheme.Spacing.xl)
        .quantumCard()
        .accessibilityElement(children: .contain)
        .sheet(isPresented: $showingDetails) {
            NoteDraftDetailSheet(draft: draft)
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
    }

    private var hasMergeCandidates: Bool {
        !(draft.mergeCandidates ?? []).isEmpty
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
                    Text(badgeText)
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
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.up.chevron.down")
                .font(.caption.weight(.semibold))
                .foregroundStyle(AppTheme.Colors.textTertiary)
                .accessibilityHidden(true)
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

            Text(previewText)
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

            HStack(spacing: AppTheme.Spacing.xs) {
                ForEach((draft.mergeCandidates ?? []).prefix(2)) { candidate in
                    Text(candidate.title)
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                        .lineLimit(1)
                        .padding(.horizontal, AppTheme.Spacing.sm)
                        .padding(.vertical, 6)
                        .background(AppTheme.Colors.cardBackground.opacity(0.82))
                        .clipShape(Capsule())
                }
                if let count = draft.mergeCandidates?.count, count > 2 {
                    Text("+\(count - 2)")
                        .font(AppTheme.Typography.micro.weight(.semibold))
                        .foregroundStyle(AppTheme.Colors.textTertiary)
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
                Button(action: onMerge) {
                    Label("合并整理并归档旧笔记", systemImage: "arrow.triangle.merge")
                }
                .buttonStyle(QuantumPrimaryButtonStyle())

                Button(action: onSave) {
                    Label("保存为新笔记", systemImage: "plus.circle")
                        .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget)
                }
                .buttonStyle(.bordered)
                .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
                .tint(AppTheme.Colors.primary)
            } else {
                Button(action: onSave) {
                    Label(draft.isUpdate ? "应用到原笔记" : "保存到笔记", systemImage: "checkmark.circle")
                }
                .buttonStyle(QuantumPrimaryButtonStyle())
            }

            HStack(spacing: AppTheme.Spacing.md) {
                Button(action: onEdit) {
                    Label("编辑后保存", systemImage: "pencil")
                        .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget)
                }
                .buttonStyle(.borderless)
                .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
                .foregroundStyle(AppTheme.Colors.textSecondary)

                Button("放弃", role: .destructive, action: onDiscard)
                    .frame(minWidth: AppTheme.Metrics.minimumTouchTarget, minHeight: AppTheme.Metrics.minimumTouchTarget)
                    .buttonStyle(.borderless)
                    .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
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
        case .saved: return draft.isUpdate ? "已更新并同步" : "已保存并同步"
        case .savedLocally: return draft.isUpdate ? "已更新到本地，等待同步" : "已保存到本地，等待同步"
        case .discarded: return "已放弃"
        case .awaitingConfirmation: return "等待确认"
        }
    }

    private var badgeText: String {
        switch draft.state {
        case .awaitingConfirmation: return draft.isUpdate ? "待应用" : "待确认"
        case .saved, .savedLocally: return draft.isUpdate ? "已更新" : "已保存"
        case .discarded: return "已放弃"
        }
    }

    private var statusIcon: String {
        draft.state == .discarded ? "xmark.circle" : "checkmark.circle.fill"
    }
}

private struct NoteDraftDetailSheet: View {
    @Environment(\.dismiss) private var dismiss
    let draft: NoteDraftBlock

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                    if draft.isUpdate {
                        Label(
                            "将更新：\(draft.targetNoteTitle ?? draft.title)",
                            systemImage: "arrow.triangle.2.circlepath"
                        )
                        .font(AppTheme.Typography.supporting.weight(.semibold))
                        .foregroundStyle(AppTheme.Icons.intelligence)
                        .padding(AppTheme.Spacing.md)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(AppTheme.Colors.surfaceTint)
                        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                    }

                    Text(draft.title)
                        .font(AppTheme.Typography.sectionTitle)
                        .foregroundStyle(AppTheme.Colors.textPrimary)

                    Text(.init(draft.markdown))
                        .font(AppTheme.Typography.body)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .lineSpacing(4)
                        .textSelection(.enabled)

                    if !draft.tags.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: AppTheme.Spacing.xs) {
                            ForEach(draft.tags, id: \.self) { tag in
                                Text("#\(tag)")
                                    .font(AppTheme.Typography.micro)
                                    .foregroundStyle(AppTheme.Icons.intelligence)
                                    .padding(.horizontal, AppTheme.Spacing.sm)
                                    .padding(.vertical, 6)
                                    .background(AppTheme.Colors.surfaceTint)
                                    .clipShape(Capsule())
                            }
                            }
                        }
                    }
                }
                .padding(AppTheme.Spacing.xl)
            }
            .background(AppTheme.Colors.background)
            .navigationTitle(draft.isUpdate ? "完善方案详情" : "笔记草稿详情")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") { dismiss() }
                }
            }
        }
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
            .pressBorderGlow(cornerRadius: AppTheme.Radius.lg)
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
            .pressBorderGlow(cornerRadius: AppTheme.Radius.lg)
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

public struct BackgroundProcessingCardView: View {
    public init() {}

    public var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            QuantumAvatarView(size: 32).padding(.top, 2)
            HStack(spacing: AppTheme.Spacing.sm) {
                ProgressView()
                    .controlSize(.small)
                VStack(alignment: .leading, spacing: 3) {
                    Text("Hermes 正在后台处理")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                    Text("正在恢复同一任务的进度，不会重复创建运行。结果返回后会自动更新。")
                        .font(.system(size: 12))
                        .foregroundColor(AppTheme.Colors.textSecondary)
                }
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(AppTheme.Colors.quantumBlue.opacity(0.25), lineWidth: 0.5)
            )
            Spacer(minLength: 44)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Hermes 正在后台处理，结果返回后会自动更新")
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
            .pressBorderGlow(cornerRadius: AppTheme.Radius.lg)
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
            .pressBorderGlow(cornerRadius: AppTheme.Radius.lg)
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

public struct KnowledgeActionCard: View {
    public let action: KnowledgeActionBlock
    public let onApply: () -> Void
    public let onDiscard: () -> Void
    public let onOpenResult: () -> Void
    @State private var showsDetail = false

    public var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Button { showsDetail = true } label: {
                VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 10) {
                    Image(systemName: "wand.and.stars")
                        .foregroundColor(AppTheme.Icons.intelligence)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("知识操作")
                            .font(.system(size: 13, weight: .semibold))
                        Text(action.summary)
                            .font(.system(size: 16, weight: .semibold))
                            .lineLimit(2)
                    }
                    Spacer()
                    stateBadge
                }
                HStack(spacing: 8) {
                    Label("\(action.steps.count) 项修改", systemImage: "list.bullet.clipboard")
                    if action.riskLevel != "low" {
                        Label("需仔细确认", systemImage: "exclamationmark.shield")
                    }
                }
                .font(.system(size: 12))
                .foregroundColor(AppTheme.Colors.textSecondary)
                }
            }
            .buttonStyle(.plain)
            if action.state == .proposed {
                HStack(spacing: 10) {
                    cardButton("查看并确认", filled: true) { showsDetail = true }
                    cardButton("放弃", filled: false, action: onDiscard)
                }
            } else if [.localApplied, .syncPending].contains(action.state) {
                HStack(spacing: 10) {
                    cardButton("继续同步", filled: true, action: onApply)
                    cardButton("打开结果", filled: false, action: onOpenResult)
                }
            } else if action.state == .synced {
                cardButton("打开结果", filled: false, action: onOpenResult)
            }
        }
        .foregroundColor(AppTheme.Colors.textPrimary)
        .padding(18)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 24).stroke(AppTheme.Colors.primary.opacity(0.16), lineWidth: 1))
        .pressBorderGlow(cornerRadius: 24)
        .sheet(isPresented: $showsDetail) { detailSheet }
    }

    private var stateBadge: some View {
        Text(stateLabel)
            .font(.system(size: 11, weight: .semibold))
            .foregroundColor(action.state == .synced ? AppTheme.Icons.success : AppTheme.Colors.primary)
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background((action.state == .synced ? AppTheme.Icons.success : AppTheme.Colors.primary).opacity(0.1))
            .clipShape(Capsule())
    }

    private var stateLabel: String {
        switch action.state {
        case .proposed: return "待确认"
        case .applying: return "应用中"
        case .localApplied: return "已应用到本地"
        case .synced: return "已同步"
        case .syncPending: return "等待同步"
        case .discarded: return "已放弃"
        case .stale: return "需重新生成"
        case .failed: return "失败"
        }
    }

    private func cardButton(_ title: String, filled: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title).font(.system(size: 14, weight: .semibold)).frame(minHeight: 44)
                .frame(maxWidth: .infinity)
                .foregroundColor(filled ? .white : AppTheme.Colors.primary)
                .background(filled ? AppTheme.Colors.primary : AppTheme.Colors.primary.opacity(0.08))
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        }.buttonStyle(.plain)
    }

    private var detailSheet: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text(action.summary).font(.title3.bold())
                    ForEach(Array(action.steps.enumerated()), id: \.offset) { index, step in
                        HStack(alignment: .top, spacing: 12) {
                            Text("\(index + 1)").font(.caption.bold()).frame(width: 28, height: 28)
                                .background(AppTheme.Colors.primary.opacity(0.1)).clipShape(Circle())
                            VStack(alignment: .leading, spacing: 4) {
                                Text(stepLabel(step.kind)).font(.body.bold())
                                if let title = step.title { Text(title).foregroundColor(AppTheme.Colors.textSecondary) }
                                if let id = step.targetNoteId { Text("目标：\(id)").font(.caption).foregroundColor(AppTheme.Colors.textSecondary) }
                            }
                        }
                    }
                    if !action.beforePreview.isEmpty || !action.afterPreview.isEmpty {
                        previewSection("修改前", action.beforePreview)
                        previewSection("修改后", action.afterPreview)
                    }
                    if !action.markdownDiff.isEmpty { previewSection("Markdown 差异", action.markdownDiff) }
                    if action.state == .proposed {
                        cardButton("确认并应用到本地", filled: true) { showsDetail = false; onApply() }
                        cardButton("放弃操作", filled: false) { showsDetail = false; onDiscard() }
                    }
                }.padding(20)
            }
            .navigationTitle("确认知识操作")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("关闭") { showsDetail = false } } }
            .presentationDetents([.medium, .large])
        }
    }

    private func previewSection(_ title: String, _ text: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.caption.bold()).foregroundColor(AppTheme.Colors.textSecondary)
            Text(text.isEmpty ? "无" : text).font(.system(size: 13, design: .monospaced)).textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading).padding(14)
                .background(AppTheme.Colors.secondaryBackground).clipShape(RoundedRectangle(cornerRadius: 14))
        }
    }

    private func stepLabel(_ kind: String) -> String {
        ["create_note":"创建笔记", "create_daily_note":"创建日记", "update_note":"修改正文",
         "rename_note":"重命名", "set_tags":"修改标签", "set_pinned":"置顶状态",
         "add_wikilink":"增加双链", "remove_wikilink":"移除双链", "merge_notes":"合并笔记",
         "archive_note":"归档", "restore_note":"恢复", "move_to_trash":"移入废纸篓"][kind] ?? kind
    }
}
