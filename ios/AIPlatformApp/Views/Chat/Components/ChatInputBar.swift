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
    @Binding public var isVoicePressing: Bool
    @ObservedObject public var speechService: SpeechRecognizerService
    public let isGenerating: Bool
    public let onSend: () -> Void
    public let onVoicePressChanged: (Bool) -> Void
    public let onPlusTap: () -> Void

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init(
        inputText: Binding<String>,
        quotedContext: Binding<QuotedContext?>,
        isVoicePressing: Binding<Bool>,
        speechService: SpeechRecognizerService,
        isGenerating: Bool,
        onSend: @escaping () -> Void,
        onVoicePressChanged: @escaping (Bool) -> Void,
        onPlusTap: @escaping () -> Void
    ) {
        self._inputText = inputText
        self._quotedContext = quotedContext
        self._isVoicePressing = isVoicePressing
        self.speechService = speechService
        self.isGenerating = isGenerating
        self.onSend = onSend
        self.onVoicePressChanged = onVoicePressChanged
        self.onPlusTap = onPlusTap
    }

    public var body: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            if let quote = quotedContext {
                quotedFollowUpBanner(quote: quote)
            }

            if shouldShowVoiceStatus {
                inlineVoiceStatus
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }

            inputRow
        }
        .padding(.top, AppTheme.Spacing.sm)
        .background(AppTheme.Colors.background.opacity(0.96))
        .animation(AppTheme.Motion.standard, value: inputText.isEmpty)
        .animation(AppTheme.Motion.standard, value: speechService.state)
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

            if shouldShowVoiceButton {
                voiceHoldButton
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

    private var shouldShowVoiceButton: Bool {
        inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || isVoicePressing
            || speechService.state != .idle
    }

    private var shouldShowVoiceStatus: Bool {
        isVoicePressing || speechService.state != .idle || speechService.permissionDenied
    }

    private var voiceHoldButton: some View {
        Button(action: {}) {
            ZStack {
                VoicePressHalo(
                    isActive: speechService.state == .recording || isVoicePressing,
                    reduceMotion: reduceMotion
                )

                Circle()
                    .fill(
                        (speechService.state == .recording || isVoicePressing)
                            ? AppTheme.Colors.actionGradient
                            : LinearGradient(
                                colors: [AppTheme.Colors.surfaceTint, AppTheme.Colors.surfaceTint],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                    )
                    .frame(width: 44, height: 44)

                Image(systemName: voiceButtonSymbol)
                    .font(.body.weight(.semibold))
                    .foregroundColor(
                        speechService.state == .recording || isVoicePressing
                            ? AppTheme.Icons.onAccent
                            : AppTheme.Icons.interactive
                    )
            }
            .frame(width: 48, height: 48)
            .scaleEffect(isVoicePressing && !reduceMotion ? 1.08 : 1)
        }
        .buttonStyle(.plain)
        .onLongPressGesture(
            minimumDuration: 0,
            maximumDistance: 80,
            pressing: updateVoicePressState,
            perform: {}
        )
        .accessibilityLabel(speechService.state == .recording ? "正在录音" : "按住说话")
        .accessibilityHint("按住开始录音，松开完成识别")
        .accessibilityAction(named: Text("开始录音")) {
            updateVoicePressState(true)
        }
        .accessibilityAction(named: Text("完成录音")) {
            updateVoicePressState(false)
        }
    }

    private var voiceButtonSymbol: String {
        switch speechService.state {
        case .recording: return "mic.fill"
        case .processing: return "ellipsis"
        case .idle: return "waveform"
        }
    }

    private var inlineVoiceStatus: some View {
        HStack(spacing: AppTheme.Spacing.md) {
            ZStack {
                Circle()
                    .fill(AppTheme.Colors.primary.opacity(0.10))
                    .frame(width: 40, height: 40)
                Image(systemName: speechService.permissionDenied ? "mic.slash.fill" : voiceButtonSymbol)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(
                        speechService.permissionDenied
                            ? AppTheme.Icons.destructive
                            : AppTheme.Icons.interactive
                    )
            }

            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: AppTheme.Spacing.xs) {
                    Text(voiceStatusTitle)
                        .font(AppTheme.Typography.label.weight(.semibold))
                        .foregroundColor(AppTheme.Colors.textPrimary)

                    if speechService.state == .recording {
                        Text(timeString(speechService.elapsedSeconds))
                            .font(AppTheme.Typography.micro.monospacedDigit())
                            .foregroundColor(AppTheme.Colors.textSecondary)
                    }
                }

                Text(voiceStatusDetail)
                    .font(AppTheme.Typography.micro)
                    .foregroundColor(AppTheme.Colors.textSecondary)
                    .lineLimit(1)
            }

            Spacer(minLength: AppTheme.Spacing.xs)

            if speechService.state == .recording {
                InlineVoiceWaveform(levels: speechService.audioLevels, reduceMotion: reduceMotion)
                    .frame(width: 92, height: 32)
            } else if speechService.state == .processing {
                ProgressView()
                    .tint(AppTheme.Colors.primary)
            }
        }
        .padding(.horizontal, AppTheme.Metrics.contentGutter)
        .padding(.vertical, 10)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                .stroke(AppTheme.Colors.primary.opacity(0.16), lineWidth: 0.75)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .accessibilityElement(children: .combine)
    }

    private var voiceStatusTitle: String {
        if speechService.permissionDenied { return "无法使用麦克风" }
        switch speechService.state {
        case .recording: return "正在聆听 · 松开完成"
        case .processing: return "正在整理识别结果"
        case .idle: return "按住说话"
        }
    }

    private var voiceStatusDetail: String {
        if speechService.permissionDenied {
            return "请在系统设置中开启麦克风与语音识别权限"
        }
        let transcript = speechService.transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        if !transcript.isEmpty { return transcript }
        if speechService.isMockMode { return "模拟器正在演示页面内拾音" }
        return speechService.state == .processing ? "请稍候…" : "说出你想输入的内容"
    }

    private func updateVoicePressState(_ pressing: Bool) {
        guard pressing != isVoicePressing else { return }
        isVoicePressing = pressing
        #if os(iOS)
        UIImpactFeedbackGenerator(style: pressing ? .rigid : .soft).impactOccurred()
        #endif
        onVoicePressChanged(pressing)
    }

    private func timeString(_ seconds: Int) -> String {
        String(format: "%02d:%02d", seconds / 60, seconds % 60)
    }
}

private struct VoicePressHalo: View {
    let isActive: Bool
    let reduceMotion: Bool

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0, paused: reduceMotion || !isActive)) { timeline in
            let elapsed = timeline.date.timeIntervalSinceReferenceDate
            let phase = reduceMotion ? 0.0 : (sin(elapsed * 4.2) + 1) / 2

            Circle()
                .stroke(
                    AppTheme.Colors.actionGradient,
                    lineWidth: 2
                )
                .frame(width: 48, height: 48)
                .scaleEffect(isActive ? 1.04 + phase * 0.18 : 0.94)
                .opacity(isActive ? 0.52 - phase * 0.32 : 0)
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

private struct InlineVoiceWaveform: View {
    let levels: [CGFloat]
    let reduceMotion: Bool
    private let barCount = 12

    var body: some View {
        HStack(alignment: .center, spacing: 3) {
            ForEach(0..<barCount, id: \.self) { index in
                Capsule()
                    .fill(AppTheme.Colors.actionGradient)
                    .frame(width: 4, height: barHeight(at: index))
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .animation(reduceMotion ? nil : .linear(duration: 0.08), value: levels)
        .accessibilityHidden(true)
    }

    private func barHeight(at index: Int) -> CGFloat {
        guard !levels.isEmpty else { return 5 }
        let position = Double(index) / Double(max(1, barCount - 1))
        let sourceIndex = Int(position * Double(max(0, levels.count - 1)))
        let level = levels[max(0, min(levels.count - 1, sourceIndex))]
        return max(5, min(30, level * 30))
    }
}
