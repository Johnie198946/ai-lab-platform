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
    @EnvironmentObject private var workflowActivities: WorkflowActivityCoordinator

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

            // Tab 3: local-first Markdown notes workspace
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
            VStack(spacing: AppTheme.Spacing.xs) {
                if let activity = workflowActivities.primaryActivity {
                    WorkflowActivityMiniBar(
                        activity: activity,
                        count: workflowActivities.visibleActivities.count,
                        onOpen: {
                            appState.pendingWorkflowId = activity.workflow.id
                            appState.activeTab = 1
                        },
                        onDismiss: {
                            workflowActivities.dismiss(activity.workflow.id)
                        }
                    )
                    .padding(.horizontal, AppTheme.Spacing.lg)
                } else if let activity = workflowActivities.primaryExecutionActivity {
                    WorkflowExecutionMiniBar(
                        activity: activity,
                        count: workflowActivities.visibleExecutionActivities.count,
                        onOpen: {
                            appState.pendingWorkflowId = activity.workflow.id
                            appState.activeTab = 1
                        },
                        onDismiss: { workflowActivities.dismiss(activity.workflow.id) }
                    )
                    .padding(.horizontal, AppTheme.Spacing.lg)
                }
                QuantumFloatingTabBar(selection: $appState.activeTab)
            }
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

private struct WorkflowExecutionMiniBar: View {
    let activity: WorkflowActivityCoordinator.ExecutionActivity
    let count: Int
    let onOpen: () -> Void
    let onDismiss: () -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var running: Bool { ["queued", "running"].contains(activity.execution.status) }
    private var statusText: String {
        switch activity.execution.status {
        case "queued": return "云端排队中"
        case "running": return "云端执行中 · \(activity.execution.progress)% · \(activity.execution.tokenUsed) tokens"
        case "awaiting_review": return "执行完成，待复核"
        case "failed": return "执行失败，点击查看或重试"
        default: return activity.execution.status
        }
    }

    var body: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Button(action: onOpen) {
                HStack(spacing: AppTheme.Spacing.sm) {
                    Image(systemName: running ? "gearshape.2.fill" : "checkmark.doc")
                        .foregroundStyle(AppTheme.Colors.quantumBlue)
                        .symbolEffect(.pulse, isActive: running && !reduceMotion)
                        .frame(width: 36, height: 36)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(count > 1 ? "\(activity.workflow.title) · 另有 \(count - 1) 项" : activity.workflow.title)
                            .font(AppTheme.Typography.supporting.weight(.semibold)).lineLimit(1)
                        Text(statusText).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary).lineLimit(1)
                    }
                    Spacer(minLength: 0)
                    if running { ProgressView().controlSize(.small) }
                    else { Image(systemName: "chevron.right").font(.caption.weight(.semibold)) }
                }
                .frame(maxWidth: .infinity, minHeight: 48)
                .contentShape(Rectangle())
            }
            .buttonStyle(SoftButtonStyle())
            .accessibilityLabel("\(activity.workflow.title)，\(statusText)")
            if !running {
                Button(action: onDismiss) { Image(systemName: "xmark").frame(width: 44, height: 44) }
                    .buttonStyle(SoftButtonStyle())
                    .accessibilityLabel("关闭任务状态")
            }
        }
        .padding(.horizontal, AppTheme.Spacing.sm)
        .background(.ultraThinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        .pressBorderGlow(cornerRadius: AppTheme.Radius.lg)
    }
}

private struct WorkflowActivityMiniBar: View {
    let activity: WorkflowActivityCoordinator.Activity
    let count: Int
    let onOpen: () -> Void
    let onDismiss: () -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var isRunning: Bool {
        ["planning", "building_agent"].contains(activity.model.phase)
    }

    private var statusText: String {
        if activity.model.phase == "awaiting_approval" { return "方案可审阅" }
        if activity.model.phase == "needs_attention" { return "规划需要处理" }
        if let message = activity.model.events.last?.message { return message }
        return activity.model.optimisticPlanningMessage ?? "云端正在准备规划"
    }

    var body: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Button(action: onOpen) {
                HStack(spacing: AppTheme.Spacing.sm) {
                    ZStack {
                        Circle()
                            .fill(AppTheme.Colors.selectionTint)
                            .frame(width: 36, height: 36)
                        Image(systemName: isRunning ? "sparkles" : "doc.text.magnifyingglass")
                            .foregroundStyle(AppTheme.Colors.quantumBlue)
                            .symbolEffect(.pulse, isActive: isRunning && !reduceMotion)
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        Text(count > 1 ? "\(activity.workflow.title) · 另有 \(count - 1) 项" : activity.workflow.title)
                            .font(AppTheme.Typography.supporting.weight(.semibold))
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                            .lineLimit(1)
                        Text(statusText)
                            .font(AppTheme.Typography.micro)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                            .lineLimit(1)
                    }
                    Spacer(minLength: 0)
                    if isRunning {
                        ProgressView().controlSize(.small)
                    } else {
                        Image(systemName: "chevron.right")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(AppTheme.Colors.textTertiary)
                    }
                }
                .contentShape(Rectangle())
                .frame(maxWidth: .infinity, minHeight: 48)
            }
            .buttonStyle(SoftButtonStyle())
            .accessibilityLabel("\(activity.workflow.title)，\(statusText)")
            .accessibilityHint("返回任务查看规划进度")

            if !isRunning {
                Button(action: onDismiss) {
                    Image(systemName: "xmark")
                        .font(.caption.weight(.semibold))
                        .frame(width: 44, height: 44)
                }
                .buttonStyle(SoftButtonStyle())
                .accessibilityLabel("关闭任务状态")
            }
        }
        .padding(.horizontal, AppTheme.Spacing.sm)
        .background(.ultraThinMaterial)
        .background(AppTheme.Colors.surfaceElevated.opacity(0.94))
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                .stroke(AppTheme.Colors.border.opacity(0.9), lineWidth: 0.75)
        }
        .pressBorderGlow(cornerRadius: AppTheme.Radius.lg)
        .shadow(color: Color.black.opacity(0.08), radius: 14, y: 6)
        .transition(reduceMotion ? .opacity : .move(edge: .bottom).combined(with: .opacity))
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
