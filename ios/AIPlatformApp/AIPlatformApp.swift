//
//  AIPlatformApp.swift
//  AIPlatformApp
//
//  Application Main Lifecycle Entry Point & AppRoot Navigation Coordinator
//  Swift 6 / iOS 17+ Standard App Entry
//

import SwiftUI

@main
public struct AIPlatformApp: App {
    @StateObject private var appState: AppState
    @StateObject private var apiClient = APIClient.shared
    @StateObject private var workflowActivities = WorkflowActivityCoordinator.shared
    // Start metadata recovery and legacy JSON migration independently of authentication/chat navigation.
    @StateObject private var sessionManager = SessionManager.shared
    #if DEBUG
    private let showBookshelfPreview: Bool
    private let showKnowledgeHomePreview: Bool
    private let showTabBarPreview: Bool
    #endif

    public init() {
        let arguments = ProcessInfo.processInfo.arguments
        let hasPersistedSession = !(KeychainStore.load() ?? "").isEmpty
#if DEBUG
        let hasE2EToken = !(ProcessInfo.processInfo.environment["AI_LAB_E2E_TOKEN"] ?? "").isEmpty
        showBookshelfPreview = arguments.contains("-bookshelfPreview")
        showKnowledgeHomePreview = arguments.contains("-knowledgeHomePreview")
        showTabBarPreview = arguments.contains("-tabBarPreview")
#else
        let hasE2EToken = false
#endif
        let initialState = AppState(
            isLoggedIn: arguments.contains("-autoLogin") || hasPersistedSession || hasE2EToken,
            activeTab: arguments.contains("-knowledgeTab") ? 2 : 0
        )
#if DEBUG
        initialState.pendingChatPrompt = ProcessInfo.processInfo.environment["AI_LAB_E2E_PROMPT"]
#endif
        _appState = StateObject(wrappedValue: initialState)
    }

    public var body: some Scene {
        WindowGroup {
            Group {
                #if DEBUG
                if showBookshelfPreview {
                    BookshelfPreviewHost()
                } else if showKnowledgeHomePreview {
                    KnowledgeView()
                } else if showTabBarPreview {
                    MainTabView()
                } else {
                    AppRootCoordinatorView()
                }
                #else
                AppRootCoordinatorView()
                #endif
            }
                .environmentObject(appState)
                .environmentObject(apiClient)
                .environmentObject(workflowActivities)
                .environmentObject(sessionManager)
        }
    }
}

#if DEBUG
private struct BookshelfPreviewHost: View {
    @State private var showingBookshelf = true
    private let center = ProcessInfo.processInfo.arguments.contains("-bookshelfSourcePreview")
        ? SubscriptionCenterResponse.sourcePreview
        : .bookshelfPreview

    var body: some View {
        if showingBookshelf {
            NavigationStack {
                SubscriptionCenterView(
                    previewCenter: center,
                    onBack: { showingBookshelf = false }
                )
            }
        } else {
            KnowledgeView()
        }
    }
}
#endif

// MARK: - App Root Coordinator
public struct AppRootCoordinatorView: View {
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var apiClient: APIClient
    @EnvironmentObject private var workflowActivities: WorkflowActivityCoordinator
    @Environment(\.scenePhase) private var scenePhase
    @State private var agreement: AgreementDTO?
    @State private var agreementError: String?
    @State private var isAgreementLoading = false
    @State private var showingAgreement = false
    @State private var isAgreementAccepting = false
    @State private var agreementAcceptanceKey = UUID().uuidString

    public var body: some View {
        Group {
            if appState.isLoggedIn {
                MainTabView()
                    .transition(.opacity.combined(with: .scale(scale: 0.98)))
            } else {
                LoginView()
                    .transition(.opacity)
            }
        }
        // 统一覆盖未声明局部样式的 Button / NavigationLink / Toolbar 入口。
        .buttonStyle(SoftButtonStyle())
        .animation(.easeInOut(duration: 0.3), value: appState.isLoggedIn)
        .overlay {
            if showingAgreement {
                AppTheme.Colors.scrim
                    .ignoresSafeArea()
                    .contentShape(Rectangle())
                    .onTapGesture {}
                    .accessibilityHidden(true)
            }
        }
        .onChange(of: apiClient.needsReauth) { _, needs in
            if needs {
                apiClient.needsReauth = false
                if !appState.isGuestMode {
                    // 真实登录态的 401 才代表凭证失效。游客访问受保护能力时应由
                    // 当前页面展示受限/演示状态，不能把游客模式误踢回登录页。
                    apiClient.clearToken()
                    appState.logout()
                }
            }
        }
        .onChange(of: apiClient.requiredAgreementVersion) { _, version in
            guard version != nil else { return }
            agreement = nil
            agreementAcceptanceKey = UUID().uuidString
            showingAgreement = true
            Task { await loadRequiredAgreement() }
        }
        .sheet(isPresented: $showingAgreement, onDismiss: {
            if apiClient.requiredAgreementVersion != nil {
                apiClient.resolveAgreementRequirement(accepted: false)
            }
        }) {
            AgreementSheet(
                agreement: agreement,
                isLoading: isAgreementLoading,
                isAccepting: isAgreementAccepting,
                errorMessage: agreementError,
                onRetry: { Task { await loadRequiredAgreement() } },
                onAccept: { Task { await acceptRequiredAgreement() } }
            )
            .presentationDetents([.medium, .large])
            .presentationDragIndicator(.visible)
            .presentationBackground(AppTheme.Colors.cardBackground)
            .presentationBackgroundInteraction(.disabled)
        }
        .task(id: appState.isLoggedIn) {
            if appState.isLoggedIn {
                await restorePersistedSession()
                if appState.isLoggedIn { await workflowActivities.bootstrap() }
            }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active {
                Task { await workflowActivities.resumeFromForeground() }
            } else if phase == .background {
                workflowActivities.pauseForBackground()
            }
        }
    }

    /// Keychain 是进程重启后的登录态真值；`/me` 继续沿用现有 Bearer JWT
    /// 契约恢复租户资料。瞬时网络失败不清除本地会话，401 则由统一重登链路处理。
    @MainActor
    private func restorePersistedSession() async {
        guard let token = apiClient.currentToken(), !token.isEmpty else { return }
        do {
            let profile = try await apiClient.fetchMe()
            let displayName = profile.username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                ? CuteDisplayNames.name(for: profile.userId)
                : profile.username
            appState.currentTenantKey = profile.tenantKey
            appState.currentUserId = profile.userId
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
            appState.isGuestMode = false
            KnowledgeNoteStore.shared.activate(
                tenantKey: profile.tenantKey,
                userId: profile.userId
            )
            await KnowledgeNoteStore.shared.restoreFromCloud()
        } catch {
            // APIClient 会把真实 401 汇入 needsReauth；离线/超时保留 Keychain 登录态。
        }
    }

    @MainActor
    private func loadRequiredAgreement() async {
        guard !isAgreementLoading else { return }
        isAgreementLoading = true
        agreementError = nil
        defer { isAgreementLoading = false }
        do {
            let loaded = try await apiClient.fetchAgreement()
            guard loaded.version == apiClient.requiredAgreementVersion else {
                throw APIError.authenticationRejected("协议版本已更新，请重新加载。")
            }
            agreement = loaded
        } catch {
            agreement = nil
            agreementError = "协议暂时无法加载，请检查网络后重试。"
        }
    }

    @MainActor
    private func acceptRequiredAgreement() async {
        guard !isAgreementAccepting, let agreement,
              agreement.version == apiClient.requiredAgreementVersion else { return }
        isAgreementAccepting = true
        defer { isAgreementAccepting = false }
        do {
            _ = try await apiClient.acceptAgreement(
                version: agreement.version, idempotencyKey: agreementAcceptanceKey
            )
            apiClient.resolveAgreementRequirement(accepted: true)
            showingAgreement = false
        } catch {
            agreementError = "协议确认未完成，请重试。"
        }
    }
}

// MARK: - Xcode #Preview

#Preview("AppRoot - Logged Out") {
    AppRootCoordinatorView()
        .environmentObject(AppState(isLoggedIn: false))
        .environmentObject(APIClient.shared)
}

#Preview("AppRoot - Logged In") {
    AppRootCoordinatorView()
        .environmentObject(AppState(isLoggedIn: true))
        .environmentObject(APIClient.shared)
}
