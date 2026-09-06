//
//  SettingsView.swift
//  AIPlatformApp
//
//  个人中心：个人信息卡（点击编辑 sheet）→ Token 极简卡 → 账号操作。
//

import SwiftUI

public struct SettingsView: View {
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var api: APIClient

    @State private var showingProfileEdit: Bool = false
    /// 云端真实数据（无任何演示数据）：拓扑/设置同源消费
    @State private var cloudAgents: [TenantAgentDTO] = []
    @State private var cloudSkills: [TenantSkillDTO] = []
    @State private var subscriptionSummary: SubscriptionCenterResponse? = nil
    @State private var skillPendingDeletion: TenantSkillDTO?
    @State private var isDeletingSkill = false
    @State private var skillDeletionFeedback: SkillDeletionFeedback?

    public init() {}

    public var body: some View {
        NavigationStack {
            ZStack {
                QuantumMistBackground()

                ScrollView {
                    VStack(spacing: AppTheme.Spacing.lg) {

                        settingsOverviewHeader
                            .padding(.horizontal, AppTheme.Metrics.contentGutter)
                            .padding(.top, AppTheme.Spacing.lg)

                        TokenSummaryCard()
                            .padding(.horizontal, AppTheme.Metrics.contentGutter)

                        // 1. 用户与租户身份卡（点击编辑）
                        tenantProfileCard
                            .padding(.horizontal, AppTheme.Metrics.contentGutter)

                        // 2. 知识订阅与套餐
                        subscriptionEntryCard
                            .padding(.horizontal, AppTheme.Metrics.contentGutter)

                        // 3. 我创建的智能体 + 我制作的技能（纯云端真实数据）
                        VStack(spacing: AppTheme.Spacing.md) {
                            createdAgentsSection()
                            createdSkillsSection()
                        }
                        .padding(.horizontal, AppTheme.Metrics.contentGutter)

                        // 4. 平台定时任务区块已移除（后续统一对接 Hermes cronjob 体系，需求6）

                        // 5. 平台与账号操作
                        accountActionsSection
                            .padding(.horizontal, AppTheme.Metrics.contentGutter)
                            .padding(.bottom, AppTheme.Spacing.xl)
                    }
                }
            }
            .toolbar(.hidden, for: .navigationBar)
            .sheet(isPresented: $showingProfileEdit) {
                ProfileEditSheet()
            }
            .task {
                // 云端真实数据（非演示）：智能体 + 技能，拓扑/设置同源消费
                if let list = try? await APIClient.shared.fetchTenantAgents(ownedOnly: true) {
                    cloudAgents = list
                }
                if let skills = try? await APIClient.shared.fetchTenantSkills(ownedOnly: true) {
                    cloudSkills = skills
                }
                subscriptionSummary = try? await api.fetchSubscriptionCenter()
            }
            .confirmationDialog(
                "删除技能「\(skillPendingDeletion?.name ?? "")」？",
                isPresented: Binding(
                    get: { skillPendingDeletion != nil },
                    set: { if !$0 { skillPendingDeletion = nil } }
                ),
                titleVisibility: .visible
            ) {
                Button("确认删除", role: .destructive) {
                    guard let skill = skillPendingDeletion else { return }
                    skillPendingDeletion = nil
                    Task { await deleteSkill(skill) }
                }
                Button("取消", role: .cancel) { skillPendingDeletion = nil }
            } message: {
                Text("删除后会从当前个人工作空间的 Hermes 技能库移除，无法撤销。")
            }
            .alert(item: $skillDeletionFeedback) { feedback in
                Alert(
                    title: Text(feedback.succeeded ? "技能已删除" : "删除失败"),
                    message: Text(feedback.message),
                    dismissButton: .default(Text("知道了"))
                )
            }
        }
    }

    private var subscriptionEntryCard: some View {
        NavigationLink {
            SubscriptionCenterView()
        } label: {
            HStack(spacing: AppTheme.Spacing.md) {
                Image(systemName: "creditcard.and.123")
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundColor(AppTheme.Icons.onAccent)
                    .frame(width: 48, height: 48)
                    .background(AppTheme.Colors.quantumGradient)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))

                VStack(alignment: .leading, spacing: 4) {
                    Text("知识订阅与套餐")
                        .font(.system(size: 16, weight: .bold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                    Text(subscriptionSummary?.subscription?.planName ?? "查看可用套餐与知识权益")
                        .font(AppTheme.Typography.supporting)
                        .foregroundColor(AppTheme.Colors.textSecondary)
                    if let count = subscriptionSummary?.pendingCount, count > 0 {
                        Label("\(count) 项等待审批", systemImage: "clock.badge.exclamationmark")
                            .font(AppTheme.Typography.micro)
                            .foregroundColor(AppTheme.Colors.securityYellow)
                    }
                }

                Spacer()
                Image(systemName: "chevron.right")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(AppTheme.Icons.tertiary)
            }
            .padding(AppTheme.Spacing.lg)
            .frame(minHeight: 88)
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(AppTheme.Colors.border, lineWidth: 0.75)
            }
        }
        .buttonStyle(SoftButtonStyle())
        .accessibilityLabel("知识订阅与套餐，\(subscriptionSummary?.subscription?.planName ?? "未选择套餐")")
    }

    private var settingsOverviewHeader: some View {
        HStack(alignment: .center, spacing: AppTheme.Spacing.md) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Overview")
                    .font(.system(size: 32, weight: .semibold, design: .rounded))
                    .foregroundColor(AppTheme.Colors.textPrimary)
                Text("账户、用量与工作空间")
                    .font(AppTheme.Typography.supporting)
                    .foregroundColor(AppTheme.Colors.textSecondary)
            }
            Spacer()
            Button { showingProfileEdit = true } label: {
                Image(systemName: "person.crop.circle")
                    .font(.title3.weight(.semibold))
                    .foregroundColor(AppTheme.Colors.textPrimary)
                    .minimumTouchTarget()
                    .background(AppTheme.Colors.cardBackground)
                    .clipShape(Circle())
                    .overlay { Circle().stroke(AppTheme.Colors.border, lineWidth: 0.75) }
            }
            .buttonStyle(SoftButtonStyle())
            .accessibilityLabel("编辑个人资料")
        }
    }

    // MARK: - 1. 用户与租户身份卡

    private var tenantProfileCard: some View {
        Button(action: {
            #if os(iOS)
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            #endif
            showingProfileEdit = true
        }) {
            HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                // Avatar（SF Symbol 头像）
                ZStack {
                    Circle()
                        .fill(AppTheme.Colors.selectionTint)
                        .frame(width: 56, height: 56)
                    Image(systemName: appState.currentProfile.avatarUrl ?? "person.crop.circle.fill")
                        .font(.system(size: 28))
                        .foregroundColor(AppTheme.Icons.intelligence)
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text("PROFILE · TENANT WORKSPACE")
                        .font(AppTheme.Typography.micro)
                        .tracking(0.7)
                        .foregroundColor(AppTheme.Icons.interactive)

                    HStack(spacing: 6) {
                        Text(appState.currentProfile.name)
                            .font(.system(size: 17, weight: .bold))
                            .foregroundColor(AppTheme.Colors.textPrimary)

                        if appState.currentProfile.isVipLane {
                            HStack(spacing: 2) {
                                Image(systemName: "crown.fill")
                                    .font(.system(size: 10))
                                Text("VIP")
                                    .font(.system(size: 10, weight: .black))
                            }
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .foregroundColor(AppTheme.Colors.securityYellow)
                            .background(AppTheme.Colors.onSemantic.opacity(0.9))
                            .clipShape(Capsule())
                        }
                    }

                    Text("普通用户")
                        .font(.system(size: 12))
                        .foregroundColor(AppTheme.Colors.textSecondary)

                    Text("个人工作空间")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(AppTheme.Colors.statusCompleted)
                }

                Spacer()

                Image(systemName: "pencil")
                    .font(.system(size: 13))
                    .foregroundColor(AppTheme.Icons.tertiary)
            }
            .padding(AppTheme.Spacing.xl)
            .background(
                LinearGradient(
                    colors: [AppTheme.Colors.cardBackground, AppTheme.Colors.surfaceTint],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(AppTheme.Colors.border.opacity(0.75), lineWidth: 0.75)
            }
            .shadow(color: Color(hex: "3D437E").opacity(0.08), radius: 18, y: 7)
        }
        .buttonStyle(SoftButtonStyle())
    }

    // MARK: - 我创建的智能体 + 我制作的技能（纯云端真实数据）

    private func createdAgentsSection() -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            artifactHeader(icon: "sparkles", title: "我创建的智能体", accent: AppTheme.Colors.quantumViolet)
            let rows = cloudAgents.map { agent in
                AgentRowData(
                    id: agent.id,
                    name: agent.customName ?? agent.baseAgentId,
                    responsibility: agent.privatePromptDelta.isEmpty ? "基于基线 \(agent.baseAgentId) 的租户私有切片" : agent.privatePromptDelta,
                    createdAt: agent.createdAt ?? "",
                    accent: AppTheme.Colors.quantumViolet
                )
            }
            if rows.isEmpty {
                emptyArtifactHint("尚未创建智能体，请在任务页创建任务，或在对话中提出「创建一个…的agent」")
            } else {
                ForEach(rows) { row in
                    artifactRow(
                        name: row.name,
                        responsibility: row.responsibility,
                        createdAt: row.createdAt,
                        accent: AppTheme.Colors.quantumViolet,
                        onDelete: {
                            Task {
                                if (try? await APIClient.shared.deleteTenantAgent(id: row.id)) != nil {
                                    cloudAgents.removeAll { $0.id == row.id }
                                }
                            }
                        }
                    )
                }
            }
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                .stroke(AppTheme.Colors.border.opacity(0.7), lineWidth: 0.75)
        }
    }

    private struct AgentRowData: Identifiable {
        let id: String
        let name: String
        let responsibility: String
        let createdAt: String
        let accent: Color
    }

    private func createdSkillsSection() -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            artifactHeader(icon: "bolt.fill", title: "我制作的技能", accent: AppTheme.Colors.quantumCyan)
            if cloudSkills.isEmpty {
                emptyArtifactHint("尚未制作技能——在对话中提出「创建一个…的agent」将自动生成租户专属技能")
            } else {
                ForEach(cloudSkills) { skill in
                    artifactRow(
                        name: skill.name,
                        responsibility: skill.description.isEmpty ? "租户专属技能" : skill.description,
                        createdAt: skill.createdAt ?? "",
                        accent: AppTheme.Colors.quantumCyan,
                        deleteDisabled: isDeletingSkill,
                        onDelete: { skillPendingDeletion = skill }
                    )
                }
            }
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                .stroke(AppTheme.Colors.border.opacity(0.7), lineWidth: 0.75)
        }
    }

    private func artifactHeader(icon: String, title: String, accent: Color) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(accent)
            Text(title)
                .font(.system(size: 14, weight: .bold))
                .foregroundColor(AppTheme.Colors.textPrimary)
            Spacer()
        }
    }

    private func emptyArtifactHint(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 12))
                            .foregroundColor(AppTheme.Icons.tertiary)
            .padding(.vertical, AppTheme.Spacing.sm)
            .frame(maxWidth: .infinity)
    }

    /// 云端真实记录卡：名称 / 职责 / 创建时间 + 删除。
    private func artifactRow(
        name: String,
        responsibility: String,
        createdAt: String,
        accent: Color,
        deleteDisabled: Bool = false,
        onDelete: @escaping () -> Void
    ) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                Circle()
                    .fill(accent.opacity(0.2))
                    .frame(width: 8, height: 8)
                Text(name)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.textPrimary)
                    .lineLimit(1)
                Spacer()
                Button(action: onDelete) {
                    Image(systemName: "trash")
                        .font(.system(size: 12))
                        .foregroundColor(AppTheme.Icons.tertiary)
                        .minimumTouchTarget()
                }
                .buttonStyle(SoftButtonStyle())
                .disabled(deleteDisabled)
                .accessibilityLabel("删除 \(name)")
            }
            Text(responsibility)
                .font(.system(size: 12))
                .foregroundColor(AppTheme.Colors.textSecondary)
                .lineSpacing(1)
            if !createdAt.isEmpty {
                Text("创建于 \(createdAt)")
                    .font(.system(size: 11))
                    .foregroundColor(AppTheme.Colors.textTertiary)
            }
        }
        .padding(AppTheme.Spacing.sm)
        .background(AppTheme.Colors.secondaryBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
    }

    @MainActor
    private func deleteSkill(_ skill: TenantSkillDTO) async {
        guard !isDeletingSkill else { return }
        isDeletingSkill = true
        defer { isDeletingSkill = false }
        do {
            try await APIClient.shared.deleteTenantSkill(name: skill.name)
            let refreshed = try await APIClient.shared.fetchTenantSkills(ownedOnly: true)
            guard !refreshed.contains(where: { $0.name == skill.name }) else {
                throw SkillDeletionError.notVerified
            }
            cloudSkills = refreshed
            skillDeletionFeedback = SkillDeletionFeedback(
                succeeded: true,
                message: "「\(skill.name)」已从当前个人工作空间移除。"
            )
        } catch {
            skillDeletionFeedback = SkillDeletionFeedback(
                succeeded: false,
                message: error.localizedDescription
            )
        }
    }

    private struct SkillDeletionFeedback: Identifiable {
        let id = UUID()
        let succeeded: Bool
        let message: String
    }

    private enum SkillDeletionError: LocalizedError {
        case notVerified

        var errorDescription: String? {
            "服务端未确认技能已删除，请稍后重试。"
        }
    }

    // MARK: - 5. 账号操作

    private var accountActionsSection: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            Button(action: {
                #if os(iOS)
                UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                #endif
                withAnimation(.spring()) {
                    appState.logout()
                }
            }) {
                HStack {
                    Image(systemName: "arrow.backward.circle.fill")
                    Text("退出登录 / 切换租户")
                        .font(.system(size: 14, weight: .semibold))
                }
            .foregroundColor(AppTheme.Icons.destructive)
                .frame(maxWidth: .infinity)
                .frame(height: 44)
                .background(AppTheme.Colors.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
            }

            Text("Quantumn \(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "—") (Build \(Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "—"))")
                .font(.system(size: 11))
                .foregroundColor(AppTheme.Colors.textTertiary)
                .padding(.top, 4)
        }
    }
}

// MARK: - Knowledge subscription center

public struct SubscriptionCenterView: View {
    @EnvironmentObject private var api: APIClient
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private let highlightedEntitlementKey: String?
    private let previewCenter: SubscriptionCenterResponse?
    private let onBack: (() -> Void)?

    @State private var center: SubscriptionCenterResponse?
    @State private var knowledgeAccess: KnowledgeAccessResponse?
    @State private var bookshelves: [KnowledgeBookshelfDTO] = []
    @State private var adminRequests: [SubscriptionRequestDTO] = []
    @State private var isLoading = true
    @State private var busyID: String?
    @State private var errorMessage: String?
    @State private var successMessage: String?
    @State private var requestIDsByPlan: [String: String] = [:]
    @State private var selectedPlanID: String?
    @State private var selectedPackIDs: Set<String> = []
    @State private var selectedShelfID: String?
    @State private var bookshelfQuery = ""
    @State private var inspectedBook: KnowledgeBookDTO?
    @State private var subscribedBookIDs: Set<String> = []
    @State private var subscriptionBusyBookID: String?
    @State private var inspectedPack: KnowledgePackDTO?
    @State private var booksRevealed = false
    @State private var publicationCandidates: [KnowledgePublicationCandidateDTO] = []
    @State private var inspectedCandidate: KnowledgePublicationCandidateDTO?
    @State private var publicationSecurity = "green"
    @State private var publicationEntitlement = ""
    @State private var publicationOwner = ""
    @State private var showingPlanManagement = false
    @Namespace private var bookshelfTransition

    public init(
        highlightedEntitlementKey: String? = nil,
        previewCenter: SubscriptionCenterResponse? = nil,
        onBack: (() -> Void)? = nil
    ) {
        self.highlightedEntitlementKey = highlightedEntitlementKey
        self.previewCenter = previewCenter
        self.onBack = onBack
        _center = State(initialValue: previewCenter)
        _bookshelves = State(initialValue: previewCenter?.bookshelves ?? [])
        _isLoading = State(initialValue: previewCenter == nil)
        _selectedShelfID = State(initialValue: ProcessInfo.processInfo.arguments.contains("-bookshelfDetailPreview") ? previewCenter?.bookshelves?.first?.id : nil)
        _inspectedBook = State(initialValue: ProcessInfo.processInfo.arguments.contains("-bookshelfBookPreview") ? previewCenter?.bookshelves?.first?.books.first : nil)
        _subscribedBookIDs = State(initialValue: ProcessInfo.processInfo.arguments.contains("-bookshelfSubscribedPreview") ? Set(previewCenter?.bookshelves?.first?.books.prefix(1).map(\.id) ?? []) : [])
    }

    public var body: some View {
        ZStack {
            QuantumMistBackground()

            if showingPlanManagement {
                subscriptionManagement
            } else if isLoading, bookshelves.isEmpty {
                ProgressView("正在整理书架…")
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            } else if let selectedShelfID,
                      let shelf = bookshelves.first(where: { $0.id == selectedShelfID }) {
                bookshelfDetail(shelf)
                    .transition(.opacity)
            } else if !bookshelves.isEmpty {
                bookshelfCollections(bookshelves)
                    .transition(.opacity)
            } else if let errorMessage {
                inlineError(errorMessage)
                    .padding(AppTheme.Metrics.contentGutter)
            } else {
                ContentUnavailableView("暂无知识书架", systemImage: "books.vertical", description: Text("可在右上角查看组织权益与订阅状态。"))
                    .padding(AppTheme.Metrics.contentGutter)
            }

            if let successMessage {
                VStack {
                    Spacer()
                    Label(successMessage, systemImage: "checkmark.circle.fill")
                        .font(AppTheme.Typography.supporting.weight(.semibold))
                        .foregroundStyle(AppTheme.Colors.onPrimary)
                        .padding(.horizontal, AppTheme.Spacing.lg)
                        .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                        .background(AppTheme.Colors.statusCompleted)
                        .clipShape(Capsule())
                        .shadow(color: Color.black.opacity(0.16), radius: 14, y: 6)
                        .padding(.bottom, AppTheme.Spacing.xl)
                }
                .transition(.move(edge: .bottom).combined(with: .opacity))
                .allowsHitTesting(false)
            }
        }
        .navigationTitle(showingPlanManagement ? "知识订阅" : "知识书架")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .navigationBarBackButtonHidden(true)
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                if selectedShelfID != nil {
                    Button {
                        withAnimation(reduceMotion ? nil : .spring(response: 0.48, dampingFraction: 0.86)) {
                            selectedShelfID = nil
                            bookshelfQuery = ""
                        }
                    } label: {
                        Image(systemName: "chevron.left")
                            .frame(width: 44, height: 44)
                    }
                    .accessibilityLabel("返回分类")
                } else {
                    Button {
                        if let onBack { onBack() } else { dismiss() }
                    } label: {
                        Image(systemName: "chevron.left")
                            .frame(width: 44, height: 44)
                    }
                    .accessibilityLabel("返回知识")
                }
            }
            ToolbarItem(placement: .topBarTrailing) {
                if selectedShelfID == nil {
                    Button(showingPlanManagement ? "书架" : "权益") {
                        withAnimation(reduceMotion ? nil : AppTheme.Motion.quick) {
                            showingPlanManagement.toggle()
                        }
                    }
                    .accessibilityLabel(showingPlanManagement ? "返回知识书架" : "查看组织权益与订阅")
                }
            }
        }
        .task {
            guard previewCenter == nil else { return }
            await load()
            await loadBookshelves()
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if showingPlanManagement, let center, center.isSuperAdmin { stickyApplicationBar(center) }
        }
        .fullScreenCover(item: $inspectedBook) { book in
            knowledgeBookDetail(book)
        }
        .sheet(item: $inspectedPack) { pack in
            knowledgePackDetail(pack)
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
        .sheet(item: $inspectedCandidate) { candidate in
            publicationApprovalSheet(candidate)
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
        .task {
            guard !booksRevealed else { return }
            withAnimation(reduceMotion ? nil : .spring(response: 0.42, dampingFraction: 0.82).delay(0.08)) {
                booksRevealed = true
            }
        }
    }

    private var subscriptionManagement: some View {
        ScrollView {
            LazyVStack(spacing: AppTheme.Spacing.lg) {
                if isLoading, center == nil {
                    ProgressView("正在同步组织套餐与知识权益…")
                        .frame(maxWidth: .infinity, minHeight: 180)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                } else if let center {
                    currentPlanCard(center)
                    if center.isSuperAdmin {
                        requestSection(center.requests)
                        plansSection(center)
                        if !publicationCandidates.isEmpty {
                            publicationApprovalSection
                        }
                        knowledgePacksSection(center)
                        adminSection
                    }
                }

                if let errorMessage {
                    inlineError(errorMessage)
                }
            }
            .padding(.horizontal, AppTheme.Metrics.contentGutter)
            .padding(.top, AppTheme.Spacing.md)
            .padding(.bottom, AppTheme.Spacing.xxxl)
        }
        .refreshable { await load() }
    }

    private func bookshelfCollections(_ allShelves: [KnowledgeBookshelfDTO]) -> some View {
        let shelves = allShelves.filter { shelf in
            bookshelfQuery.isEmpty || shelf.title.localizedStandardContains(bookshelfQuery)
                || shelf.books.contains { $0.title.localizedStandardContains(bookshelfQuery) || $0.author.localizedStandardContains(bookshelfQuery) }
        }
        return ScrollView {
            LazyVStack(spacing: AppTheme.Spacing.lg) {
                bookshelfSearch(placeholder: "搜索分类或作者")
                HStack {
                    Text("全部收藏")
                        .font(AppTheme.Typography.micro.weight(.semibold))
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                    Spacer()
                    Text("\(shelves.count) 个分类")
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textTertiary)
                }
                if shelves.isEmpty {
                    ContentUnavailableView("没有匹配的书", systemImage: "books.vertical", description: Text("试试其他书名、作者或分类。"))
                        .frame(minHeight: 300)
                } else {
                    ForEach(Array(shelves.enumerated()), id: \.element.id) { index, shelf in
                        bookshelfCollectionCard(shelf)
                            .opacity(booksRevealed ? 1 : 0)
                            .offset(y: booksRevealed ? 0 : 22)
                            .animation(reduceMotion ? nil : .spring(response: 0.46, dampingFraction: 0.86).delay(Double(index) * 0.06), value: booksRevealed)
                    }
                }
                if let errorMessage { inlineError(errorMessage) }
            }
            .padding(.horizontal, AppTheme.Metrics.contentGutter)
            .padding(.top, AppTheme.Spacing.sm)
            .padding(.bottom, AppTheme.Spacing.xxxl)
        }
        .refreshable { await loadBookshelves() }
    }

    private func bookshelfSearch(placeholder: String) -> some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(AppTheme.Colors.textTertiary)
            TextField(placeholder, text: $bookshelfQuery)
                .textInputAutocapitalization(.never)
                .submitLabel(.search)
            if !bookshelfQuery.isEmpty {
                Button { bookshelfQuery = "" } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(AppTheme.Colors.textTertiary)
                        .frame(width: 44, height: 44)
                }
                .accessibilityLabel("清除搜索")
            }
            Image(systemName: "slider.horizontal.3")
                .foregroundStyle(AppTheme.Colors.textSecondary)
                .frame(width: 28)
                .accessibilityHidden(true)
        }
        .font(AppTheme.Typography.supporting)
        .padding(.leading, AppTheme.Spacing.md)
        .padding(.trailing, AppTheme.Spacing.sm)
        .frame(minHeight: 48)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(Capsule())
        .shadow(color: Color.black.opacity(0.08), radius: 12, y: 5)
    }

    private func bookshelfCollectionCard(_ shelf: KnowledgeBookshelfDTO) -> some View {
        Button {
            withAnimation(reduceMotion ? nil : .spring(response: 0.52, dampingFraction: 0.84)) {
                selectedShelfID = shelf.id
                bookshelfQuery = ""
            }
        } label: {
            VStack(spacing: 0) {
                HStack {
                    Label("刚刚更新", systemImage: "clock")
                    Spacer()
                    Label("\(shelf.bookCount)", systemImage: "books.vertical")
                }
                .font(.caption2)
                .foregroundStyle(AppTheme.Colors.textTertiary)
                .padding(.horizontal, AppTheme.Spacing.lg)
                .padding(.top, AppTheme.Spacing.md)

                Text(shelf.title)
                    .font(AppTheme.Typography.cardTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                    .padding(.top, 3)
                Text(shelfSubtitle(shelf))
                    .font(.caption)
                    .foregroundStyle(AppTheme.Colors.textSecondary)

                Spacer(minLength: 8)
                ZStack(alignment: .bottom) {
                    HStack(alignment: .bottom, spacing: -12) {
                        ForEach(Array(shelf.books.prefix(3).enumerated()), id: \.element.id) { index, book in
                            bookCover(title: book.title, author: book.author, seed: book.id, theme: book.coverTheme, variant: book.coverVariant, width: 82)
                                .rotationEffect(.degrees(Double(index - 1) * 5))
                                .zIndex(Double(index == 1 ? 2 : index))
                                .matchedGeometryEffect(id: "\(shelf.id)-\(book.id)", in: bookshelfTransition)
                        }
                    }
                    .padding(.bottom, 8)
                    shelfPlank
                }
                .frame(height: 132)
                .clipped()
            }
            .frame(maxWidth: .infinity)
            .frame(height: 218)
            .background(AppTheme.Colors.secondaryBackground.opacity(0.86))
            .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        }
        .buttonStyle(SoftButtonStyle())
        .accessibilityLabel("\(shelf.title)，\(shelf.bookCount) 本书")
        .accessibilityHint("点按打开分类书架")
    }

    private func bookshelfDetail(_ shelf: KnowledgeBookshelfDTO) -> some View {
        let books = shelf.books.filter {
            bookshelfQuery.isEmpty || $0.title.localizedStandardContains(bookshelfQuery) || $0.author.localizedStandardContains(bookshelfQuery)
        }
        return ScrollView {
            VStack(spacing: AppTheme.Spacing.lg) {
                Text(shelf.title)
                    .font(AppTheme.Typography.sectionTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Text(shelfSubtitle(shelf))
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                bookshelfSearch(placeholder: "搜索这个书架")
                HStack {
                    Text("书架上的精选")
                        .font(AppTheme.Typography.micro.weight(.semibold))
                    Spacer()
                    Text("\(books.count) 本")
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textTertiary)
                }

                if books.isEmpty {
                    ContentUnavailableView("没有匹配的书", systemImage: "book.closed", description: Text("试试其他书名或作者。"))
                        .frame(minHeight: 300)
                } else {
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], alignment: .center, spacing: AppTheme.Spacing.xl) {
                        ForEach(Array(books.enumerated()), id: \.element.id) { index, book in
                            Button { inspectedBook = book } label: {
                                bookCover(title: book.title, author: book.author, seed: book.id, theme: book.coverTheme, variant: book.coverVariant, width: 140)
                                    .matchedGeometryEffect(id: "\(shelf.id)-\(book.id)", in: bookshelfTransition)
                                    .opacity(booksRevealed ? 1 : 0)
                                    .offset(y: booksRevealed ? (index.isMultiple(of: 2) ? 0 : 36) : 54)
                                    .rotationEffect(.degrees(index.isMultiple(of: 2) ? -1.5 : 1.8))
                                    .animation(reduceMotion ? nil : .spring(response: 0.42, dampingFraction: 0.86).delay(Double(index) * 0.035), value: booksRevealed)
                            }
                            .buttonStyle(SoftButtonStyle())
                            .accessibilityLabel("\(book.title)，作者 \(book.author)")
                            .accessibilityHint("点按查看概要")
                        }
                    }
                    .padding(.bottom, 36)
                }
            }
            .padding(.horizontal, AppTheme.Metrics.contentGutter)
            .padding(.top, AppTheme.Spacing.md)
            .padding(.bottom, AppTheme.Spacing.xxxl)
        }
    }

    private func shelfSubtitle(_ shelf: KnowledgeBookshelfDTO) -> String {
        switch shelf.title {
        case "产品与方案": return "从问题到产品，理解一套完整解法"
        case "方法论": return "把复杂工作变成可重复的方法"
        case "战略信号": return "从变化中辨认真正值得行动的信号"
        case "竞品档案", "竞品情报": return "看清头部公司的产品、技术与选择"
        case "客户洞察": return "从业务现场理解真实需求"
        default: return "为你精选的 Quantum 知识收藏"
        }
    }

    private func bookCover(
        title: String,
        author: String,
        seed: String,
        theme: String? = nil,
        variant: Int? = nil,
        width: CGFloat = 112
    ) -> some View {
        let resolvedVariant = variant ?? stableCoverVariant(seed)
        let colors = coverColors(theme: theme, variant: resolvedVariant)
        return ZStack {
            LinearGradient(colors: colors, startPoint: .topLeading, endPoint: .bottomTrailing)
                .opacity(0.34)
            Color.white.opacity(0.34)
            coverArtwork(resolvedVariant)
                .foregroundStyle(AppTheme.Colors.primary.opacity(0.10))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 0) {
                Rectangle()
                    .fill(AppTheme.Colors.primary.opacity(0.16))
                    .frame(height: 4)
                Text(title)
                    .font((width < 100 ? Font.caption : Font.headline).weight(.bold))
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                    .lineLimit(4)
                    .minimumScaleFactor(0.76)
                    .padding(.horizontal, AppTheme.Spacing.sm)
                    .padding(.top, AppTheme.Spacing.md)
                Spacer(minLength: AppTheme.Spacing.sm)
                Text(author)
                    .font((width < 100 ? Font.system(size: 8) : Font.caption2).weight(.semibold))
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .lineLimit(2)
                    .padding(AppTheme.Spacing.sm)
            }
        }
        .frame(width: width, height: width * 1.41, alignment: .leading)
        .clipShape(RoundedRectangle(cornerRadius: 5, style: .continuous))
        .overlay(alignment: .leading) { Rectangle().fill(AppTheme.Colors.primary.opacity(0.12)).frame(width: 7) }
        .overlay { RoundedRectangle(cornerRadius: 5).stroke(AppTheme.Colors.primary.opacity(0.08), lineWidth: 0.75) }
        .shadow(color: AppTheme.Colors.primary.opacity(0.10), radius: 12, x: 3, y: 8)
    }

    private var shelfPlank: some View {
        RoundedRectangle(cornerRadius: 3, style: .continuous)
            .fill(AppTheme.Colors.border.opacity(0.72))
            .frame(height: 5)
            .shadow(color: AppTheme.Colors.primary.opacity(0.06), radius: 5, y: 3)
    }

    @ViewBuilder
    private func coverArtwork(_ variant: Int) -> some View {
        switch variant % 6 {
        case 0:
            Circle().stroke(lineWidth: 16).frame(width: 104, height: 104).offset(x: 35, y: -28)
        case 1:
            RoundedRectangle(cornerRadius: 12).stroke(lineWidth: 12)
                .frame(width: 92, height: 92).rotationEffect(.degrees(28)).offset(x: 34, y: -30)
        case 2:
            VStack(spacing: 10) {
                ForEach(0..<5, id: \.self) { _ in Capsule().frame(width: 92, height: 5) }
            }
            .rotationEffect(.degrees(-24))
            .offset(x: 36, y: -26)
        case 3:
            ZStack {
                Circle().stroke(lineWidth: 8).frame(width: 76, height: 76)
                Circle().stroke(lineWidth: 5).frame(width: 42, height: 42)
            }
            .offset(x: 38, y: -32)
        case 4:
            RoundedRectangle(cornerRadius: 4).stroke(lineWidth: 9)
                .frame(width: 68, height: 110).rotationEffect(.degrees(42)).offset(x: 45, y: -34)
        default:
            HStack(spacing: 9) {
                ForEach(0..<5, id: \.self) { _ in Capsule().frame(width: 5, height: 112) }
            }
            .rotationEffect(.degrees(18))
            .offset(x: 40, y: -25)
        }
    }

    private func stableCoverVariant(_ seed: String) -> Int {
        let hash = seed.utf8.reduce(UInt64(14_695_981_039_346_656_037)) {
            ($0 ^ UInt64($1)) &* 1_099_511_628_211
        }
        return Int(hash % 6)
    }

    private func coverColors(theme: String?, variant: Int) -> [Color] {
        let pair: [Color]
        switch theme {
        case "product": pair = [AppTheme.Colors.interactiveBlue, AppTheme.Colors.quantumCyan]
        case "methodology": pair = [AppTheme.Colors.interactiveViolet, AppTheme.Colors.quantumViolet]
        case "strategic-signal": pair = [AppTheme.Colors.emberOrange, AppTheme.Colors.interactiveViolet]
        case "customer": pair = [AppTheme.Colors.statusCompleted, AppTheme.Colors.quantumBlue]
        case "competitor", "competitor-topic": pair = [AppTheme.Colors.emberInk, AppTheme.Colors.emberOrange]
        default: pair = [AppTheme.Colors.primary, AppTheme.Icons.intelligence]
        }
        return variant.isMultiple(of: 2) ? pair : Array(pair.reversed())
    }

    private func knowledgeBookDetail(_ book: KnowledgeBookDTO) -> some View {
        KnowledgeBookReaderView(
            book: book,
            isSubscribed: subscribedBookIDs.contains(book.id),
            isBusy: subscriptionBusyBookID == book.id,
            onToggleSubscription: { Task { await toggleBookSubscription(book) } },
            onSaveExcerpt: { saveBookSummaryToNote(book) },
            onDismiss: { inspectedBook = nil }
        )
    }

    private func currentPlanCard(_ center: SubscriptionCenterResponse) -> some View {
        let effective = knowledgeAccess?.effectiveKnowledge ?? knowledgeAccess?.effectiveCategories.map { category in
            let isPrivate = knowledgeAccess?.tenantPrivateKnowledge?.categories.contains(category) == true
            return EffectiveKnowledgeDTO(
                category: category,
                title: category.split(separator: "/").last.map(String.init) ?? category,
                securityLevel: isPrivate ? "red" : "green",
                source: isPrivate ? "tenant_private" : "runtime",
                documentCount: 0
            )
        } ?? []
        let greenCount = effective.filter { $0.securityLevel == "green" }.count
        let yellowCount = effective.filter { $0.securityLevel == "yellow" }.count
        let redCount = effective.filter { $0.securityLevel == "red" }.count

        return VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            HStack {
                Label("当前可用知识", systemImage: "checkmark.shield.fill")
                    .font(AppTheme.Typography.label)
                    .foregroundStyle(AppTheme.Colors.statusCompleted)
                Spacer()
                Text("运行时真实权限")
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.textTertiary)
            }

            if let subscription = center.subscription {
                HStack(alignment: .firstTextBaseline, spacing: AppTheme.Spacing.sm) {
                    Text(subscription.planName)
                        .font(AppTheme.Typography.sectionTitle)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    Spacer()
                    Label(subscription.status == "active" ? "已生效" : subscription.status, systemImage: "checkmark.circle.fill")
                        .font(AppTheme.Typography.micro.weight(.semibold))
                        .foregroundStyle(AppTheme.Colors.statusCompleted)
                }
                Text("权益版本 V\(subscription.entitlementVersion) · 有效期 \(subscription.effectiveUntil?.dateOnly ?? "长期")")
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.textTertiary)
            } else {
                Text("个人工作空间")
                    .font(AppTheme.Typography.cardTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Text("以下只显示当前账号已被知识网关实际放行的内容。")
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            }

            HStack(spacing: 0) {
                entitlementMetric(value: "\(greenCount)项", label: "公共知识")
                Divider().frame(height: 34)
                entitlementMetric(value: "\(yellowCount)项", label: "受限知识")
                Divider().frame(height: 34)
                entitlementMetric(value: "\(redCount)项", label: "私有知识")
            }
            .padding(.vertical, AppTheme.Spacing.sm)
            .background(AppTheme.Colors.secondaryBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))

            if knowledgeAccess?.entitlementStale == true {
                Label("权益同步状态不可确认，受限知识已按安全策略隐藏。", systemImage: "arrow.triangle.2.circlepath")
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.statusWarning)
            } else if effective.isEmpty {
                ContentUnavailableView("暂无可用知识", systemImage: "books.vertical", description: Text("下拉刷新以重新同步当前账号的知识权限。"))
                    .frame(minHeight: 120)
            } else {
                VStack(spacing: 0) {
                    ForEach(effective) { item in
                        HStack(spacing: AppTheme.Spacing.md) {
                            Image(systemName: item.securityLevel == "green" ? "checkmark.circle.fill" : (item.securityLevel == "yellow" ? "lock.open.fill" : "lock.shield.fill"))
                                .foregroundStyle(item.securityLevel == "green" ? AppTheme.Colors.statusCompleted : (item.securityLevel == "yellow" ? AppTheme.Colors.statusWarning : AppTheme.Colors.primary))
                            VStack(alignment: .leading, spacing: 2) {
                                Text(item.title)
                                    .font(AppTheme.Typography.supporting.weight(.semibold))
                                    .foregroundStyle(AppTheme.Colors.textPrimary)
                                Text("\(item.documentCount) 篇 · \(item.source == "subscription" ? "已获批" : (item.source == "tenant_private" ? "当前工作空间" : "公共可用"))")
                                    .font(AppTheme.Typography.micro)
                                    .foregroundStyle(AppTheme.Colors.textSecondary)
                            }
                            Spacer()
                        }
                        .padding(.vertical, AppTheme.Spacing.sm)
                        if item.id != effective.last?.id { Divider() }
                    }
                }
            }
        }
        .padding(AppTheme.Spacing.xl)
        .subscriptionSurface()
    }

    private func entitlementMetric(value: String, label: String) -> some View {
        VStack(spacing: 2) {
            Text(value)
                .font(AppTheme.Typography.supporting.weight(.semibold))
                .foregroundStyle(AppTheme.Colors.textPrimary)
                .lineLimit(1)
                .minimumScaleFactor(0.75)
            Text(label)
                .font(AppTheme.Typography.micro)
                .foregroundStyle(AppTheme.Colors.textTertiary)
        }
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder
    private func requestSection(_ requests: [SubscriptionRequestDTO]) -> some View {
        let visibleRequests = requests.filter { $0.status == "pending" || $0.status == "rejected" }
        if !visibleRequests.isEmpty {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                Text("申请进度")
                    .font(AppTheme.Typography.cardTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)

                ForEach(visibleRequests) { request in
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                        HStack {
                            Image(systemName: request.status == "pending" ? "clock.fill" : "xmark.circle.fill")
                                .foregroundStyle(request.status == "pending" ? AppTheme.Colors.statusWarning : AppTheme.Colors.statusError)
                            Text(request.targetPlanName)
                                .font(AppTheme.Typography.supporting.weight(.semibold))
                                .foregroundStyle(AppTheme.Colors.textPrimary)
                            Spacer()
                            Text(request.status == "pending" ? "等待审批" : "未通过")
                                .font(AppTheme.Typography.micro)
                                .foregroundStyle(request.status == "pending" ? AppTheme.Colors.statusWarning : AppTheme.Colors.statusError)
                        }
                        if !request.reviewNote.isEmpty {
                            Text(request.reviewNote)
                                .font(AppTheme.Typography.micro)
                                .foregroundStyle(AppTheme.Colors.textSecondary)
                        }
                        if request.status == "pending" {
                            Button(role: .destructive) { cancel(request) } label: {
                                busyLabel(id: request.id, title: "撤销申请", systemImage: "xmark")
                            }
                            .buttonStyle(.bordered)
                            .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
                            .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                            .disabled(busyID != nil)
                        }
                    }
                    .padding(AppTheme.Spacing.md)
                    .background(AppTheme.Colors.secondaryBackground)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                }
            }
            .padding(AppTheme.Spacing.xl)
            .subscriptionSurface()
        }
    }

    private func plansSection(_ center: SubscriptionCenterResponse) -> some View {
        let sortedPlans = center.plans.sorted { lhs, rhs in
            let left = planRank(lhs)
            let right = planRank(rhs)
            return left == right ? lhs.name < rhs.name : left < right
        }

        return VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            sectionHeader(
                step: "01",
                title: "选择平台套餐",
                subtitle: "套餐决定请求额度与可选知识包数量"
            )

            if sortedPlans.isEmpty {
                ContentUnavailableView("暂无可申请套餐", systemImage: "creditcard", description: Text("下拉刷新，或联系平台管理员配置套餐。"))
                    .frame(minHeight: 180)
            } else {
                ScrollView(.horizontal) {
                    LazyHStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                        ForEach(sortedPlans) { plan in
                            planCard(plan, center: center)
                                .frame(width: 276)
                        }
                    }
                    .scrollTargetLayout()
                }
                .scrollIndicators(.hidden)
                .scrollTargetBehavior(.viewAligned)
                .contentMargins(.horizontal, 1, for: .scrollContent)
            }
        }
    }

    private func planCard(_ plan: SubscriptionPlanDTO, center: SubscriptionCenterResponse) -> some View {
        let isCurrent = center.subscription?.planId == plan.id && center.subscription?.status == "active"
        let pending = center.requests.first { $0.targetPlanId == plan.id && $0.status == "pending" }
        let isSelected = selectedPlanID == plan.id
        let allowance = plan.packAllowance ?? 0
        let isCustom = plan.customOnly == true
        let isBuilding = plan.isAvailable == false || plan.availability == "content_building"
        let isBasePlan = plan.name.contains("基础")

        return VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Text(plan.name)
                            .font(AppTheme.Typography.cardTitle)
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                    }
                }
                Spacer(minLength: AppTheme.Spacing.md)
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundStyle(isSelected ? AppTheme.Colors.primary : AppTheme.Colors.textTertiary)
            }

            if let description = plan.description, !description.isEmpty {
                Text(description)
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
            }

            VStack(spacing: AppTheme.Spacing.sm) {
                planFact(icon: "arrow.triangle.2.circlepath", text: plan.requestQuota < 0 ? "请求额度定制" : "\(plan.requestQuota.formatted()) 次请求/月")
                planFact(icon: "sparkles", text: plan.tokenQuota < 0 ? "Token 额度定制" : "\(tokenQuota(plan.tokenQuota))/月")
                if isBasePlan, let baseKnowledge = center.baseKnowledge {
                    planFact(
                        icon: baseKnowledge.isReady ? "checkmark.seal.fill" : "hammer.fill",
                        text: baseKnowledge.isReady
                            ? "自动包含 \(baseKnowledge.documentCount) 篇公共知识"
                            : "公共知识建设中 \(baseKnowledge.documentCount)/\(baseKnowledge.minimumDocumentCount)"
                    )
                } else {
                    planFact(icon: "square.stack.3d.up.fill", text: isCustom ? "知识包按合同配置" : "最多 \(allowance) 个黄色知识包")
                }
            }

            Button {
                select(plan, center: center)
            } label: {
                busyLabel(
                    id: plan.id,
                    title: isCurrent ? "当前套餐" : (isBuilding ? "知识建设中" : (isCustom ? "联系管理员" : (pending == nil ? (isSelected ? "已选择" : "选择套餐") : "等待管理员审批"))),
                    systemImage: isCurrent || isSelected ? "checkmark" : (isBuilding ? "hammer.fill" : (isCustom ? "person.badge.key.fill" : (pending == nil ? "checkmark.circle" : "clock.fill")))
                )
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
            .tint(AppTheme.Colors.primary)
            .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
            .disabled(isCurrent || isBuilding || isCustom || pending != nil || busyID != nil)
        }
        .padding(AppTheme.Spacing.xl)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                .stroke(isSelected ? AppTheme.Colors.primary : AppTheme.Colors.border, lineWidth: isSelected ? 2 : 0.75)
        }
        .accessibilityElement(children: .contain)
    }

    private func planFact(icon: String, text: String) -> some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: icon)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(AppTheme.Colors.primary)
                .frame(width: 20)
            Text(text)
                .font(AppTheme.Typography.micro)
                .foregroundStyle(AppTheme.Colors.textSecondary)
            Spacer()
        }
    }

    private func sectionHeader(step: String, title: String, subtitle: String) -> some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
            Text(step)
                .font(AppTheme.Typography.micro.weight(.bold))
                .foregroundStyle(AppTheme.Colors.primary)
                .frame(width: 36, height: 28)
                .background(AppTheme.Colors.primary.opacity(0.10))
                .clipShape(Capsule())
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(AppTheme.Typography.sectionTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Text(subtitle)
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            }
        }
    }

    private var publicationApprovalSection: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            sectionHeader(
                step: "ADMIN",
                title: "知识发布审批",
                subtitle: "一次批准颜色，Catalog、Authen 与网关自动联动"
            )
            ForEach(publicationCandidates.prefix(6)) { candidate in
                Button {
                    publicationSecurity = candidate.securityLevel
                    publicationEntitlement = candidate.entitlementKey
                    publicationOwner = candidate.ownerTenant
                    inspectedCandidate = candidate
                } label: {
                    HStack(spacing: AppTheme.Spacing.md) {
                        Image(systemName: candidate.securityLevel == "green" ? "checkmark.circle.fill" : (candidate.securityLevel == "yellow" ? "lock.open.fill" : "lock.shield.fill"))
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundStyle(candidate.securityLevel == "green" ? AppTheme.Colors.statusCompleted : (candidate.securityLevel == "yellow" ? AppTheme.Colors.statusWarning : AppTheme.Icons.destructive))
                            .frame(width: 44, height: 44)
                            .background(AppTheme.Colors.secondaryBackground)
                            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                        VStack(alignment: .leading, spacing: 3) {
                            Text(candidate.title)
                                .font(AppTheme.Typography.supporting.weight(.semibold))
                                .foregroundStyle(AppTheme.Colors.textPrimary)
                                .lineLimit(2)
                            Text("建议 \(candidate.securityLevel.uppercased()) · 质量 \(candidate.knowledgeLevel)")
                                .font(AppTheme.Typography.micro)
                                .foregroundStyle(AppTheme.Colors.textSecondary)
                        }
                        Spacer()
                        Text("审批")
                            .font(AppTheme.Typography.micro.weight(.semibold))
                            .foregroundStyle(AppTheme.Colors.primary)
                        Image(systemName: "chevron.right")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(AppTheme.Colors.textTertiary)
                    }
                    .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                    .contentShape(Rectangle())
                }
                .buttonStyle(SoftButtonStyle())
                if candidate.id != publicationCandidates.prefix(6).last?.id { Divider() }
            }
        }
        .padding(AppTheme.Spacing.lg)
        .subscriptionSurface()
    }

    private func publicationApprovalSheet(_ candidate: KnowledgePublicationCandidateDTO) -> some View {
        NavigationStack {
            Form {
                Section("知识条目") {
                    LabeledContent("标题", value: candidate.title)
                    LabeledContent("当前质量", value: candidate.knowledgeLevel)
                    Text(candidate.path)
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                }
                Section("访问决定") {
                    Picker("安全等级", selection: $publicationSecurity) {
                        Text("GREEN").tag("green")
                        Text("YELLOW").tag("yellow")
                        Text("RED").tag("red")
                    }
                    .pickerStyle(.segmented)
                    if publicationSecurity == "yellow" {
                        TextField("精确 entitlement_key", text: $publicationEntitlement)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                    }
                    if publicationSecurity == "red" {
                        TextField("所属租户 owner_tenant", text: $publicationOwner)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                    }
                    Text(publicationSecurity == "green" ? "批准后立即向正式租户开放。" : (publicationSecurity == "yellow" ? "批准后发布知识包，仅向获批订阅租户开放。" : "批准后仅所属租户可用。"))
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                }
                Section {
                    Button { approvePublication(candidate) } label: {
                        busyLabel(id: "publish-\(candidate.id)", title: "批准并自动放行", systemImage: "checkmark.shield.fill")
                            .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget)
                    }
                    .disabled(
                        busyID != nil
                        || (publicationSecurity == "yellow" && publicationEntitlement.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        || (publicationSecurity == "red" && publicationOwner.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    )
                } footer: {
                    Text("K5、来源数量与新鲜度会继续展示，但不再形成第二道权限开关。")
                }
            }
            .navigationTitle("发布审批")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) { Button("取消") { inspectedCandidate = nil } }
            }
        }
    }

    @ViewBuilder
    private func knowledgePacksSection(_ center: SubscriptionCenterResponse) -> some View {
        let packs = (center.knowledgePacks ?? []).sorted { $0.sortOrder < $1.sortOrder }
        let launchPacks = packs.filter { $0.status != "incubating" }
        let candidatePacks = packs.filter { $0.status == "incubating" }
        let readyCount = packs.filter { $0.status == "published" && $0.isSelectable }.count
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            sectionHeader(
                step: "02",
                title: "会员书架",
                subtitle: "这些书是黄色受限知识；先读概要，再决定是否订阅"
            )

            if packs.isEmpty {
                ContentUnavailableView("暂无已登记知识包", systemImage: "square.stack.3d.up.slash", description: Text("管理员批准 Yellow 内容后会自动登记。"))
                    .frame(minHeight: 160)
            } else {
                HStack(spacing: AppTheme.Spacing.sm) {
                    Label("\(launchPacks.count) 个首发包", systemImage: "square.stack.3d.up.fill")
                    Spacer()
                    Text(readyCount == 0 ? "等待内容批准" : "\(readyCount) 个可申请")
                        .foregroundStyle(readyCount == 0 ? AppTheme.Colors.textTertiary : AppTheme.Colors.statusCompleted)
                }
                .font(AppTheme.Typography.micro.weight(.semibold))
                .foregroundStyle(AppTheme.Colors.textSecondary)

                if readyCount == 0 {
                    Label("不再要求凑够 5 篇 K5。管理员批准一条 Yellow 后，对应知识包会自动开放；Green 批准后直接进入公共知识。", systemImage: "info.circle.fill")
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                        .padding(AppTheme.Spacing.md)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(AppTheme.Colors.secondaryBackground)
                        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                }

                ScrollView(.horizontal) {
                    LazyHStack(alignment: .bottom, spacing: AppTheme.Spacing.lg) {
                        ForEach(launchPacks) { pack in
                            premiumBook(pack, center: center)
                        }
                    }
                    .scrollTargetLayout()
                    .padding(.horizontal, AppTheme.Spacing.xs)
                    .padding(.top, AppTheme.Spacing.md)
                }
                .scrollIndicators(.hidden)
                .scrollTargetBehavior(.viewAligned)
                .contentMargins(.horizontal, 1, for: .scrollContent)
                .overlay(alignment: .bottom) {
                    shelfPlank
                        .offset(y: 9)
                        .allowsHitTesting(false)
                }
                .padding(.bottom, AppTheme.Spacing.md)

                if !candidatePacks.isEmpty {
                    DisclosureGroup {
                        VStack(spacing: 0) {
                            ForEach(candidatePacks) { pack in
                                candidatePackRow(pack)
                                if pack.id != candidatePacks.last?.id { Divider() }
                            }
                        }
                        .padding(.top, AppTheme.Spacing.sm)
                    } label: {
                        HStack {
                            Label("候选知识包", systemImage: "tray.full.fill")
                                .font(AppTheme.Typography.supporting.weight(.semibold))
                            Spacer()
                            Text("\(candidatePacks.count) 个")
                                .font(AppTheme.Typography.micro)
                                .foregroundStyle(AppTheme.Colors.textTertiary)
                        }
                    }
                    .tint(AppTheme.Colors.primary)
                    .padding(AppTheme.Spacing.md)
                    .subscriptionSurface()
                }
            }
        }
    }

    private func premiumBook(_ pack: KnowledgePackDTO, center: SubscriptionCenterResponse) -> some View {
        let active = (center.activePackGrants ?? []).contains { $0.knowledgePackId == pack.id && $0.status == "active" }
        let pending = center.requests.contains { ($0.requestedPackIds ?? []).contains(pack.id) && $0.status == "pending" }
        let state = active ? "已订阅" : (pending ? "审批中" : (pack.isSelectable ? "可订阅" : "整理中"))
        return Button { inspectedPack = pack } label: {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                bookCover(title: pack.name, author: "AI Lab 知识编译组", seed: pack.id)
                Text(state)
                    .font(AppTheme.Typography.micro.weight(.semibold))
                    .foregroundStyle(active ? AppTheme.Colors.statusCompleted : AppTheme.Colors.primary)
            }
        }
        .buttonStyle(SoftButtonStyle())
        .accessibilityLabel("\(pack.name)，\(state)")
        .accessibilityHint("点按查看概要和订阅状态")
    }

    private func candidatePackRow(_ pack: KnowledgePackDTO) -> some View {
        Button { inspectedPack = pack } label: {
            HStack(spacing: AppTheme.Spacing.md) {
                Image(systemName: "hammer.fill")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(AppTheme.Colors.textTertiary)
                    .frame(width: 36, height: 36)
                    .background(AppTheme.Colors.secondaryBackground)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
                VStack(alignment: .leading, spacing: 2) {
                    Text(pack.name)
                        .font(AppTheme.Typography.supporting.weight(.semibold))
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    Text("等待管理员批准 Yellow 内容")
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textTertiary)
                }
                Spacer()
                Text("待批准")
                    .font(AppTheme.Typography.micro.weight(.semibold))
                    .foregroundStyle(AppTheme.Colors.textTertiary)
                Image(systemName: "chevron.right")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(AppTheme.Colors.textTertiary)
            }
            .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
            .contentShape(Rectangle())
        }
        .buttonStyle(SoftButtonStyle())
        .accessibilityLabel("\(pack.name)，等待内容批准")
        .accessibilityHint("点按查看治理详情")
    }

    private func knowledgePackDetail(_ pack: KnowledgePackDTO) -> some View {
        let governanceReady = pack.status == "published" && pack.isSelectable
        let allowedByPlan = selectedPlan?.selectablePackIds?.contains(pack.id) == true
        let selected = selectedPackIDs.contains(pack.id)
        let canToggle = governanceReady && allowedByPlan

        return NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xl) {
                    HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                        Image(systemName: governanceReady ? "books.vertical.fill" : "hammer.fill")
                            .font(.system(size: 22, weight: .semibold))
                            .foregroundStyle(AppTheme.Colors.primary)
                            .frame(width: 52, height: 52)
                            .background(AppTheme.Colors.primary.opacity(0.10))
                            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                        VStack(alignment: .leading, spacing: 4) {
                            Text(pack.name)
                                .font(AppTheme.Typography.sectionTitle)
                                .foregroundStyle(AppTheme.Colors.textPrimary)
                            Text("AI Lab 知识编译组")
                                .font(AppTheme.Typography.supporting)
                                .foregroundStyle(AppTheme.Colors.textSecondary)
                            Text(pack.riskLabel)
                                .font(AppTheme.Typography.micro.weight(.semibold))
                                .foregroundStyle(AppTheme.Colors.textSecondary)
                        }
                    }

                    Text(pack.description)
                        .font(AppTheme.Typography.body)
                        .foregroundStyle(AppTheme.Colors.textSecondary)

                    VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                        Text("治理状态")
                            .font(AppTheme.Typography.cardTitle)
                        detailRow(label: "已批准条目", value: "\(pack.approvedDocumentCount) 篇", icon: "doc.text.fill")
                        detailRow(label: "内容新鲜度", value: "\(pack.freshnessPercent)%", icon: "clock.arrow.circlepath")
                        detailRow(label: "授权标识", value: pack.entitlementKey, icon: "key.fill")
                    }
                    .padding(AppTheme.Spacing.lg)
                    .subscriptionSurface()

                    Label(
                        canToggle
                            ? "该知识包可随当前套餐提交审批。"
                            : (governanceReady ? "请先选择支持该知识包的套餐。" : "管理员批准 Yellow 内容后自动开放，无需另配网关。"),
                        systemImage: canToggle ? "checkmark.circle.fill" : "info.circle.fill"
                    )
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(canToggle ? AppTheme.Colors.statusCompleted : AppTheme.Colors.textSecondary)

                    Button {
                        toggle(pack)
                        inspectedPack = nil
                    } label: {
                        Label(selected ? "从申请中移除" : "加入本次申请", systemImage: selected ? "minus.circle.fill" : "plus.circle.fill")
                            .font(AppTheme.Typography.supporting.weight(.semibold))
                            .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget)
                    }
                    .buttonStyle(.borderedProminent)
                    .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
                    .tint(AppTheme.Colors.primary)
                    .disabled(!canToggle)
                }
                .padding(AppTheme.Metrics.contentGutter)
            }
            .background(AppTheme.Colors.background)
            .navigationTitle("知识包详情")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("完成") { inspectedPack = nil }
                }
            }
        }
    }

    private func detailRow(label: String, value: String, icon: String) -> some View {
        HStack(spacing: AppTheme.Spacing.md) {
            Image(systemName: icon)
                .foregroundStyle(AppTheme.Colors.primary)
                .frame(width: 24)
            Text(label)
                .font(AppTheme.Typography.supporting)
                .foregroundStyle(AppTheme.Colors.textSecondary)
            Spacer()
            Text(value)
                .font(AppTheme.Typography.micro.weight(.semibold))
                .foregroundStyle(AppTheme.Colors.textPrimary)
                .lineLimit(1)
                .minimumScaleFactor(0.65)
        }
    }

    @ViewBuilder
    private func stickyApplicationBar(_ center: SubscriptionCenterResponse) -> some View {
        if let plan = selectedPlan,
           center.subscription?.planId != plan.id,
           !center.requests.contains(where: { $0.targetPlanId == plan.id && $0.status == "pending" }),
           plan.customOnly != true,
           plan.isAvailable != false,
           plan.availability != "content_building" {
            let allowance = plan.packAllowance ?? 0
            HStack(spacing: AppTheme.Spacing.md) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(plan.name)
                        .font(AppTheme.Typography.supporting.weight(.semibold))
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .lineLimit(1)
                    Text("已选 \(selectedPackIDs.count)/\(allowance) 个知识包")
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                }
                Spacer(minLength: AppTheme.Spacing.sm)
                Button { apply(for: plan) } label: {
                    busyLabel(id: "submit-\(plan.id)", title: "提交审批", systemImage: "paperplane.fill")
                        .frame(minWidth: 112, minHeight: AppTheme.Metrics.minimumTouchTarget)
                }
                .buttonStyle(.borderedProminent)
                .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
                .tint(AppTheme.Colors.primary)
                .disabled(selectedPackIDs.count > allowance || busyID != nil)
            }
            .padding(.horizontal, AppTheme.Metrics.contentGutter)
            .padding(.vertical, AppTheme.Spacing.sm)
            .background(.ultraThinMaterial)
            .overlay(alignment: .top) { Divider() }
        }
    }

    private var selectedPlan: SubscriptionPlanDTO? {
        center?.plans.first { $0.id == selectedPlanID }
    }

    private func planRank(_ plan: SubscriptionPlanDTO) -> Int {
        if plan.name.contains("基础") { return 0 }
        if plan.name.contains("专业") { return 1 }
        if plan.name.contains("治理") { return 2 }
        if plan.name.contains("专属") { return 3 }
        return 10
    }

    private func select(_ plan: SubscriptionPlanDTO, center: SubscriptionCenterResponse) {
        guard plan.isAvailable != false, plan.availability != "content_building" else { return }
        withAnimation(AppTheme.Motion.quick) {
            selectedPlanID = plan.id
            selectedPackIDs = selectedPackIDs.intersection(Set(plan.selectablePackIds ?? []))
        }
    }

    private func toggle(_ pack: KnowledgePackDTO) {
        guard let plan = selectedPlan else { return }
        let allowance = plan.packAllowance ?? 0
        if selectedPackIDs.contains(pack.id) {
            selectedPackIDs.remove(pack.id)
        } else if selectedPackIDs.count < allowance {
            selectedPackIDs.insert(pack.id)
        } else {
            errorMessage = "当前套餐最多选择 \(allowance) 个知识包，请先移除一个。"
        }
    }

    private var adminSection: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack {
                Label("订阅审批", systemImage: "person.badge.key.fill")
                    .font(AppTheme.Typography.cardTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Spacer()
                Text("\(adminRequests.count) 项待办")
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.statusWarning)
            }

            if adminRequests.isEmpty {
                Text("当前没有待审批的组织套餐申请。")
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            } else {
                ForEach(adminRequests) { request in
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                        Text(request.targetPlanName)
                            .font(AppTheme.Typography.supporting.weight(.semibold))
                        Text("组织 \(request.organizationId) · 申请人 \(request.requestedBy)")
                            .font(AppTheme.Typography.micro)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                            .lineLimit(2)
                        HStack(spacing: AppTheme.Spacing.sm) {
                            Button { review(request, approve: false) } label: {
                                busyLabel(id: "reject-\(request.id)", title: "拒绝", systemImage: "xmark")
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.bordered)
                            .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
                            .tint(AppTheme.Colors.statusError)

                            Button { review(request, approve: true) } label: {
                                busyLabel(id: "approve-\(request.id)", title: "批准", systemImage: "checkmark")
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.borderedProminent)
                            .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
                            .tint(AppTheme.Colors.statusCompleted)
                        }
                        .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                        .disabled(busyID != nil)
                    }
                    .padding(AppTheme.Spacing.md)
                    .background(AppTheme.Colors.secondaryBackground)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                }
            }
        }
        .padding(AppTheme.Spacing.xl)
        .subscriptionSurface()
    }

    private func inlineError(_ message: String) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Label("暂时无法完成操作", systemImage: "exclamationmark.triangle.fill")
                .font(AppTheme.Typography.cardTitle)
                .foregroundStyle(AppTheme.Colors.statusError)
            Text(message)
                .font(AppTheme.Typography.supporting)
                .foregroundStyle(AppTheme.Colors.textSecondary)
            Button { Task { await loadBookshelves() } } label: {
                Label("重试", systemImage: "arrow.clockwise")
                    .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget)
            }
            .buttonStyle(.bordered)
            .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
        }
        .padding(AppTheme.Spacing.xl)
        .background(AppTheme.Colors.dangerSurface)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
    }

    @ViewBuilder
    private func busyLabel(id: String, title: String, systemImage: String) -> some View {
        if busyID == id {
            ProgressView().controlSize(.small)
        } else {
            Label(title, systemImage: systemImage)
                .font(AppTheme.Typography.supporting.weight(.semibold))
        }
    }

    private func load() async {
        isLoading = true
        errorMessage = nil
        do {
            async let centerRequest = api.fetchSubscriptionCenter()
            async let accessRequest = api.fetchKnowledgeAccess()
            let response = try await centerRequest
            let access = try await accessRequest
            center = response
            knowledgeAccess = access
            if let highlightedEntitlementKey,
               let pack = (response.knowledgePacks ?? []).first(where: { $0.entitlementKey == highlightedEntitlementKey }) {
                inspectedPack = pack
                if let plan = response.plans.first(where: { ($0.selectablePackIds ?? []).contains(pack.id) && $0.customOnly != true }) {
                    selectedPlanID = plan.id
                }
            }
            if response.isSuperAdmin {
                adminRequests = try await api.fetchAdminSubscriptionRequests()
                publicationCandidates = try await api.fetchKnowledgePublicationCandidates()
            } else {
                adminRequests = []
                publicationCandidates = []
            }
        } catch {
            knowledgeAccess = nil
            errorMessage = actionableMessage(for: error)
        }
        isLoading = false
    }

    private func loadBookshelves() async {
        isLoading = true
        errorMessage = nil
        do {
            bookshelves = try await api.fetchKnowledgeBookshelves()
            if let subscriptions = try? await api.fetchBookSubscriptions() {
                subscribedBookIDs = Set(subscriptions.map(\.book.id))
            }
        } catch {
            errorMessage = actionableMessage(for: error)
        }
        isLoading = false
    }

    private func toggleBookSubscription(_ book: KnowledgeBookDTO) async {
        guard subscriptionBusyBookID == nil else { return }
        subscriptionBusyBookID = book.id
        defer { subscriptionBusyBookID = nil }
        do {
            if subscribedBookIDs.contains(book.id) {
                try await api.unsubscribeBook(id: book.id)
                subscribedBookIDs.remove(book.id)
            } else {
                _ = try await api.subscribeBook(id: book.id)
                subscribedBookIDs.insert(book.id)
            }
        } catch {
            if case APIError.server(404, _) = error {
                errorMessage = "当前服务器尚未启用书籍订阅接口，请更新服务端后重试。"
            } else {
                errorMessage = actionableMessage(for: error)
            }
        }
    }

    private func saveBookSummaryToNote(_ book: KnowledgeBookDTO) {
        let body = """
        > [!abstract] 书籍摘录
        > 《\(book.title)》 · \(book.author)
        > Quantum 编研版 · \(book.knowledgeLevel) · \(book.sourceCount) 个来源

        \(book.summary)

        ---
        来源书籍 ID：`\(book.id)`
        """
        guard let note = KnowledgeNoteStore.shared.createNote(
            title: "\(book.title)｜概述摘录",
            body: body,
            tags: ["书籍摘录", "quantum-books"]
        ) else { return }
        let markdown = KnowledgeNoteStore.shared.markdown(for: note)
        Task {
            try? await api.syncKnowledgeNote(id: note.id, markdown: markdown, updatedAt: note.updatedAt)
        }
        showSuccess("已摘录到笔记")
    }

    private func approvePublication(_ candidate: KnowledgePublicationCandidateDTO) {
        guard busyID == nil else { return }
        Task {
            busyID = "publish-\(candidate.id)"
            defer { busyID = nil }
            do {
                _ = try await api.approveKnowledgePublication(
                    path: candidate.path,
                    securityLevel: publicationSecurity,
                    entitlementKey: publicationSecurity == "yellow" ? publicationEntitlement : "",
                    ownerTenant: publicationSecurity == "red" ? publicationOwner : ""
                )
                inspectedCandidate = nil
                showSuccess(publicationSecurity == "green" ? "GREEN 已进入公共知识" : (publicationSecurity == "yellow" ? "YELLOW 已发布为可订阅知识包" : "RED 已向所属租户开放"))
                await load()
            } catch {
                errorMessage = actionableMessage(for: error)
            }
        }
    }

    private func apply(for plan: SubscriptionPlanDTO) {
        guard busyID == nil else { return }
        guard plan.isAvailable != false, plan.availability != "content_building" else {
            errorMessage = "基础公共知识仍在治理建设中，开放后无需再次申请。"
            return
        }
        Task {
            busyID = "submit-\(plan.id)"
            defer { busyID = nil }
            do {
                let requestID = requestIDsByPlan[plan.id] ?? UUID().uuidString
                requestIDsByPlan[plan.id] = requestID
                _ = try await api.createSubscriptionRequest(
                    planId: plan.id,
                    entitlementKeys: [],
                    packIds: Array(selectedPackIDs).sorted(),
                    reason: selectedPackIDs.isEmpty ? "从 iOS 知识订阅中心提交" : "申请平台套餐并开通 \(selectedPackIDs.count) 个知识包",
                    requestId: requestID
                )
                requestIDsByPlan.removeValue(forKey: plan.id)
                showSuccess("申请已提交，等待管理员审批")
                await load()
            } catch {
                errorMessage = actionableMessage(for: error)
            }
        }
    }

    private func cancel(_ request: SubscriptionRequestDTO) {
        guard busyID == nil else { return }
        Task {
            busyID = request.id
            defer { busyID = nil }
            do {
                _ = try await api.cancelSubscriptionRequest(id: request.id)
                showSuccess("申请已撤销")
                await load()
            } catch {
                errorMessage = actionableMessage(for: error)
            }
        }
    }

    private func review(_ request: SubscriptionRequestDTO, approve: Bool) {
        guard busyID == nil else { return }
        let operationID = "\(approve ? "approve" : "reject")-\(request.id)"
        Task {
            busyID = operationID
            defer { busyID = nil }
            do {
                _ = try await api.reviewSubscriptionRequest(
                    id: request.id,
                    approve: approve,
                    note: approve ? "iOS 订阅中心批准" : "iOS 订阅中心拒绝",
                    approvedPackIds: approve ? request.requestedPackIds : nil
                )
                showSuccess(approve ? "审批已通过，权益正在同步" : "申请已拒绝")
                await load()
            } catch {
                errorMessage = actionableMessage(for: error)
            }
        }
    }

    private func showSuccess(_ message: String) {
        withAnimation(AppTheme.Motion.quick) { successMessage = message }
        Task {
            try? await Task.sleep(nanoseconds: 2_400_000_000)
            await MainActor.run {
                withAnimation(AppTheme.Motion.quick) { successMessage = nil }
            }
        }
    }

    private func actionableMessage(for error: Error) -> String {
        if let apiError = error as? APIError, let actionable = apiError.actionable {
            return actionable.message
        }
        return error.localizedDescription
    }

    private func tokenQuota(_ value: Int64) -> String {
        value.formatted(.number.notation(.compactName)) + " Token"
    }
}

struct KnowledgeBookReaderView: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    let book: KnowledgeBookDTO
    let isSubscribed: Bool
    let isBusy: Bool
    let onToggleSubscription: () -> Void
    var onSaveExcerpt: (() -> Void)? = nil
    let onDismiss: () -> Void

    @State private var appeared = false
    @State private var showingReading = ProcessInfo.processInfo.arguments.contains("-bookReadingPreview")

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Text("QUANTUM EDITIONS  /  01")
                        .font(.caption2.weight(.bold))
                        .tracking(1.4)
                        .foregroundStyle(AppTheme.Colors.textTertiary)
                        .padding(.top, 42)
                        .padding(.leading, 8)

                    HStack {
                        Spacer()
                        editorialCover
                            .rotationEffect(.degrees(appeared ? -3.5 : -9))
                            .offset(x: appeared ? 16 : 52, y: appeared ? 0 : 24)
                            .opacity(appeared ? 1 : 0)
                        Spacer().frame(width: 48)
                    }
                    .frame(height: 300)

                    VStack(alignment: .leading, spacing: 12) {
                        Text(book.title)
                            .font(.system(.largeTitle, design: .rounded, weight: .bold))
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(book.author)
                            .font(.title3.weight(.medium))
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                        Text(book.authorSource == "fallback" ? "QUANTUM 编研" : "原文署名  ·  QUANTUM 编研")
                            .font(.caption.weight(.bold))
                            .tracking(0.7)
                            .foregroundStyle(AppTheme.Colors.primary)
                    }
                    .frame(maxWidth: 330, alignment: .leading)
                    .offset(x: appeared ? 0 : -22)
                    .opacity(appeared ? 1 : 0)
                    .padding(.top, 18)

                    Rectangle()
                        .fill(AppTheme.Colors.textPrimary)
                        .frame(width: 72, height: 2)
                        .padding(.vertical, 38)
                        .offset(x: 36)

                    Text("ABOUT  /  本书概述")
                        .font(.caption.weight(.bold))
                        .tracking(1.1)
                        .foregroundStyle(AppTheme.Colors.textTertiary)
                    Text(book.summary.isEmpty ? "这本知识正在补充读者概要。" : book.summary)
                        .font(.title3.weight(.regular))
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .lineSpacing(9)
                        .padding(.top, 14)
                        .frame(maxWidth: 344, alignment: .leading)

                    HStack(spacing: 10) {
                        readerPill(book.knowledgeLevel, icon: "checkmark.seal")
                        readerPill("\(book.sourceCount) 个来源", icon: "link")
                    }
                    .padding(.top, 34)
                    .offset(x: 22)

                    readerPill(book.freshness == "current" ? "持续更新" : book.freshness, icon: "clock")
                        .padding(.top, 10)
                        .offset(x: 104)

                    Label(
                        "正文为已批准的 Wiki 编研版；Raw 仅用于署名、引用与溯源。",
                        systemImage: "quote.opening"
                    )
                    .font(.footnote)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .lineSpacing(5)
                    .padding(.top, 48)
                    .frame(maxWidth: 330, alignment: .leading)

                    Spacer(minLength: 80)
                }
                .padding(.horizontal, 28)
            }
            .background(
                ZStack {
                    AppTheme.Colors.cardBackground
                    Circle()
                        .fill(AppTheme.Colors.selectionTint.opacity(0.72))
                        .frame(width: 330, height: 330)
                        .blur(radius: 18)
                        .offset(x: -180, y: -330)
                }
                .ignoresSafeArea()
            )
            .safeAreaInset(edge: .bottom) {
                VStack(spacing: 4) {
                    Button(action: isSubscribed ? { showingReading = true } : onToggleSubscription) {
                        HStack(spacing: 10) {
                            if isBusy { ProgressView().tint(.white) }
                            Image(systemName: isSubscribed ? "book.pages.fill" : "plus")
                            Text(isSubscribed ? "开始阅读" : "加入我的笔记书架")
                        }
                        .font(.body.weight(.semibold))
                        .foregroundStyle(Color.white)
                        .frame(maxWidth: .infinity, minHeight: 52)
                        .background(AppTheme.Colors.textPrimary)
                        .clipShape(Capsule())
                    }
                    .disabled(isBusy && !isSubscribed)
                    .buttonStyle(SoftButtonStyle())
                    .accessibilityLabel(isSubscribed ? "开始阅读《\(book.title)》" : "加入我的笔记书架")
                    HStack(spacing: 18) {
                        if isSubscribed {
                            Button("移出书架", action: onToggleSubscription)
                                .disabled(isBusy)
                        }
                        if let onSaveExcerpt {
                            Button("将概述摘录到笔记", action: onSaveExcerpt)
                        }
                    }
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .frame(minHeight: 44)
                }
                .padding(.horizontal, 28)
                .padding(.top, 10)
                .background(.ultraThinMaterial)
            }
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(action: onDismiss) {
                        Image(systemName: "xmark")
                            .font(.system(size: 14, weight: .bold))
                            .frame(width: 44, height: 44)
                            .background(AppTheme.Colors.secondaryBackground, in: Circle())
                    }
                    .accessibilityLabel("关闭书籍")
                }
            }
            .onAppear {
                withAnimation(reduceMotion ? nil : .spring(response: 0.46, dampingFraction: 0.82)) {
                    appeared = true
                }
            }
        }
        .fullScreenCover(isPresented: $showingReading) {
            KnowledgeBookReadingView(book: book) { showingReading = false }
        }
    }

    private var editorialCover: some View {
        ZStack(alignment: .leading) {
            RoundedRectangle(cornerRadius: 4, style: .continuous)
                .fill(LinearGradient(
                    colors: [AppTheme.Colors.selectionTint, AppTheme.Colors.surfaceTint],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                ))
            Circle()
                .stroke(AppTheme.Colors.primary.opacity(0.12), lineWidth: 18)
                .frame(width: 126, height: 126)
                .offset(x: 76, y: -34)
            Rectangle()
                .fill(AppTheme.Colors.primary.opacity(0.16))
                .frame(width: 9)
            VStack(alignment: .leading) {
                Text(book.title)
                    .font(.headline.weight(.bold))
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                    .lineLimit(4)
                Spacer()
                Text(book.author)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .lineLimit(2)
            }
            .padding(18)
        }
        .frame(width: 176, height: 248)
        .shadow(color: AppTheme.Colors.primary.opacity(0.10), radius: 22, x: 8, y: 16)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("《\(book.title)》，作者 \(book.author)")
    }

    private func readerPill(_ text: String, icon: String) -> some View {
        Label(text, systemImage: icon)
            .font(.caption.weight(.semibold))
            .foregroundStyle(AppTheme.Colors.textSecondary)
            .padding(.horizontal, 14)
            .frame(minHeight: 40)
            .background(AppTheme.Colors.secondaryBackground, in: Capsule())
    }
}

private struct KnowledgeBookReadingView: View {
    @EnvironmentObject private var api: APIClient
    @State private var progressError: String?
    let book: KnowledgeBookDTO
    let onDismiss: () -> Void

    private func recordReading() async {
        do {
            let subscriptions = try await api.fetchBookSubscriptions()
            guard let subscription = subscriptions.first(where: { $0.book.id == book.id }) else { return }
            // Opening a guide records recency, not fictional full-book progress.
            _ = try await api.updateBookProgress(id: book.id, progress: subscription.progress)
            progressError = nil
        } catch {
            progressError = "阅读记录未同步，请重试。"
        }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Text("QUANTUM LIBRARY  ·  卷一")
                        .font(.caption2.weight(.bold))
                        .tracking(1.5)
                        .foregroundStyle(Color.brown.opacity(0.62))
                    Text(book.title)
                        .font(.system(.largeTitle, design: .serif, weight: .bold))
                        .foregroundStyle(Color(red: 0.20, green: 0.15, blue: 0.10))
                        .padding(.top, 48)
                    Text(book.author)
                        .font(.system(.title3, design: .serif))
                        .foregroundStyle(Color.brown.opacity(0.78))
                        .padding(.top, 12)

                    HStack(spacing: 12) {
                        Rectangle().frame(width: 54, height: 1)
                        Image(systemName: "leaf.fill")
                        Rectangle().frame(width: 54, height: 1)
                    }
                    .foregroundStyle(Color.brown.opacity(0.42))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 52)

                    Text("导读")
                        .font(.system(.title2, design: .serif, weight: .semibold))
                    Text(book.summary.isEmpty ? "本书正文正在编研中。" : book.summary)
                        .font(.system(.title3, design: .serif))
                        .lineSpacing(11)
                        .padding(.top, 22)
                    Text("本页为已批准 Wiki 编研版导读。完整章节将在正文治理完成后按目录加入。")
                        .font(.system(.footnote, design: .serif))
                        .foregroundStyle(Color.brown.opacity(0.68))
                        .lineSpacing(5)
                        .padding(.top, 48)
                    if let progressError {
                        Button(progressError) { Task { await recordReading() } }
                            .padding(.top, 20)
                    }
                    Spacer(minLength: 120)
                }
                .frame(maxWidth: 560, alignment: .leading)
                .padding(.horizontal, 34)
                .padding(.top, 42)
            }
            .foregroundStyle(Color(red: 0.23, green: 0.17, blue: 0.11))
            .background(
                ZStack {
                    Color(red: 0.96, green: 0.91, blue: 0.79)
                    RadialGradient(
                        colors: [Color.white.opacity(0.28), Color.brown.opacity(0.07)],
                        center: .topLeading,
                        startRadius: 20,
                        endRadius: 720
                    )
                }
                .ignoresSafeArea()
            )
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(action: onDismiss) {
                        Image(systemName: "chevron.left")
                            .frame(width: 44, height: 44)
                            .background(Color.white.opacity(0.34), in: Circle())
                    }
                    .accessibilityLabel("返回书籍概述")
                }
            }
            .task(id: book.id) { await recordReading() }
        }
    }
}

#if DEBUG
extension SubscriptionCenterResponse {
    static var bookshelfPreview: Self {
        func book(
            _ id: String,
            _ title: String,
            author: String,
            _ summary: String,
            theme: String,
            variant: Int,
            sources: Int
        ) -> KnowledgeBookDTO {
            KnowledgeBookDTO(
                id: id,
                title: title,
                author: author,
                authorSource: author == "Quantum 研究团队" ? "fallback" : "raw",
                summary: summary,
                coverTheme: theme,
                coverVariant: variant,
                coverVersion: 1,
                securityLevel: "green",
                knowledgeLevel: "K5",
                freshness: "current",
                sourceCount: sources
            )
        }

        let product = [
            book("product-map", "AI 产品全景图", author: "Quantum 研究团队", "从用户问题、能力边界到商业闭环，理解 AI 产品的完整结构。", theme: "product", variant: 0, sources: 18),
            book("subscription", "AI 原生研发手册", author: "Louis Claxton · Anthropic", "把意图、规格、验证和部署重组为 Agent 可执行的研发闭环。", theme: "product", variant: 1, sources: 12),
            book("agent-os", "LLM Knowledge Bases", author: "Andrej Karpathy", "从 Raw 原始材料到 Wiki 增量编译，理解面向 LLM 的知识库工作方式。", theme: "product", variant: 2, sources: 23),
        ]
        let strategy = [
            book("signals", "战略信号手册", author: "Quantum 研究团队", "识别市场变化、技术拐点与竞争动作中的高价值信号。", theme: "strategic-signal", variant: 3, sources: 31),
            book("competitor", "Claude 工程实践", author: "Anthropic", "从官方案例中提炼 Claude Code 的工程化方法与适用边界。", theme: "competitor", variant: 4, sources: 27),
            book("decision", "高质量决策框架", author: "Quantum 研究团队", "用假设、反例与证据强度降低复杂决策中的判断偏差。", theme: "methodology", variant: 5, sources: 16),
        ]
        let methodology = [
            book("effective-agents", "Building Effective AI Agents", author: "Anthropic", "从可组合工作流到自主 Agent，选择足够简单且可验证的构建方式。", theme: "methodology", variant: 0, sources: 14),
            book("qwen-agent", "千问 Agent 工程演进", author: "储旭（槿柏）", "梳理 Agent 平台从单体工具调用到工程化交付的演进路径。", theme: "methodology", variant: 2, sources: 9),
            book("harness", "Harness Engineering", author: "Louis Claxton · Anthropic", "用确定性约束、验证与反馈环路提升 Agent 交付质量。", theme: "methodology", variant: 4, sources: 17),
        ]
        var center = SubscriptionCenterResponse(
            organizationId: "preview",
            applicationId: "ai-lab-platform",
            subscription: nil,
            requests: [],
            plans: [],
            isSuperAdmin: false,
            pendingCount: 0
        )
        center.bookshelves = [
            KnowledgeBookshelfDTO(id: "knowledge/product/public", title: "产品与方案", securityLevel: "green", bookCount: product.count, books: product),
            KnowledgeBookshelfDTO(id: "knowledge/strategy/public", title: "战略与竞品", securityLevel: "green", bookCount: strategy.count, books: strategy),
            KnowledgeBookshelfDTO(id: "knowledge/methodology/public", title: "方法论", securityLevel: "green", bookCount: methodology.count, books: methodology),
        ]
        center.knowledgePacks = []
        center.activePackGrants = []
        center.packAllowance = 0
        return center
    }
}
#endif

private extension View {
    func subscriptionSurface() -> some View {
        background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(AppTheme.Colors.border, lineWidth: 0.75)
            }
    }
}

private extension String {
    var dateOnly: String { String(prefix(10)) }
}

// MARK: - Xcode #Preview

#Preview("SettingsView - Light") {
    SettingsView()
        .environmentObject(AppState())
        .environmentObject(APIClient.shared)
}

#Preview("SettingsView - Dark") {
    SettingsView()
        .environmentObject(AppState())
        .environmentObject(APIClient.shared)
        .preferredColorScheme(.dark)
}
