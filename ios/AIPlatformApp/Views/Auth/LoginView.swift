//
//  LoginView.swift
//  AIPlatformApp
//
//  Authentication & Guest Experience Entry Point
//  Quantum 品牌纯粹化：官方主标 + 手机验证码直登 + 第三方通道 + Guest Mode
//  （2026-08-16 拍板：移除 Apple 登录与手写品牌文字，仅保留官方集成 Logo）
//

import SwiftUI

public struct LoginView: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.colorScheme) private var colorScheme
    
    @State private var phoneNumber: String = ""
    @State private var smsCode: String = ""
    @State private var isCountdownActive: Bool = false
    @State private var countdownSeconds: Int = 60
    @State private var isLoading: Bool = false
    @State private var errorMessage: String? = nil
    
    private let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()
    
    public init() {}
    
    public var body: some View {
        NavigationStack {
            ZStack {
                AppTheme.Colors.groupedBackground
                    .ignoresSafeArea()

                LinearGradient(
                    colors: [
                        AppTheme.Colors.quantumCyan.opacity(colorScheme == .dark ? 0.10 : 0.12),
                        AppTheme.Colors.quantumViolet.opacity(colorScheme == .dark ? 0.08 : 0.06),
                        .clear
                    ],
                    startPoint: .topLeading,
                    endPoint: .center
                )
                .ignoresSafeArea()
                
                GeometryReader { geometry in
                    ScrollView(showsIndicators: false) {
                        VStack(spacing: 0) {
                            
                            // Top spacing: 将整体视觉重心舒适下移
                            Spacer(minLength: max(16, geometry.size.height * 0.05))
                            
                            // MARK: - 1. Top Brand Header
                            brandHeaderSection
                                .padding(.bottom, AppTheme.Spacing.xl)
                            
                            // MARK: - 2. Authentication Container Card
                            VStack(spacing: AppTheme.Spacing.xl) {
                                VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                                    Text("登录 Quantum")
                                        .font(AppTheme.Typography.sectionTitle)
                                        .foregroundColor(AppTheme.Colors.textPrimary)
                                    Text("继续进入你的智能体工作台")
                                        .font(AppTheme.Typography.supporting)
                                        .foregroundColor(AppTheme.Colors.textSecondary)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                
                                // Phone & SMS OTP Input Fields
                                phoneLoginSection
                                
                                // Third-Party Channels (WeChat / Alipay / SSO)
                                thirdPartyChannelsSection
                            }
                            .padding(AppTheme.Spacing.xl)
                            .background(AppTheme.Colors.cardBackground)
                            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous))
                            .cardShadow(colorScheme: colorScheme)
                            .padding(.horizontal, AppTheme.Spacing.lg)
                            
                            // Flexible spacer: 将访客模式与签署协议沉降至屏幕底部
                            Spacer(minLength: max(24, geometry.size.height * 0.06))
                            
                            // MARK: - 3. Guest Mode Entry
                            guestModeSection
                                .padding(.bottom, AppTheme.Spacing.md)
                            
                            // MARK: - 4. Terms and Privacy Footer（贴近屏幕底部安全区）
                            footerTermsSection
                                .padding(.bottom, max(12, geometry.safeAreaInsets.bottom + 10))
                        }
                        .frame(minHeight: geometry.size.height)
                    }
                }
            }
            .toolbar(.hidden, for: .navigationBar)
        }
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
    
    private var brandHeaderSection: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            QuantumAvatarView(size: 76)

            Text("Quantum")
                .font(.largeTitle.weight(.bold))
                .foregroundColor(AppTheme.Colors.textPrimary)

            Text("把复杂工作，变成清晰的下一步")
                .font(AppTheme.Typography.supporting.weight(.medium))
                .foregroundColor(AppTheme.Colors.textSecondary)
                .multilineTextAlignment(.center)
        }
    }
    
    private var phoneLoginSection: some View {
        VStack(spacing: AppTheme.Spacing.md) {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                Text("手机号码")
                    .font(AppTheme.Typography.label)
                    .foregroundColor(AppTheme.Colors.textSecondary)
                HStack(spacing: AppTheme.Spacing.sm) {
                    Image(systemName: "iphone")
                        .foregroundColor(AppTheme.Colors.textSecondary)
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
                        .foregroundColor(AppTheme.Colors.textSecondary)
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
                .frame(maxWidth: .infinity)
                .frame(height: 48)
                .foregroundColor(AppTheme.Colors.onPrimary)
                .background(AppTheme.Colors.quantumBlue)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            }
            .buttonStyle(SoftButtonStyle())
            .disabled(isLoading || phoneNumber.isEmpty || smsCode.isEmpty)
            .opacity((phoneNumber.isEmpty || smsCode.isEmpty) ? 0.6 : 1.0)
        }
    }
    
    private var thirdPartyChannelsSection: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            Text("其他企业与协同登录方式")
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
                
                // Enterprise SSO Button
                Button(action: { handleThirdPartyAuth(provider: "Enterprise SSO") }) {
                    VStack(spacing: AppTheme.Spacing.xs) {
                        Circle()
                            .fill(AppTheme.Colors.accent.opacity(0.12))
                            .frame(width: 48, height: 48)
                            .overlay(
                                Image(systemName: "building.2.fill")
                                    .foregroundColor(AppTheme.Colors.accent)
                                    .font(.system(size: 20))
                            )
                        Text("企业 SSO")
                            .font(.system(size: 11))
                            .foregroundColor(AppTheme.Colors.textSecondary)
                    }
                }
                .buttonStyle(SoftButtonStyle())
            }
        }
    }
    
    private var guestModeSection: some View {
        Button(action: {
            #if os(iOS)
            UIImpactFeedbackGenerator(style: .medium).impactOccurred()
            #endif
            withAnimation(.spring()) {
                appState.loginAsGuest()
            }
        }) {
            HStack(spacing: AppTheme.Spacing.xs) {
                Image(systemName: "person.crop.circle.badge.questionmark")
                    .font(.system(size: 15))
                Text("暂不登录，以游客身份体验")
                    .font(AppTheme.Typography.supporting.weight(.semibold))
                Image(systemName: "arrow.right")
                    .font(.caption.weight(.bold))
            }
            .foregroundColor(AppTheme.Colors.primary)
            .padding(.vertical, AppTheme.Spacing.sm)
            .padding(.horizontal, AppTheme.Spacing.lg)
            .background(AppTheme.Colors.primary.opacity(0.08))
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        }
        .buttonStyle(SoftButtonStyle())
        .minimumTouchTarget()
        .accessibilityHint("进入演示工作台，不会创建账号")
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
        .font(.system(size: 11))
        .multilineTextAlignment(.center)
        .padding(.horizontal, AppTheme.Spacing.xl)
    }
    
    // MARK: - Actions
    
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
                if profile.tenantKey == "demo" || profile.username == "dev" {
                    isDev = true
                }
            } catch {
                isDev = true
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
            appState.isLoggedIn = true
            appState.isGuestMode = false
            appState.currentProfile = MockData.tenantProfile
        }
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
