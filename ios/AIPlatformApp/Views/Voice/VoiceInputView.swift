//
//  VoiceInputView.swift
//  AIPlatformApp
//
//  语音输入交互视图：红环 pulse + 实时波形 + 计时；静音 3.5s 自动结束；× 取消；权限拒绝引导。
//

import SwiftUI

public struct VoiceInputView: View {
    @ObservedObject var service: SpeechRecognizerService
    public var onTranscript: (String) -> Void
    public var onDismiss: () -> Void

    @Environment(\.colorScheme) private var colorScheme

    public var body: some View {
        ZStack {
            AppTheme.Colors.groupedBackground
                .ignoresSafeArea()

            if service.permissionDenied {
                permissionDeniedView
            } else {
                recordingView
            }
        }
        .onChange(of: service.state) { _, newState in
            if newState == .idle && !service.transcript.isEmpty {
                onTranscript(service.transcript)
                onDismiss()
            }
        }
    }

    // MARK: - 录音视图

    private var recordingView: some View {
        VStack(spacing: AppTheme.Spacing.xxl) {
            // 顶部标题 + 关闭
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(service.state == .recording ? "正在聆听…" : "语音输入")
                        .font(.system(size: 18, weight: .bold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                    if let hint = service.mockHint {
                        HStack(spacing: 4) {
                            Image(systemName: "info.circle.fill")
                                .font(.system(size: 10))
                            Text(hint)
                                .font(.system(size: 11))
                        }
                        .foregroundColor(AppTheme.Colors.securityYellow)
                        .lineLimit(2)
                    }
                }
                Spacer()
                Button(action: {
                    service.cancel()
                    onDismiss()
                }) {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 26))
                        .foregroundColor(AppTheme.Colors.textTertiary)
                }
            }
            .padding(.horizontal, AppTheme.Spacing.lg)
            .padding(.top, AppTheme.Spacing.lg)

            Spacer()

            // 麦克风 + 红环 pulse + 波形
            VStack(spacing: AppTheme.Spacing.xl) {
                micWithPulseRing
                WaveformView(levels: service.audioLevels)
                    .frame(height: 48)
                timerLabel
            }

            Spacer()

            // 底部操作
            VStack(spacing: AppTheme.Spacing.sm) {
                if service.state == .recording {
                    Button(action: {
                        #if os(iOS)
                        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                        #endif
                        service.stop()
                    }) {
                        Text("完成")
                            .font(.system(size: 15, weight: .bold))
                            .frame(maxWidth: .infinity)
                            .frame(height: 48)
                            .foregroundColor(AppTheme.Colors.onPrimary)
                            .background(AppTheme.Colors.primary)
                            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                    }
                    .buttonStyle(SoftButtonStyle())
                } else if service.state == .processing {
                    HStack(spacing: AppTheme.Spacing.sm) {
                        ProgressView()
                            .tint(AppTheme.Colors.accent)
                        Text("识别中…")
                            .font(.system(size: 14))
                            .foregroundColor(AppTheme.Colors.textSecondary)
                    }
                    .frame(maxWidth: .infinity)
                    .frame(height: 48)
                } else {
                    Button(action: {
                        #if os(iOS)
                        UIImpactFeedbackGenerator(style: .light).impactOccurred()
                        #endif
                        Task { await service.start() }
                    }) {
                        Text("轻点开始说话")
                            .font(.system(size: 15, weight: .bold))
                            .frame(maxWidth: .infinity)
                            .frame(height: 48)
                            .foregroundColor(AppTheme.Colors.onPrimary)
                            .background(AppTheme.Colors.primary)
                            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                    }
                    .buttonStyle(SoftButtonStyle())
                }

                if service.state == .recording {
                    Text("静音 3.5s 自动结束 · 点 × 取消")
                        .font(.system(size: 11))
                        .foregroundColor(AppTheme.Colors.textTertiary)
                }
            }
            .padding(.horizontal, AppTheme.Spacing.lg)
            .padding(.bottom, AppTheme.Spacing.xl)
        }
    }

    // MARK: - 麦克风 + 红环 pulse

    private var micWithPulseRing: some View {
        ZStack {
            // pulse 外环
            if service.state == .recording {
                Circle()
                    .stroke(AppTheme.Colors.securityRed.opacity(0.35), lineWidth: 3)
                    .frame(width: 96, height: 96)
                    .scaleEffect(service.state == .recording ? 1.35 : 1.0)
                    .opacity(service.state == .recording ? 0.0 : 0.6)
                    .animation(
                        .easeOut(duration: 1.2).repeatForever(autoreverses: false),
                        value: service.state
                    )
            }

            // 红环
            Circle()
                .stroke(
                    service.state == .recording ? AppTheme.Colors.securityRed : AppTheme.Colors.border,
                    lineWidth: 4
                )
                .frame(width: 96, height: 96)

            // 麦克风图标
            Image(systemName: service.state == .recording ? "mic.fill" : "mic")
                .font(.system(size: 40, weight: .medium))
                .foregroundColor(
                    service.state == .recording ? AppTheme.Colors.securityRed : AppTheme.Colors.textSecondary
                )
        }
        .frame(height: 140)
    }

    private var timerLabel: some View {
        Text(timeString(service.elapsedSeconds))
            .font(.system(size: 34, weight: .medium, design: .rounded))
            .monospacedDigit()
            .foregroundColor(
                service.state == .recording ? AppTheme.Colors.securityRed : AppTheme.Colors.textPrimary
            )
    }

    // MARK: - 权限拒绝引导

    private var permissionDeniedView: some View {
        VStack(spacing: AppTheme.Spacing.md) {
            Image(systemName: "mic.slash.circle.fill")
                .font(.system(size: 56))
                .foregroundColor(AppTheme.Colors.securityRed)

            Text("需要麦克风与语音识别权限")
                .font(.system(size: 17, weight: .bold))
                .foregroundColor(AppTheme.Colors.textPrimary)

            Text("请在系统设置中开启「麦克风」与「语音识别」权限后重试。")
                .font(.system(size: 13))
                .foregroundColor(AppTheme.Colors.textSecondary)
                .multilineTextAlignment(.center)

            Button(action: openSettings) {
                Text("前往设置")
                    .font(.system(size: 15, weight: .bold))
                    .frame(maxWidth: .infinity)
                    .frame(height: 46)
                    .foregroundColor(AppTheme.Colors.onPrimary)
                    .background(AppTheme.Colors.primary)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            }
            .buttonStyle(SoftButtonStyle())
            .padding(.top, AppTheme.Spacing.sm)

            Button(action: onDismiss) {
                Text("取消")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.textSecondary)
            }
        }
        .padding(AppTheme.Spacing.xl)
    }

    private func openSettings() {
        #if os(iOS)
        if let url = URL(string: UIApplication.openSettingsURLString) {
            UIApplication.shared.open(url)
        }
        #endif
    }

    private func timeString(_ seconds: Int) -> String {
        String(format: "%02d:%02d", seconds / 60, seconds % 60)
    }
}

// MARK: - 波形视图

public struct WaveformView: View {
    public let levels: [CGFloat]
    public var barCount: Int = 28

    public var body: some View {
        HStack(spacing: 3) {
            ForEach(0..<barCount, id: \.self) { index in
                RoundedRectangle(cornerRadius: 1.5)
                    .fill(AppTheme.Colors.securityRed)
                    .frame(width: 3, height: max(4, normalizedLevel(at: index) * 44))
            }
        }
        .animation(.linear(duration: 0.08), value: levels)
        .frame(maxWidth: .infinity)
    }

    private func normalizedLevel(at index: Int) -> CGFloat {
        guard !levels.isEmpty else { return 0.12 }
        let position = Double(index) / Double(max(1, barCount - 1))
        let idx = Int(position * Double(max(0, levels.count - 1)))
        return levels[max(0, min(levels.count - 1, idx))]
    }
}

// MARK: - Xcode #Preview

#Preview("VoiceInputView - Light") {
    VoiceInputView(service: SpeechRecognizerService(), onTranscript: { _ in }, onDismiss: {})
}

#Preview("VoiceInputView - Dark") {
    VoiceInputView(service: SpeechRecognizerService(), onTranscript: { _ in }, onDismiss: {})
        .preferredColorScheme(.dark)
}
