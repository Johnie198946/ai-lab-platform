//
//  BubbleActionBar.swift
//  AIPlatformApp
//
//  ChatGPT / Gemini Style Bubble Action Bar
//  Provides one-click Copy, Regenerate, Text-to-Speech (TTS), and Feedback.
//

import SwiftUI
import AVFoundation

public struct BubbleActionBar: View {
    public let messageId: String
    public let content: String
    public var onRegenerate: (() -> Void)? = nil

    @State private var isCopied: Bool = false
    @State private var isSpeaking: Bool = false
    @State private var feedbackState: FeedbackState = .none

    private static let speechSynthesizer = AVSpeechSynthesizer()

    public enum FeedbackState {
        case none
        case up
        case down
    }

    public init(messageId: String, content: String, onRegenerate: (() -> Void)? = nil) {
        self.messageId = messageId
        self.content = content
        self.onRegenerate = onRegenerate
    }

    public var body: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            // 一键复制
            Button(action: copyContent) {
                HStack(spacing: 3) {
                    Image(systemName: isCopied ? "checkmark" : "doc.on.doc")
                        .font(.system(size: 11))
                    Text(isCopied ? "已复制" : "复制")
                        .font(.system(size: 11))
                }
                .foregroundColor(isCopied ? AppTheme.Colors.quantumCyan : AppTheme.Colors.textTertiary)
                .padding(.horizontal, 6)
                .padding(.vertical, 3)
            }
            .buttonStyle(SoftButtonStyle())

            // 重新生成
            if let onRegenerate {
                Button(action: onRegenerate) {
                    HStack(spacing: 3) {
                        Image(systemName: "arrow.clockwise")
                            .font(.system(size: 11))
                        Text("重新生成")
                            .font(.system(size: 11))
                    }
                    .foregroundColor(AppTheme.Colors.textTertiary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 3)
                }
                .buttonStyle(SoftButtonStyle())
            }

            // 语音朗读 (TTS)
            Button(action: toggleSpeech) {
                HStack(spacing: 3) {
                    Image(systemName: isSpeaking ? "speaker.slash.fill" : "speaker.wave.2")
                        .font(.system(size: 11))
                    Text(isSpeaking ? "停止" : "朗读")
                        .font(.system(size: 11))
                }
                .foregroundColor(isSpeaking ? AppTheme.Colors.quantumViolet : AppTheme.Colors.textTertiary)
                .padding(.horizontal, 6)
                .padding(.vertical, 3)
            }
            .buttonStyle(SoftButtonStyle())

            // 赞 / 踩反馈
            HStack(spacing: 2) {
                Button(action: { toggleFeedback(.up) }) {
                    Image(systemName: feedbackState == .up ? "hand.thumbsup.fill" : "hand.thumbsup")
                        .font(.system(size: 11))
                        .foregroundColor(feedbackState == .up ? AppTheme.Colors.primary : AppTheme.Colors.textTertiary)
                        .padding(4)
                }
                .buttonStyle(SoftButtonStyle())

                Button(action: { toggleFeedback(.down) }) {
                    Image(systemName: feedbackState == .down ? "hand.thumbsdown.fill" : "hand.thumbsdown")
                        .font(.system(size: 11))
                        .foregroundColor(feedbackState == .down ? AppTheme.Colors.securityRed : AppTheme.Colors.textTertiary)
                        .padding(4)
                }
                .buttonStyle(SoftButtonStyle())
            }

            Spacer(minLength: 0)
        }
        .padding(.top, 2)
    }

    private func copyContent() {
        #if os(iOS)
        UIPasteboard.general.string = content
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        #endif
        withAnimation(.easeInOut(duration: 0.2)) { isCopied = true }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            withAnimation(.easeInOut(duration: 0.2)) { isCopied = false }
        }
    }

    private func toggleSpeech() {
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        if Self.speechSynthesizer.isSpeaking {
            Self.speechSynthesizer.stopSpeaking(at: .immediate)
            isSpeaking = false
        } else {
            let utterance = AVSpeechUtterance(string: content)
            utterance.voice = AVSpeechSynthesisVoice(language: "zh-CN")
            utterance.rate = 0.52
            Self.speechSynthesizer.speak(utterance)
            isSpeaking = true
        }
        #endif
    }

    private func toggleFeedback(_ target: FeedbackState) {
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        #endif
        withAnimation(.easeInOut(duration: 0.2)) {
            feedbackState = (feedbackState == target) ? .none : target
        }
    }
}
