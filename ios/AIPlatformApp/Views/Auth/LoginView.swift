//
//  LoginView.swift
//  AIPlatformApp
//
//  Authentication Entry Point
//  Quantum 渐进式登录：Magic Rings 品牌图案 + 点击后登录卡片刹停入场
//  （2026-08-16 拍板：移除 Apple 登录与手写品牌文字，仅保留官方集成 Logo）
//

import SwiftUI
import AuthenticationServices

struct LoginChannelAvailability: Equatable {
    // Start fail-closed while capability discovery is in flight, avoiding the
    // misleading enabled-then-grey flash on production startup.
    var phone = false
    var wechat = false
    var alipay = false

    mutating func apply(_ capabilities: AuthCapabilitiesDTO) {
        phone = capabilities.phone.enabled
        wechat = capabilities.oauth.wechat.enabled
        alipay = capabilities.oauth.alipay.enabled
    }
}

enum LoginInputPolicy {
    static let developerPhone = "13800138000"
    static let developerCode = "246810"

    static func digits(_ value: String, limit: Int) -> String {
        String(value.filter(\.isNumber).prefix(limit))
    }

    static func isDeveloperCredentials(phone: String, code: String) -> Bool {
        digits(phone, limit: 11) == developerPhone && digits(code, limit: 6) == developerCode
    }

    static func canSubmit(
        phone: String,
        code: String,
        phoneChannelEnabled: Bool,
        isLoading: Bool
    ) -> Bool {
        guard !isLoading else { return false }
        let normalizedPhone = digits(phone, limit: 11)
        let normalizedCode = digits(code, limit: 6)
        guard normalizedPhone.count == 11, normalizedCode.count == 6 else { return false }
        return phoneChannelEnabled || isDeveloperCredentials(phone: normalizedPhone, code: normalizedCode)
    }
}

enum LoginConsentPolicy {
    static func hasValidAgreementVersion(_ version: String) -> Bool {
        let trimmed = version.trimmingCharacters(in: .whitespacesAndNewlines)
        return !trimmed.isEmpty && trimmed == version && trimmed.count <= 96
    }

    static func isAccepted(selectedVersion: String?, currentVersion: String?) -> Bool {
        guard let selectedVersion, let currentVersion else { return false }
        return selectedVersion == currentVersion && hasValidAgreementVersion(currentVersion)
    }

    static func failureMessage(for error: Error) -> String {
        guard let apiError = error as? APIError else {
            return "协议记录未完成，请重试。"
        }
        switch apiError {
        case .network:
            return "网络连接中断，协议记录未完成，请重试。"
        case .timeout:
            return "协议记录响应超时，请重试。"
        case .unauthorized, .server(401, _):
            return "登录凭证未被接受，请重新登录。"
        case .server(403, _), .knowledgeScopeChanged:
            return "当前账号无权记录协议选择，请联系管理员。"
        case .server(409, _):
            return "协议版本已更新，请重新阅读并确认。"
        case .server(422, _):
            return "协议选择未被服务接受，请重新确认。"
        case .server(let status, _) where (500...599).contains(status):
            return "协议服务暂时不可用，请稍后重试。"
        case .decoding:
            return "协议服务响应无法确认，请稍后重试。"
        case .invalidURL, .authenticationRejected, .server:
            return "协议记录未完成，请重试。"
        }
    }
}

private enum PendingAuthAction {
    case phone(phone: String, code: String, isDeveloper: Bool)
    case oauth(provider: String)
    case authenticated(LoginSessionDTO, isDeveloper: Bool, idempotencyKey: String)
}

public struct LoginView: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    @State private var phoneNumber: String = ""
    @State private var smsCode: String = ""
    @State private var isCountdownActive: Bool = false
    @State private var countdownSeconds: Int = 60
    @State private var isLoading: Bool = false
    @State private var errorMessage: String? = nil
    @State private var isLoginCardVisible = false
    @State private var channels = LoginChannelAvailability()
    @State private var isCapabilityLoading = true
    @State private var capabilityMessage: String?
    @State private var acceptedAgreementVersion: String?
    @State private var agreement: AgreementDTO?
    @State private var isAgreementLoading = false
    @State private var agreementError: String?
    @State private var showingAgreement = false
    @State private var pendingAuthAction: PendingAuthAction?
    @StateObject private var oauthCoordinator = OAuthSessionCoordinator()
    @FocusState private var focusedField: LoginField?

    private enum LoginField: Hashable {
        case phone
        case code
    }
    
    private let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()
    
    public init() {}
    
    public var body: some View {
        NavigationStack {
            ZStack {
                QuantumMistBackground()
                    .contentShape(Rectangle())
                    .onTapGesture(perform: dismissLoginCard)

                GeometryReader { geometry in
                    ScrollView(showsIndicators: false) {
                        VStack(spacing: isLoginCardVisible ? 10 : 0) {
                            Spacer(minLength: isLoginCardVisible ? 6 : 0)

                            Button(action: revealLoginCard) {
                                QuantumMagicRingsHero(
                                    isCompact: isLoginCardVisible,
                                    reduceMotion: reduceMotion || isLoginCardVisible
                                )
                                .frame(
                                    height: isLoginCardVisible
                                        ? min(132, geometry.size.height * 0.18)
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
                        .frame(maxWidth: .infinity, minHeight: geometry.size.height)
                    }
                    .scrollDismissesKeyboard(.interactively)
                }
            }
            .toolbar(.hidden, for: .navigationBar)
        }
        .background(AppTheme.Colors.background)
        .overlay {
            if showingAgreement {
                AppTheme.Colors.scrim
                    .ignoresSafeArea()
                    .contentShape(Rectangle())
                    .onTapGesture {}
                    .accessibilityHidden(true)
            }
        }
        .onReceive(timer) { _ in
            if isCountdownActive && countdownSeconds > 0 {
                countdownSeconds -= 1
            } else if countdownSeconds == 0 {
                isCountdownActive = false
                countdownSeconds = 60
            }
        }
        .task {
            await loadAuthCapabilities()
            await loadAgreement(forcePresentation: false)
        }
        .onOpenURL { url in
            oauthCoordinator.handleCallback(url)
        }
        .sheet(isPresented: $showingAgreement, onDismiss: agreementSheetDismissed) {
            AgreementSheet(
                agreement: agreement,
                isLoading: isAgreementLoading,
                isAccepting: false,
                errorMessage: agreementError,
                onRetry: { Task { await loadAgreement(forcePresentation: true) } },
                onAccept: acceptCurrentAgreement
            )
            .presentationDetents([.medium, .large])
            .presentationDragIndicator(.visible)
            .presentationBackground(AppTheme.Colors.cardBackground)
            .presentationBackgroundInteraction(.disabled)
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

            if isCapabilityLoading {
                Label("正在检测可用登录方式…", systemImage: "arrow.triangle.2.circlepath")
                    .font(AppTheme.Typography.micro)
                    .foregroundColor(AppTheme.Colors.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else if let capabilityMessage {
                Label(capabilityMessage, systemImage: "info.circle.fill")
                    .font(AppTheme.Typography.micro)
                    .foregroundColor(AppTheme.Colors.statusWarning)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }

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
                        .focused($focusedField, equals: .phone)
                        .onChange(of: phoneNumber) { _, value in
                            let normalized = LoginInputPolicy.digits(value, limit: 11)
                            if normalized != value { phoneNumber = normalized }
                        }
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
                        .focused($focusedField, equals: .code)
                        .onChange(of: smsCode) { _, value in
                            let normalized = LoginInputPolicy.digits(value, limit: 6)
                            if normalized != value { smsCode = normalized }
                        }

                    Button(action: sendSmsCode) {
                        if isCountdownActive {
                            Text("\(countdownSeconds)s 后重发")
                                .font(AppTheme.Typography.label)
                                .foregroundColor(AppTheme.Colors.textTertiary)
                        } else if isCapabilityLoading {
                            Text("检测中")
                                .font(AppTheme.Typography.label)
                                .foregroundColor(AppTheme.Colors.textTertiary)
                        } else if !channels.phone {
                            Text("短信暂未开放")
                                .font(AppTheme.Typography.label)
                                .foregroundColor(AppTheme.Colors.textTertiary)
                        } else {
                            Text("获取验证码")
                                .font(AppTheme.Typography.label)
                                .foregroundColor(AppTheme.Colors.primary)
                        }
                    }
                    .minimumTouchTarget()
                    .disabled(
                        !channels.phone || isLoading || isCountdownActive
                            || phoneNumber.count < 11
                    )
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
                    Text(isRetryingAgreementAcceptance ? "重试协议确认" : "登录 / 注册")
                        .font(.headline.weight(.semibold))
                }
            }
            .buttonStyle(QuantumPrimaryButtonStyle())
            .disabled(!canPerformPrimaryAuth)
            .opacity(canPerformPrimaryAuth ? 1.0 : 0.6)
        }
    }
    
    private var thirdPartyChannelsSection: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            Text("其他登录方式")
                .font(.caption)
                .foregroundColor(AppTheme.Colors.textTertiary)
            
            HStack(spacing: AppTheme.Spacing.xl) {
                // WeChat Button
                Button(action: { handleThirdPartyAuth(provider: "wechat") }) {
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
                .disabled(!channels.wechat || isLoading || isRetryingAgreementAcceptance)
                .opacity(channels.wechat && !isRetryingAgreementAcceptance ? 1 : 0.45)
                
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
                        Text(channels.alipay ? "支付宝" : "支付宝·暂未开放")
                            .font(.system(size: 11))
                            .foregroundColor(AppTheme.Colors.textSecondary)
                    }
                }
                .buttonStyle(SoftButtonStyle())
                .disabled(!channels.alipay || isLoading || isRetryingAgreementAcceptance)
                .opacity(channels.alipay && !isRetryingAgreementAcceptance ? 1 : 0.45)
            }
        }
    }
    
    private var footerTermsSection: some View {
        HStack(spacing: 0) {
            Button {
                guard let version = agreement?.version else {
                    showingAgreement = true
                    Task { await loadAgreement(forcePresentation: true) }
                    return
                }
                acceptedAgreementVersion = acceptedAgreementVersion == version ? nil : version
            } label: {
                Image(systemName: isCurrentAgreementAccepted ? "checkmark.square.fill" : "square")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.primary)
            }
            .buttonStyle(.plain)
            .frame(width: 44, height: 44)
            .contentShape(Rectangle())
            .disabled(isLoading)
            .accessibilityLabel("我已阅读服务协议")
            .accessibilityValue(isCurrentAgreementAccepted ? "已勾选" : "未勾选")
            .accessibilityIdentifier("login.agreement.checkbox")

            Text("我已阅读")
                .font(.caption)
                .foregroundColor(AppTheme.Colors.textPrimary)
            Button {
                showingAgreement = true
                if agreement == nil { Task { await loadAgreement(forcePresentation: true) } }
            } label: {
                Text("服务协议")
                    .font(.caption)
                    .foregroundColor(AppTheme.Colors.primary)
            }
            .buttonStyle(.plain)
            .frame(minWidth: 44, minHeight: 44)
            .contentShape(Rectangle())
            .accessibilityLabel("打开服务协议")
            .accessibilityHint("阅读当前版本的全部协议章节")
            .accessibilityIdentifier("login.agreement.link")
        }
        .frame(maxWidth: .infinity, alignment: .center)
    }

    private var isCurrentAgreementAccepted: Bool {
        LoginConsentPolicy.isAccepted(
            selectedVersion: acceptedAgreementVersion, currentVersion: agreement?.version
        )
    }

    private var isRetryingAgreementAcceptance: Bool {
        if case .authenticated = pendingAuthAction { return true }
        return false
    }

    private var canPerformPrimaryAuth: Bool {
        guard !isLoading else { return false }
        return isRetryingAgreementAcceptance || LoginInputPolicy.canSubmit(
            phone: phoneNumber,
            code: smsCode,
            phoneChannelEnabled: channels.phone,
            isLoading: false
        )
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

    private func dismissLoginCard() {
        guard isLoginCardVisible else { return }
        focusedField = nil
        let animation: Animation = reduceMotion
            ? .easeOut(duration: 0.16)
            : .interpolatingSpring(mass: 0.9, stiffness: 220, damping: 27)
        withAnimation(animation) {
            isLoginCardVisible = false
        }
    }
    
    private func sendSmsCode() {
        let normalizedPhone = LoginInputPolicy.digits(phoneNumber, limit: 11)
        guard normalizedPhone.count == 11, channels.phone, !isLoading else { return }
        isLoading = true
        errorMessage = nil
        Task { @MainActor in
            do {
                try await APIClient.shared.sendPhoneCode(phone: normalizedPhone)
                isCountdownActive = true
                countdownSeconds = 60
                #if os(iOS)
                UINotificationFeedbackGenerator().notificationOccurred(.success)
                #endif
            } catch {
                errorMessage = "验证码发送失败：\(error.localizedDescription)"
            }
            isLoading = false
        }
    }
    
    private func performPhoneLogin() {
        if case .authenticated = pendingAuthAction {
            guard let pendingAuthAction else { return }
            beginAuth(pendingAuthAction)
            return
        }
        guard LoginInputPolicy.canSubmit(
            phone: phoneNumber,
            code: smsCode,
            phoneChannelEnabled: channels.phone,
            isLoading: isLoading
        ) else { return }
        let normalizedPhone = LoginInputPolicy.digits(phoneNumber, limit: 11)
        let normalizedCode = LoginInputPolicy.digits(smsCode, limit: 6)
        beginAuth(.phone(
            phone: normalizedPhone,
            code: normalizedCode,
            isDeveloper: LoginInputPolicy.isDeveloperCredentials(
                phone: normalizedPhone, code: normalizedCode
            )
        ))
    }

    private func handleThirdPartyAuth(provider: String) {
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        #endif
        guard !isLoading else { return }
        beginAuth(.oauth(provider: provider))
    }

    @MainActor
    private func loadAuthCapabilities() async {
        isCapabilityLoading = true
        capabilityMessage = nil
        defer { isCapabilityLoading = false }
        do {
            let capabilities = try await APIClient.shared.fetchAuthCapabilities()
            channels.apply(capabilities)
            if !channels.phone && !channels.alipay && !channels.wechat {
                capabilityMessage = "认证渠道未配置；开发登录待服务端更新。"
            } else if !channels.phone {
                capabilityMessage = "短信登录暂未开放，请使用已启用的第三方方式。"
            }
        } catch {
            channels = LoginChannelAvailability()
            capabilityMessage = "认证服务暂时不可用，请稍后重试。"
        }
    }

    @MainActor
    private func beginAuth(_ action: PendingAuthAction) {
        guard isCurrentAgreementAccepted else {
            pendingAuthAction = action
            showingAgreement = true
            if agreement == nil { Task { await loadAgreement(forcePresentation: true) } }
            return
        }
        pendingAuthAction = action
        isLoading = true
        errorMessage = nil
        Task { await executePendingAuth() }
    }

    @MainActor
    private func executePendingAuth() async {
        guard let action = pendingAuthAction else { return }
        do {
            switch action {
            case let .phone(phone, code, isDeveloper):
                let response: LoginSessionDTO
                if isDeveloper {
                    response = try await APIClient.shared.developerLogin(
                        phone: phone, verificationCode: code
                    )
                } else {
                    response = try await APIClient.shared.loginWithPhone(phone: phone, code: code)
                }
                pendingAuthAction = .authenticated(
                    response, isDeveloper: isDeveloper, idempotencyKey: UUID().uuidString
                )
                try await completeAuthenticatedLogin(
                    response, isDeveloper: isDeveloper,
                    idempotencyKey: authenticatedIdempotencyKey
                )
            case let .oauth(provider):
                let start = try await APIClient.shared.startOAuth(provider: provider)
                let ticket = try await oauthCoordinator.authenticate(
                    url: start.authorizationUrl, provider: provider
                )
                let response = try await APIClient.shared.completeOAuth(ticket: ticket)
                let key = UUID().uuidString
                pendingAuthAction = .authenticated(
                    response, isDeveloper: false, idempotencyKey: key
                )
                try await completeAuthenticatedLogin(
                    response, isDeveloper: false, idempotencyKey: key
                )
            case let .authenticated(response, isDeveloper, idempotencyKey):
                try await completeAuthenticatedLogin(
                    response, isDeveloper: isDeveloper, idempotencyKey: idempotencyKey
                )
            }
        } catch OAuthSessionCoordinatorError.cancelled {
            pendingAuthAction = nil
            isLoading = false
        } catch {
            isLoading = false
            errorMessage = LoginConsentPolicy.failureMessage(for: error)
        }
    }

    private var authenticatedIdempotencyKey: String {
        guard case let .authenticated(_, _, key) = pendingAuthAction else { return UUID().uuidString }
        return key
    }

    @MainActor
    private func completeAuthenticatedLogin(
        _ response: LoginSessionDTO,
        isDeveloper: Bool,
        idempotencyKey: String
    ) async throws {
        guard let version = acceptedAgreementVersion,
              version == agreement?.version else {
            throw APIError.authenticationRejected("请先阅读并同意当前有效的服务协议。")
        }
        guard APIClient.shared.saveToken(response.token) else {
            throw APIError.authenticationRejected("无法安全保存登录凭证，请重试")
        }
        do {
            _ = try await APIClient.shared.acceptAgreement(
                version: version, idempotencyKey: idempotencyKey
            )
        } catch {
            if let apiError = error as? APIError,
               case .server(409, _) = apiError {
                acceptedAgreementVersion = nil
                agreement = nil
                await loadAgreement(forcePresentation: true, allowCache: false)
            }
            // The JWT remains in Keychain: retrying agreement acceptance must not
            // repeat SMS verification or the external OAuth ceremony.
            throw error
        }
        let profile = try await APIClient.shared.fetchMe()
        appState.currentTenantKey = profile.tenantKey
        appState.currentUserId = profile.userId
        KnowledgeNoteStore.shared.activate(
            tenantKey: profile.tenantKey,
            userId: profile.userId
        )
        await KnowledgeNoteStore.shared.restoreFromCloud()
        appState.isDevMode = isDeveloper
        isLoading = false
        #if os(iOS)
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        #endif
        withAnimation(.spring()) {
            appState.isLoggedIn = true
            appState.isGuestMode = false
            let displayName = profile.username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                ? CuteDisplayNames.name(for: profile.userId)
                : profile.username
            appState.currentProfile = TenantProfile(
                id: profile.userId,
                name: displayName,
                tenantId: profile.tenantKey,
                role: .tenantMember,
                avatarUrl: profile.avatarUrl,
                concurrencyLimit: 5,
                tokenQuotaUsage: 0,
                isVipLane: false
            )
        }
        pendingAuthAction = nil
    }

    @MainActor
    private func loadAgreement(forcePresentation: Bool, allowCache: Bool = true) async {
        guard !isAgreementLoading else { return }
        isAgreementLoading = true
        agreementError = nil
        if forcePresentation { showingAgreement = true }
        defer { isAgreementLoading = false }
        do {
            let latest = try await APIClient.shared.fetchAgreement(allowCache: allowCache)
            if agreement?.version != latest.version { acceptedAgreementVersion = nil }
            agreement = latest
        } catch {
            agreement = nil
            agreementError = "协议暂时无法加载，请检查网络后重试。"
        }
    }

    private func acceptCurrentAgreement() {
        guard let version = agreement?.version else { return }
        acceptedAgreementVersion = version
        showingAgreement = false
        guard pendingAuthAction != nil else { return }
        isLoading = true
        Task { await executePendingAuth() }
    }

    private func agreementSheetDismissed() {
        guard !isCurrentAgreementAccepted else { return }
        if !isRetryingAgreementAcceptance { pendingAuthAction = nil }
        isLoading = false
    }
}

private enum OAuthSessionCoordinatorError: LocalizedError {
    case cancelled
    case invalidCallback
    case providerError(String)
    case alipayUnavailable
    case cannotOpenProvider

    var errorDescription: String? {
        switch self {
        case .cancelled: return "已取消授权"
        case .invalidCallback: return "登录回调无效"
        case .providerError(let code): return "第三方授权失败（\(code)）"
        case .alipayUnavailable: return "未检测到支付宝客户端，请先安装支付宝后重试"
        case .cannotOpenProvider: return "无法打开第三方授权客户端"
        }
    }
}

@MainActor
private final class OAuthSessionCoordinator: NSObject, ObservableObject,
    ASWebAuthenticationPresentationContextProviding
{
    private var session: ASWebAuthenticationSession?
    private var externalContinuation: CheckedContinuation<String, Error>?

    func authenticate(url: URL, provider: String) async throws -> String {
        if provider == "alipay" {
            return try await authenticateInAlipay(url: url)
        }
        return try await authenticateInWebSession(url: url)
    }

    func handleCallback(_ url: URL) {
        guard let continuation = externalContinuation else { return }
        externalContinuation = nil
        do {
            continuation.resume(returning: try ticket(from: url))
        } catch {
            continuation.resume(throwing: error)
        }
    }

    private func authenticateInWebSession(url: URL) async throws -> String {
        try await withCheckedThrowingContinuation { continuation in
            let session = ASWebAuthenticationSession(
                url: url,
                callbackURLScheme: "quantum"
            ) { [weak self] callbackURL, error in
                defer { self?.session = nil }
                if let authError = error as? ASWebAuthenticationSessionError,
                   authError.code == .canceledLogin {
                    continuation.resume(throwing: OAuthSessionCoordinatorError.cancelled)
                    return
                }
                guard let callbackURL else {
                    continuation.resume(throwing: error ?? OAuthSessionCoordinatorError.invalidCallback)
                    return
                }
                do {
                    guard let self else {
                        throw OAuthSessionCoordinatorError.invalidCallback
                    }
                    continuation.resume(returning: try self.ticket(from: callbackURL))
                } catch {
                    continuation.resume(throwing: error)
                }
            }
            session.presentationContextProvider = self
            session.prefersEphemeralWebBrowserSession = true
            self.session = session
            if !session.start() {
                self.session = nil
                continuation.resume(throwing: OAuthSessionCoordinatorError.invalidCallback)
            }
        }
    }

    private func authenticateInAlipay(url: URL) async throws -> String {
        guard let deepLink = alipayDeepLink(for: url),
              UIApplication.shared.canOpenURL(deepLink) else {
            throw OAuthSessionCoordinatorError.alipayUnavailable
        }
        return try await withCheckedThrowingContinuation { continuation in
            externalContinuation = continuation
            UIApplication.shared.open(deepLink, options: [:]) { [weak self] opened in
                guard !opened, let self,
                      let continuation = self.externalContinuation else { return }
                self.externalContinuation = nil
                continuation.resume(throwing: OAuthSessionCoordinatorError.cannotOpenProvider)
            }
        }
    }

    private func alipayDeepLink(for authorizationURL: URL) -> URL? {
        // 20000067 是支付宝官方“打开 URL”容器，不是商户 appId；
        // 商户、redirect_uri、state 等真实授权参数仍完整使用后端返回值。
        var components = URLComponents()
        components.scheme = "alipays"
        components.host = "platformapi"
        components.path = "/startapp"
        components.queryItems = [
            URLQueryItem(name: "appId", value: "20000067"),
            URLQueryItem(name: "url", value: authorizationURL.absoluteString),
        ]
        return components.url
    }

    private func ticket(from callbackURL: URL) throws -> String {
        guard callbackURL.scheme?.lowercased() == "quantum",
              callbackURL.host?.lowercased() == "oauth",
              callbackURL.path == "/callback",
              let components = URLComponents(url: callbackURL, resolvingAgainstBaseURL: false)
        else {
            throw OAuthSessionCoordinatorError.invalidCallback
        }
        if let providerError = components.queryItems?
            .first(where: { $0.name == "oauth_error" })?.value,
           !providerError.isEmpty {
            throw OAuthSessionCoordinatorError.providerError(providerError)
        }
        guard let ticket = components.queryItems?
            .first(where: { $0.name == "oauth_ticket" })?.value,
              !ticket.isEmpty else {
            throw OAuthSessionCoordinatorError.invalidCallback
        }
        return ticket
    }

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        return scenes.flatMap(\.windows).first(where: \.isKeyWindow) ?? ASPresentationAnchor()
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
}
