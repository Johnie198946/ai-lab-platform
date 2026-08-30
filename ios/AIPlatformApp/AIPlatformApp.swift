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

    public init() {
        let arguments = ProcessInfo.processInfo.arguments
        let hasPersistedSession = !(KeychainStore.load() ?? "").isEmpty
        _appState = StateObject(wrappedValue: AppState(
            isLoggedIn: arguments.contains("-autoLogin") || hasPersistedSession,
            activeTab: arguments.contains("-knowledgeTab") ? 2 : 0
        ))
    }

    public var body: some Scene {
        WindowGroup {
            AppRootCoordinatorView()
                .environmentObject(appState)
                .environmentObject(apiClient)
                .environmentObject(workflowActivities)
                .environmentObject(sessionManager)
                .preferredColorScheme(.light)
        }
    }
}

// MARK: - App Root Coordinator
public struct AppRootCoordinatorView: View {
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var apiClient: APIClient
    @EnvironmentObject private var workflowActivities: WorkflowActivityCoordinator
    @Environment(\.scenePhase) private var scenePhase

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
        } catch {
            // APIClient 会把真实 401 汇入 needsReauth；离线/超时保留 Keychain 登录态。
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
