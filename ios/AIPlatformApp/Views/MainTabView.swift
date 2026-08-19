//
//  MainTabView.swift
//  AIPlatformApp
//
//  Native iOS Bottom TabBar Navigation Container
//  Standard HIG Navigation Architecture with Smooth State Switching
//  + 开发态「开发模式·免鉴权」Quantum 蓝细 banner（顶部导航栏下）
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

            // Tab 2: 可执行工作流（拓扑从任务页按需打开）
            WorkflowDashboardView()
                .tabItem {
                    Label("任务", systemImage: "square.grid.2x2.fill")
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
        .toolbar(.hidden, for: .tabBar)
        .safeAreaInset(edge: .bottom, spacing: 18) {
            QuantumFloatingTabBar(selection: $appState.activeTab)
        }
        .safeAreaInset(edge: .top, spacing: 0) {
            if appState.isDevMode {
                DevModeBanner()
                    .transition(.move(edge: .top).combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.25), value: appState.isDevMode)
    }
}

private struct QuantumFloatingTabBar: View {
    @Binding var selection: Int
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private let items: [(title: String, symbol: String, selectedSymbol: String)] = [
        ("对话", "bubble.left.and.bubble.right", "bubble.left.and.bubble.right.fill"),
        ("任务", "square.grid.2x2", "square.grid.2x2.fill"),
        ("知识", "books.vertical", "books.vertical.fill"),
        ("设置", "gearshape", "gearshape.fill")
    ]

    var body: some View {
        HStack(spacing: AppTheme.Spacing.xs) {
            ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                Button {
                    guard selection != index else { return }
                    #if os(iOS)
                    UISelectionFeedbackGenerator().selectionChanged()
                    #endif
                    if reduceMotion {
                        selection = index
                    } else {
                        withAnimation(AppTheme.Motion.spring) { selection = index }
                    }
                } label: {
                    VStack(spacing: 3) {
                        Image(systemName: selection == index ? item.selectedSymbol : item.symbol)
                            .font(.system(size: 18, weight: .semibold))
                            .frame(height: 22)
                        Text(item.title)
                            .font(.caption2.weight(selection == index ? .bold : .medium))
                    }
                    .foregroundStyle(selection == index ? AppTheme.Colors.primary : AppTheme.Icons.navigationInactive)
                    .frame(maxWidth: .infinity, minHeight: 52)
                    .background {
                        if selection == index {
                            RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                                .fill(AppTheme.Colors.selectionTint)
                                .overlay {
                                    RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                                        .stroke(AppTheme.Colors.border.opacity(0.8), lineWidth: 0.75)
                                }
                        }
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(SoftButtonStyle())
                .accessibilityLabel(item.title)
                .accessibilityAddTraits(selection == index ? .isSelected : [])
            }
        }
        .padding(6)
        .frame(height: AppTheme.Metrics.floatingTabBarHeight)
        .background(.ultraThinMaterial)
        .background(AppTheme.Colors.surfaceElevated.opacity(0.92))
        .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .stroke(AppTheme.Colors.border.opacity(0.9), lineWidth: 0.75)
        }
        .shadow(color: Color(hex: "6B5A8A").opacity(0.14), radius: 24, y: 10)
        .padding(.horizontal, AppTheme.Spacing.lg)
        .padding(.top, AppTheme.Spacing.sm)
        .padding(.bottom, AppTheme.Spacing.xs)
        .background(AppTheme.Colors.background.opacity(0.96))
        .offset(y: 14)
    }
}

// MARK: - 开发模式·免鉴权 提示 banner（Quantum 蓝细窄条 · 小号白字）

public struct DevModeBanner: View {
    public init() {}

    public var body: some View {
        HStack(spacing: AppTheme.Spacing.xs) {
            Image(systemName: "shield.lefthalf.filled.badge.checkmark")
                .font(.caption2.weight(.semibold))
            Text("开发模式·免鉴权")
                .font(AppTheme.Typography.micro)
        }
        .foregroundColor(AppTheme.Icons.onAccent)
        .frame(maxWidth: .infinity)
        .padding(.vertical, 5)
        .background(AppTheme.Colors.quantumGradient)
        .accessibilityElement(children: .combine)
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
