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
    @StateObject private var appState = AppState(isLoggedIn: ProcessInfo.processInfo.arguments.contains("-autoLogin"))
    @StateObject private var apiClient = APIClient.shared
    @StateObject private var workflowActivities = WorkflowActivityCoordinator.shared

    public init() {}

    public var body: some Scene {
        WindowGroup {
            AppRootCoordinatorView()
                .environmentObject(appState)
                .environmentObject(apiClient)
                .environmentObject(workflowActivities)
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
            if appState.isLoggedIn { await workflowActivities.bootstrap() }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active {
                Task { await workflowActivities.resumeFromForeground() }
            } else if phase == .background {
                workflowActivities.pauseForBackground()
            }
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
