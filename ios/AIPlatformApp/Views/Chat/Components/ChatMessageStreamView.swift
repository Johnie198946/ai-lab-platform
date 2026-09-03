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
    public let onBackgroundTap: () -> Void
    public let onStartTopic: ((ChatMessage) -> Void)?

    public init(
        coordinator: TenantSessionCoordinator,
        onBackgroundTap: @escaping () -> Void = {},
        onStartTopic: ((ChatMessage) -> Void)? = nil
    ) {
        self.coordinator = coordinator
        self.onBackgroundTap = onBackgroundTap
        self.onStartTopic = onStartTopic
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
                    ChatWelcomeView()
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
            .background {
                Color.clear
                    .contentShape(Rectangle())
                    .onTapGesture {
                        coordinator.collapseActiveClarify()
                        onBackgroundTap()
                    }
            }
        }
        .id(coordinator.historyPageIdentity)
        // 仅设置首次进入会话的位置。不能使用无 role 的 defaultScrollAnchor：
        // 超长消息后继续发送时，它会参与内容尺寸变化的锚点平移，并在 iOS 26
        // 触发消息栈的 AttributeGraph 布局循环。
        .initialScrollAnchor(startsAtBottom: coordinator.historyPageStartsAtBottom)
        .scrollDismissesKeyboard(.immediately)
    }

    private func historyButton(_ title: String, systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(title, systemImage: systemImage)
                .font(.footnote.weight(.medium))
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, AppTheme.Spacing.sm)
                .background(.thinMaterial, in: Capsule())
        }
        .buttonStyle(SoftButtonStyle())
        .foregroundStyle(Color.accentColor)
        .disabled(coordinator.isGenerating)
        .opacity(coordinator.isGenerating ? 0.45 : 1)
    }

    @ViewBuilder
    private func messageRow(_ message: ChatMessage) -> some View {
        if coordinator.isProcessingExistingRun(message) {
            BackgroundProcessingCardView()
        } else if message.role == .interrupted {
            InterruptedCardView(onRetry: { coordinator.retryMessage(message.id) })
        } else if message.degraded {
            DegradedCardView(
                message: message.content,
                onRetry: { coordinator.retryMessage(message.id) }
            )
        } else if message.usesPendingPlaceholder {
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
                onRecover: { coordinator.recoverExpiredClarify(messageId: message.id) },
                onDraftChange: { ids, text in
                    coordinator.updateClarifyDraft(messageId: message.id, selectionIDs: ids, customText: text)
                },
                onExpand: { coordinator.setClarifyCollapsed(messageId: message.id, collapsed: false) }
            )
        } else {
            // 提交后（isSubmitted）：降级为完整气泡渲染——思维链胶囊 + 已提交澄清卡 + 正文
            // 实时可见（同 SSE 流事件驱动，绝不因澄清卡独占遮住执行过程）
            MessageBubbleView(
                message: message,
                context: coordinator.makeRenderContext(for: message),
                onQuoteFollowUp: { quoted in coordinator.quotedContext = quoted },
                onRegenerate: { msgId in coordinator.retryMessage(msgId) },
                onStartTopic: { message in
                    if let onStartTopic { onStartTopic(message) }
                    else { coordinator.startTargetedTopic(from: message) }
                }
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

extension ChatMessage {
    var usesPendingPlaceholder: Bool {
        pending && role == .assistant
            && content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
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
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var appeared = false
    @State private var interactionPoint = CGPoint(x: 0.5, y: 0.5)
    @State private var isInteracting = false

    private let cardCornerRadius: CGFloat = 30

    var body: some View {
        GeometryReader { proxy in
            let normalizedX = (interactionPoint.x - 0.5) * 2
            let normalizedY = (interactionPoint.y - 0.5) * 2
            let tiltAmount = reduceMotion ? 0 : sqrt(normalizedX * normalizedX + normalizedY * normalizedY) * 6

            ZStack {
                RoundedRectangle(cornerRadius: cardCornerRadius, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [
                                AppTheme.Colors.quantumBlue.opacity(0.18),
                                AppTheme.Colors.cardBackground.opacity(0.98),
                                AppTheme.Colors.quantumViolet.opacity(0.22)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )

                profileAtmosphere

                VStack(spacing: 18) {
                    Spacer(minLength: 18)

                    Text("QUANTUM · AI WORKSPACE")
                        .font(.system(size: 11, weight: .semibold, design: .rounded))
                        .tracking(1.5)
                        .foregroundStyle(AppTheme.Colors.quantumViolet)

                    ZStack {
                        Circle()
                            .fill(Color.white.opacity(0.62))
                            .frame(width: 176, height: 176)
                            .blur(radius: 1)
                            .shadow(color: AppTheme.Colors.quantumBlue.opacity(0.20), radius: 28)

                        QuantumAvatarView(size: 148)
                    }
                    .accessibilityHidden(true)

                    VStack(spacing: 7) {
                        Text("Quantum")
                            .font(.system(size: 30, weight: .bold, design: .rounded))
                            .foregroundStyle(AppTheme.Colors.textPrimary)

                        Text("你的智能工作空间")
                            .font(AppTheme.Typography.supporting)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                    }

                    HStack(spacing: 8) {
                        Circle()
                            .fill(AppTheme.Colors.statusCompleted)
                            .frame(width: 7, height: 7)
                        Text("描述目标，开始协作")
                            .font(AppTheme.Typography.micro.weight(.medium))
                    }
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .padding(.horizontal, 14)
                    .frame(minHeight: 36)
                    .background(.ultraThinMaterial, in: Capsule())

                    Spacer(minLength: 18)
                }
                .padding(.horizontal, 24)

                if !reduceMotion {
                    RadialGradient(
                        colors: [Color.white.opacity(isInteracting ? 0.42 : 0.16), .clear],
                        center: UnitPoint(x: interactionPoint.x, y: interactionPoint.y),
                        startRadius: 0,
                        endRadius: 190
                    )
                    .blendMode(.screen)
                    .allowsHitTesting(false)
                }
            }
            .frame(width: min(proxy.size.width, 318), height: 382)
            .clipShape(RoundedRectangle(cornerRadius: cardCornerRadius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: cardCornerRadius, style: .continuous)
                    .stroke(AppTheme.Colors.quantumGradient, lineWidth: isInteracting ? 2 : 1)
                    .opacity(isInteracting ? 0.88 : 0.34)
                    .allowsHitTesting(false)
            }
            .shadow(
                color: AppTheme.Colors.quantumViolet.opacity(isInteracting ? 0.22 : 0.12),
                radius: isInteracting ? 26 : 18,
                y: isInteracting ? 14 : 9
            )
            .rotation3DEffect(
                .degrees(tiltAmount),
                axis: (x: -normalizedY, y: normalizedX, z: 0),
                perspective: 0.72
            )
            .scaleEffect(isInteracting && !reduceMotion ? 0.985 : 1)
            .animation(.spring(response: 0.28, dampingFraction: 0.78), value: isInteracting)
            .animation(.spring(response: 0.34, dampingFraction: 0.82), value: interactionPoint)
            .contentShape(RoundedRectangle(cornerRadius: cardCornerRadius, style: .continuous))
            .simultaneousGesture(profileGesture(in: CGSize(width: min(proxy.size.width, 318), height: 382)))
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
        }
        .frame(height: 420, alignment: .center)
        .padding(.horizontal, max(AppTheme.Metrics.contentGutter, 22))
        .opacity(appeared ? 1 : 0)
        .offset(y: appeared ? 0 : (reduceMotion ? 0 : 12))
        .onAppear {
            withAnimation(reduceMotion ? nil : AppTheme.Motion.standard) {
                appeared = true
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Quantum，你的智能工作空间")
        .accessibilityHint("在下方输入框描述你想完成的任务")
    }

    private var profileAtmosphere: some View {
        ZStack {
            Circle()
                .fill(AppTheme.Colors.quantumCyan.opacity(0.18))
                .frame(width: 190, height: 190)
                .blur(radius: 42)
                .offset(x: -112, y: -146)

            Circle()
                .fill(AppTheme.Colors.quantumViolet.opacity(0.20))
                .frame(width: 210, height: 210)
                .blur(radius: 50)
                .offset(x: 118, y: 136)

            RoundedRectangle(cornerRadius: cardCornerRadius, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [Color.white.opacity(0.18), .clear, Color.white.opacity(0.10)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
        }
        .allowsHitTesting(false)
    }

    private func profileGesture(in size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 8, coordinateSpace: .local)
            .onChanged { value in
                guard !reduceMotion else { return }
                isInteracting = true
                interactionPoint = CGPoint(
                    x: min(max(value.location.x / max(size.width, 1), 0), 1),
                    y: min(max(value.location.y / max(size.height, 1), 0), 1)
                )
            }
            .onEnded { _ in
                guard !reduceMotion else { return }
                isInteracting = false
                interactionPoint = CGPoint(x: 0.5, y: 0.5)
            }
        }
}
