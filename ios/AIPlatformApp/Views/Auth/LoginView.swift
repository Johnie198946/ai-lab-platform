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
                // Background Gradient Surface
                AppTheme.Colors.groupedBackground
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
                                
                                // Phone & SMS OTP Input Fields
                                phoneLoginSection
                                
                                // Third-Party Channels (WeChat / Alipay / SSO)
                                thirdPartyChannelsSection
                            }
                            .padding(AppTheme.Spacing.xl)
                            .background(AppTheme.Colors.cardBackground)
                            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
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
        VStack(spacing: AppTheme.Spacing.md) {
            // Quantum 官方主 Logo（Any=彩色主标 / Dark=反白主标，自适应亮暗模式）
            // 仅保留官方集成完整 Logo（球体 + 官方标准字），无任何手写文字 / 副标题
            Image("quantum_logo_full")
                .resizable()
                .renderingMode(.original)
                .scaledToFit()
                .frame(maxWidth: 260, maxHeight: 120)
                .padding(.horizontal, AppTheme.Spacing.lg)
        }
    }
    
    private var phoneLoginSection: some View {
        VStack(spacing: AppTheme.Spacing.md) {
            // Phone Field
            HStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: "iphone")
                    .foregroundColor(AppTheme.Colors.textSecondary)
                    .frame(width: 24)
                
                Text("+86")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.textPrimary)
                
                Divider()
                    .frame(height: 18)
                
                TextField("请输入手机号", text: $phoneNumber)
                    .keyboardType(.numberPad)
                    .font(.system(size: 15))
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.Colors.secondaryBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            
            // SMS Code Field
            HStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: "lock.shield")
                    .foregroundColor(AppTheme.Colors.textSecondary)
                    .frame(width: 24)
                
                TextField("6 位短信验证码", text: $smsCode)
                    .keyboardType(.numberPad)
                    .font(.system(size: 15))
                
                Button(action: sendSmsCode) {
                    if isCountdownActive {
                        Text("\(countdownSeconds)s 后重发")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(AppTheme.Colors.textTertiary)
                    } else {
                        Text("获取验证码")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(AppTheme.Colors.primary)
                    }
                }
                .disabled(isCountdownActive || phoneNumber.count < 11)
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.Colors.secondaryBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            
            if let error = errorMessage {
                Text(error)
                    .font(.system(size: 12))
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
                    Text("登 录 / 注 册")
                        .font(.system(size: 16, weight: .bold))
                }
                .frame(maxWidth: .infinity)
                .frame(height: 48)
                .foregroundColor(AppTheme.Colors.onPrimary)
                .background(AppTheme.Colors.primary)
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
                .font(.system(size: 12))
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
                Text("暂不登录，以游客身份体验 (Guest Mode) ➔")
                    .font(.system(size: 14, weight: .semibold))
            }
            .foregroundColor(AppTheme.Colors.primary)
            .padding(.vertical, AppTheme.Spacing.sm)
            .padding(.horizontal, AppTheme.Spacing.lg)
            .background(AppTheme.Colors.primary.opacity(0.08))
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        }
        .buttonStyle(SoftButtonStyle())
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
            // 1. 真实注册（开发态 Authen 未起 → 连接失败，降级开发模式）
            do {
                let resp = try await APIClient.shared.register(
                    email: email,
                    username: username,
                    password: password,
                    verificationCode: code
                )
                if let token = resp.token, !token.isEmpty {
                    APIClient.shared.saveToken(token)
                }
            } catch {
                isDev = true
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
