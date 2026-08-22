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

                Section("历史会话") {
                    ForEach(sessionManager.sortedSessionIDs(), id: \.self) { id in
                        Button {
                            onSelect(id)
                        } label: {
                            SessionRow(
                                title: sessionManager.title(for: id),
                                messageCount: sessionManager.messageCount(for: id),
                                updatedAt: sessionManager.sessionUpdatedAt[id] ?? .distantPast,
                                isActive: sessionManager.activeSessionId == id
                            )
                        }
                        .buttonStyle(SoftButtonStyle())
                        .swipeActions {
                            Button(role: .destructive) {
                                onDelete(id)
                            } label: {
                                Label("删除", systemImage: "trash")
                            }
                        }
                    }
                }
            }
            .navigationTitle("会话")
            .navigationBarTitleDisplayMode(.inline)
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

    public init(title: String, messageCount: Int, updatedAt: Date, isActive: Bool) {
        self.title = title
        self.messageCount = messageCount
        self.updatedAt = updatedAt
        self.isActive = isActive
    }

    public var body: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            VStack(alignment: .leading, spacing: 3) {
                Text(title.isEmpty ? "新会话" : title)
                    .font(.system(size: 14, weight: isActive ? .bold : .medium))
                    .foregroundColor(isActive ? AppTheme.Colors.primary : AppTheme.Colors.textPrimary)
                    .lineLimit(1)
                Text("\(messageCount) 条消息 · \(relativeTime(updatedAt))")
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
