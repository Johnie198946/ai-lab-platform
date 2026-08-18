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

                    // 底部锚点，确保可靠滚动吸底
                    Color.clear
                        .frame(height: 1)
                        .id("bottom_anchor")
                }
                .frame(maxWidth: AppTheme.Metrics.readableContentWidth)
                .frame(maxWidth: .infinity)
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
            // Clarify 卡是在既有续写消息上追加 block，不会改变 messages.count。
            // 监听尾消息块签名，确保最终“需求确认单 + 确认卡”出现时自动滚入视野。
            .onChange(of: tailBlockSignature) { _, _ in
                scrollToBottom(proxy)
            }
        }
    }

    private var tailBlockSignature: String {
        guard let last = coordinator.messages.last else { return "empty" }
        return "\(last.id):\(last.blocks.count):\(last.clarifyBlock?.isSubmitted == true)"
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
        } else if let clarify = message.clarifyBlock,
                  !clarify.isSubmitted,
                  !containsRequirementConfirmation(message) {
            ClarifyCard(
                block: clarify,
                onSubmit: { selection in
                    coordinator.sendClarifySelection(messageId: message.id, selection: selection)
                }
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
                }
            )
        default:
            EmptyView()
        }
    }
}

private struct ChatWelcomeView: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var appeared = false

    var body: some View {
        VStack(spacing: AppTheme.Spacing.xl) {
            ZStack {
                Circle()
                    .fill(AppTheme.Colors.quantumBlue.opacity(0.08))
                    .frame(width: 104, height: 104)
                Circle()
                    .fill(AppTheme.Colors.quantumGradient)
                    .frame(width: 72, height: 72)
                    .shadow(color: AppTheme.Colors.quantumBlue.opacity(0.2), radius: 18, y: 8)
                Image(systemName: "sparkles")
                    .font(.title.weight(.semibold))
                    .foregroundColor(.white)
            }

            VStack(spacing: AppTheme.Spacing.sm) {
                Text("今天想推进什么？")
                    .font(AppTheme.Typography.screenTitle)
                    .foregroundColor(AppTheme.Colors.textPrimary)

                Text("描述目标即可。Quantum 会先确认需求，再组织 Agent、知识与工具完成任务。")
                    .font(AppTheme.Typography.body)
                    .foregroundColor(AppTheme.Colors.textSecondary)
                    .multilineTextAlignment(.center)
                    .lineSpacing(3)
                    .frame(maxWidth: 360)
            }

            HStack(spacing: AppTheme.Spacing.sm) {
                capability("需求澄清", icon: "checklist")
                capability("智能编排", icon: "point.3.connected.trianglepath.dotted")
                capability("知识增强", icon: "books.vertical")
            }
        }
        .padding(.horizontal, AppTheme.Spacing.xl)
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

    private func capability(_ title: String, icon: String) -> some View {
        VStack(spacing: AppTheme.Spacing.xs) {
            Image(systemName: icon)
                .font(.body.weight(.semibold))
                .foregroundColor(AppTheme.Colors.quantumBlue)
            Text(title)
                .font(AppTheme.Typography.micro)
                .foregroundColor(AppTheme.Colors.textSecondary)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, minHeight: 64)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                .stroke(AppTheme.Colors.border, lineWidth: 0.75)
        }
    }
}
