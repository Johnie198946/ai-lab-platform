//
//  LoginView.swift
//  AIPlatformApp
//
//  Authentication & Guest Experience Entry Point
//  Quantum 品牌纯粹化：官方主标 + 手机验证码直登 + 第三方通道 + Guest Mode
//  （2026-08-16 拍板：移除 Apple 登录与手写品牌文字，仅保留官方集成 Logo）
//

import SwiftUI
import AuthenticationServices
#if os(iOS)
import UIKit
#endif

public struct LoginView: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.colorScheme) private var colorScheme
    
    @State private var phoneNumber: String = ""
    @State private var smsCode: String = ""
    @State private var isCountdownActive: Bool = false
    @State private var countdownSeconds: Int = 60
    @State private var isLoading: Bool = false
    @State private var errorMessage: String? = nil
    @StateObject private var oauthCoordinator = OAuthSessionCoordinator()
    
    private let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()
    
    public init() {}
    
    public var body: some View {
        NavigationStack {
            ZStack {
                QuantumMistBackground()

                GeometryReader { geometry in
                    ScrollView(showsIndicators: false) {
                        VStack(spacing: AppTheme.Spacing.xl) {
                            brandHeaderSection

                            PearlLoginArtwork()
                                .frame(height: min(260, geometry.size.height * 0.30))

                            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                                Text("让想法成为\n可执行的智能工作流")
                                    .font(.system(size: 36, weight: .semibold, design: .rounded))
                                    .foregroundColor(AppTheme.Colors.textPrimary)
                                    .minimumScaleFactor(0.82)

                                Text("连接 Agent、知识与工具，在一个工作空间里完成从需求确认到交付。")
                                    .font(AppTheme.Typography.body)
                                    .foregroundColor(AppTheme.Colors.textSecondary)
                                    .lineSpacing(4)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)

                            VStack(spacing: AppTheme.Spacing.xl) {
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
                            }
                            .padding(AppTheme.Spacing.xxl)
                            .background(AppTheme.Colors.cardBackground)
                            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous))
                            .overlay {
                                RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous)
                                    .stroke(AppTheme.Colors.border, lineWidth: 0.75)
                            }
                            .shadow(
                                color: Color(hex: "6B5A8A").opacity(0.12),
                                radius: 26,
                                y: 10
                            )

                            guestModeSection
                            footerTermsSection
                        }
                        .padding(.horizontal, AppTheme.Metrics.contentGutter)
                        .padding(.top, max(18, geometry.safeAreaInsets.top + 8))
                        .padding(.bottom, max(24, geometry.safeAreaInsets.bottom + 12))
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
        HStack(spacing: AppTheme.Spacing.sm) {
            QuantumAvatarView(size: 38)
            Text("Quantum")
                .font(.system(size: 20, weight: .semibold, design: .rounded))
                .foregroundColor(AppTheme.Colors.textPrimary)
            Spacer()
            Label("本地优先", systemImage: "lock.shield")
                .font(AppTheme.Typography.micro)
                .foregroundColor(AppTheme.Icons.interactive)
                .padding(.horizontal, 10)
                .padding(.vertical, 7)
                .background(AppTheme.Colors.surfaceTint)
                .clipShape(Capsule())
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
                Button(action: { handleThirdPartyAuth(provider: "alipay") }) {
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
                            .foregroundColor(AppTheme.Icons.intelligence)
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
            .foregroundColor(AppTheme.Icons.interactive)
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
        .font(.caption)
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
        guard !isLoading else { return }
        isLoading = true
        errorMessage = nil
        Task { @MainActor in
            do {
                let start = try await APIClient.shared.startOAuth(provider: provider)
                let ticket = try await oauthCoordinator.authenticate(url: start.authorizationUrl)
                let response = try await APIClient.shared.completeOAuth(ticket: ticket)
                APIClient.shared.saveToken(response.token)
                _ = try? await APIClient.shared.fetchMe()
                isLoading = false
                withAnimation(.spring()) {
                    appState.isLoggedIn = true
                    appState.isGuestMode = false
                    appState.currentProfile = MockData.tenantProfile
                }
            } catch OAuthSessionCoordinatorError.cancelled {
                isLoading = false
            } catch {
                isLoading = false
                errorMessage = "第三方登录失败：\(error.localizedDescription)"
            }
        }
    }
}

private enum OAuthSessionCoordinatorError: LocalizedError {
    case invalidCallback
    case cancelled

    var errorDescription: String? {
        switch self {
        case .invalidCallback: return "支付宝回调无效"
        case .cancelled: return "用户取消登录"
        }
    }
}

@MainActor
private final class OAuthSessionCoordinator: NSObject, ObservableObject, ASWebAuthenticationPresentationContextProviding {
    private var session: ASWebAuthenticationSession?

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        #if os(iOS)
        return UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .flatMap(\.windows)
            .first(where: { $0.isKeyWindow }) ?? ASPresentationAnchor()
        #else
        return ASPresentationAnchor()
        #endif
    }

    func authenticate(url: URL) async throws -> String {
        try await withCheckedThrowingContinuation { continuation in
            let authSession = ASWebAuthenticationSession(
                url: url,
                callbackURLScheme: "quantum"
            ) { [weak self] callbackURL, error in
                self?.session = nil
                if let error {
                    if let authError = error as? ASWebAuthenticationSessionError,
                       authError.code == .canceledLogin {
                        continuation.resume(throwing: OAuthSessionCoordinatorError.cancelled)
                    } else {
                        continuation.resume(throwing: error)
                    }
                    return
                }
                guard let callbackURL,
                      let components = URLComponents(url: callbackURL, resolvingAgainstBaseURL: false),
                      let ticket = components.queryItems?.first(where: { $0.name == "oauth_ticket" })?.value,
                      !ticket.isEmpty else {
                    continuation.resume(throwing: OAuthSessionCoordinatorError.invalidCallback)
                    return
                }
                continuation.resume(returning: ticket)
            }
            authSession.presentationContextProvider = self
            authSession.prefersEphemeralWebBrowserSession = false
            self.session = authSession
            guard authSession.start() else {
                self.session = nil
                continuation.resume(throwing: OAuthSessionCoordinatorError.invalidCallback)
                return
            }
        }
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
