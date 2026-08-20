//
//  ChatView.swift
//  AIPlatformApp
//
//  Microkernel Canvas for iOS Agent Chat (DeepSeek Harness Pattern)
//  Governed footprint (<= 200 lines), zero business clutter, pure declarative UI.
//

import SwiftUI

public struct ChatView: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var coordinator = TenantSessionCoordinator()
    @StateObject private var speechService = SpeechRecognizerService()

    @State private var isShowingClearAlert: Bool = false
    @State private var showingVoiceInput: Bool = false
    @State private var showingPlusMenu: Bool = false
    @State private var showingSessionDrawer: Bool = false
    @State private var showingAgentPicker: Bool = false
    @State private var tenantAgents: [TenantAgentDTO] = []

    private let waitingTimer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    public init() {}

    public var body: some View {
        NavigationStack {
            ZStack {
                if coordinator.messages.isEmpty {
                    QuantumMistBackground()
                } else {
                    QuantumMistBackground()
                }

                VStack(spacing: 0) {
                    ChatTopBarView(
                        isGenerating: coordinator.isGenerating,
                        title: coordinator.sessionManager.title(for: coordinator.sessionManager.activeSessionID()),
                        agentName: appState.selectedAgentName,
                        onTitleTap: { showingSessionDrawer = true },
                        onAgentTap: { showingAgentPicker = true },
                        onNewSession: { coordinator.newSession() },
                        onHistoryTap: { showingSessionDrawer = true },
                        onClearTap: { isShowingClearAlert = true }
                    )
                    ChatMessageStreamView(coordinator: coordinator)
                    ChatInputBar(
                        inputText: $coordinator.inputText,
                        quotedContext: $coordinator.quotedContext,
                        isGenerating: coordinator.isGenerating,
                        onSend: { coordinator.sendMessage() },
                        onVoiceTap: { showingVoiceInput = true },
                        onPlusTap: { showingPlusMenu = true }
                    )
                }
            }
            .navigationTitle("")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar(.hidden, for: .navigationBar)
            .alert("清空当前对话？", isPresented: $isShowingClearAlert) {
                Button("取消", role: .cancel) {}
                Button("清空", role: .destructive) { coordinator.clearCurrentSession() }
            } message: {
                Text("此操作将清空当前会话所有消息记录。")
            }
            .overlay(alignment: .bottom) { toastOverlay }
            .animation(.easeInOut(duration: 0.2), value: coordinator.toastMessage)
            .sheet(isPresented: $showingVoiceInput) {
                VoiceInputView(
                    service: speechService,
                    onTranscript: { text in coordinator.inputText = text },
                    onDismiss: { showingVoiceInput = false }
                )
            }
            .sheet(isPresented: $showingPlusMenu) {
                PlusMenuSheet(
                    onPhotoPicked: { data in coordinator.attachPhoto(data) },
                    onDocumentPicked: { url in coordinator.attachDocument(url) },
                    onWeChatImported: { link in coordinator.importWeChatLink(link) },
                    onKnowledgeReferenced: { item in coordinator.referenceKnowledge(item) }
                )
            }
            .sheet(isPresented: $showingSessionDrawer) {
                SessionDrawerSheet(
                    sessionManager: coordinator.sessionManager,
                    onSelect: { id in
                        coordinator.switchSession(to: id)
                        showingSessionDrawer = false
                    },
                    onNew: {
                        coordinator.newSession()
                        showingSessionDrawer = false
                    },
                    onDelete: { id in coordinator.deleteSession(id) }
                )
            }
            .sheet(isPresented: $showingAgentPicker) {
                ChatAgentPickerSheet(
                    tenantAgents: tenantAgents,
                    selectedAgentId: appState.selectedAgentId,
                    onSelect: { id, name in
                        showingAgentPicker = false
                        appState.openChat(agentId: id, agentName: name)
                        coordinator.handlePendingAgent()
                    }
                )
            }
            .onAppear {
                coordinator.appState = appState
                coordinator.restoreActiveSession()
                coordinator.refreshQuickCommands()
                coordinator.handlePendingAgent()
                coordinator.handlePendingPrompt()
            }
            .task { await refreshAgents() }
            .onReceive(NotificationCenter.default.publisher(for: .tenantAgentsDidUpdate)) { _ in
                Task { await refreshAgents() }
            }
            .onChange(of: appState.pendingChatAgent?.id) { _, _ in
                coordinator.handlePendingAgent()
            }
            .onChange(of: appState.pendingChatPrompt) { _, _ in coordinator.handlePendingPrompt() }
            .onReceive(waitingTimer) { _ in coordinator.tickWaitingTimer() }
            .onChange(of: scenePhase) { _, phase in
                if phase == .active { InboxFileManager.shared.cleanupStaleInboxFiles() }
            }
        }
    }

    @MainActor
    private func refreshAgents() async {
        do {
            tenantAgents = try await APIClient.shared.fetchTenantAgents().filter(\.isActive)
            let baseline = ["main_agent", "supervision", "coder", "knowledge"]
            if !baseline.contains(appState.selectedAgentId),
               !tenantAgents.contains(where: { $0.id == appState.selectedAgentId }) {
                appState.openChat(agentId: "main_agent", agentName: "Main 智能编排")
                coordinator.handlePendingAgent()
                coordinator.showToast("原 Agent 已停用或不可访问，已切换到 Main Agent")
            }
        } catch {
            coordinator.showToast("Agent 列表加载失败，保留当前会话")
        }
    }

    @ViewBuilder
    private var toastOverlay: some View {
        if let toast = coordinator.toastMessage {
            Text(toast)
                .font(AppTheme.Typography.supporting.weight(.medium))
                .foregroundColor(AppTheme.Colors.onPrimary)
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, 8)
                .background(AppTheme.Colors.interactiveBlue)
                .clipShape(Capsule())
                .shadow(color: AppTheme.Colors.auroraBlue.opacity(0.22), radius: 12, y: 5)
                .transition(.move(edge: .bottom).combined(with: .opacity))
                .padding(.bottom, 90)
        }
    }
}

private struct ChatAgentPickerSheet: View {
    let tenantAgents: [TenantAgentDTO]
    let selectedAgentId: String
    let onSelect: (String, String) -> Void
    @Environment(\.dismiss) private var dismiss

    private let baseline: [(String, String)] = [
        ("main_agent", "Main 智能编排"),
        ("supervision", "Supervision 架构审查"),
        ("coder", "Coder 独立开发"),
        ("knowledge", "知识星海"),
    ]

    var body: some View {
        NavigationStack {
            List {
                Section("平台 Agent") {
                    ForEach(baseline, id: \.0) { item in
                        agentRow(id: item.0, name: item.1, detail: "平台基线 Agent")
                    }
                }
                if !tenantAgents.isEmpty {
                    Section("我的专属 Agent") {
                        ForEach(tenantAgents) { agent in
                            agentRow(
                                id: agent.id,
                                name: agent.customName ?? "专属 Agent",
                                detail: agent.visibility == "private" ? "仅自己可见" : "租户可见"
                            )
                        }
                    }
                }
            }
            .navigationTitle("选择 Agent")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
            }
        }
    }

    private func agentRow(id: String, name: String, detail: String) -> some View {
        Button {
            onSelect(id, name)
        } label: {
            HStack(spacing: AppTheme.Spacing.md) {
                Image(systemName: id == "main_agent" ? "sparkles" : "person.crop.circle.badge.checkmark")
                    .foregroundColor(AppTheme.Colors.quantumBlue)
                VStack(alignment: .leading, spacing: 2) {
                    Text(name).foregroundColor(AppTheme.Colors.textPrimary)
                    Text(detail)
                        .font(AppTheme.Typography.micro)
                        .foregroundColor(AppTheme.Colors.textSecondary)
                }
                Spacer()
                if id == selectedAgentId {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(AppTheme.Colors.quantumBlue)
                }
            }
        }
    }
}
