//
//  MainTabView.swift
//  AIPlatformApp
//
//  Native iOS Bottom TabBar Navigation Container
//  Standard HIG Navigation Architecture with Smooth State Switching
//

import SwiftUI

public struct MainTabView: View {
    @EnvironmentObject private var appState: AppState
    
    public init() {}
    
    public var body: some View {
        TabView(selection: $appState.activeTab) {
            
            // Tab 1: Chat Stream & Multiturn Dialogues
            ChatView()
                .tabItem {
                    Label("对话", systemImage: "bubble.left.and.bubble.right.fill")
                }
                .tag(0)
            
            // Tab 2: Read-Only DAG Topology Canvas
            TopologyCanvasView()
                .tabItem {
                    Label("拓扑", systemImage: "point.3.connected.trianglepath.dotted")
                }
                .tag(1)
            
            // Tab 3: 知识两层（类目订阅 + 已订内容分组浏览）；仅改显示字符串，内部 .tag(2)/枚举不变
            KnowledgeView()
                .tabItem {
                    Label("知识", systemImage: "books.vertical.fill")
                }
                .tag(2)
            
            // Tab 4: Tenant Profile & Prompt Studio Settings
            SettingsView()
                .tabItem {
                    Label("设置", systemImage: "gearshape.fill")
                }
                .tag(3)
        }
        .tint(AppTheme.Colors.quantumBlue)
    }
}

// MARK: - Xcode #Preview

#Preview("MainTabView - Light") {
    MainTabView()
        .environmentObject(AppState())
}

#Preview("MainTabView - Dark") {
    MainTabView()
        .environmentObject(AppState())
        .preferredColorScheme(.dark)
}
