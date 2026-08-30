//
//  BubbleActionBar.swift
//  AIPlatformApp
//
//  ChatGPT / Gemini Style Bubble Action Bar
//  Provides one-click Copy, Regenerate, Text-to-Speech (TTS), and Feedback.
//

import SwiftUI
import AVFoundation

/// App-scoped speech playback keeps synthesis alive when a bubble or tab leaves the view tree.
/// The `.playback` session routes built-in audio to the speaker and, with the `audio`
/// background mode, lets an utterance that the user started continue while locked/backgrounded.
@MainActor
final class SpeechPlaybackController: NSObject, ObservableObject, AVSpeechSynthesizerDelegate {
    static let shared = SpeechPlaybackController()

    @Published private(set) var speakingMessageID: String?

    private let synthesizer = AVSpeechSynthesizer()
    private var currentUtterance: AVSpeechUtterance?

    override private init() {
        super.init()
        synthesizer.delegate = self
    }

    func isSpeaking(messageID: String) -> Bool {
        speakingMessageID == messageID && (synthesizer.isSpeaking || synthesizer.isPaused)
    }

    func toggle(messageID: String, content: String) {
        if speakingMessageID == messageID,
           synthesizer.isSpeaking || synthesizer.isPaused {
            stop()
            return
        }

        if synthesizer.isSpeaking || synthesizer.isPaused {
            synthesizer.stopSpeaking(at: .immediate)
        }

        guard configureAudioSession() else { return }

        let utterance = AVSpeechUtterance(string: content)
        utterance.voice = preferredMandarinVoice()
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate * 0.94
        utterance.pitchMultiplier = 1.0
        utterance.volume = 1.0

        currentUtterance = utterance
        speakingMessageID = messageID
        synthesizer.speak(utterance)
    }

    func stop() {
        guard synthesizer.isSpeaking || synthesizer.isPaused else { return }
        synthesizer.stopSpeaking(at: .immediate)
        finishPlayback()
    }

    private func configureAudioSession() -> Bool {
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .spokenAudio, options: [])
            try session.setActive(true)
            return true
        } catch {
            assertionFailure("Unable to activate speech audio session: \(error)")
            return false
        }
    }

    private func preferredMandarinVoice() -> AVSpeechSynthesisVoice? {
        let voices = AVSpeechSynthesisVoice.speechVoices()
            .filter { $0.language.caseInsensitiveCompare("zh-CN") == .orderedSame }
            .sorted { $0.quality.rawValue > $1.quality.rawValue }
        return voices.first ?? AVSpeechSynthesisVoice(language: "zh-CN")
    }

    private func finishPlayback() {
        currentUtterance = nil
        speakingMessageID = nil
        try? AVAudioSession.sharedInstance().setActive(
            false,
            options: .notifyOthersOnDeactivation
        )
    }

    nonisolated func speechSynthesizer(
        _ synthesizer: AVSpeechSynthesizer,
        didFinish utterance: AVSpeechUtterance
    ) {
        Task { @MainActor in
            guard utterance === self.currentUtterance else { return }
            self.finishPlayback()
        }
    }

    nonisolated func speechSynthesizer(
        _ synthesizer: AVSpeechSynthesizer,
        didCancel utterance: AVSpeechUtterance
    ) {
        Task { @MainActor in
            guard utterance === self.currentUtterance else { return }
            self.finishPlayback()
        }
    }
}

public struct BubbleActionBar: View {
    public let messageId: String
    public let content: String
    public var onRegenerate: (() -> Void)? = nil

    @State private var isCopied: Bool = false
    @State private var feedbackState: FeedbackState = .none
    @ObservedObject private var speechPlayback = SpeechPlaybackController.shared

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
                .foregroundColor(isCopied ? AppTheme.Icons.success : AppTheme.Icons.tertiary)
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
                .foregroundColor(AppTheme.Icons.tertiary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 3)
                }
                .buttonStyle(SoftButtonStyle())
            }

            // 语音朗读 (TTS)
            Button(action: toggleSpeech) {
                HStack(spacing: 3) {
                    Image(systemName: speechPlayback.isSpeaking(messageID: messageId) ? "speaker.slash.fill" : "speaker.wave.2")
                        .font(.system(size: 11))
                    Text(speechPlayback.isSpeaking(messageID: messageId) ? "停止" : "朗读")
                        .font(.system(size: 11))
                }
                .foregroundColor(speechPlayback.isSpeaking(messageID: messageId) ? AppTheme.Icons.intelligence : AppTheme.Icons.tertiary)
                .padding(.horizontal, 6)
                .padding(.vertical, 3)
            }
            .buttonStyle(SoftButtonStyle())

            // 赞 / 踩反馈
            HStack(spacing: 2) {
                Button(action: { toggleFeedback(.up) }) {
                    Image(systemName: feedbackState == .up ? "hand.thumbsup.fill" : "hand.thumbsup")
                        .font(.system(size: 11))
                .foregroundColor(feedbackState == .up ? AppTheme.Icons.interactive : AppTheme.Icons.tertiary)
                        .padding(4)
                }
                .buttonStyle(SoftButtonStyle())

                Button(action: { toggleFeedback(.down) }) {
                    Image(systemName: feedbackState == .down ? "hand.thumbsdown.fill" : "hand.thumbsdown")
                        .font(.system(size: 11))
                .foregroundColor(feedbackState == .down ? AppTheme.Icons.destructive : AppTheme.Icons.tertiary)
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
        speechPlayback.toggle(messageID: messageId, content: content)
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
