//
//  ChatMessageStreamView.swift
//  AIPlatformApp
//
//  ChatGPT / Gemini Style Message Stream (v2 - Butter-Smooth & Zero-Jank)
//  - Pure ScrollViewReader + LazyVStack message canvas
//  - Stable scroll anchor without continuous GeometryReader preference loops
//

import SwiftUI

public struct ChatMessageStreamView: View {
    @ObservedObject public var coordinator: TenantSessionCoordinator

    public init(coordinator: TenantSessionCoordinator) {
        self.coordinator = coordinator
    }

    public var body: some View {
        ScrollViewReader { proxy in
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

                    // 底部锚点，确保可靠滚动吸底
                    Color.clear
                        .frame(height: 1)
                        .id("bottom_anchor")
                }
                .padding(.vertical, AppTheme.Spacing.md)
            }
            .scrollDismissesKeyboard(.interactively)
            .onChange(of: coordinator.messages.count) { _, _ in
                scrollToBottom(proxy)
            }
            .onChange(of: coordinator.pendingQueue.count) { _, _ in
                scrollToBottom(proxy)
            }
            .onChange(of: coordinator.inflight?.id) { _, _ in
                scrollToBottom(proxy)
            }
        }
    }

    private func scrollToBottom(_ proxy: ScrollViewProxy) {
        withAnimation(.easeOut(duration: 0.25)) {
            proxy.scrollTo("bottom_anchor", anchor: .bottom)
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
                onQuoteFollowUp: { quoted in coordinator.quotedContext = quoted },
                onRegenerate: { msgId in coordinator.retryMessage(msgId) }
            )
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
                }
            )
        default:
            EmptyView()
        }
    }
}
