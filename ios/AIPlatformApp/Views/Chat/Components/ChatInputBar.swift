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
        VStack(spacing: 0) {
            // Suggestion Chips
            suggestionChipsBar

            // Quoted Follow-Up Banner
            if let quote = quotedContext {
                quotedFollowUpBanner(quote: quote)
            }

            // Input Row
            inputRow
        }
    }

    private var suggestionChipsBar: some View {
        VStack(spacing: 2) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: AppTheme.Spacing.xs) {
                    ForEach(quickCommands, id: \.self) { chip in
                        Button(action: {
                            onCommandSelected(chip)
                        }) {
                            Text(chip)
                                .font(.system(size: 12))
                                .foregroundColor(AppTheme.Colors.textSecondary)
                                .padding(.horizontal, AppTheme.Spacing.sm + 2)
                                .padding(.vertical, 4)
                                .background(AppTheme.Colors.cardBackground)
                                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
                                .overlay(
                                    RoundedRectangle(cornerRadius: AppTheme.Radius.sm)
                                        .stroke(AppTheme.Colors.border, lineWidth: 0.5)
                                )
                        }
                        .buttonStyle(SoftButtonStyle())
                    }
                }
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, AppTheme.Spacing.xs)
            }

            // 隐私标注：快捷指令仅本地计算
            HStack(spacing: 4) {
                Image(systemName: "lock.fill")
                    .font(.system(size: 9))
                Text("仅本地计算 · 保护隐私")
                    .font(.system(size: 10))
            }
            .foregroundColor(AppTheme.Colors.textTertiary)
            .padding(.bottom, 2)
        }
    }

    private func quotedFollowUpBanner(quote: QuotedContext) -> some View {
        HStack {
            Image(systemName: "quote.bubble.fill")
                .foregroundColor(AppTheme.Colors.primary)
                .font(.system(size: 14))

            VStack(alignment: .leading, spacing: 2) {
                Text("引用追问中")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(AppTheme.Colors.primary)
                Text(quote.text)
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                    .lineLimit(1)
            }

            Spacer()

            Button(action: {
                withAnimation(.spring()) {
                    quotedContext = nil
                }
            }) {
                Image(systemName: "xmark.circle.fill")
                    .foregroundColor(AppTheme.Colors.textTertiary)
                    .font(.system(size: 16))
            }
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, 6)
        .background(AppTheme.Colors.primary.opacity(0.08))
        .transition(.move(edge: .bottom).combined(with: .opacity))
    }

    private var inputRow: some View {
        HStack(alignment: .bottom, spacing: AppTheme.Spacing.sm) {
            Button(action: onPlusTap) {
                Image(systemName: "plus.circle.fill")
                    .font(.system(size: 24))
                    .foregroundColor(AppTheme.Colors.textSecondary)
            }
            .padding(.bottom, 6)

            HStack {
                TextField("发送指令或提出问题...", text: $inputText, axis: .vertical)
                    .lineLimit(1...5)
                    .font(.system(size: 15))
                    .padding(.horizontal, AppTheme.Spacing.sm)
                    .padding(.vertical, 8)

                if !inputText.isEmpty {
                    Button(action: { inputText = "" }) {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 14))
                            .foregroundColor(AppTheme.Colors.textTertiary)
                    }
                    .padding(.trailing, 6)
                }
            }
            .background(AppTheme.Colors.secondaryBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))

            if inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Button(action: onVoiceTap) {
                    Image(systemName: "mic.fill")
                        .font(.system(size: 18))
                        .foregroundColor(AppTheme.Colors.onPrimary)
                        .frame(width: 36, height: 36)
                        .background(AppTheme.Colors.accent)
                        .clipShape(Circle())
                        .overlay(
                            Circle()
                                .stroke(AppTheme.Colors.quantumCyan.opacity(0.6), lineWidth: 1.5)
                        )
                        .shadow(color: AppTheme.Colors.quantumCyan.opacity(0.55), radius: 8, x: 0, y: 0)
                }
                .buttonStyle(SoftButtonStyle())
                .padding(.bottom, 2)
            } else {
                Button(action: onSend) {
                    Image(systemName: "arrow.up")
                        .font(.system(size: 16, weight: .bold))
                        .foregroundColor(AppTheme.Colors.onPrimary)
                        .frame(width: 36, height: 36)
                        .background(AppTheme.Colors.quantumGradient)
                        .clipShape(Circle())
                }
                .buttonStyle(SoftButtonStyle())
                .padding(.bottom, 2)
            }
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.sm)
        .background(AppTheme.Colors.cardBackground)
    }
}
