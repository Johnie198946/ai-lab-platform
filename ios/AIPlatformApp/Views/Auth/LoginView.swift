//
//  LoginView.swift
//  AIPlatformApp
//
//  Authentication Entry Point
//  Quantum 渐进式登录：Magic Rings 品牌图案 + 点击后登录卡片刹停入场
//  （2026-08-16 拍板：移除 Apple 登录与手写品牌文字，仅保留官方集成 Logo）
//

import SwiftUI

public struct LoginView: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    
    @State private var phoneNumber: String = ""
    @State private var smsCode: String = ""
    @State private var isCountdownActive: Bool = false
    @State private var countdownSeconds: Int = 60
    @State private var isLoading: Bool = false
    @State private var errorMessage: String? = nil
    @State private var isLoginCardVisible = false
    
    private let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()
    
    public init() {}
    
    public var body: some View {
        NavigationStack {
            ZStack {
                QuantumMistBackground()

                GeometryReader { geometry in
                    VStack(spacing: isLoginCardVisible ? 10 : 0) {
                        Spacer(minLength: isLoginCardVisible ? 6 : 0)

                        Button(action: revealLoginCard) {
                            QuantumMagicRingsHero(
                                isCompact: isLoginCardVisible,
                                reduceMotion: reduceMotion || isLoginCardVisible
                            )
                            .frame(
                                height: isLoginCardVisible
                                    ? min(176, geometry.size.height * 0.23)
                                    : min(390, geometry.size.height * 0.52)
                            )
                        }
                        .buttonStyle(.plain)
                        .disabled(isLoginCardVisible)
                        .accessibilityLabel("打开登录")
                        .accessibilityHint("显示手机号登录卡片")

                        if isLoginCardVisible {
                            loginCard
                                .transition(
                                    .asymmetric(
                                        insertion: .offset(y: geometry.size.height * 0.78)
                                            .combined(with: .opacity),
                                        removal: .offset(y: geometry.size.height * 0.24)
                                            .combined(with: .opacity)
                                    )
                                )
                        }

                        Spacer(minLength: isLoginCardVisible ? 6 : 0)
                    }
                    .padding(.horizontal, max(20, AppTheme.Metrics.contentGutter))
                    .padding(.top, max(8, geometry.safeAreaInsets.top))
                    .padding(.bottom, max(8, geometry.safeAreaInsets.bottom))
                    .frame(width: geometry.size.width, height: geometry.size.height)
                    .clipped()
                }
            }
            .toolbar(.hidden, for: .navigationBar)
        }
        .background(AppTheme.Colors.background)
        .onReceive(timer) { _ in
            if isCountdownActive && countdownSeconds > 0 {
                countdownSeconds -= 1
            } else if countdownSeconds == 0 {
                isCountdownActive = false
                countdownSeconds = 60
            }
        }
    }
    
    // MARK: - Subviews
    
    private var loginCard: some View {
        VStack(spacing: AppTheme.Spacing.lg) {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                Text("欢迎回来")
                    .font(AppTheme.Typography.sectionTitle)
                    .foregroundColor(AppTheme.Colors.textPrimary)
                Text("使用手机号进入你的 Quantum 工作空间")
                    .font(AppTheme.Typography.supporting)
                    .foregroundColor(AppTheme.Colors.textSecondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            phoneLoginSection
            thirdPartyChannelsSection
            footerTermsSection
        }
        .padding(AppTheme.Spacing.xl)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous)
                .stroke(AppTheme.Colors.border, lineWidth: 0.75)
        }
        .shadow(color: Color(hex: "6B5A8A").opacity(0.16), radius: 28, y: 12)
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .contain)
    }
    
    private var phoneLoginSection: some View {
        VStack(spacing: AppTheme.Spacing.md) {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                Text("手机号码")
                    .font(AppTheme.Typography.label)
                    .foregroundColor(AppTheme.Colors.textSecondary)
                HStack(spacing: AppTheme.Spacing.sm) {
                    Image(systemName: "iphone")
                        .foregroundColor(AppTheme.Icons.secondary)
                        .frame(width: 24)

                    Text("+86")
                        .font(AppTheme.Typography.body.weight(.semibold))
                        .foregroundColor(AppTheme.Colors.textPrimary)

                    Divider()
                        .frame(height: 20)

                    TextField("请输入手机号", text: $phoneNumber)
                        .keyboardType(.numberPad)
                        .textContentType(.telephoneNumber)
                        .font(AppTheme.Typography.body)
                }
                .frame(minHeight: AppTheme.Metrics.inputHeight)
                .padding(.horizontal, AppTheme.Spacing.md)
                .background(AppTheme.Colors.secondaryBackground)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                .overlay {
                    RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                        .stroke(AppTheme.Colors.border, lineWidth: 0.75)
                }
            }
            
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                Text("短信验证码")
                    .font(AppTheme.Typography.label)
                    .foregroundColor(AppTheme.Colors.textSecondary)
                HStack(spacing: AppTheme.Spacing.sm) {
                    Image(systemName: "lock.shield")
                        .foregroundColor(AppTheme.Icons.secondary)
                        .frame(width: 24)

                    TextField("输入 6 位验证码", text: $smsCode)
                        .keyboardType(.numberPad)
                        .textContentType(.oneTimeCode)
                        .font(AppTheme.Typography.body)

                    Button(action: sendSmsCode) {
                        if isCountdownActive {
                            Text("\(countdownSeconds)s 后重发")
                                .font(AppTheme.Typography.label)
                                .foregroundColor(AppTheme.Colors.textTertiary)
                        } else {
                            Text("获取验证码")
                                .font(AppTheme.Typography.label)
                                .foregroundColor(AppTheme.Colors.primary)
                        }
                    }
                    .minimumTouchTarget()
                    .disabled(isCountdownActive || phoneNumber.count < 11)
                }
                .frame(minHeight: AppTheme.Metrics.inputHeight)
                .padding(.horizontal, AppTheme.Spacing.md)
                .background(AppTheme.Colors.secondaryBackground)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                .overlay {
                    RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                        .stroke(AppTheme.Colors.border, lineWidth: 0.75)
                }
            }
            
            if let error = errorMessage {
                Text(error)
                    .font(.caption)
                    .foregroundColor(AppTheme.Colors.securityRed)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            
            // Login Action Button
            Button(action: performPhoneLogin) {
                HStack {
                    if isLoading {
                        ProgressView()
                            .tint(AppTheme.Colors.onPrimary)
                            .padding(.trailing, AppTheme.Spacing.xs)
                    }
                    Text("登录 / 注册")
                        .font(.headline.weight(.semibold))
                }
            }
            .buttonStyle(QuantumPrimaryButtonStyle())
            .disabled(isLoading || phoneNumber.isEmpty || smsCode.isEmpty)
            .opacity((phoneNumber.isEmpty || smsCode.isEmpty) ? 0.6 : 1.0)
        }
    }
    
    private var thirdPartyChannelsSection: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            Text("其他登录方式")
                .font(.caption)
                .foregroundColor(AppTheme.Colors.textTertiary)
            
            HStack(spacing: AppTheme.Spacing.xl) {
                // WeChat Button
                Button(action: { handleThirdPartyAuth(provider: "WeChat") }) {
                    VStack(spacing: AppTheme.Spacing.xs) {
                        Circle()
                            .fill(AppTheme.Colors.thirdPartyWeChat.opacity(0.12))
                            .frame(width: 48, height: 48)
                            .overlay(
                                Image(systemName: "message.fill")
                                    .foregroundColor(AppTheme.Colors.thirdPartyWeChat)
                                    .font(.system(size: 22))
                            )
                        Text("微信")
                            .font(.system(size: 11))
                            .foregroundColor(AppTheme.Colors.textSecondary)
                    }
                }
                .buttonStyle(SoftButtonStyle())
                
                // Alipay Button
                Button(action: { handleThirdPartyAuth(provider: "Alipay") }) {
                    VStack(spacing: AppTheme.Spacing.xs) {
                        Circle()
                            .fill(AppTheme.Colors.thirdPartyAlipay.opacity(0.12))
                            .frame(width: 48, height: 48)
                            .overlay(
                                Image(systemName: "creditcard.fill")
                                    .foregroundColor(AppTheme.Colors.thirdPartyAlipay)
                                    .font(.system(size: 20))
                            )
                        Text("支付宝")
                            .font(.system(size: 11))
                            .foregroundColor(AppTheme.Colors.textSecondary)
                    }
                }
                .buttonStyle(SoftButtonStyle())
            }
        }
    }
    
    private var footerTermsSection: some View {
        VStack(spacing: AppTheme.Spacing.xs) {
            Text("登录即代表您已同意")
                .foregroundColor(AppTheme.Colors.textTertiary)
            + Text("《用户服务协议》")
                .foregroundColor(AppTheme.Colors.primary)
            + Text(" 与 ")
                .foregroundColor(AppTheme.Colors.textTertiary)
            + Text("《隐私保护政策》")
                .foregroundColor(AppTheme.Colors.primary)
        }
        .font(.caption)
        .multilineTextAlignment(.center)
        .padding(.horizontal, AppTheme.Spacing.xl)
    }
    
    // MARK: - Actions

    private func revealLoginCard() {
        guard !isLoginCardVisible else { return }
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        #endif

        if reduceMotion {
            withAnimation(.easeOut(duration: 0.18)) {
                isLoginCardVisible = true
            }
        } else {
            withAnimation(
                .interpolatingSpring(
                    mass: 0.92,
                    stiffness: 235,
                    damping: 25,
                    initialVelocity: 9
                )
            ) {
                isLoginCardVisible = true
            }
        }
    }
    
    private func sendSmsCode() {
        guard phoneNumber.count >= 11 else { return }
        isCountdownActive = true
        #if os(iOS)
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        #endif
    }
    
    private func performPhoneLogin() {
        guard !isLoading else { return }
        isLoading = true
        errorMessage = nil

        // 手机号表单 → register 契约桥接（开发态占位；生产需真实邮箱/密码表单，见开发总结）
        let username = phoneNumber
        let email = "\(phoneNumber)@ailab.quantum"
        let password = smsCode
        let code = smsCode

        Task { @MainActor in
            var isDev = false
            // 1. 真实注册（后端内建兜底：注册失败自动回退登录，返回平台 JWT）
            do {
                let resp = try await APIClient.shared.register(
                    email: email,
                    username: username,
                    password: password,
                    verificationCode: code
                )
                guard let token = resp.token, !token.isEmpty else {
                    // 顶设铁律：未拿到凭证绝不进入主界面（避免"假装登录成功"后被 401 踢回）
                    isLoading = false
                    errorMessage = "登录失败：未获取到访问凭证，请稍后重试"
                    return
                }
                APIClient.shared.saveToken(token)
            } catch {
                isLoading = false
                errorMessage = "登录失败：\(error.localizedDescription)"
                return
            }

            // 2. 探测 /me 判定开发态（dev 载荷 tenant_key=demo）或连接失败
            do {
                let profile = try await APIClient.shared.fetchMe()
                appState.currentTenantKey = profile.tenantKey
                appState.currentUserId = profile.userId
                KnowledgeNoteStore.shared.activate(
                    tenantKey: profile.tenantKey, userId: profile.userId
                )
                if profile.tenantKey == "demo" || profile.username == "dev" {
                    isDev = true
                }
            } catch {
                isDev = true
                appState.currentUserId = "demo-user"
                appState.currentTenantKey = appState.currentProfile.tenantId
                KnowledgeNoteStore.shared.activate(
                    tenantKey: appState.currentProfile.tenantId,
                    userId: appState.currentUserId
                )
            }

            isLoading = false
            #if os(iOS)
            UINotificationFeedbackGenerator().notificationOccurred(.success)
            #endif
            appState.isDevMode = isDev
            withAnimation(.spring()) {
                appState.isLoggedIn = true
                appState.isGuestMode = false
                appState.currentProfile = MockData.tenantProfile
            }
        }
    }
    
    private func handleThirdPartyAuth(provider: String) {
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        #endif
        withAnimation(.spring()) {
            appState.currentUserId = "third-party-\(provider.lowercased())"
            appState.currentTenantKey = appState.currentProfile.tenantId
            KnowledgeNoteStore.shared.activate(
                tenantKey: appState.currentProfile.tenantId,
                userId: appState.currentUserId
            )
            appState.isLoggedIn = true
            appState.isGuestMode = false
            appState.currentProfile = MockData.tenantProfile
        }
    }
}

private struct QuantumMagicRingsHero: View {
    let isCompact: Bool
    let reduceMotion: Bool

    var body: some View {
        GeometryReader { proxy in
            let side = min(proxy.size.width, proxy.size.height)
            let artworkSide = side * (isCompact ? 0.72 : 0.78)

            ZStack {
                MagicRingsView(reduceMotion: reduceMotion)
                    .frame(width: side, height: side)

                PearlLoginArtwork()
                    .frame(width: artworkSide, height: artworkSide * 0.72)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .contentShape(Circle())
        }
        .accessibilityHidden(true)
    }
}

private struct MagicRingsView: View {
    let reduceMotion: Bool

    private let ringColors = [
        AppTheme.Colors.auroraPink,
        AppTheme.Colors.quantumViolet,
        AppTheme.Colors.quantumCyan,
        AppTheme.Colors.quantumBlue,
        AppTheme.Colors.auroraPink
    ]

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0, paused: reduceMotion)) { timeline in
            let elapsed = timeline.date.timeIntervalSinceReferenceDate

            GeometryReader { proxy in
                let side = min(proxy.size.width, proxy.size.height)

                ZStack {
                    ForEach(0..<5, id: \.self) { index in
                        let progress = Double(index) / 4.0
                        let diameter = side * (0.45 + progress * 0.48)
                        let direction = index.isMultiple(of: 2) ? 1.0 : -1.0
                        let rotation = reduceMotion
                            ? Double(index * 24)
                            : elapsed * (11 + Double(index) * 2.4) * direction
                        let pulse = reduceMotion
                            ? 1.0
                            : 1.0 + sin(elapsed * 1.8 + Double(index) * 0.72) * 0.025

                        Circle()
                            .trim(from: 0.04 + progress * 0.03, to: 0.72 + progress * 0.05)
                            .stroke(
                                AngularGradient(
                                    colors: [
                                        ringColors[index],
                                        ringColors[(index + 2) % ringColors.count],
                                        ringColors[index].opacity(0.10),
                                        ringColors[index]
                                    ],
                                    center: .center
                                ),
                                style: StrokeStyle(
                                    lineWidth: max(2, side * (0.012 - progress * 0.003)),
                                    lineCap: .round
                                )
                            )
                            .frame(width: diameter, height: diameter)
                            .rotationEffect(.degrees(rotation))
                            .scaleEffect(pulse)
                            .opacity(0.78 - progress * 0.34)
                            .blur(radius: index == 4 ? 1.2 : 0)
                    }

                    Circle()
                        .fill(
                            RadialGradient(
                                colors: [
                                    AppTheme.Colors.quantumViolet.opacity(0.20),
                                    AppTheme.Colors.quantumCyan.opacity(0.08),
                                    .clear
                                ],
                                center: .center,
                                startRadius: 2,
                                endRadius: side * 0.48
                            )
                        )
                        .blur(radius: 14)
                }
                .frame(width: proxy.size.width, height: proxy.size.height)
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

private struct PearlLoginArtwork: View {
    var body: some View {
        GeometryReader { proxy in
            let side = min(proxy.size.width, proxy.size.height * 1.42)
            ZStack {
                Circle()
                    .fill(AppTheme.Colors.quantumViolet.opacity(0.10))
                    .frame(width: side * 0.88, height: side * 0.88)
                    .blur(radius: 24)

                RoundedRectangle(cornerRadius: 34, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [Color.white, Color(hex: "E7E0FA")],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: side * 0.72, height: side * 0.30)
                    .rotationEffect(.degrees(-14))
                    .offset(y: 20)
                    .shadow(color: Color(hex: "6B5A8A").opacity(0.16), radius: 22, y: 12)

                Capsule()
                    .fill(
                        LinearGradient(
                            colors: [AppTheme.Colors.quantumCyan, AppTheme.Colors.quantumBlue],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: side * 0.42, height: side * 0.15)
                    .rotationEffect(.degrees(29))
                    .offset(x: side * 0.20, y: -side * 0.13)

                Circle()
                    .fill(
                        RadialGradient(
                            colors: [Color.white, AppTheme.Colors.quantumViolet],
                            center: .topLeading,
                            startRadius: 3,
                            endRadius: side * 0.16
                        )
                    )
                    .frame(width: side * 0.25, height: side * 0.25)
                    .offset(x: -side * 0.18, y: -side * 0.08)
                    .shadow(color: AppTheme.Colors.quantumViolet.opacity(0.25), radius: 20, y: 10)

                QuantumAvatarView(size: side * 0.23)
                    .offset(x: side * 0.15, y: side * 0.10)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .accessibilityHidden(true)
    }
}

// MARK: - Xcode #Preview

#Preview("LoginView - Light Mode") {
    LoginView()
        .environmentObject(AppState(isLoggedIn: false))
}

#Preview("LoginView - Dark Mode") {
    LoginView()
        .environmentObject(AppState(isLoggedIn: false))
        .preferredColorScheme(.dark)
}
