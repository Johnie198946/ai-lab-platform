//
//  KnowledgeView.swift
//  AIPlatformApp
//
//  Notion-like interface backed by an Obsidian-compatible local Markdown vault.
//

import SwiftUI
import UIKit

private let knowledgeRouteSeparator = "\u{001F}"

private func knowledgeRoute(noteID: String, anchor: String? = nil) -> String {
    guard let anchor, !anchor.isEmpty else { return noteID }
    return noteID + knowledgeRouteSeparator + anchor
}

private func knowledgeRouteParts(_ route: String) -> (noteID: String, anchor: String?) {
    let parts = route.split(separator: Character(knowledgeRouteSeparator), maxSplits: 1, omittingEmptySubsequences: false)
    return (String(parts[0]), parts.count == 2 ? String(parts[1]) : nil)
}

private func noteAnchorID(_ raw: String) -> String {
    "note-anchor:" + raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
}

private enum NoteScope: String, CaseIterable, Identifiable {
    case all = "全部"
    case pinned = "已置顶"
    case daily = "每日笔记"

    var id: String { rawValue }
}

private enum NoteEditorMode: String, CaseIterable, Identifiable {
    case edit = "编辑"
    case preview = "阅读"

    var id: String { rawValue }
}

public struct KnowledgeView: View {
    @EnvironmentObject private var appState: AppState
    @StateObject private var store = KnowledgeNoteStore.shared

    @State private var path: [String] = []
    @State private var searchText = ""
    @State private var scope: NoteScope = .all
    @State private var selectedTag: String?
    @State private var notePendingTrash: KnowledgeNote?
    @State private var showingTrashConfirmation = false
    @State private var showingArchive = false

    public init() {}

    private var visibleNotes: [KnowledgeNote] {
        store.search(searchText, tag: selectedTag).filter { note in
            switch scope {
            case .all: return true
            case .pinned: return note.isPinned
            case .daily: return note.isDailyNote
            }
        }
    }

    private var pinnedNotes: [KnowledgeNote] {
        visibleNotes.filter(\.isPinned)
    }

    private var recentNotes: [KnowledgeNote] {
        visibleNotes.filter { !$0.isPinned || scope != .all }
    }

    public var body: some View {
        NavigationStack(path: $path) {
            List {
                workspaceHeader
                archiveEntry
                quickActions

                if !store.allTags.isEmpty {
                    tagFilter
                }

                scopePicker

                if store.isLoading && store.notes.isEmpty {
                    loadingRow
                } else if visibleNotes.isEmpty {
                    emptyState
                } else {
                    if scope == .all && !pinnedNotes.isEmpty {
                        noteSection(title: "置顶", systemImage: "pin", notes: pinnedNotes)
                    }
                    noteSection(
                        title: scope == .all ? "最近笔记" : scope.rawValue,
                        systemImage: scope == .daily ? "calendar" : "clock",
                        notes: recentNotes
                    )
                }

            }
            .listStyle(.plain)
            .scrollContentBackground(.hidden)
            .background(AppTheme.Colors.cardBackground)
            .navigationTitle("笔记")
            .navigationBarTitleDisplayMode(.large)
            .searchable(
                text: $searchText,
                placement: .navigationBarDrawer(displayMode: .always),
                prompt: "搜索标题、正文和标签"
            )
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button {
                            createNote()
                        } label: {
                            Label("新建笔记", systemImage: "square.and.pencil")
                        }
                        Button {
                            openDailyNote()
                        } label: {
                            Label("打开每日笔记", systemImage: "calendar")
                        }
                    } label: {
                        Image(systemName: "plus")
                            .frame(width: AppTheme.Metrics.minimumTouchTarget, height: AppTheme.Metrics.minimumTouchTarget)
                    }
                    .accessibilityLabel("创建笔记")
                }
            }
            .refreshable {
                store.reload()
            }
            .navigationDestination(for: String.self) { route in
                let parts = knowledgeRouteParts(route)
                KnowledgeNoteEditor(noteID: parts.noteID, initialAnchor: parts.anchor)
            }
            .onOpenURL { url in
                guard url.scheme == "ailab-note", url.host == "open",
                      let components = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return }
                let values = Dictionary(uniqueKeysWithValues: (components.queryItems ?? []).map { ($0.name, $0.value ?? "") })
                let target = values["target"] ?? ""
                let current = values["current"] ?? ""
                let destination = target.isEmpty ? store.note(id: current) : store.note(matchingLink: target)
                if let destination {
                    let route = knowledgeRoute(noteID: destination.id, anchor: values["anchor"])
                    if path.last != route { path.append(route) }
                }
            }
            .confirmationDialog(
                "将“\(notePendingTrash?.title ?? "这篇笔记")”移到废纸篓？",
                isPresented: $showingTrashConfirmation,
                titleVisibility: .visible
            ) {
                Button("移到废纸篓", role: .destructive) {
                    if let notePendingTrash {
                        store.moveToTrash(id: notePendingTrash.id)
                    }
                    notePendingTrash = nil
                }
                Button("取消", role: .cancel) {
                    notePendingTrash = nil
                }
            } message: {
                Text("文件会保留在 KnowledgeVault/.trash 中，可通过文件工具恢复。")
            }
            .alert("笔记不可用", isPresented: Binding(
                get: { store.lastError != nil },
                set: { if !$0 { store.clearError() } }
            )) {
                Button("重新加载") { store.reload() }
                Button("关闭", role: .cancel) { store.clearError() }
            } message: {
                Text(store.lastError ?? "请稍后重试")
            }
            .task {
                await syncLocalNotes()
            }
            .sheet(isPresented: $showingArchive) {
                KnowledgeArchiveView()
            }
        }
    }

    private var archiveEntry: some View {
        Button {
            showingArchive = true
        } label: {
            HStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: "archivebox")
                Text("归档")
                Text("\(store.archivedNotes.count)")
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
            }
            .font(.footnote)
            .foregroundStyle(AppTheme.Colors.textTertiary)
            .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("归档笔记，\(store.archivedNotes.count) 篇")
        .listRowInsets(pageInsets(vertical: AppTheme.Spacing.xs))
        .listRowSeparator(.hidden)
        .listRowBackground(AppTheme.Colors.cardBackground)
    }

    private var workspaceHeader: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                Image(systemName: "note.text")
                    .font(.system(size: 24, weight: .medium))
                    .foregroundStyle(AppTheme.Icons.interactive)
                    .frame(width: 48, height: 48)
                    .background(AppTheme.Colors.selectionTint)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
                    .accessibilityHidden(true)

                VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                    Text("我的笔记空间")
                        .font(.title2.weight(.bold))
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    Text("\(store.notes.count) 篇笔记 · \(store.allTags.count) 个标签 · 本地 Markdown")
                        .font(.subheadline)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                }
            }

            Button {
                appState.navigateToChatWithPrompt(
                    "请基于我的本地笔记，帮我整理最近记录的重点和待办。",
                    contextScope: localOnlyContext()
                )
            } label: {
                HStack(spacing: AppTheme.Spacing.md) {
                    Image(systemName: "sparkles")
                        .font(.body.weight(.semibold))
                        .foregroundStyle(AppTheme.Icons.intelligence)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("用 AI 整理笔记")
                            .font(.body.weight(.semibold))
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                        Text("切换到对话页并带入整理任务")
                            .font(.caption)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                    }
                    Spacer(minLength: AppTheme.Spacing.sm)
                    Image(systemName: "chevron.right")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(AppTheme.Colors.textTertiary)
                }
                .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityHint("切换到对话页")
        }
        .padding(.vertical, AppTheme.Spacing.lg)
        .listRowInsets(pageInsets(vertical: AppTheme.Spacing.sm))
        .listRowSeparator(.hidden)
        .listRowBackground(AppTheme.Colors.cardBackground)
        .accessibilityElement(children: .contain)
    }

    private var quickActions: some View {
        HStack(spacing: AppTheme.Spacing.md) {
            quickAction(
                title: "新建笔记",
                subtitle: "空白 Markdown",
                systemImage: "square.and.pencil",
                action: createNote
            )
            quickAction(
                title: "每日笔记",
                subtitle: "记录今天",
                systemImage: "calendar",
                action: openDailyNote
            )
        }
        .padding(.vertical, AppTheme.Spacing.sm)
        .listRowInsets(pageInsets(vertical: 0))
        .listRowSeparator(.hidden)
        .listRowBackground(AppTheme.Colors.cardBackground)
    }

    private func quickAction(
        title: String,
        subtitle: String,
        systemImage: String,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                Image(systemName: systemImage)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(AppTheme.Icons.interactive)
                Text(title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            }
            .frame(maxWidth: .infinity, minHeight: 88, alignment: .leading)
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.Colors.surfaceTint)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private var tagFilter: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: AppTheme.Spacing.sm) {
                tagButton(title: "全部标签", tag: nil)
                ForEach(store.allTags, id: \.self) { tag in
                    tagButton(title: "#\(tag)", tag: tag)
                }
            }
            .padding(.vertical, AppTheme.Spacing.xs)
        }
        .listRowInsets(pageInsets(vertical: AppTheme.Spacing.xs))
        .listRowSeparator(.hidden)
        .listRowBackground(AppTheme.Colors.cardBackground)
        .accessibilityLabel("标签筛选")
    }

    private func tagButton(title: String, tag: String?) -> some View {
        let selected = selectedTag == tag
        return Button {
            withAnimation(AppTheme.Motion.quick) {
                selectedTag = tag
            }
        } label: {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(selected ? AppTheme.Colors.onPrimary : AppTheme.Colors.textSecondary)
                .padding(.horizontal, AppTheme.Spacing.md)
                .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                .background(selected ? AppTheme.Colors.primary : AppTheme.Colors.surfaceTint)
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    private var scopePicker: some View {
        Picker("笔记范围", selection: $scope) {
            ForEach(NoteScope.allCases) { item in
                Text(item.rawValue).tag(item)
            }
        }
        .pickerStyle(.segmented)
        .padding(.vertical, AppTheme.Spacing.sm)
        .listRowInsets(pageInsets(vertical: 0))
        .listRowSeparator(.hidden)
        .listRowBackground(AppTheme.Colors.cardBackground)
    }

    private func noteSection(title: String, systemImage: String, notes: [KnowledgeNote]) -> some View {
        Section {
            ForEach(notes) { note in
                NavigationLink(value: note.id) {
                    KnowledgeNoteRow(note: note, backlinkCount: store.backlinks(to: note).count)
                }
                .buttonStyle(.plain)
                .swipeActions(edge: .leading, allowsFullSwipe: true) {
                    Button {
                        store.togglePin(id: note.id)
                    } label: {
                        Label(note.isPinned ? "取消置顶" : "置顶", systemImage: note.isPinned ? "pin.slash" : "pin")
                    }
                    .tint(AppTheme.Colors.primary)
                }
                .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                    Button(role: .destructive) {
                        notePendingTrash = note
                        showingTrashConfirmation = true
                    } label: {
                        Label("移到废纸篓", systemImage: "trash")
                    }
                }
                .listRowInsets(EdgeInsets(
                    top: AppTheme.Spacing.xs,
                    leading: AppTheme.Metrics.contentGutter,
                    bottom: AppTheme.Spacing.xs,
                    trailing: AppTheme.Spacing.md
                ))
                .listRowBackground(AppTheme.Colors.cardBackground)
            }
        } header: {
            Label(title, systemImage: systemImage)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(AppTheme.Colors.textSecondary)
                .textCase(nil)
        }
    }

    private var loadingRow: some View {
        HStack(spacing: AppTheme.Spacing.md) {
            ProgressView()
            Text("正在读取本地笔记…")
                .font(.subheadline)
                .foregroundStyle(AppTheme.Colors.textSecondary)
        }
        .frame(minHeight: 120)
        .listRowSeparator(.hidden)
        .listRowBackground(AppTheme.Colors.cardBackground)
    }

    private var emptyState: some View {
        ContentUnavailableView {
            Label("没有匹配的笔记", systemImage: "note.text")
        } description: {
            Text(searchText.isEmpty ? "创建第一篇笔记，或切换其他筛选范围。" : "请尝试其他关键词或标签。")
        } actions: {
            Button("新建笔记") { createNote() }
                .buttonStyle(.borderedProminent)
        }
        .frame(minHeight: 260)
        .listRowSeparator(.hidden)
        .listRowBackground(AppTheme.Colors.cardBackground)
    }

    private func pageInsets(vertical: CGFloat) -> EdgeInsets {
        EdgeInsets(
            top: vertical,
            leading: AppTheme.Metrics.contentGutter,
            bottom: vertical,
            trailing: AppTheme.Metrics.contentGutter
        )
    }

    private func createNote() {
        guard let note = store.createNote() else { return }
        syncInBackground(note)
        path.append(note.id)
    }

    private func openDailyNote() {
        guard let note = store.dailyNote() else { return }
        syncInBackground(note)
        path.append(note.id)
    }

    private func localOnlyContext() -> ChatContextScopeDTO {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let notes = store.notes.prefix(8).map { note in
            ChatLocalNoteDTO(
                id: note.id,
                title: note.title,
                markdown: store.markdown(for: note),
                updatedAt: formatter.string(from: note.updatedAt)
            )
        }
        return ChatContextScopeDTO(mode: .localOnly, localNotes: Array(notes))
    }

    private func syncInBackground(_ note: KnowledgeNote) {
        let markdown = store.markdown(for: note)
        Task {
            try? await APIClient.shared.syncKnowledgeNote(
                id: note.id, markdown: markdown, updatedAt: note.updatedAt
            )
        }
    }

    private func syncLocalNotes() async {
        for note in store.notes {
            try? await APIClient.shared.syncKnowledgeNote(
                id: note.id,
                markdown: store.markdown(for: note),
                updatedAt: note.updatedAt
            )
        }
        for note in store.archivedNotes {
            guard let mergedIntoNoteId = note.mergedIntoNoteId else { continue }
            try? await APIClient.shared.syncKnowledgeNote(
                id: note.id,
                markdown: store.markdown(for: note),
                updatedAt: note.updatedAt
            )
            try? await APIClient.shared.archiveKnowledgeNote(
                id: note.id, mergedIntoNoteId: mergedIntoNoteId
            )
        }
    }
}

private struct KnowledgeArchiveView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var store = KnowledgeNoteStore.shared

    var body: some View {
        NavigationStack {
            List {
                if store.archivedNotes.isEmpty {
                    ContentUnavailableView(
                        "没有归档笔记",
                        systemImage: "archivebox",
                        description: Text("合并整理后的旧笔记会保留在这里。")
                    )
                } else {
                    Section {
                        ForEach(store.archivedNotes) { note in
                            HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                                VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                                    Text(note.title)
                                        .font(.body.weight(.semibold))
                                    if !note.preview.isEmpty {
                                        Text(note.preview)
                                            .font(.subheadline)
                                            .foregroundStyle(AppTheme.Colors.textSecondary)
                                            .lineLimit(2)
                                    }
                                }
                                Spacer(minLength: AppTheme.Spacing.sm)
                                Button("恢复") { restore(note) }
                                    .buttonStyle(.bordered)
                                    .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                            }
                            .swipeActions(edge: .leading, allowsFullSwipe: false) {
                                Button {
                                    restore(note)
                                } label: {
                                    Label("恢复", systemImage: "arrow.uturn.backward")
                                }
                                .tint(AppTheme.Colors.primary)
                            }
                            .accessibilityAction(named: "恢复笔记") { restore(note) }
                        }
                    } footer: {
                        Text("归档不会删除内容；向右轻扫可恢复到当前笔记列表。")
                    }
                }
            }
            .navigationTitle("归档")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") { dismiss() }
                }
            }
        }
    }

    private func restore(_ note: KnowledgeNote) {
        guard KnowledgeNoteStore.shared.restoreArchivedNote(id: note.id) != nil else { return }
        Task {
            try? await APIClient.shared.restoreKnowledgeNote(id: note.id)
        }
    }
}

private struct KnowledgeNoteRow: View {
    let note: KnowledgeNote
    let backlinkCount: Int

    var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
            Image(systemName: note.isDailyNote ? "calendar" : "doc.text")
                .font(.system(size: 17, weight: .medium))
                .foregroundStyle(note.isDailyNote ? AppTheme.Icons.intelligence : AppTheme.Icons.interactive)
                .frame(width: 40, height: 40)
                .background(AppTheme.Colors.surfaceTint)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xs, style: .continuous))
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                HStack(alignment: .firstTextBaseline, spacing: AppTheme.Spacing.xs) {
                    Text(note.title)
                        .font(.body.weight(.semibold))
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                    if note.isPinned {
                        Image(systemName: "pin.fill")
                            .font(.caption2)
                            .foregroundStyle(AppTheme.Colors.textTertiary)
                            .accessibilityLabel("已置顶")
                    }
                }

                if !note.preview.isEmpty {
                    Text(note.preview)
                        .font(.subheadline)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                        .lineLimit(2)
                }

                HStack(spacing: AppTheme.Spacing.sm) {
                    Text(note.updatedAt, style: .relative)
                    if !note.tags.isEmpty {
                        Text("·")
                        Text(note.tags.prefix(2).map { "#\($0)" }.joined(separator: "  "))
                    }
                    if backlinkCount > 0 {
                        Text("·")
                        Label("\(backlinkCount)", systemImage: "link")
                    }
                }
                .font(.caption)
                .foregroundStyle(AppTheme.Colors.textTertiary)
                .lineLimit(1)
            }
        }
        .padding(.vertical, AppTheme.Spacing.sm)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(note.title)，\(note.tags.map { "标签 \($0)" }.joined(separator: "，"))")
        .accessibilityHint("打开笔记")
    }
}

private struct KnowledgeNoteEditor: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject private var store = KnowledgeNoteStore.shared

    let noteID: String
    let initialAnchor: String?

    @State private var title = ""
    @State private var noteContent = ""
    @State private var selectedRange = NSRange(location: 0, length: 0)
    @State private var tagsText = ""
    @State private var isPinned = false
    @State private var mode: NoteEditorMode = .edit
    @State private var isLoaded = false
    @State private var saveStatus = "已保存到本地"
    @State private var saveTask: Task<Void, Never>?
    @State private var showingTrashConfirmation = false
    @State private var wikiLinkContext: WikiLinkCompletionContext?
    @State private var wikiLinkSelectionIndex = 0
    @FocusState private var titleFocused: Bool

    private var note: KnowledgeNote? { store.note(id: noteID) }

    var body: some View {
        editorPage
        .navigationTitle(title.isEmpty ? "笔记" : title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                if let note {
                    ShareLink(item: note.fileURL) {
                        Image(systemName: "square.and.arrow.up")
                            .frame(width: AppTheme.Metrics.minimumTouchTarget, height: AppTheme.Metrics.minimumTouchTarget)
                    }
                    .accessibilityLabel("分享 Markdown 文件")
                }

                Menu {
                    Button {
                        isPinned.toggle()
                        scheduleSave()
                    } label: {
                        Label(isPinned ? "取消置顶" : "置顶", systemImage: isPinned ? "pin.slash" : "pin")
                    }
                    Button(role: .destructive) {
                        showingTrashConfirmation = true
                    } label: {
                        Label("移到废纸篓", systemImage: "trash")
                    }
                } label: {
                    Image(systemName: "ellipsis")
                        .frame(width: AppTheme.Metrics.minimumTouchTarget, height: AppTheme.Metrics.minimumTouchTarget)
                }
                .accessibilityLabel("更多笔记操作")
            }
        }
        .task(id: noteID) {
            loadNote()
        }
        .onChange(of: title) { _, _ in scheduleSave() }
        .onChange(of: noteContent) { _, _ in scheduleSave() }
        .onChange(of: tagsText) { _, _ in scheduleSave() }
        .onDisappear {
            saveTask?.cancel()
            saveNow()
        }
        .confirmationDialog(
            "将这篇笔记移到废纸篓？",
            isPresented: $showingTrashConfirmation,
            titleVisibility: .visible
        ) {
            Button("移到废纸篓", role: .destructive) {
                store.moveToTrash(id: noteID)
                dismiss()
            }
            Button("取消", role: .cancel) {}
        } message: {
            Text("文件会保留在 KnowledgeVault/.trash 中。")
        }
    }

    @ViewBuilder
    private var editorPage: some View {
        if let note {
            ScrollViewReader { proxy in
                ScrollView {
                    editorContents(note: note)
                }
                .background(AppTheme.Colors.cardBackground)
                .task(id: initialAnchor) {
                    guard let initialAnchor, !initialAnchor.isEmpty else { return }
                    mode = .preview
                    try? await Task.sleep(nanoseconds: 120_000_000)
                    withAnimation(.easeInOut(duration: 0.2)) {
                        proxy.scrollTo(noteAnchorID(initialAnchor), anchor: .top)
                    }
                }
            }
        } else {
            ContentUnavailableView(
                "笔记不存在",
                systemImage: "doc.questionmark",
                description: Text("文件可能已被移动或删除。")
            )
        }
    }

    private func editorContents(note: KnowledgeNote) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xl) {
            editorHeader(note: note)
            Divider()
            modePicker
            editorModeContent
            relationSection(note: note)
        }
        .frame(maxWidth: AppTheme.Metrics.readableContentWidth, alignment: .leading)
        .padding(.horizontal, AppTheme.Metrics.contentGutter)
        .padding(.top, AppTheme.Spacing.lg)
        .padding(.bottom, 120)
        .frame(maxWidth: .infinity, alignment: .center)
    }

    @ViewBuilder
    private var editorModeContent: some View {
        if mode == .edit {
            formattingToolbar
            if WikiLinkParser.hasMalformedTripleBrackets(noteContent) {
                Label("发现三层方括号；双链应写成 [[笔记名称]]", systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(AppTheme.Icons.warning)
                    .accessibilityLabel("双链格式错误，应使用两层方括号")
            }
            editorBody
            if let wikiLinkContext {
                wikiLinkSuggestions(for: wikiLinkContext)
            }
        } else {
            NoteReadingView(noteID: noteID, content: noteContent)
        }
    }

    private func editorHeader(note: KnowledgeNote) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            Image(systemName: note.isDailyNote ? "calendar" : "note.text")
                .font(.system(size: 30, weight: .medium))
                .foregroundStyle(AppTheme.Icons.interactive)
                .frame(width: 60, height: 60)
                .background(AppTheme.Colors.selectionTint)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
                .accessibilityHidden(true)

            TextField("无标题", text: $title, axis: .vertical)
                .font(.largeTitle.weight(.bold))
                .foregroundStyle(AppTheme.Colors.textPrimary)
                .textFieldStyle(.plain)
                .focused($titleFocused)
                .accessibilityLabel("笔记标题")

            HStack(spacing: AppTheme.Spacing.sm) {
                Label(saveStatus, systemImage: saveStatus == "正在保存…" ? "arrow.triangle.2.circlepath" : "checkmark.circle")
                Text("·")
                Text(note.fileURL.lastPathComponent)
                    .lineLimit(1)
            }
            .font(.caption)
            .foregroundStyle(AppTheme.Colors.textTertiary)

            HStack(alignment: .firstTextBaseline, spacing: AppTheme.Spacing.md) {
                Label("标签", systemImage: "number")
                    .font(.subheadline)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .frame(width: 72, alignment: .leading)
                TextField("项目, 灵感", text: $tagsText)
                    .font(.subheadline)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .accessibilityLabel("标签，用逗号分隔")
            }
        }
    }

    private var modePicker: some View {
        Picker("显示模式", selection: $mode) {
            ForEach(NoteEditorMode.allCases) { item in
                Text(item.rawValue).tag(item)
            }
        }
        .pickerStyle(.segmented)
    }

    private var formattingToolbar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: AppTheme.Spacing.sm) {
                formatButton("标题", systemImage: "textformat.size") { insertMarkdown("## 标题", selecting: "标题") }
                formatButton("待办", systemImage: "checklist") { insertMarkdown("- [ ] 待办事项", selecting: "待办事项") }
                formatButton("双链", systemImage: "link") { beginWikiLink() }
                formatButton("标签", systemImage: "number") { insertMarkdown("#标签", selecting: "标签") }
                formatButton("提示", systemImage: "lightbulb") { insertMarkdown("> [!tip] 提示\n> 内容", selecting: "内容") }
                formatButton("代码", systemImage: "chevron.left.forwardslash.chevron.right") { insertMarkdown("```\n代码\n```", selecting: "代码") }
            }
        }
        .accessibilityLabel("Markdown 格式工具栏")
    }

    private func formatButton(_ title: String, systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(title, systemImage: systemImage)
                .font(.caption.weight(.semibold))
                .foregroundStyle(AppTheme.Colors.textSecondary)
                .padding(.horizontal, AppTheme.Spacing.md)
                .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                .background(AppTheme.Colors.surfaceTint)
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }

    private var editorBody: some View {
        MarkdownTextEditor(
            text: $noteContent,
            selectedRange: $selectedRange,
            onWikiLinkContextChange: { context in
                if wikiLinkContext != context { wikiLinkSelectionIndex = 0 }
                wikiLinkContext = context
            },
            onWikiLinkKey: handleWikiLinkKey
        )
            .frame(minHeight: 420, alignment: .topLeading)
            .accessibilityLabel("Markdown 正文")
            .overlay(alignment: .topLeading) {
                if noteContent.isEmpty {
                    Text("开始记录。输入 [[笔记名称]] 创建双向链接…")
                        .font(.body)
                        .foregroundStyle(AppTheme.Colors.textTertiary)
                        .padding(.top, 8)
                        .padding(.leading, 5)
                        .allowsHitTesting(false)
                        .accessibilityHidden(true)
                }
            }
    }

    @ViewBuilder
    private func wikiLinkSuggestions(for context: WikiLinkCompletionContext) -> some View {
        let suggestions = store.wikiLinkSuggestions(context.query, excluding: noteID)
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
            HStack {
                Label("链接到笔记", systemImage: "link")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                Spacer()
                Text("输入 ]] 完成")
                    .font(.caption2)
                    .foregroundStyle(AppTheme.Colors.textTertiary)
            }
            ForEach(Array(suggestions.enumerated()), id: \.element.id) { index, suggestion in
                Button {
                    completeWikiLink(with: suggestion.title, context: context)
                } label: {
                    relationRow(title: suggestion.title, detail: suggestion.aliases.first ?? suggestion.preview)
                }
                .buttonStyle(.plain)
                .background(index == wikiLinkSelectionIndex ? AppTheme.Colors.selectionTint : .clear)
            }
            if suggestions.isEmpty, !context.query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Button {
                    if let created = store.createNote(title: context.query) {
                        completeWikiLink(with: created.title, context: context)
                        Task { await syncPendingNotes() }
                    }
                } label: {
                    Label("创建《\(context.query)》", systemImage: "plus.circle")
                        .font(.subheadline.weight(.semibold))
                        .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget, alignment: .leading)
                }
                .buttonStyle(.plain)
                .foregroundStyle(AppTheme.Icons.interactive)
            }
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.surfaceTint)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
    }

    @ViewBuilder
    private func relationSection(note: KnowledgeNote) -> some View {
        let resolvedLinks = note.outgoingLinks.compactMap { store.note(matchingLink: $0) }
        let backlinks = store.backlinkReferences(to: note)
        let unresolved = store.unresolvedLinks(in: note)

        if !resolvedLinks.isEmpty || !backlinks.isEmpty || !unresolved.isEmpty {
            Divider()
            VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                Text("连接")
                    .font(.title3.weight(.bold))
                    .foregroundStyle(AppTheme.Colors.textPrimary)

                if !resolvedLinks.isEmpty {
                    relationGroup(title: "链接到", systemImage: "arrow.up.right") {
                        ForEach(resolvedLinks) { linked in
                            NavigationLink(value: linked.id) {
                                relationRow(title: linked.title, detail: linked.preview)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }

                if !backlinks.isEmpty {
                    relationGroup(title: "反向链接", systemImage: "arrow.uturn.backward") {
                        ForEach(backlinks) { linked in
                            NavigationLink(value: linked.sourceNote.id) {
                                relationRow(title: linked.sourceNote.title, detail: linked.context)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }

                if !unresolved.isEmpty {
                    relationGroup(title: "尚未创建", systemImage: "questionmark.diamond") {
                        ForEach(unresolved, id: \.self) { link in
                            Button {
                                if let created = store.createNote(title: link) {
                                    noteContent = noteContent.replacingOccurrences(of: "[[\(link)]]", with: "[[\(created.title)]]")
                                    Task { await syncPendingNotes() }
                                }
                            } label: {
                                HStack {
                                    Text(link)
                                    Spacer()
                                    Label("创建", systemImage: "plus")
                                        .font(.caption.weight(.semibold))
                                }
                                .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                            .foregroundStyle(AppTheme.Icons.interactive)
                        }
                    }
                }
            }
        }
    }

    private func relationGroup<Content: View>(
        title: String,
        systemImage: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Label(title, systemImage: systemImage)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(AppTheme.Colors.textSecondary)
            content()
        }
    }

    private func relationRow(title: String, detail: String) -> some View {
        HStack(spacing: AppTheme.Spacing.md) {
            Image(systemName: "doc.text")
                .foregroundStyle(AppTheme.Colors.textTertiary)
                .frame(width: 28)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                if !detail.isEmpty {
                    Text(detail)
                        .font(.caption)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                        .lineLimit(1)
                }
            }
            Spacer()
            Image(systemName: "chevron.right")
                .font(.caption.weight(.semibold))
                .foregroundStyle(AppTheme.Colors.textTertiary)
        }
        .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
        .contentShape(Rectangle())
    }

    private func loadNote() {
        guard let note else { return }
        saveTask?.cancel()
        title = note.title
        noteContent = note.body
        tagsText = note.tags.joined(separator: ", ")
        isPinned = note.isPinned
        saveStatus = "已保存到本地"
        isLoaded = true
        if note.title == "无标题" {
            Task { @MainActor in titleFocused = true }
        }
    }

    private func scheduleSave() {
        guard isLoaded else { return }
        saveTask?.cancel()
        saveStatus = "正在保存…"
        saveTask = Task {
            try? await Task.sleep(nanoseconds: 650_000_000)
            guard !Task.isCancelled else { return }
            await MainActor.run { saveNow() }
        }
    }

    private func saveNow() {
        guard isLoaded else { return }
        let tags = tagsText
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "#")) }
            .filter { !$0.isEmpty }
        if store.save(id: noteID, title: title, body: noteContent, tags: tags, isPinned: isPinned) != nil {
            saveStatus = "已保存到本地"
            Task { await syncPendingNotes() }
        } else {
            saveStatus = "保存失败"
        }
    }

    private func syncPendingNotes() async {
        for pending in store.pendingSyncNotes() {
            do {
                try await APIClient.shared.syncKnowledgeNote(
                    id: pending.id,
                    markdown: store.markdown(for: pending),
                    updatedAt: pending.updatedAt
                )
                store.markSynced(noteID: pending.id)
            } catch {
                // Local Markdown remains authoritative and the pending ID is
                // retained for the next save/sync attempt.
            }
        }
    }

    private func beginWikiLink() {
        let source = noteContent as NSString
        let safeLocation = min(max(selectedRange.location, 0), source.length)
        let safeLength = min(max(selectedRange.length, 0), source.length - safeLocation)
        let selected = source.substring(with: NSRange(location: safeLocation, length: safeLength))
        let replacement = selected.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? "[["
            : "[[\(selected)]]"
        noteContent = source.replacingCharacters(
            in: NSRange(location: safeLocation, length: safeLength),
            with: replacement
        )
        selectedRange = NSRange(location: safeLocation + (replacement as NSString).length, length: 0)
        wikiLinkContext = WikiLinkCompletionContext.detect(in: noteContent, selectedRange: selectedRange)
    }

    private func completeWikiLink(with title: String, context: WikiLinkCompletionContext) {
        let source = noteContent as NSString
        guard NSMaxRange(context.replacementRange) <= source.length else { return }
        let replacement = "[[\(title)]]"
        noteContent = source.replacingCharacters(in: context.replacementRange, with: replacement)
        selectedRange = NSRange(location: context.replacementRange.location + (replacement as NSString).length, length: 0)
        wikiLinkContext = nil
        wikiLinkSelectionIndex = 0
    }

    private func handleWikiLinkKey(_ action: WikiLinkKeyAction) {
        guard let context = wikiLinkContext else { return }
        let suggestions = store.wikiLinkSuggestions(context.query, excluding: noteID)
        switch action {
        case .move(let delta):
            guard !suggestions.isEmpty else { return }
            wikiLinkSelectionIndex = min(
                max(wikiLinkSelectionIndex + delta, 0),
                suggestions.count - 1
            )
        case .commit:
            guard !suggestions.isEmpty else { return }
            completeWikiLink(with: suggestions[wikiLinkSelectionIndex].title, context: context)
        case .dismiss:
            wikiLinkContext = nil
            wikiLinkSelectionIndex = 0
        }
    }

    private func insertMarkdown(_ template: String, selecting placeholder: String) {
        let source = noteContent as NSString
        let location = min(max(selectedRange.location, 0), source.length)
        let length = min(max(selectedRange.length, 0), source.length - location)
        let range = NSRange(location: location, length: length)
        let selectedText = source.substring(with: range)
        let replacement: String

        if !selectedText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            switch placeholder {
            case "页面名称": replacement = "[[\(selectedText)]]"
            case "标签": replacement = "#\(selectedText.replacingOccurrences(of: "#", with: ""))"
            case "标题": replacement = "## \(selectedText)"
            case "待办事项": replacement = "- [ ] \(selectedText)"
            case "内容": replacement = "> \(selectedText)"
            case "代码": replacement = "```\n\(selectedText)\n```"
            default: replacement = template
            }
        } else {
            replacement = template
        }

        noteContent = source.replacingCharacters(in: range, with: replacement)
        if let placeholderRange = replacement.range(of: placeholder) {
            let offset = replacement.utf16.distance(from: replacement.utf16.startIndex, to: placeholderRange.lowerBound)
            selectedRange = NSRange(location: location + offset, length: placeholder.utf16.count)
        } else {
            selectedRange = NSRange(location: location + (replacement as NSString).length, length: 0)
        }
    }
}

private struct WikiLinkCompletionContext: Equatable {
    let query: String
    let replacementRange: NSRange

    static func detect(in text: String, selectedRange: NSRange) -> WikiLinkCompletionContext? {
        guard selectedRange.length == 0 else { return nil }
        let source = text as NSString
        let cursor = min(max(selectedRange.location, 0), source.length)
        let prefix = source.substring(to: cursor) as NSString
        let opener = prefix.range(of: "[[", options: .backwards)
        guard opener.location != NSNotFound else { return nil }
        if opener.location > 0,
           prefix.substring(with: NSRange(location: opener.location - 1, length: 1)) == "[" { return nil }
        let fragmentRange = NSRange(location: NSMaxRange(opener), length: cursor - NSMaxRange(opener))
        let fragment = prefix.substring(with: fragmentRange)
        guard !fragment.contains("]]"), !fragment.contains("\n"), !fragment.contains("]") else { return nil }
        let query = fragment
            .split(whereSeparator: { $0 == "|" || $0 == "#" })
            .first
            .map(String.init) ?? ""
        return WikiLinkCompletionContext(
            query: query.trimmingCharacters(in: .whitespacesAndNewlines),
            replacementRange: NSRange(location: opener.location, length: cursor - opener.location)
        )
    }
}

private enum WikiLinkKeyAction {
    case move(Int)
    case commit
    case dismiss
}

private final class WikiLinkTextView: UITextView {
    var onWikiLinkKey: ((WikiLinkKeyAction) -> Void)?
    var wikiCompletionIsActive = false

    override var keyCommands: [UIKeyCommand]? {
        guard wikiCompletionIsActive else { return super.keyCommands }
        return [
            UIKeyCommand(input: UIKeyCommand.inputUpArrow, modifierFlags: [], action: #selector(moveUp)),
            UIKeyCommand(input: UIKeyCommand.inputDownArrow, modifierFlags: [], action: #selector(moveDown)),
            UIKeyCommand(input: "\r", modifierFlags: [], action: #selector(commitLink)),
            UIKeyCommand(input: UIKeyCommand.inputEscape, modifierFlags: [], action: #selector(dismissLink))
        ]
    }

    @objc private func moveUp() { onWikiLinkKey?(.move(-1)) }
    @objc private func moveDown() { onWikiLinkKey?(.move(1)) }
    @objc private func commitLink() { onWikiLinkKey?(.commit) }
    @objc private func dismissLink() { onWikiLinkKey?(.dismiss) }
}

private struct MarkdownTextEditor: UIViewRepresentable {
    @Binding var text: String
    @Binding var selectedRange: NSRange
    let onWikiLinkContextChange: (WikiLinkCompletionContext?) -> Void
    let onWikiLinkKey: (WikiLinkKeyAction) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> UITextView {
        let textView = WikiLinkTextView()
        textView.onWikiLinkKey = onWikiLinkKey
        textView.delegate = context.coordinator
        textView.font = UIFont.preferredFont(forTextStyle: .body)
        textView.adjustsFontForContentSizeCategory = true
        textView.textColor = UIColor.label
        textView.backgroundColor = .clear
        textView.isScrollEnabled = true
        textView.alwaysBounceVertical = false
        textView.keyboardDismissMode = .interactive
        textView.textContainerInset = UIEdgeInsets(top: 8, left: 4, bottom: 8, right: 4)
        textView.accessibilityLabel = "Markdown 正文"
        return textView
    }

    func updateUIView(_ textView: UITextView, context: Context) {
        if textView.text != text { textView.text = text }
        let safeLocation = min(max(selectedRange.location, 0), textView.text.utf16.count)
        let safeLength = min(max(selectedRange.length, 0), textView.text.utf16.count - safeLocation)
        let safeRange = NSRange(location: safeLocation, length: safeLength)
        if textView.selectedRange != safeRange { textView.selectedRange = safeRange }
    }

    final class Coordinator: NSObject, UITextViewDelegate {
        var parent: MarkdownTextEditor

        init(_ parent: MarkdownTextEditor) { self.parent = parent }

        func textViewDidChange(_ textView: UITextView) {
            parent.text = textView.text
            parent.selectedRange = textView.selectedRange
            updateWikiContext(for: textView)
        }

        func textViewDidChangeSelection(_ textView: UITextView) {
            parent.selectedRange = textView.selectedRange
            updateWikiContext(for: textView)
        }

        func updateWikiContext(for textView: UITextView) {
            let context = WikiLinkCompletionContext.detect(in: textView.text, selectedRange: textView.selectedRange)
            (textView as? WikiLinkTextView)?.wikiCompletionIsActive = context != nil
            parent.onWikiLinkContextChange(context)
        }
    }
}

private struct NoteReadingView: View {
    let noteID: String
    let content: String
    var depth: Int = 0

    private var blocks: [NoteReadingBlock] {
        NoteReadingBlock.parse(content)
    }

    var body: some View {
        LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            if blocks.isEmpty {
                Text("这篇笔记还没有正文。")
                    .font(.body)
                    .foregroundStyle(AppTheme.Colors.textTertiary)
            } else {
                ForEach(blocks) { block in
                    block.view(currentNoteID: noteID, depth: depth)
                        .id(block.navigationID)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .textSelection(.enabled)
    }
}

private struct WikiInlineView: View {
    let text: String
    let currentNoteID: String
    let depth: Int

    private struct Segment: Identifiable {
        let id: String
        let text: String
        let link: WikiLinkReference?
    }

    private var segments: [Segment] {
        let source = text as NSString
        let links = WikiLinkParser.parse(text)
        guard links.contains(where: \.isEmbed) else {
            return [Segment(id: "plain", text: text, link: nil)]
        }
        var result: [Segment] = []
        var cursor = 0
        for link in links {
            if link.location > cursor {
                result.append(Segment(
                    id: "text-\(cursor)",
                    text: source.substring(with: NSRange(location: cursor, length: link.location - cursor)),
                    link: nil
                ))
            }
            result.append(Segment(id: link.id, text: link.rawText, link: link))
            cursor = NSMaxRange(link.range)
        }
        if cursor < source.length {
            result.append(Segment(id: "text-\(cursor)", text: source.substring(from: cursor), link: nil))
        }
        return result
    }

    var body: some View {
        if segments.count == 1, segments[0].link == nil {
            Text(attributedMarkdown(text))
                .foregroundStyle(AppTheme.Colors.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        } else {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                ForEach(segments) { segment in
                    if let link = segment.link, link.isEmbed {
                        EmbeddedNoteView(reference: link, depth: depth)
                    } else if !segment.text.isEmpty {
                        Text(attributedMarkdown(segment.text))
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
    }

    private func attributedMarkdown(_ value: String) -> AttributedString {
        let displayText = value.replacingOccurrences(
            of: #"(?:^|\s)\^[\p{L}\p{N}_-]+\s*$"#,
            with: "",
            options: .regularExpression
        )
        let source = displayText as NSString
        var result = AttributedString()
        var cursor = 0
        func markdown(_ text: String) -> AttributedString {
            (try? AttributedString(markdown: text)) ?? AttributedString(text)
        }
        for link in WikiLinkParser.parse(displayText) {
            if link.location > cursor {
                result.append(markdown(source.substring(with: NSRange(location: cursor, length: link.location - cursor))))
            }
            var linked = AttributedString(link.visibleText)
            var components = URLComponents()
            components.scheme = "ailab-note"
            components.host = "open"
            components.queryItems = [
                URLQueryItem(name: "target", value: link.target),
                URLQueryItem(name: "current", value: currentNoteID),
                URLQueryItem(name: "anchor", value: link.anchor?.rawValue ?? "")
            ]
            linked.link = components.url
            result.append(linked)
            cursor = NSMaxRange(link.range)
        }
        if cursor < source.length {
            result.append(markdown(source.substring(from: cursor)))
        }
        return result
    }
}

private struct EmbeddedNoteView: View {
    @ObservedObject private var store = KnowledgeNoteStore.shared
    let reference: WikiLinkReference
    let depth: Int

    private var note: KnowledgeNote? { store.note(matchingLink: reference.target) }

    var body: some View {
        if let note {
            NavigationLink(value: knowledgeRoute(noteID: note.id, anchor: reference.anchor?.rawValue)) {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    Label("嵌入 · \(note.title)", systemImage: "rectangle.inset.filled")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(AppTheme.Icons.interactive)
                    if depth < 2 {
                        NoteReadingView(
                            noteID: note.id,
                            content: embeddedContent(note: note, anchor: reference.anchor),
                            depth: depth + 1
                        )
                        .allowsHitTesting(false)
                    } else {
                        Text(note.preview)
                            .font(.subheadline)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                            .lineLimit(5)
                    }
                }
                .padding(AppTheme.Spacing.md)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(AppTheme.Colors.surfaceTint)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
            }
            .buttonStyle(.plain)
        } else {
            Label("未找到嵌入笔记：\(reference.target)", systemImage: "questionmark.diamond")
                .font(.caption)
                .foregroundStyle(AppTheme.Colors.textTertiary)
        }
    }

    private func embeddedContent(note: KnowledgeNote, anchor: WikiLinkAnchor?) -> String {
        guard let anchor else { return note.body }
        let lines = note.body.components(separatedBy: .newlines)
        switch anchor {
        case .block(let blockID):
            return lines.first(where: { $0.contains("^\(blockID)") }) ?? note.body
        case .heading(let heading):
            guard let start = lines.firstIndex(where: {
                $0.trimmingCharacters(in: .whitespaces).replacingOccurrences(
                    of: #"^#{1,6}\s*"#, with: "", options: .regularExpression
                ).caseInsensitiveCompare(heading) == .orderedSame
            }) else { return note.body }
            let startLevel = lines[start].prefix(while: { $0 == "#" }).count
            var end = lines.count
            for index in (start + 1)..<lines.count {
                let candidate = lines[index].trimmingCharacters(in: .whitespaces)
                let level = candidate.prefix(while: { $0 == "#" }).count
                if level > 0 && level <= startLevel { end = index; break }
            }
            return lines[start..<end].joined(separator: "\n")
        }
    }
}

private enum NoteReadingBlock: Identifiable {
    case heading(level: Int, text: String, id: UUID = UUID())
    case paragraph(String, id: UUID = UUID())
    case list([String], ordered: Bool, id: UUID = UUID())
    case quote(String, id: UUID = UUID())
    case callout(type: String, title: String, text: String, id: UUID = UUID())
    case code(String, id: UUID = UUID())
    case divider(id: UUID = UUID())

    var id: UUID {
        switch self {
        case .heading(_, _, let id), .paragraph(_, let id), .list(_, _, let id), .quote(_, let id),
             .callout(_, _, _, let id), .code(_, let id), .divider(let id): return id
        }
    }

    var navigationID: String {
        switch self {
        case .heading(_, let text, _):
            return noteAnchorID(text)
        case .paragraph(let text, _), .quote(let text, _):
            return blockAnchor(in: text).map(noteAnchorID) ?? id.uuidString
        case .list(let items, _, _):
            return blockAnchor(in: items.joined(separator: "\n")).map(noteAnchorID) ?? id.uuidString
        case .callout(_, _, let text, _), .code(let text, _):
            return blockAnchor(in: text).map(noteAnchorID) ?? id.uuidString
        case .divider:
            return id.uuidString
        }
    }

    @ViewBuilder
    func view(currentNoteID: String, depth: Int) -> some View {
        switch self {
        case .heading(let level, let text, _):
            WikiInlineView(text: text, currentNoteID: currentNoteID, depth: depth)
                .font(level == 1 ? .title.weight(.bold) : level == 2 ? .title2.weight(.bold) : .title3.weight(.semibold))
                .foregroundStyle(AppTheme.Colors.textPrimary)
                .padding(.top, level <= 2 ? AppTheme.Spacing.sm : 0)
        case .paragraph(let text, _):
            WikiInlineView(text: text, currentNoteID: currentNoteID, depth: depth)
                .font(.body)
                .foregroundStyle(AppTheme.Colors.textPrimary)
                .lineSpacing(5)
                .fixedSize(horizontal: false, vertical: true)
        case .list(let items, let ordered, _):
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                    HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                        if item.hasPrefix("[ ] ") || item.hasPrefix("[x] ") {
                            Image(systemName: item.hasPrefix("[x]") ? "checkmark.square.fill" : "square")
                                .foregroundStyle(AppTheme.Icons.interactive)
                        } else {
                            Text(ordered ? "\(index + 1)." : "•")
                                .foregroundStyle(AppTheme.Colors.textSecondary)
                                .frame(width: 22, alignment: .trailing)
                        }
                        WikiInlineView(
                            text: item.replacingOccurrences(of: #"^\[[ xX]\]\s*"#, with: "", options: .regularExpression),
                            currentNoteID: currentNoteID,
                            depth: depth
                        )
                            .font(.body)
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        case .quote(let text, _):
            HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                Rectangle()
                    .fill(AppTheme.Colors.border)
                    .frame(width: 3)
                WikiInlineView(text: text, currentNoteID: currentNoteID, depth: depth)
                    .font(.body.italic())
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            }
        case .callout(_, let title, let text, _):
            HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                Image(systemName: "lightbulb")
                    .foregroundStyle(AppTheme.Icons.intelligence)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                    Text(title)
                        .font(.subheadline.weight(.semibold))
                    WikiInlineView(text: text, currentNoteID: currentNoteID, depth: depth)
                        .font(.subheadline)
                        .lineSpacing(3)
                }
                .foregroundStyle(AppTheme.Colors.textPrimary)
            }
            .padding(AppTheme.Spacing.md)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(AppTheme.Colors.surfaceTint)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
        case .code(let code, _):
            ScrollView(.horizontal, showsIndicators: false) {
                Text(code)
                    .font(.system(.body, design: .monospaced))
                    .foregroundStyle(AppTheme.Colors.codeSyntaxForeground)
                    .padding(AppTheme.Spacing.md)
            }
            .background(AppTheme.Colors.codeBlockBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
        case .divider:
            Divider()
        }
    }

    private func inlineMarkdown(_ text: String, currentNoteID: String) -> AttributedString {
        let displayText = text.replacingOccurrences(
            of: #"(?:^|\s)\^[\p{L}\p{N}_-]+\s*$"#,
            with: "",
            options: .regularExpression
        )
        let source = displayText as NSString
        var cursor = 0
        var result = AttributedString()

        func markdown(_ value: String) -> AttributedString {
            (try? AttributedString(markdown: value)) ?? AttributedString(value)
        }

        for link in WikiLinkParser.parse(displayText) {
            if link.location > cursor {
                result.append(markdown(source.substring(with: NSRange(location: cursor, length: link.location - cursor))))
            }
            var linked = AttributedString(link.visibleText)
            var components = URLComponents()
            components.scheme = "ailab-note"
            components.host = "open"
            components.queryItems = [
                URLQueryItem(name: "target", value: link.target),
                URLQueryItem(name: "current", value: currentNoteID),
                URLQueryItem(name: "anchor", value: link.anchor?.rawValue ?? "")
            ]
            linked.link = components.url
            result.append(linked)
            cursor = NSMaxRange(link.range)
        }
        if cursor < source.length {
            result.append(markdown(source.substring(from: cursor)))
        }
        return result
    }

    private func blockAnchor(in text: String) -> String? {
        guard let regex = try? NSRegularExpression(pattern: #"(?:^|\s)\^([\p{L}\p{N}_-]+)\s*$"#),
              let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
              let range = Range(match.range(at: 1), in: text) else { return nil }
        return "^" + String(text[range])
    }

    static func parse(_ source: String) -> [NoteReadingBlock] {
        let lines = source.components(separatedBy: .newlines)
        var result: [NoteReadingBlock] = []
        var paragraph: [String] = []
        var list: [String] = []
        var ordered = false
        var code: [String] = []
        var inCode = false
        var index = 0

        func flushParagraph() {
            if !paragraph.isEmpty {
                result.append(.paragraph(paragraph.joined(separator: "\n")))
                paragraph.removeAll()
            }
        }
        func flushList() {
            if !list.isEmpty {
                result.append(.list(list, ordered: ordered))
                list.removeAll()
            }
        }

        while index < lines.count {
            let raw = lines[index]
            let line = raw.trimmingCharacters(in: .whitespaces)

            if inCode {
                if line.hasPrefix("```") {
                    result.append(.code(code.joined(separator: "\n")))
                    code.removeAll()
                    inCode = false
                } else {
                    code.append(raw)
                }
                index += 1
                continue
            }

            if line.hasPrefix("```") {
                flushParagraph(); flushList(); inCode = true; index += 1; continue
            }
            if line == "---" || line == "***" {
                flushParagraph(); flushList(); result.append(.divider()); index += 1; continue
            }
            if line.hasPrefix("#") {
                flushParagraph(); flushList()
                let level = min(line.prefix(while: { $0 == "#" }).count, 3)
                result.append(.heading(level: level, text: line.dropFirst(level).trimmingCharacters(in: .whitespaces)))
                index += 1; continue
            }
            if line.hasPrefix("> [!") {
                flushParagraph(); flushList()
                let close = line.firstIndex(of: "]")
                let type = close.map { String(line[line.index(line.startIndex, offsetBy: 4)..<$0]) } ?? "note"
                let title = close.map { String(line[line.index(after: $0)...]).trimmingCharacters(in: .whitespaces) } ?? "提示"
                var content: [String] = []
                var cursor = index + 1
                while cursor < lines.count, lines[cursor].trimmingCharacters(in: .whitespaces).hasPrefix(">") {
                    content.append(String(lines[cursor].trimmingCharacters(in: .whitespaces).dropFirst()).trimmingCharacters(in: .whitespaces))
                    cursor += 1
                }
                result.append(.callout(type: type, title: title.isEmpty ? type.capitalized : title, text: content.joined(separator: "\n")))
                index = cursor; continue
            }
            if line.hasPrefix(">") {
                flushParagraph(); flushList()
                result.append(.quote(String(line.dropFirst()).trimmingCharacters(in: .whitespaces)))
                index += 1; continue
            }
            if line.hasPrefix("- ") || line.hasPrefix("* ") {
                flushParagraph()
                if list.isEmpty { ordered = false }
                list.append(String(line.dropFirst(2)))
                index += 1; continue
            }
            if let match = line.range(of: #"^\d+[.)]\s+"#, options: .regularExpression) {
                flushParagraph()
                if list.isEmpty { ordered = true }
                list.append(String(line[match.upperBound...]))
                index += 1; continue
            }
            if line.isEmpty {
                flushParagraph(); flushList(); index += 1; continue
            }

            flushList()
            paragraph.append(raw)
            index += 1
        }

        if inCode { result.append(.code(code.joined(separator: "\n"))) }
        flushParagraph(); flushList()
        return result
    }
}

#Preview("Knowledge Notes") {
    KnowledgeView()
        .environmentObject(AppState())
        .environmentObject(APIClient.shared)
}
