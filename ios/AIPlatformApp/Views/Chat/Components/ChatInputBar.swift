//
//  ChatInputBar.swift
//  AIPlatformApp
//
//  Modular Bottom Input Bar with Suggestion Chips, Quoted Banner & Action Triggers
//  Extracted from ChatView for minimal footprint.
//

import SwiftUI

public struct ChatInputBar: View {
    @Binding public var inputText: String
    @Binding public var quotedContext: QuotedContext?
    public let isGenerating: Bool
    public let onSend: () -> Void
    public let onVoiceTap: () -> Void
    public let onPlusTap: () -> Void

    public init(
        inputText: Binding<String>,
        quotedContext: Binding<QuotedContext?>,
        isGenerating: Bool,
        onSend: @escaping () -> Void,
        onVoiceTap: @escaping () -> Void,
        onPlusTap: @escaping () -> Void
    ) {
        self._inputText = inputText
        self._quotedContext = quotedContext
        self.isGenerating = isGenerating
        self.onSend = onSend
        self.onVoiceTap = onVoiceTap
        self.onPlusTap = onPlusTap
    }

    public var body: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            if let quote = quotedContext {
                quotedFollowUpBanner(quote: quote)
            }

            inputRow
        }
        .padding(.top, AppTheme.Spacing.sm)
        .background(AppTheme.Colors.background.opacity(0.96))
        .animation(AppTheme.Motion.standard, value: inputText.isEmpty)
    }

    private func quotedFollowUpBanner(quote: QuotedContext) -> some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: "quote.bubble.fill")
                    .foregroundColor(AppTheme.Icons.interactive)
                .font(.body)

            VStack(alignment: .leading, spacing: 2) {
                Text("引用追问中")
                    .font(AppTheme.Typography.micro)
                    .foregroundColor(AppTheme.Icons.interactive)
                Text(quote.text)
                    .font(.caption)
                    .foregroundColor(AppTheme.Colors.textSecondary)
                    .lineLimit(1)
            }

            Spacer()

            Button(action: {
                withAnimation(AppTheme.Motion.spring) {
                    quotedContext = nil
                }
            }) {
                Image(systemName: "xmark.circle.fill")
                    .foregroundColor(AppTheme.Icons.tertiary)
                    .font(.body)
            }
            .minimumTouchTarget()
            .accessibilityLabel("取消引用")
        }
        .padding(.leading, AppTheme.Metrics.contentGutter)
        .padding(.trailing, AppTheme.Spacing.sm)
        .padding(.vertical, AppTheme.Spacing.sm)
        .background(AppTheme.Colors.primary.opacity(0.08))
        .transition(.move(edge: .bottom).combined(with: .opacity))
    }

    private var inputRow: some View {
        HStack(alignment: .bottom, spacing: 2) {
            Button(action: onPlusTap) {
                Image(systemName: "plus")
                    .font(.body.weight(.medium))
                    .foregroundColor(AppTheme.Icons.secondary)
                    .minimumTouchTarget()
            }
            .buttonStyle(SoftButtonStyle())
            .accessibilityLabel("添加附件或引用知识")

            TextField(isGenerating ? "任务执行中，可继续输入" : "描述目标，或继续当前任务…", text: $inputText, axis: .vertical)
                .lineLimit(1...5)
                .font(AppTheme.Typography.body)
                .padding(.vertical, 11)

            if !inputText.isEmpty {
                Button(action: { inputText = "" }) {
                    Image(systemName: "xmark.circle.fill")
                        .font(.body)
                        .foregroundColor(AppTheme.Icons.tertiary)
                        .minimumTouchTarget()
                }
                .accessibilityLabel("清空输入")
            }

            if inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Button(action: onVoiceTap) {
                    Image(systemName: "waveform")
                        .font(.body.weight(.semibold))
                    .foregroundColor(AppTheme.Icons.interactive)
                        .minimumTouchTarget()
                }
                .buttonStyle(SoftButtonStyle())
                .accessibilityLabel("语音输入")
            } else {
                Button(action: onSend) {
                    Image(systemName: "arrow.up")
                        .font(.body.weight(.bold))
                    .foregroundColor(AppTheme.Icons.onAccent)
                        .minimumTouchTarget()
                        .background(AppTheme.Colors.actionGradient)
                        .clipShape(Circle())
                }
                .buttonStyle(SoftButtonStyle())
                .accessibilityLabel(isGenerating ? "加入消息队列" : "发送消息")
            }
        }
        .padding(.horizontal, AppTheme.Metrics.contentGutter)
        .padding(.vertical, 6)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous)
                .stroke(AppTheme.Colors.border, lineWidth: 0.75)
        }
        .shadow(color: Color(hex: "6B5A8A").opacity(0.15), radius: 20, y: 8)
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.bottom, AppTheme.Spacing.sm)
    }
}
