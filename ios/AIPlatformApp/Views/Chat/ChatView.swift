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

    private let waitingTimer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    public init() {}

    public var body: some View {
        NavigationStack {
            ZStack {
                AppTheme.Colors.groupedBackground
                    .ignoresSafeArea()

                VStack(spacing: 0) {
                    ChatTopBarView(
                        isGenerating: coordinator.isGenerating,
                        title: coordinator.sessionManager.title(for: coordinator.sessionManager.activeSessionID()),
                        onTitleTap: { showingSessionDrawer = true },
                        onNewSession: { coordinator.newSession() },
                        onHistoryTap: { showingSessionDrawer = true }
                    )
                    Divider().background(AppTheme.Colors.border)
                    ChatMessageStreamView(coordinator: coordinator)
                    ChatInputBar(
                        inputText: $coordinator.inputText,
                        quotedContext: $coordinator.quotedContext,
                        quickCommands: coordinator.quickCommands,
                        isGenerating: coordinator.isGenerating,
                        onSend: { coordinator.sendMessage() },
                        onVoiceTap: { showingVoiceInput = true },
                        onPlusTap: { showingPlusMenu = true },
                        onCommandSelected: { chip in coordinator.selectCommand(chip) }
                    )
                }
            }
            .navigationTitle("")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: { isShowingClearAlert = true }) {
                        Image(systemName: "trash")
                            .font(.system(size: 14))
                            .foregroundColor(AppTheme.Colors.textSecondary)
                    }
                }
            }
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
            .onAppear {
                coordinator.appState = appState
                coordinator.restoreActiveSession()
                coordinator.refreshQuickCommands()
                coordinator.handlePendingPrompt()
            }
            .onChange(of: appState.pendingChatPrompt) { _, _ in coordinator.handlePendingPrompt() }
            .onReceive(waitingTimer) { _ in coordinator.tickWaitingTimer() }
            .onChange(of: scenePhase) { _, phase in
                if phase == .active { InboxFileManager.shared.cleanupStaleInboxFiles() }
            }
        }
    }

    @ViewBuilder
    private var toastOverlay: some View {
        if let toast = coordinator.toastMessage {
            Text(toast)
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(AppTheme.Colors.onPrimary)
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, 8)
                .background(AppTheme.Colors.quantumBlue)
                .clipShape(Capsule())
                .shadow(radius: 8)
                .transition(.move(edge: .bottom).combined(with: .opacity))
                .padding(.bottom, 90)
        }
    }
}
