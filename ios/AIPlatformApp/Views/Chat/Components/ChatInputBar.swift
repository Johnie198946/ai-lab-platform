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
    public let quickCommands: [String]
    public let isGenerating: Bool
    public let onSend: () -> Void
    public let onVoiceTap: () -> Void
    public let onPlusTap: () -> Void
    public let onCommandSelected: (String) -> Void

    public init(
        inputText: Binding<String>,
        quotedContext: Binding<QuotedContext?>,
        quickCommands: [String],
        isGenerating: Bool,
        onSend: @escaping () -> Void,
        onVoiceTap: @escaping () -> Void,
        onPlusTap: @escaping () -> Void,
        onCommandSelected: @escaping (String) -> Void
    ) {
        self._inputText = inputText
        self._quotedContext = quotedContext
        self.quickCommands = quickCommands
        self.isGenerating = isGenerating
        self.onSend = onSend
        self.onVoiceTap = onVoiceTap
        self.onPlusTap = onPlusTap
        self.onCommandSelected = onCommandSelected
    }

    public var body: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            if inputText.isEmpty && quotedContext == nil && !quickCommands.isEmpty {
                suggestionChipsBar
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }

            if let quote = quotedContext {
                quotedFollowUpBanner(quote: quote)
            }

            inputRow
        }
        .padding(.top, AppTheme.Spacing.sm)
        .background(.ultraThinMaterial)
        .overlay(alignment: .top) {
            Rectangle()
                .fill(AppTheme.Colors.border.opacity(0.55))
                .frame(height: 0.5)
        }
        .animation(AppTheme.Motion.standard, value: inputText.isEmpty)
    }

    private var suggestionChipsBar: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            ForEach(Array(quickCommands.prefix(2)), id: \.self) { chip in
                Button(action: { onCommandSelected(chip) }) {
                    Text(chip)
                        .font(AppTheme.Typography.label)
                        .foregroundColor(AppTheme.Colors.textSecondary)
                        .lineLimit(1)
                        .frame(maxWidth: .infinity)
                        .minimumTouchTarget()
                        .padding(.horizontal, AppTheme.Spacing.sm)
                        .background(AppTheme.Colors.cardBackground.opacity(0.88))
                        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                        .overlay {
                            RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                                .stroke(AppTheme.Colors.border, lineWidth: 0.75)
                        }
                }
                .buttonStyle(SoftButtonStyle())
            }

            if quickCommands.count > 2 {
                Menu {
                    ForEach(Array(quickCommands.dropFirst(2)), id: \.self) { chip in
                        Button(chip) { onCommandSelected(chip) }
                    }
                } label: {
                    Image(systemName: "ellipsis")
                        .font(.body.weight(.semibold))
                        .foregroundColor(AppTheme.Colors.textSecondary)
                        .minimumTouchTarget()
                        .background(AppTheme.Colors.cardBackground.opacity(0.88))
                        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                        .overlay {
                            RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                                .stroke(AppTheme.Colors.border, lineWidth: 0.75)
                        }
                }
                .accessibilityLabel("更多快捷指令")
            }
        }
        .padding(.horizontal, AppTheme.Metrics.contentGutter)
    }

    private func quotedFollowUpBanner(quote: QuotedContext) -> some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: "quote.bubble.fill")
                .foregroundColor(AppTheme.Colors.primary)
                .font(.body)

            VStack(alignment: .leading, spacing: 2) {
                Text("引用追问中")
                    .font(AppTheme.Typography.micro)
                    .foregroundColor(AppTheme.Colors.primary)
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
                    .foregroundColor(AppTheme.Colors.textTertiary)
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
        VStack(spacing: AppTheme.Spacing.xs) {
            HStack(alignment: .bottom, spacing: AppTheme.Spacing.sm) {
                Button(action: onPlusTap) {
                    Image(systemName: "plus")
                        .font(.body.weight(.semibold))
                        .foregroundColor(AppTheme.Colors.textSecondary)
                        .minimumTouchTarget()
                        .background(AppTheme.Colors.secondaryBackground)
                        .clipShape(Circle())
                }
                .buttonStyle(SoftButtonStyle())
                .accessibilityLabel("添加附件或引用知识")

                HStack(spacing: AppTheme.Spacing.xs) {
                    TextField("给 Quantum 发送消息", text: $inputText, axis: .vertical)
                        .lineLimit(1...5)
                        .font(AppTheme.Typography.body)
                        .padding(.leading, AppTheme.Spacing.md)
                        .padding(.vertical, 11)

                    if !inputText.isEmpty {
                        Button(action: { inputText = "" }) {
                            Image(systemName: "xmark.circle.fill")
                                .font(.body)
                                .foregroundColor(AppTheme.Colors.textTertiary)
                                .minimumTouchTarget()
                        }
                        .accessibilityLabel("清空输入")
                    }
                }
                .frame(minHeight: AppTheme.Metrics.inputHeight)
                .background(AppTheme.Colors.secondaryBackground)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
                .overlay {
                    RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                        .stroke(AppTheme.Colors.border, lineWidth: 0.75)
                }

                if inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Button(action: onVoiceTap) {
                        Image(systemName: "mic.fill")
                            .font(.body.weight(.semibold))
                            .foregroundColor(AppTheme.Colors.quantumBlue)
                            .minimumTouchTarget()
                            .background(AppTheme.Colors.surfaceTint)
                            .clipShape(Circle())
                    }
                    .buttonStyle(SoftButtonStyle())
                    .accessibilityLabel("语音输入")
                } else {
                    Button(action: onSend) {
                        Image(systemName: "arrow.up")
                            .font(.body.weight(.bold))
                            .foregroundColor(AppTheme.Colors.onPrimary)
                            .minimumTouchTarget()
                            .background(AppTheme.Colors.quantumGradient)
                            .clipShape(Circle())
                            .shadow(color: AppTheme.Colors.quantumBlue.opacity(0.24), radius: 8, y: 3)
                    }
                    .buttonStyle(SoftButtonStyle())
                    .accessibilityLabel(isGenerating ? "加入消息队列" : "发送消息")
                }
            }

            Label(
                isGenerating ? "任务执行中 · 新消息将自动排队" : "本地加密上下文 · 内容仅用于当前任务",
                systemImage: isGenerating ? "clock.badge.checkmark" : "lock.fill"
            )
            .font(AppTheme.Typography.micro)
            .foregroundColor(AppTheme.Colors.textTertiary)
            .frame(maxWidth: .infinity, alignment: .center)
        }
        .padding(.horizontal, AppTheme.Metrics.contentGutter)
        .padding(.vertical, AppTheme.Spacing.sm)
        .padding(.bottom, 1)
    }
}
