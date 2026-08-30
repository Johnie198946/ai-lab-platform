//
//  SessionDrawerSheet.swift
//  AIPlatformApp
//
//  Session Management Drawer (New, Switch, Delete, Time Formatting)
//  Extracted from ChatView for modularity.
//

import SwiftUI

public struct SessionDrawerSheet: View {
    @ObservedObject public var sessionManager: SessionManager
    public let onSelect: (String) -> Void
    public let onNew: () -> Void
    public let onDelete: (String) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var lifecycle: SessionLifecycleStatus = .active
    @State private var searchText = ""
    @State private var pendingPermanentDelete: String?

    public init(
        sessionManager: SessionManager,
        onSelect: @escaping (String) -> Void,
        onNew: @escaping () -> Void,
        onDelete: @escaping (String) -> Void
    ) {
        self.sessionManager = sessionManager
        self.onSelect = onSelect
        self.onNew = onNew
        self.onDelete = onDelete
    }

    public var body: some View {
        NavigationStack {
            List {
                Section {
                    Button(action: onNew) {
                        Label("新建会话", systemImage: "square.and.pencil")
                    }
                }

                Picker("会话状态", selection: $lifecycle) {
                    Text("活跃").tag(SessionLifecycleStatus.active)
                    Text("归档").tag(SessionLifecycleStatus.archived)
                    Text("回收站").tag(SessionLifecycleStatus.trashed)
                }
                .pickerStyle(.segmented)

                Section(lifecycle == .active ? "历史会话" : lifecycle == .archived ? "已归档" : "可恢复会话") {
                    ForEach(sessionManager.sortedSessionIDs(status: lifecycle, query: searchText), id: \.self) { id in
                        Button {
                            if lifecycle == .active { onSelect(id) }
                        } label: {
                            SessionRow(
                                title: sessionManager.title(for: id),
                                messageCount: sessionManager.messageCount(for: id),
                                updatedAt: sessionManager.sessionUpdatedAt[id] ?? .distantPast,
                                isActive: lifecycle == .active && sessionManager.activeSessionId == id,
                                organized: sessionManager.sessionOrganizedAt[id] != nil
                            )
                        }
                        .buttonStyle(SoftButtonStyle())
                        .swipeActions {
                            if lifecycle == .active {
                                Button { sessionManager.setLifecycle(.archived, for: id) } label: {
                                    Label("归档", systemImage: "archivebox")
                                }
                                Button(role: .destructive) { sessionManager.setLifecycle(.trashed, for: id) } label: {
                                    Label("回收站", systemImage: "trash")
                                }
                            } else {
                                Button { sessionManager.setLifecycle(.active, for: id) } label: {
                                    Label("恢复", systemImage: "arrow.uturn.backward")
                                }
                                if lifecycle == .archived {
                                    Button(role: .destructive) { sessionManager.setLifecycle(.trashed, for: id) } label: {
                                        Label("回收站", systemImage: "trash")
                                    }
                                } else {
                                    Button(role: .destructive) { pendingPermanentDelete = id } label: {
                                        Label("永久删除", systemImage: "trash.slash")
                                    }
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("会话")
            .navigationBarTitleDisplayMode(.inline)
            .searchable(text: $searchText, prompt: "搜索标题或消息内容")
            .confirmationDialog(
                "永久删除这个会话？",
                isPresented: Binding(
                    get: { pendingPermanentDelete != nil },
                    set: { if !$0 { pendingPermanentDelete = nil } }
                ),
                titleVisibility: .visible
            ) {
                Button("永久删除", role: .destructive) {
                    if let id = pendingPermanentDelete { onDelete(id) }
                    pendingPermanentDelete = nil
                }
                Button("取消", role: .cancel) { pendingPermanentDelete = nil }
            } message: {
                Text("此操作无法撤销；关联笔记会保留，但来源原文将不可打开。")
            }
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("完成") { dismiss() }
                }
            }
        }
    }
}

public struct SessionRow: View {
    public let title: String
    public let messageCount: Int
    public let updatedAt: Date
    public let isActive: Bool
    public let organized: Bool

    public init(title: String, messageCount: Int, updatedAt: Date, isActive: Bool, organized: Bool = false) {
        self.title = title
        self.messageCount = messageCount
        self.updatedAt = updatedAt
        self.isActive = isActive
        self.organized = organized
    }

    public var body: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            VStack(alignment: .leading, spacing: 3) {
                Text(title.isEmpty ? "新会话" : title)
                    .font(.system(size: 14, weight: isActive ? .bold : .medium))
                    .foregroundColor(isActive ? AppTheme.Colors.primary : AppTheme.Colors.textPrimary)
                    .lineLimit(1)
                Text("\(messageCount) 条消息 · \(relativeTime(updatedAt))\(organized ? " · 已整理" : "")")
                    .font(.system(size: 11))
                    .foregroundColor(AppTheme.Colors.textTertiary)
            }
            Spacer()
            if isActive {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 14))
                                .foregroundColor(AppTheme.Icons.interactive)
            }
        }
        .padding(.vertical, 2)
    }

    private func relativeTime(_ date: Date) -> String {
        let s = Int(Date().timeIntervalSince(date))
        if s < 60 { return "刚刚" }
        if s < 3600 { return "\(s / 60) 分钟前" }
        if s < 86400 { return "\(s / 3600) 小时前" }
        let f = DateFormatter()
        f.dateFormat = "MM-dd HH:mm"
        return f.string(from: date)
    }
}
