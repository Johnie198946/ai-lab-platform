import SwiftUI

public struct MemoryCenterView: View {
    @EnvironmentObject private var api: APIClient
    @State private var center: HermesMemoryCenterDTO?
    @State private var isLoading = true
    @State private var errorMessage: String?
    @State private var editor: MemoryEditorContext?
    @State private var pendingDeletion: HermesMemoryDTO?
    @State private var isSaving = false

    public init() {}

    public var body: some View {
        ZStack {
            QuantumMistBackground()

            ScrollView {
                LazyVStack(spacing: AppTheme.Spacing.lg) {
                    overviewCard
                    memorySection(
                        target: "user",
                        title: "关于你",
                        subtitle: "稳定的身份、偏好与长期目标",
                        icon: "person.text.rectangle",
                        tint: AppTheme.Colors.quantumViolet
                    )
                    memorySection(
                        target: "memory",
                        title: "工作方法",
                        subtitle: "Hermes 逐步积累的经验与协作方式",
                        icon: "point.3.connected.trianglepath.dotted",
                        tint: AppTheme.Colors.quantumCyan
                    )
                    privacyNote
                }
                .padding(.horizontal, AppTheme.Metrics.contentGutter)
                .padding(.vertical, AppTheme.Spacing.lg)
            }
            .refreshable { await load() }

            if isLoading, center == nil {
                ProgressView("正在读取 Hermes 记忆…")
                    .padding(AppTheme.Spacing.xl)
                    .background(AppTheme.Colors.cardBackground)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
            }
        }
        .navigationTitle("记忆中心")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    editor = MemoryEditorContext(target: "user")
                } label: {
                    Image(systemName: "plus")
                        .minimumTouchTarget()
                }
                .disabled(isSaving)
                .accessibilityLabel("添加记忆")
            }
        }
        .task { await load() }
        .sheet(item: $editor) { context in
            MemoryEditorSheet(
                context: context,
                limit: limit(for: context.target),
                isSaving: isSaving,
                onSave: { target, content in
                    Task { await save(context, target: target, content: content) }
                }
            )
            .presentationDetents([.medium, .large])
            .presentationBackground(AppTheme.Colors.cardBackground)
        }
        .confirmationDialog(
            "删除这条记忆？",
            isPresented: Binding(
                get: { pendingDeletion != nil },
                set: { if !$0 { pendingDeletion = nil } }
            ),
            titleVisibility: .visible
        ) {
            Button("删除", role: .destructive) {
                guard let item = pendingDeletion else { return }
                pendingDeletion = nil
                Task { await remove(item) }
            }
            Button("取消", role: .cancel) { pendingDeletion = nil }
        } message: {
            Text("删除后，Hermes 将不再把它作为长期背景使用。")
        }
    }

    private var overviewCard: some View {
        HStack(spacing: AppTheme.Spacing.lg) {
            MemoryOrbitMark()

            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                Text("持续成长，也始终可控")
                    .font(AppTheme.Typography.cardTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Text("Hermes 会在约 \(center?.reviewIntervalTurns ?? 10) 轮对话后复盘一次，并只在你的独立空间内沉淀长期信息。")
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .padding(AppTheme.Spacing.lg)
        .quantumCard()
    }

    private func memorySection(
        target: String,
        title: String,
        subtitle: String,
        icon: String,
        tint: Color
    ) -> some View {
        let items = center?.items.filter { $0.target == target } ?? []
        let used = center?.usage[target] ?? 0
        let maximum = limit(for: target)

        return VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack(spacing: AppTheme.Spacing.md) {
                Image(systemName: icon)
                    .font(.headline)
                    .foregroundStyle(tint)
                    .frame(width: 44, height: 44)
                    .background(tint.opacity(0.12))
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm))

                VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
                    Text(title)
                        .font(AppTheme.Typography.cardTitle)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    Text(subtitle)
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                }
                Spacer()
                Button {
                    editor = MemoryEditorContext(target: target)
                } label: {
                    Image(systemName: "plus.circle.fill")
                        .font(.title3)
                        .foregroundStyle(AppTheme.Icons.interactive)
                        .minimumTouchTarget()
                }
                .accessibilityLabel("添加\(title)记忆")
            }

            ProgressView(value: Double(used), total: Double(max(1, maximum)))
                .tint(tint)
            Text("已使用 \(used) / \(maximum) 字符")
                .font(AppTheme.Typography.micro)
                .foregroundStyle(AppTheme.Colors.textTertiary)

            if items.isEmpty {
                Text(errorMessage ?? "尚无内容。你可以主动添加，Hermes 也会在长期协作中逐步沉淀。")
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(errorMessage == nil ? AppTheme.Colors.textSecondary : AppTheme.Colors.statusError)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, AppTheme.Spacing.sm)
            } else {
                ForEach(items) { item in
                    memoryRow(item, tint: tint)
                }
            }
        }
        .padding(AppTheme.Spacing.lg)
        .quantumCard()
    }

    private func memoryRow(_ item: HermesMemoryDTO, tint: Color) -> some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
            Circle()
                .fill(tint)
                .frame(width: 7, height: 7)
                .padding(.top, 7)
                .accessibilityHidden(true)

            Text(item.content)
                .font(AppTheme.Typography.body)
                .foregroundStyle(AppTheme.Colors.textPrimary)
                .frame(maxWidth: .infinity, alignment: .leading)

            Menu {
                Button("编辑", systemImage: "pencil") {
                    editor = MemoryEditorContext(item: item)
                }
                Button("删除", systemImage: "trash", role: .destructive) {
                    pendingDeletion = item
                }
            } label: {
                Image(systemName: "ellipsis")
                    .foregroundStyle(AppTheme.Icons.tertiary)
                    .minimumTouchTarget()
            }
            .accessibilityLabel("管理记忆")
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.secondaryBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
    }

    private var privacyNote: some View {
        Label {
            Text("记忆与账号、租户双重隔离，并随状态胶囊一起备份。删除操作会直接修改 Hermes 的原生记忆。")
                .font(AppTheme.Typography.supporting)
                .foregroundStyle(AppTheme.Colors.textSecondary)
        } icon: {
            Image(systemName: "lock.shield")
                .foregroundStyle(AppTheme.Icons.interactive)
        }
        .padding(AppTheme.Spacing.lg)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.Colors.selectionTint.opacity(0.72))
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    private func limit(for target: String) -> Int {
        center?.limits[target] ?? (target == "user" ? 1_375 : 2_200)
    }

    @MainActor
    private func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            center = try await api.fetchHermesMemory()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @MainActor
    private func save(
        _ context: MemoryEditorContext,
        target: String,
        content: String
    ) async {
        guard !isSaving else { return }
        isSaving = true
        defer { isSaving = false }
        do {
            center = if let id = context.memoryId {
                try await api.replaceHermesMemory(memoryId: id, content: content)
            } else {
                try await api.addHermesMemory(target: target, content: content)
            }
            errorMessage = nil
            editor = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @MainActor
    private func remove(_ item: HermesMemoryDTO) async {
        do {
            center = try await api.removeHermesMemory(memoryId: item.id)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct MemoryEditorContext: Identifiable {
    let id = UUID()
    let memoryId: String?
    let target: String
    let content: String

    init(target: String) {
        memoryId = nil
        self.target = target
        content = ""
    }

    init(item: HermesMemoryDTO) {
        memoryId = item.id
        target = item.target
        content = item.content
    }
}

private struct MemoryEditorSheet: View {
    @Environment(\.dismiss) private var dismiss
    let context: MemoryEditorContext
    let limit: Int
    let isSaving: Bool
    let onSave: (String, String) -> Void
    @State private var target: String
    @State private var content: String

    init(
        context: MemoryEditorContext,
        limit: Int,
        isSaving: Bool,
        onSave: @escaping (String, String) -> Void
    ) {
        self.context = context
        self.limit = limit
        self.isSaving = isSaving
        self.onSave = onSave
        _target = State(initialValue: context.target)
        _content = State(initialValue: context.content)
    }

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                if context.memoryId == nil {
                    Picker("记忆类型", selection: $target) {
                        Text("关于你").tag("user")
                        Text("工作方法").tag("memory")
                    }
                    .pickerStyle(.segmented)
                }

                TextEditor(text: $content)
                    .font(AppTheme.Typography.body)
                    .scrollContentBackground(.hidden)
                    .padding(AppTheme.Spacing.sm)
                    .frame(minHeight: 150)
                    .background(AppTheme.Colors.secondaryBackground)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                    .overlay {
                        RoundedRectangle(cornerRadius: AppTheme.Radius.md)
                            .stroke(AppTheme.Colors.border, lineWidth: 0.75)
                    }
                    .onChange(of: content) { _, value in
                        if value.count > effectiveLimit {
                            content = String(value.prefix(effectiveLimit))
                        }
                    }

                Text("\(content.count) / \(effectiveLimit) 字符")
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.textTertiary)
                    .frame(maxWidth: .infinity, alignment: .trailing)

                Text(target == "user" ? "适合保存称呼、偏好、长期目标与稳定约束。" : "适合保存反复有效的工作流程、判断标准与协作经验。")
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                Spacer()
            }
            .padding(AppTheme.Metrics.contentGutter)
            .background(AppTheme.Colors.background)
            .navigationTitle(context.memoryId == nil ? "添加记忆" : "编辑记忆")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("保存") { onSave(target, content.trimmingCharacters(in: .whitespacesAndNewlines)) }
                        .disabled(content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSaving)
                }
            }
        }
    }

    private var effectiveLimit: Int {
        context.memoryId == nil ? (target == "user" ? 1_375 : 2_200) : limit
    }
}

private struct MemoryOrbitMark: View {
    var body: some View {
        ZStack {
            Circle()
                .stroke(AppTheme.Colors.quantumBlue.opacity(0.22), lineWidth: 1)
                .frame(width: 58, height: 58)
            Circle()
                .fill(AppTheme.Colors.quantumViolet)
                .frame(width: 10, height: 10)
                .offset(x: 22, y: -13)
            Circle()
                .fill(AppTheme.Colors.quantumCyan)
                .frame(width: 8, height: 8)
                .offset(x: -20, y: 16)
            Image(systemName: "brain.head.profile")
                .font(.title2.weight(.medium))
                .foregroundStyle(AppTheme.Icons.interactive)
        }
        .frame(width: 64, height: 64)
        .accessibilityHidden(true)
    }
}

#Preview {
    NavigationStack { MemoryCenterView() }
        .environmentObject(APIClient.shared)
}
