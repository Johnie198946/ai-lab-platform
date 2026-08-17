//
//  ChatMessageStreamView.swift
//  AIPlatformApp
//
//  ChatGPT / Gemini Style Message Stream with Smart Auto-Scroll
//  - ScrollViewReader + LazyVStack message canvas
//  - Auto-follow while streaming; user drag-up pauses follow and shows "返回最新" floating capsule
//

import SwiftUI

// MARK: - Scroll Offset Preference

public struct ChatScrollOffsetKey: PreferenceKey {
    public static var defaultValue: CGFloat = 0
    public static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = nextValue()
    }
}

// MARK: - Message Stream Canvas

public struct ChatMessageStreamView: View {
    @ObservedObject public var coordinator: TenantSessionCoordinator

    @State private var scrollOffset: CGFloat = 0
    @State private var autoScroll: Bool = true
    @State private var showBackToLatest: Bool = false

    public init(coordinator: TenantSessionCoordinator) {
        self.coordinator = coordinator
    }

    public var body: some View {
        ScrollViewReader { proxy in
            ZStack(alignment: .bottomTrailing) {
                ScrollView {
                    LazyVStack(spacing: AppTheme.Spacing.md) {
                        ForEach(coordinator.messages) { message in
                            messageRow(message).id(message.id)
                        }
                        ForEach(Array(coordinator.pendingQueue.enumerated()), id: \.element.id) { index, item in
                            PendingPlaceholderView(
                                position: index + 1,
                                onCancel: { coordinator.cancelQueued(item.id) }
                            ).id("pending_\(item.id)")
                        }
                    }
                    .padding(.vertical, AppTheme.Spacing.md)
                    .background(
                        GeometryReader { geo in
                            Color.clear.preference(
                                key: ChatScrollOffsetKey.self,
                                value: geo.frame(in: .named("chatScroll")).minY
                            )
                        }
                    )
                }
                .coordinateSpace(name: "chatScroll")
                .onPreferenceChange(ChatScrollOffsetKey.self) { value in
                    scrollOffset = value
                    // 用户向上翻看历史（offset 变大）→ 暂停自动吸底并弹出悬浮按钮
                    if value > 48 {
                        autoScroll = false
                        showBackToLatest = true
                    }
                }
                .onChange(of: coordinator.messages.count) { _, _ in
                    if autoScroll { scrollToLatest(proxy) }
                }
                .onChange(of: coordinator.pendingQueue.count) { _, _ in
                    if autoScroll { scrollToLatest(proxy) }
                }
                .onChange(of: coordinator.inflight?.id) { _, _ in
                    if autoScroll { scrollToLatest(proxy) }
                }

                if showBackToLatest {
                    Button(action: {
                        withAnimation(.easeOut(duration: 0.3)) {
                            autoScroll = true
                            showBackToLatest = false
                            scrollToLatest(proxy)
                        }
                    }) {
                        HStack(spacing: 4) {
                            Image(systemName: "arrow.down")
                                .font(.system(size: 11, weight: .bold))
                            Text("返回最新")
                                .font(.system(size: 12, weight: .semibold))
                        }
                        .foregroundColor(AppTheme.Colors.onPrimary)
                        .padding(.horizontal, AppTheme.Spacing.md)
                        .padding(.vertical, 8)
                        .background(AppTheme.Colors.quantumBlue)
                        .clipShape(Capsule())
                        .shadow(color: AppTheme.Colors.quantumBlue.opacity(0.4), radius: 8, x: 0, y: 3)
                    }
                    .buttonStyle(SoftButtonStyle())
                    .padding(.trailing, AppTheme.Spacing.md)
                    .padding(.bottom, AppTheme.Spacing.sm)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }
        }
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
        } else if let clarify = message.clarifyBlock {
            ClarifyCard(
                block: clarify,
                onSubmit: { selection in
                    coordinator.sendClarifySelection(messageId: message.id, selection: selection)
                }
            )
        } else {
            MessageBubbleView(
                message: message,
                onQuoteFollowUp: { quote in
                    withAnimation(.spring()) { coordinator.quotedContext = quote }
                },
                onRegenerate: { messageId in coordinator.retryMessage(messageId) }
            )
        }
    }

    /// 流式期间实时揭示的块（仅 reasoning / clarify 有实时价值，其余等待完成态统一渲染）
    @ViewBuilder
    private func liveBlockCard(_ block: MessageBlock) -> some View {
        switch block {
        case .reasoning(let steps):
            ReasoningCard(steps: steps, durationSeconds: nil, isStreaming: true)
        case .clarify(let clarify):
            ClarifyCard(block: clarify, onSubmit: { selection in
                coordinator.sendClarifySelection(messageId: coordinator.inflight?.id ?? "", selection: selection)
            })
        default:
            EmptyView()
        }
    }

    private func scrollToLatest(_ proxy: ScrollViewProxy) {
        withAnimation(.easeOut(duration: 0.25)) {
            if let last = coordinator.messages.last {
                proxy.scrollTo(last.id, anchor: .bottom)
            }
        }
    }
}
