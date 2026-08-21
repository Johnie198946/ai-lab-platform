//
//  ChatMessageStreamView.swift
//  AIPlatformApp
//
//  ChatGPT / Gemini Style Message Stream (v2 - Butter-Smooth & Zero-Jank)
//  - Native ScrollView + deterministic VStack message canvas
//  - No lazy placement or programmatic scroll transactions competing with gestures
//

import SwiftUI

public struct ChatMessageStreamView: View {
    @ObservedObject public var coordinator: TenantSessionCoordinator

    public init(coordinator: TenantSessionCoordinator) {
        self.coordinator = coordinator
    }

    public var body: some View {
        ScrollView {
            // iOS 26.1 的 LazyVStack 在“单条超高 Markdown + 尾部新增消息”后向下拖动时，
            // 会持续重算 LazySubviewPlacements 并占满主线程。消息解析已有有界缓存，
            // 因此这里优先采用确定性的 VStack，换取可收敛的滚动内容尺寸。
            VStack(spacing: AppTheme.Spacing.md) {
                if coordinator.hasOlderMessages {
                    historyButton("加载更早消息", systemImage: "clock.arrow.circlepath") {
                        coordinator.loadOlderMessagePage()
                    }
                }

                if coordinator.messages.isEmpty && coordinator.pendingQueue.isEmpty {
                    ChatWelcomeView(
                        quickCommands: coordinator.quickCommands,
                        onSelect: { coordinator.selectCommand($0) }
                    )
                        .frame(minHeight: 420)
                        .transition(.opacity)
                }

                ForEach(coordinator.messages) { message in
                    messageRow(message).id(message.id)
                }
                ForEach(Array(coordinator.pendingQueue.enumerated()), id: \.element.id) { index, item in
                    PendingPlaceholderView(
                        position: index + 1,
                        onCancel: { coordinator.cancelQueued(item.id) }
                    ).id("pending_\(item.id)")
                }

                if coordinator.hasNewerMessages {
                    HStack(spacing: AppTheme.Spacing.sm) {
                        historyButton("加载更新消息", systemImage: "arrow.down.circle") {
                            coordinator.loadNewerMessagePage()
                        }
                        historyButton("回到最新", systemImage: "arrow.down.to.line") {
                            coordinator.returnToLatestMessages()
                        }
                    }
                }

                Color.clear.frame(height: 1)
            }
            .frame(maxWidth: AppTheme.Metrics.readableContentWidth)
            .frame(maxWidth: .infinity)
            .padding(.vertical, AppTheme.Spacing.md)
        }
        .id(coordinator.historyPageIdentity)
        // 仅设置首次进入会话的位置。不能使用无 role 的 defaultScrollAnchor：
        // 超长消息后继续发送时，它会参与内容尺寸变化的锚点平移，并在 iOS 26
        // 触发消息栈的 AttributeGraph 布局循环。
        .initialScrollAnchor(startsAtBottom: coordinator.historyPageStartsAtBottom)
        .scrollDismissesKeyboard(.interactively)
    }

    private func historyButton(_ title: String, systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(title, systemImage: systemImage)
                .font(.footnote.weight(.medium))
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, AppTheme.Spacing.sm)
                .background(.thinMaterial, in: Capsule())
        }
        .buttonStyle(.plain)
        .foregroundStyle(Color.accentColor)
        .disabled(coordinator.isGenerating)
        .opacity(coordinator.isGenerating ? 0.45 : 1)
    }

    @ViewBuilder
    private func messageRow(_ message: ChatMessage) -> some View {
        if message.role == .interrupted {
            InterruptedCardView(onRetry: { coordinator.retryMessage(message.id) })
        } else if message.degraded {
            DegradedCardView(onRetry: { coordinator.retryMessage(message.id) })
        } else if message.pending && message.role == .assistant {
            if let req = coordinator.inflight, req.id == message.id {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                    // 实时思考链：流式期间的 thought/tool 步骤逐步揭示，绝不藏在占位卡后面
                    if !message.blocks.isEmpty {
                        ForEach(message.blocks) { block in
                            liveBlockCard(block)
                        }
                    }
                    ChatInFlightPlaceholderView(req: req, coordinator: coordinator)
                }
            } else {
                OrphanPendingCardView(onRetry: { coordinator.retryMessage(message.id) })
            }
        } else if let clarify = message.clarifyBlock,
                  !clarify.isSubmitted,
                  !containsRequirementConfirmation(message) {
            ClarifyCard(
                block: clarify,
                onSubmit: { selection in
                    coordinator.sendClarifySelection(messageId: message.id, selection: selection)
                },
                onRecover: { coordinator.recoverExpiredClarify(messageId: message.id) }
            )
        } else {
            // 提交后（isSubmitted）：降级为完整气泡渲染——思维链胶囊 + 已提交澄清卡 + 正文
            // 实时可见（同 SSE 流事件驱动，绝不因澄清卡独占遮住执行过程）
            MessageBubbleView(
                message: message,
                context: coordinator.makeRenderContext(for: message),
                onQuoteFollowUp: { quoted in coordinator.quotedContext = quoted },
                onRegenerate: { msgId in coordinator.retryMessage(msgId) }
            )
        }
    }

    /// 普通 Clarify 保持卡片独占的轻量形态；最终确认必须同时呈现需求确认单表格。
    private func containsRequirementConfirmation(_ message: ChatMessage) -> Bool {
        if message.content.contains("确认维度") && message.content.contains("已确认需求") {
            return true
        }
        return message.blocks.contains { block in
            if case .table(let table) = block {
                return table.title.contains("需求确认")
            }
            return false
        }
    }

    /// 流式期间实时揭示的块（仅 reasoning / clarify 有实时价值，其余等待完成态统一渲染）
    @ViewBuilder
    private func liveBlockCard(_ block: MessageBlock) -> some View {
        switch block {
        case .reasoning(let steps):
            ReasoningCard(steps: steps, isStreaming: true)
        case .clarify(let clarifyBlock):
            ClarifyCard(
                block: clarifyBlock,
                onSubmit: { selection in
                    if let msg = coordinator.messages.first(where: {
                        if case .clarify(let c) = $0.blocks.first { return c.id == clarifyBlock.id }
                        return false
                    }) {
                        coordinator.sendClarifySelection(messageId: msg.id, selection: selection)
                    }
                },
                onRecover: {
                    if let msg = coordinator.messages.last(where: {
                        $0.clarifyBlock?.id == clarifyBlock.id
                    }) { coordinator.recoverExpiredClarify(messageId: msg.id) }
                }
            )
        default:
            EmptyView()
        }
    }
}

private extension View {
    @ViewBuilder
    func initialScrollAnchor(startsAtBottom: Bool) -> some View {
        if #available(iOS 18.0, *), startsAtBottom {
            defaultScrollAnchor(.bottom, for: .initialOffset)
        } else {
            // iOS 17 没有按角色限定锚点的 API；保持原生顶部初始位置，
            // 也不要恢复会影响后续内容尺寸变化的全局底部锚点。
            self
        }
    }
}

private struct ChatWelcomeView: View {
    let quickCommands: [String]
    let onSelect: (String) -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var appeared = false

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xl) {
            HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                QuantumAvatarView(size: 52)

                VStack(alignment: .leading, spacing: 6) {
                    Text("AI LAB · GENERATED WORKSPACE")
                        .font(AppTheme.Typography.micro)
                        .tracking(0.8)
                        .foregroundColor(AppTheme.Icons.interactive)

                    Text("今天想推进什么？")
                        .font(.system(.title, design: .rounded, weight: .bold))
                        .foregroundColor(AppTheme.Colors.textPrimary)

                    Text("先确认目标，再组织 Agent、知识与工具完成交付。")
                        .font(AppTheme.Typography.supporting)
                        .foregroundColor(AppTheme.Colors.textSecondary)
                        .lineSpacing(3)
                }
                Spacer(minLength: 0)
            }

            HStack(spacing: AppTheme.Spacing.sm) {
                statusChip("实时编排", icon: "waveform.path", color: AppTheme.Colors.statusCompleted)
                statusChip("本地隐私", icon: "lock.shield", color: AppTheme.Colors.interactiveBlue)
            }

            if !quickCommands.isEmpty {
                VStack(alignment: .leading, spacing: 0) {
                    Text("推荐工作流")
                        .font(AppTheme.Typography.label)
                        .foregroundColor(AppTheme.Colors.textSecondary)
                        .padding(.horizontal, AppTheme.Spacing.md)
                        .padding(.bottom, AppTheme.Spacing.sm)

                    ForEach(Array(quickCommands.prefix(3).enumerated()), id: \.element) { index, command in
                        Button(action: { onSelect(command) }) {
                            HStack(spacing: AppTheme.Spacing.md) {
                                Image(systemName: suggestionIcon(index))
                                    .font(.body.weight(.medium))
                            .foregroundColor(AppTheme.Icons.interactive)
                                    .frame(width: 24)
                                Text(command)
                                    .font(AppTheme.Typography.supporting)
                                    .foregroundColor(AppTheme.Colors.textPrimary)
                                    .lineLimit(2)
                                    .multilineTextAlignment(.leading)
                                Spacer(minLength: AppTheme.Spacing.sm)
                                Image(systemName: "arrow.up.right")
                                    .font(.caption.weight(.semibold))
                            .foregroundColor(AppTheme.Icons.tertiary)
                            }
                            .padding(.horizontal, AppTheme.Spacing.md)
                            .frame(minHeight: 52)
                        }
                        .buttonStyle(SoftButtonStyle())

                        if index < min(quickCommands.count, 3) - 1 {
                            Divider()
                                .padding(.leading, 52)
                        }
                    }
                }
                .quantumCard()
                .frame(maxWidth: 420)
            }
        }
        .padding(AppTheme.Spacing.xl)
        .background(AppTheme.Colors.cardBackground.opacity(0.54))
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous)
                .stroke(AppTheme.Colors.border.opacity(0.72), lineWidth: 0.75)
        }
        .padding(.horizontal, AppTheme.Metrics.contentGutter)
        .opacity(appeared ? 1 : 0)
        .offset(y: appeared ? 0 : (reduceMotion ? 0 : 10))
        .onAppear {
            withAnimation(reduceMotion ? nil : AppTheme.Motion.standard) {
                appeared = true
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Quantum 助手已就绪。可以进行需求澄清、智能编排和知识增强。")
    }

    private func statusChip(_ title: String, icon: String, color: Color) -> some View {
        Label(title, systemImage: icon)
            .font(AppTheme.Typography.micro)
            .foregroundColor(color)
            .padding(.horizontal, 10)
            .padding(.vertical, 7)
            .background(color.opacity(0.10))
            .clipShape(Capsule())
    }

    private func suggestionIcon(_ index: Int) -> String {
        switch index {
        case 0: return "scope"
        case 1: return "doc.text.magnifyingglass"
        default: return "point.3.connected.trianglepath.dotted"
        }
    }
}
