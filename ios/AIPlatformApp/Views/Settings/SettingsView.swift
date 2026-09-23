//
//  SettingsView.swift
//  AIPlatformApp
//
//  个人中心：个人信息卡（点击编辑 sheet）→ Token 极简卡 → 账号操作。
//

import SwiftUI
import UIKit

struct AgentDescriptionPresentation: Equatable {
    static let maximumLength = 100

    let full: String

    init(function: String?, suitable: String?, boundary: String?) {
        func normalized(_ raw: String?, fallback: String) -> String {
            let value = (raw ?? "")
            .replacingOccurrences(of: "\n", with: " ")
            .split(whereSeparator: { $0.isWhitespace })
            .joined(separator: " ")
            return String((value.isEmpty ? fallback : value).prefix(29))
        }
        let functionValue = normalized(function, fallback: "能力清单暂不可用")
        let suitableValue = normalized(suitable, fallback: "请刷新后查看适用任务")
        let boundaryValue = normalized(boundary, fallback: "未取得能力边界，暂不执行")
        full = "功能：\(functionValue)。适合：\(suitableValue)。边界：\(boundaryValue)。"
    }

    var isCollapsible: Bool { full.count > 34 }
}

struct AgentDescriptionText: View {
    let text: String
    let name: String
    @Binding var isExpanded: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(text)
                .font(.system(size: 12))
                .foregroundColor(AppTheme.Colors.textSecondary)
                .lineSpacing(1)
                .lineLimit(isExpanded ? nil : 2)
                .accessibilityIdentifier("agent-description-\(name)")
            Button(isExpanded ? "收起描述" : "展开描述") {
                withAnimation(AppTheme.Motion.quick) { isExpanded.toggle() }
            }
            .font(.system(size: 11, weight: .semibold))
            .buttonStyle(.plain)
            .foregroundStyle(AppTheme.Colors.quantumBlue)
            .frame(minHeight: AppTheme.Metrics.minimumTouchTarget, alignment: .leading)
            .accessibilityIdentifier("agent-description-toggle")
            .accessibilityValue(isExpanded ? "已展开" : "已折叠两行")
        }
    }
}

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
    @State private var expandedAgentIDs: Set<String> = []
    @State private var selectedAgent: TenantAgentDTO?

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

                        // 1. 用户与租户身份卡（点击编辑）
                        tenantProfileCard
                            .padding(.horizontal, AppTheme.Metrics.contentGutter)

                        TokenSummaryCard()
                            .padding(.horizontal, AppTheme.Metrics.contentGutter)

                        // 2. Hermes 原生长期记忆
                        memoryCenterEntryCard
                            .padding(.horizontal, AppTheme.Metrics.contentGutter)

                        // 3. 对话式创建智能体
                        agentCreatorEntryCard
                            .padding(.horizontal, AppTheme.Metrics.contentGutter)

                        // 4. 知识订阅与套餐
                        subscriptionEntryCard
                            .padding(.horizontal, AppTheme.Metrics.contentGutter)

                        // 4. 我创建的智能体 + 我制作的技能（纯云端真实数据）
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
            .sheet(item: $selectedAgent) { agent in
                TenantAgentManagementView(agent: agent) { updated in
                    if let index = cloudAgents.firstIndex(where: { $0.id == updated.id }) {
                        cloudAgents[index] = updated
                    }
                    selectedAgent = nil
                }
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
            .onReceive(NotificationCenter.default.publisher(for: .tenantAgentsDidUpdate)) { _ in
                Task {
                    if let list = try? await APIClient.shared.fetchTenantAgents(ownedOnly: true) {
                        cloudAgents = list
                    }
                }
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
                    Text("我的知识计划")
                        .font(.system(size: 16, weight: .bold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                    Text(subscriptionSummary?.subscription?.planName ?? "看看适合自己的阅读与学习权益")
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

    private var agentCreatorEntryCard: some View {
        NavigationLink {
            AgentCreatorView()
        } label: {
            HStack(spacing: AppTheme.Spacing.md) {
                Image(systemName: "cpu.fill")
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundStyle(Color.white)
                    .frame(width: 48, height: 48)
                    .background(AppTheme.Colors.actionGradient, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))

                VStack(alignment: .leading, spacing: 4) {
                    Text("创建专属学习搭子")
                        .font(.headline.weight(.bold))
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    Text("从学习目标出发，定制它的能力与边界")
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(AppTheme.Icons.tertiary)
            }
            .padding(AppTheme.Spacing.lg)
            .frame(minHeight: 88)
            .quantumCard()
        }
        .buttonStyle(SoftButtonStyle())
        .accessibilityLabel("创建专属学习搭子")
    }

    private var memoryCenterEntryCard: some View {
        NavigationLink {
            MemoryCenterView()
        } label: {
            HStack(spacing: AppTheme.Spacing.md) {
                Image(systemName: "brain.head.profile")
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundStyle(AppTheme.Icons.onAccent)
                    .frame(width: 48, height: 48)
                    .background(AppTheme.Colors.actionGradient)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))

                VStack(alignment: .leading, spacing: 4) {
                    Text("Quantum 记得的我")
                        .font(.headline.weight(.bold))
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    Text("查看和管理长期偏好与学习习惯")
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                }

                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(AppTheme.Icons.tertiary)
            }
            .padding(AppTheme.Spacing.lg)
            .frame(minHeight: 88)
            .quantumCard()
        }
        .buttonStyle(SoftButtonStyle())
        .accessibilityLabel("查看和管理长期偏好与学习习惯")
    }

    private var settingsOverviewHeader: some View {
        HStack(alignment: .center, spacing: AppTheme.Spacing.md) {
            VStack(alignment: .leading, spacing: 4) {
                Text("我的日常")
                    .font(.system(size: 32, weight: .bold, design: .rounded))
                    .foregroundColor(AppTheme.Colors.textPrimary)
                Text("学习、收藏，还有你的 Quantum")
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
            ZStack(alignment: .leading) {
                Image("knowledge_home_hero")
                    .resizable()
                    .scaledToFill()
                    .frame(height: 174)
                    .clipped()
                LinearGradient(
                    colors: [Color.black.opacity(0.04), Color(hex: "254144").opacity(0.66)],
                    startPoint: .top,
                    endPoint: .bottom
                )
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    HStack {
                        UserAvatarView(value: appState.currentProfile.avatarUrl, size: 52)
                            .background(.ultraThinMaterial, in: Circle())
                        Spacer()
                        Image(systemName: "pencil")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(.white)
                            .frame(width: 40, height: 40)
                            .background(.ultraThinMaterial, in: Circle())
                    }
                    Spacer()
                    HStack(spacing: 6) {
                        Text(appState.currentProfile.name)
                            .font(.title3.weight(.bold))
                        if appState.currentProfile.isVipLane {
                            Label("VIP", systemImage: "crown.fill")
                                .font(.caption2.weight(.bold))
                                .padding(.horizontal, 8)
                                .frame(height: 24)
                                .background(.ultraThinMaterial, in: Capsule())
                        }
                    }
                    Text("个人工作空间 · 今天也继续成长")
                        .font(.caption.weight(.medium))
                        .foregroundStyle(Color.white.opacity(0.82))
                }
                .foregroundStyle(.white)
                .padding(AppTheme.Spacing.lg)
            }
            .frame(height: 174)
            .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 28, style: .continuous)
                    .stroke(Color.white.opacity(0.76), lineWidth: 0.8)
            }
            .shadow(color: Color(hex: "385A58").opacity(0.13), radius: 20, y: 8)
        }
        .buttonStyle(SoftButtonStyle())
    }

    // MARK: - 我创建的智能体 + 我制作的技能（纯云端真实数据）

    private func createdAgentsSection() -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            artifactHeader(icon: "sparkles", title: "我创建的智能体", accent: AppTheme.Colors.quantumViolet)
            let rows = cloudAgents.map { agent in
                let description = AgentDescriptionPresentation(
                    function: agent.functionDescription,
                    suitable: agent.suitableDescription,
                    boundary: agent.boundaryDescription
                )
                return AgentRowData(
                    id: agent.id,
                    name: agent.customName ?? agent.baseAgentId,
                    responsibility: description.full,
                    collapsedResponsibility: description.isCollapsible ? description.full : nil,
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
                        collapsedResponsibility: row.collapsedResponsibility,
                        createdAt: row.createdAt,
                        accent: AppTheme.Colors.quantumViolet,
                        isExpanded: row.collapsedResponsibility == nil ? nil : Binding(
                            get: { expandedAgentIDs.contains(row.id) },
                            set: { expanded in
                                if expanded { expandedAgentIDs.insert(row.id) }
                                else { expandedAgentIDs.remove(row.id) }
                            }
                        ),
                        onDelete: {
                            Task {
                                if (try? await APIClient.shared.deleteTenantAgent(id: row.id)) != nil {
                                    cloudAgents.removeAll { $0.id == row.id }
                                }
                            }
                        },
                        onOpen: { selectedAgent = cloudAgents.first(where: { $0.id == row.id }) }
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
        let collapsedResponsibility: String?
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
        collapsedResponsibility: String? = nil,
        createdAt: String,
        accent: Color,
        isExpanded: Binding<Bool>? = nil,
        deleteDisabled: Bool = false,
        onDelete: @escaping () -> Void,
        onOpen: (() -> Void)? = nil
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
                if let onOpen {
                    Button(action: onOpen) {
                        Image(systemName: "slider.horizontal.3")
                            .font(.system(size: 12))
                            .foregroundColor(AppTheme.Icons.interactive)
                            .minimumTouchTarget()
                    }
                    .buttonStyle(SoftButtonStyle())
                    .accessibilityLabel("管理 \(name)")
                }
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
            if let isExpanded {
                AgentDescriptionText(text: responsibility, name: name, isExpanded: isExpanded)
            } else {
                Text(responsibility)
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textSecondary)
            }
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

private struct TenantAgentManagementView: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.dismiss) private var dismiss
    let agent: TenantAgentDTO
    let onSaved: (TenantAgentDTO) -> Void

    @State private var name: String
    @State private var prompt: String
    @State private var knowledgePacks: String
    @State private var isActive: Bool
    @State private var isSaving = false
    @State private var errorMessage: String?

    init(agent: TenantAgentDTO, onSaved: @escaping (TenantAgentDTO) -> Void) {
        self.agent = agent
        self.onSaved = onSaved
        _name = State(initialValue: agent.customName ?? agent.baseAgentId)
        _prompt = State(initialValue: agent.privatePromptDelta)
        _knowledgePacks = State(initialValue: agent.subscribedKnowledgePacks.joined(separator: "，"))
        _isActive = State(initialValue: agent.isActive)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    HStack(spacing: AppTheme.Spacing.md) {
                        Image(systemName: "cpu")
                            .font(.title2)
                            .foregroundStyle(AppTheme.Colors.quantumViolet)
                            .frame(width: 52, height: 52)
                            .background(AppTheme.Colors.mistLilac, in: RoundedRectangle(cornerRadius: 15))
                        VStack(alignment: .leading) {
                            Text(name).font(AppTheme.Typography.cardTitle)
                            Text(agent.baseAgentId).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
                        }
                    }
                }

                Section("基本配置") {
                    TextField("智能体名称", text: $name)
                    TextField("它应该怎样工作", text: $prompt, axis: .vertical).lineLimit(4...8)
                    Toggle("启用智能体", isOn: $isActive)
                }

                Section("知识访问") {
                    TextField("知识包 ID，用逗号分隔", text: $knowledgePacks, axis: .vertical)
                    if agent.subscribedKnowledgePacks.isEmpty {
                        Label("尚未授权知识包", systemImage: "books.vertical")
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                    }
                }

                Section("工具能力") {
                    if let tools = agent.allowedTools, !tools.isEmpty {
                        ForEach(tools, id: \.self) { tool in
                            HStack {
                                Image(systemName: "wrench.and.screwdriver")
                                Text(tool)
                                Spacer()
                                Text("已授权").foregroundStyle(AppTheme.Colors.statusCompleted)
                            }
                        }
                    } else {
                        Label("未配置额外工具", systemImage: "wrench.and.screwdriver")
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                    }
                    Text("当前后端仅提供工具授权读取；不会伪造增删保存成功。")
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textTertiary)
                }

                Section {
                    Button("在 Chat 预览能力", systemImage: "bubble.left.and.bubble.right") {
                        dismiss()
                        appState.openChat(
                            agentId: agent.id,
                            agentName: name,
                            prompt: "请简短介绍你的能力、可访问知识与工具边界"
                        )
                    }
                }

                if let errorMessage {
                    Section { Label(errorMessage, systemImage: "exclamationmark.triangle.fill").foregroundStyle(AppTheme.Colors.statusError) }
                }
            }
            .navigationTitle("配置智能体")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(isSaving ? "保存中…" : "保存") { save() }.disabled(isSaving || name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
    }

    private func save() {
        isSaving = true
        errorMessage = nil
        let packs = knowledgePacks
            .components(separatedBy: CharacterSet(charactersIn: ",，\n"))
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        Task {
            do {
                let updated = try await APIClient.shared.updateTenantAgent(
                    id: agent.id,
                    body: TenantAgentCreateDTO(
                        baseAgentId: agent.baseAgentId,
                        customName: name,
                        privatePromptDelta: prompt,
                        subscribedKnowledgePacks: packs,
                        customAvatar: agent.customAvatar,
                        isActive: isActive
                    )
                )
                NotificationCenter.default.post(name: .tenantAgentsDidUpdate, object: nil)
                onSaved(updated)
            } catch {
                errorMessage = error.localizedDescription
                isSaving = false
            }
        }
    }
}

// MARK: - Knowledge subscription center

private enum BookshelfScope: String, CaseIterable, Identifiable {
    case reading = "在读"
    case saved = "收藏"
    case finished = "已读"

    var id: String { rawValue }
}

public struct SubscriptionCenterView: View {
    @EnvironmentObject private var api: APIClient
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private let highlightedEntitlementKey: String?
    private let previewCenter: SubscriptionCenterResponse?
    private let onBack: (() -> Void)?
    private let showsBackButton: Bool

    @State private var center: SubscriptionCenterResponse?
    @State private var knowledgeAccess: KnowledgeAccessResponse?
    @State private var bookshelves: [KnowledgeBookshelfDTO] = []
    @State private var publicCollections: [PublicKnowledgeCollectionDTO] = []
    @State private var ownerPrivateCollections: [OwnerPrivateCollectionDTO] = []
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
    @State private var showsBookshelfSearch = false
    @State private var bookshelfScope: BookshelfScope = .reading
    @State private var inspectedBook: KnowledgeBookDTO?
    @State private var subscribedBookIDs: Set<String> = []
    @State private var bookSubscriptions: [KnowledgeBookSubscriptionDTO] = []
    @State private var subscriptionBusyBookID: String?
    @State private var inspectedPack: KnowledgePackDTO?
    @State private var booksRevealed = false
    @State private var publicationCandidates: [KnowledgePublicationCandidateDTO] = []
    @State private var inspectedCandidate: KnowledgePublicationCandidateDTO?
    @State private var publicationSecurity = "green"
    @State private var publicationEntitlement = ""
    @State private var publicationOwner = ""
    @Namespace private var bookshelfTransition

    public init(
        highlightedEntitlementKey: String? = nil,
        previewCenter: SubscriptionCenterResponse? = nil,
        onBack: (() -> Void)? = nil,
        showsBackButton: Bool = true
    ) {
        self.highlightedEntitlementKey = highlightedEntitlementKey
        self.previewCenter = previewCenter
        self.onBack = onBack
        self.showsBackButton = showsBackButton
        _center = State(initialValue: previewCenter)
        _bookshelves = State(initialValue: previewCenter?.bookshelves ?? [])
        _isLoading = State(initialValue: previewCenter == nil)
        _selectedShelfID = State(initialValue: ProcessInfo.processInfo.arguments.contains("-bookshelfDetailPreview") ? previewCenter?.bookshelves?.first?.id : nil)
        _inspectedBook = State(initialValue: ProcessInfo.processInfo.arguments.contains("-bookshelfBookPreview") ? previewCenter?.bookshelves?.first?.books.first : nil)
        _subscribedBookIDs = State(initialValue: ProcessInfo.processInfo.arguments.contains("-bookshelfSubscribedPreview") ? Set(previewCenter?.bookshelves?.first?.books.prefix(2).map(\.id) ?? []) : [])
    }

    public var body: some View {
        ZStack {
            Color(hex: "FFFCF6").ignoresSafeArea()

            if isLoading, bookshelves.isEmpty {
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
                ContentUnavailableView("暂无知识书架", systemImage: "books.vertical", description: Text("暂时没有可阅读的知识书籍。"))
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
        .navigationTitle("")
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
                    .buttonStyle(.plain)
                    .accessibilityLabel("返回分类")
                } else if showsBackButton {
                    Button {
                        if let onBack { onBack() } else { dismiss() }
                    } label: {
                        Image(systemName: "chevron.left")
                            .frame(width: 44, height: 44)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("返回知识")
                }
            }
            ToolbarItem(placement: .topBarTrailing) {
                if selectedShelfID != nil {
                    Button { Task { await loadBookshelves() } } label: {
                        Image(systemName: "arrow.clockwise")
                            .frame(width: 44, height: 44)
                    }
                    .buttonStyle(.plain)
                    .disabled(isLoading)
                    .accessibilityLabel("刷新知识书架")
                    .accessibilityIdentifier("publication-bookshelf-refresh")
                }
            }
        }
        .task {
            guard previewCenter == nil else { return }
            await loadBookshelves()
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
        let allBooks = uniqueBooks(in: allShelves)
        let matchingBooks = allBooks.filter {
            bookshelfQuery.isEmpty || $0.title.localizedStandardContains(bookshelfQuery)
                || $0.author.localizedStandardContains(bookshelfQuery)
        }
        let progressByBookID = Dictionary(uniqueKeysWithValues: bookSubscriptions.map { ($0.book.id, $0.progress) })
        let ownedBooks = matchingBooks.filter { subscribedBookIDs.contains($0.id) }
        let shelfBooks = ownedBooks.isEmpty && bookshelfScope == .reading ? Array(matchingBooks.prefix(2)) : ownedBooks
        let scopedBooks = shelfBooks.filter { book in
            let progress = progressByBookID[book.id] ?? 0
            switch bookshelfScope {
            case .reading: return progress < 0.98
            case .saved: return true
            case .finished: return progress >= 0.98
            }
        }
        let visibleShelfIDs = Set(scopedBooks.map(\.id))
        let recommendations = allBooks.filter {
            !subscribedBookIDs.contains($0.id) && !visibleShelfIDs.contains($0.id)
        }
        return ScrollView {
            LazyVStack(spacing: AppTheme.Spacing.lg) {
                HStack(alignment: .center) {
                    Text("书架")
                        .font(.system(size: 34, weight: .bold, design: .serif))
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    Spacer()
                    Button {
                        withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) {
                            showsBookshelfSearch.toggle()
                            if !showsBookshelfSearch { bookshelfQuery = "" }
                        }
                    } label: {
                        Image(systemName: showsBookshelfSearch ? "xmark" : "magnifyingglass")
                            .font(.headline)
                            .frame(width: 44, height: 44)
                            .background(Color.white.opacity(0.82), in: Circle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(showsBookshelfSearch ? "关闭搜索" : "搜索书籍")
                    Button { Task { await loadBookshelves() } } label: {
                        Image(systemName: "arrow.clockwise")
                            .font(.headline)
                            .frame(width: 44, height: 44)
                            .background(Color.white.opacity(0.82), in: Circle())
                    }
                    .buttonStyle(.plain)
                    .disabled(isLoading)
                    .accessibilityLabel("刷新知识书架")
                    .accessibilityIdentifier("publication-bookshelf-refresh")
                }

                if showsBookshelfSearch || !bookshelfQuery.isEmpty {
                    bookshelfSearch(placeholder: "搜索书名、作者或关键词")
                        .transition(.move(edge: .top).combined(with: .opacity))
                }

                HStack(spacing: AppTheme.Spacing.xl) {
                    ForEach(BookshelfScope.allCases) { scope in
                        Button {
                            withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) { bookshelfScope = scope }
                        } label: {
                            VStack(spacing: 7) {
                                Text(scope.rawValue)
                                    .font(.subheadline.weight(bookshelfScope == scope ? .bold : .regular))
                                Capsule()
                                    .fill(bookshelfScope == scope ? AppTheme.Colors.textPrimary : Color.clear)
                                    .frame(width: 26, height: 3)
                            }
                            .foregroundStyle(bookshelfScope == scope ? AppTheme.Colors.textPrimary : AppTheme.Colors.textSecondary)
                        }
                        .buttonStyle(.plain)
                    }
                    Spacer()
                }

                if !bookshelfQuery.isEmpty {
                    bookSearchResults(matchingBooks)
                } else {
                    readingShelf(scopedBooks, progressByBookID: progressByBookID)
                    if !recommendations.isEmpty {
                        recommendationShelf(Array(recommendations.prefix(8)))
                    }
                }
                if let errorMessage { inlineError(errorMessage) }
            }
            .padding(.horizontal, AppTheme.Metrics.contentGutter)
            .padding(.top, AppTheme.Spacing.sm)
            .padding(.bottom, AppTheme.Spacing.xxxl)
        }
        .refreshable { await loadBookshelves() }
        .accessibilityIdentifier("publication-bookshelf-container")
    }

    private func uniqueBooks(in shelves: [KnowledgeBookshelfDTO]) -> [KnowledgeBookDTO] {
        var seen: Set<String> = []
        return shelves.flatMap(\.books).filter { seen.insert($0.id).inserted }
    }

    @ViewBuilder
    private func readingShelf(_ books: [KnowledgeBookDTO], progressByBookID: [String: Double]) -> some View {
        if books.isEmpty {
            VStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: bookshelfScope == .finished ? "checkmark.circle" : "book.closed")
                    .font(.system(size: 30, weight: .light))
                    .foregroundStyle(AppTheme.Colors.primary.opacity(0.55))
                Text(bookshelfScope == .finished ? "还没有读完的书" : "这里还没有书")
                    .font(.headline)
                Text(bookshelfScope == .reading ? "从下方推荐中选一本开始阅读。" : "切换其他分类看看。")
                    .font(.caption)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            }
            .frame(maxWidth: .infinity, minHeight: 138)
            .background(AppTheme.Colors.cardBackground.opacity(0.78), in: RoundedRectangle(cornerRadius: AppTheme.Radius.lg))
        } else {
            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(alignment: .top, spacing: AppTheme.Spacing.lg) {
                    ForEach(Array(books.enumerated()), id: \.element.id) { index, book in
                        Button { inspectedBook = book } label: {
                            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                                bookCover(
                                    title: book.title, author: book.author, seed: book.id,
                                    theme: book.coverTheme, variant: book.coverVariant, width: 146
                                )
                                ProgressView(value: min(max(progressByBookID[book.id] ?? 0, 0), 1))
                                    .tint(index.isMultiple(of: 2) ? AppTheme.Colors.quantumBlue : AppTheme.Colors.statusCompleted)
                                    .frame(width: 146)
                                HStack {
                                    Text(progressByBookID[book.id, default: 0] > 0
                                         ? "已读 \(Int(progressByBookID[book.id, default: 0] * 100))%"
                                         : "开始阅读")
                                    Spacer()
                                }
                                .font(.caption.weight(.medium))
                                .foregroundStyle(AppTheme.Colors.textSecondary)
                                .frame(width: 146)
                                Text(progressByBookID[book.id, default: 0] > 0 ? "继续阅读" : "打开阅读")
                                    .font(.caption.weight(.bold))
                                    .foregroundStyle(.white)
                                    .frame(width: 146, height: 36)
                                    .background(AppTheme.Colors.textPrimary, in: Capsule())
                            }
                        }
                        .buttonStyle(SoftButtonStyle())
                        .accessibilityLabel("打开《\(book.title)》")
                    }
                }
                .padding(.vertical, AppTheme.Spacing.sm)
            }
        }
    }

    private func recommendationShelf(_ books: [KnowledgeBookDTO]) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack {
                Text("为你推荐")
                    .font(.system(.title3, design: .serif, weight: .bold))
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Spacer()
                Text("更多  ›")
                    .font(.caption)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: AppTheme.Spacing.lg) {
                    ForEach(books) { book in
                        Button { inspectedBook = book } label: {
                            VStack(alignment: .leading, spacing: 7) {
                                bookCover(
                                    title: book.title, author: book.author, seed: book.id,
                                    theme: book.coverTheme, variant: book.coverVariant, width: 92
                                )
                                Text(book.title)
                                    .font(.caption2.weight(.semibold))
                                    .foregroundStyle(AppTheme.Colors.textPrimary)
                                    .lineLimit(2)
                                    .frame(width: 92, alignment: .leading)
                                Text(book.author)
                                    .font(.caption2)
                                    .foregroundStyle(AppTheme.Colors.textTertiary)
                                    .lineLimit(1)
                                    .frame(width: 92, alignment: .leading)
                            }
                        }
                        .buttonStyle(SoftButtonStyle())
                    }
                }
                .padding(.vertical, AppTheme.Spacing.sm)
            }
        }
    }

    @ViewBuilder
    private func bookSearchResults(_ books: [KnowledgeBookDTO]) -> some View {
        if books.isEmpty {
            ContentUnavailableView("没有匹配的书", systemImage: "books.vertical", description: Text("试试其他书名、作者或关键词。"))
                .frame(minHeight: 220)
        } else {
            LazyVStack(spacing: AppTheme.Spacing.sm) {
                ForEach(books) { book in
                    Button { inspectedBook = book } label: {
                        HStack(spacing: AppTheme.Spacing.md) {
                            bookCover(
                                title: book.title, author: book.author, seed: book.id,
                                theme: book.coverTheme, variant: book.coverVariant, width: 58
                            )
                            VStack(alignment: .leading, spacing: 5) {
                                Text(book.title)
                                    .font(.headline)
                                    .foregroundStyle(AppTheme.Colors.textPrimary)
                                Text(book.author)
                                    .font(.caption)
                                    .foregroundStyle(AppTheme.Colors.textSecondary)
                                Text(book.publicationTypeLabel ?? book.knowledgeLevel)
                                    .font(.caption2)
                                    .foregroundStyle(AppTheme.Colors.textTertiary)
                            }
                            Spacer()
                            Image(systemName: subscribedBookIDs.contains(book.id) ? "heart.fill" : "heart")
                                .foregroundStyle(subscribedBookIDs.contains(book.id) ? Color.pink : AppTheme.Colors.textTertiary)
                                .frame(width: 44, height: 44)
                        }
                        .padding(AppTheme.Spacing.md)
                        .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                    }
                    .buttonStyle(SoftButtonStyle())
                }
            }
        }
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

    private func ownerPrivateRoster(_ collection: OwnerPrivateCollectionDTO) -> some View {
        let authorities = collection.authorities.filter {
            bookshelfQuery.isEmpty || $0.handle.localizedStandardContains(bookshelfQuery)
                || ($0.displayName?.localizedStandardContains(bookshelfQuery) ?? false)
        }
        return DisclosureGroup {
            LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                ForEach(authorities) { authority in
                    HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(authority.displayName ?? "@\(authority.handle)")
                                .font(AppTheme.Typography.supporting.weight(.semibold))
                            Text("@\(authority.handle) · \(authority.identityAssessment == "identity_mismatch" ? "身份不匹配" : "按存档，未重新核验")")
                                .font(AppTheme.Typography.micro)
                                .foregroundStyle(authority.identityAssessment == "identity_mismatch" ? AppTheme.Icons.destructive : AppTheme.Colors.textSecondary)
                            Text("与 \(collection.sourceCount) 条来源的关系：未知")
                                .font(.caption2)
                                .foregroundStyle(AppTheme.Colors.textTertiary)
                            if let note = authority.identityNotes.last, authority.identityAssessment == "identity_mismatch" {
                                Text(note).font(.caption2).foregroundStyle(AppTheme.Colors.textSecondary)
                            }
                        }
                        Spacer()
                        if let value = authority.officialEntry, let url = URL(string: value), ["http", "https"].contains(url.scheme?.lowercased() ?? "") {
                            Link(destination: url) { Image(systemName: "arrow.up.right.square") }
                                .frame(width: 44, height: 44)
                                .accessibilityLabel("打开 @\(authority.handle) 的存档入口")
                        }
                    }
                }
            }
            .padding(.top, AppTheme.Spacing.sm)
        } label: {
            VStack(alignment: .leading, spacing: 3) {
                Text("跟踪账号名册 · \(collection.authorityCount)")
                    .font(AppTheme.Typography.supporting.weight(.semibold))
                Text("与下方 \(collection.sourceCount) 条来源分开展示；零关联表示未知，不代表确认无关联。")
                    .font(.caption2)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            }
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
        .accessibilityIdentifier("follow-builders-owner-private-roster")
    }

    private func publicRoster(_ collection: PublicKnowledgeCollectionDTO) -> some View {
        let authorities = collection.authorities.filter {
            bookshelfQuery.isEmpty || $0.recordedHandle.localizedStandardContains(bookshelfQuery)
                || $0.recordedDisplayName.localizedStandardContains(bookshelfQuery)
        }
        return DisclosureGroup {
            LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                ForEach(authorities) { authority in
                    HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(authority.recordedDisplayName)
                                .font(AppTheme.Typography.supporting.weight(.semibold))
                            Text(authority.admissionStatus == "website_entry_only_x_mapping_quarantined"
                                 ? "X 身份映射已隔离" : "@\(authority.recordedHandle) · 未独立核验")
                                .font(AppTheme.Typography.micro)
                                .foregroundStyle(authority.admissionStatus == "website_entry_only_x_mapping_quarantined"
                                                 ? AppTheme.Icons.destructive : AppTheme.Colors.textSecondary)
                            Text("与 \(collection.sourceCount) 条来源的作者或背书关系：未建立")
                                .font(.caption2)
                                .foregroundStyle(AppTheme.Colors.textTertiary)
                            if let note = authority.specificQualifications.first {
                                Text(note).font(.caption2).foregroundStyle(AppTheme.Colors.textSecondary)
                            }
                        }
                        Spacer()
                        if let url = URL(string: authority.recordedWebsiteUrl),
                           ["http", "https"].contains(url.scheme?.lowercased() ?? "") {
                            Link(destination: url) { Image(systemName: "arrow.up.right.square") }
                                .frame(width: 44, height: 44)
                                .accessibilityLabel("打开原样保存的网站入口")
                        }
                    }
                }
            }
            .padding(.top, AppTheme.Spacing.sm)
        } label: {
            VStack(alignment: .leading, spacing: 3) {
                Text("公开关注名册 · \(collection.authorityCount)")
                    .font(AppTheme.Typography.supporting.weight(.semibold))
                Text("未独立核验；与下方来源分开展示，不代表作者关系或背书。")
                    .font(.caption2)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            }
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
        .accessibilityIdentifier("follow-builders-public-roster")
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
                    Label(shelf.isSourceShelf ? "\(shelf.bookCount) 条来源" : "\(shelf.bookCount) 本书", systemImage: shelf.isSourceShelf ? "link" : "books.vertical")
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
        .accessibilityLabel("\(shelf.title)，\(shelf.bookCount) \(shelf.isSourceShelf ? "条来源" : "本书")")
        .accessibilityHint("点按打开分类书架")
        .accessibilityIdentifier("bookshelf-collection.\(shelf.id)")
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
                    Text(shelf.isSourceShelf ? "资料来源" : "书架上的精选")
                        .font(AppTheme.Typography.micro.weight(.semibold))
                    Spacer()
                    Text("\(books.count) \(shelf.isSourceShelf ? "条" : "本")")
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
                            .accessibilityIdentifier("publication-book-card.\(book.seriesId ?? "none").\(book.id)")
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
        if shelf.id == "knowledge/publication/follow-builders" {
            return "PUBLIC · 仅来源元数据与链接，不含第三方全文"
        }
        if shelf.id.hasPrefix("owner-private/follow-builders/") {
            return "OWNER PRIVATE · 外部来源按原始署名收录"
        }
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
        seed _: String,
        theme: String? = nil,
        variant: Int? = nil,
        width: CGFloat = 112
    ) -> some View {
        IllustratedBookCover(title: title, author: author, theme: theme, variant: variant, width: width)
    }

    private var shelfPlank: some View {
        RoundedRectangle(cornerRadius: 3, style: .continuous)
            .fill(AppTheme.Colors.border.opacity(0.72))
            .frame(height: 5)
            .shadow(color: AppTheme.Colors.primary.opacity(0.06), radius: 5, y: 3)
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
            let response = try await api.fetchKnowledgeBookshelves()
            bookshelves = response.bookshelves
            publicCollections = response.publicCollections ?? []
            ownerPrivateCollections = response.ownerPrivateCollections ?? []
            if let subscriptions = try? await api.fetchBookSubscriptions() {
                bookSubscriptions = subscriptions
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
                bookSubscriptions.removeAll { $0.book.id == book.id }
            } else {
                let subscription = try await api.subscribeBook(id: book.id)
                subscribedBookIDs.insert(book.id)
                bookSubscriptions.removeAll { $0.book.id == book.id }
                bookSubscriptions.append(subscription)
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
        let credentialGeneration = api.currentCredentialGeneration()
        Task {
            try? await api.syncKnowledgeNote(
                id: note.id, markdown: markdown, updatedAt: note.updatedAt,
                credentialGeneration: credentialGeneration
            )
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
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var api: APIClient

    let book: KnowledgeBookDTO
    let isSubscribed: Bool
    let isBusy: Bool
    let onToggleSubscription: () -> Void
    var onSaveExcerpt: (() -> Void)? = nil
    let onDismiss: () -> Void

    @State private var appeared = false
    @State private var showingReading = ProcessInfo.processInfo.arguments.contains("-bookReadingPreview")
    @State private var selectedBookVersion: String?
    @State private var selectedBookSectionID: String?
    @State private var selectedBookSectionTitle: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Text(book.sourceKind == "owner_private_external" ? "FOLLOW BUILDERS  /  OWNER PRIVATE" : (book.sourceKind == "public_source_index" ? "FOLLOW BUILDERS  /  PUBLIC SOURCE INDEX" : "QUANTUM EDITIONS  /  01"))
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
                        Text(book.sourceKind == "owner_private_external" ? "外部来源原始署名 · 非 Quantumn 出版物" : (book.sourceKind == "public_source_index" ? "原样保存的署名 · 未独立核验" : (book.testSerial == true ? "已审核冻结发布" : (book.authorSource == "fallback" ? "QUANTUM 编研" : "原文署名  ·  QUANTUM 编研"))))
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

                    Text(["owner_private_external", "public_source_index"].contains(book.sourceKind ?? "") ? "SOURCE  /  资料来源" : "ABOUT  /  本书概述")
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
                        readerPill(book.sourceKind == "owner_private_external" ? "外部来源" : (book.sourceKind == "public_source_index" ? "公开元数据" : book.knowledgeLevel), icon: "checkmark.seal")
                        readerPill("\(book.sourceCount) 个来源", icon: "link")
                        if let status = book.contentStatus {
                            readerPill(status == "snapshot" ? "快照正文" : (status == "summary" ? "来源摘要" : (status == "metadata_only" ? "仅元数据" : (status == "unavailable" ? "正文不可用" : "仅链接"))), icon: status == "link_only" ? "link" : "doc.text")
                        }
                    }
                    .padding(.top, 34)
                    .offset(x: 22)

                    if let label = book.publicationTypeLabel {
                        readerPill(label, icon: "book.closed")
                            .padding(.top, 10)
                            .offset(x: 64)
                            .accessibilityIdentifier("publication-type.\(book.id)")
                    }

                    readerPill(book.testSerial == true ? "冻结期次" : (book.freshness == "current" ? "持续更新" : book.freshness), icon: "clock")
                        .padding(.top, 10)
                        .offset(x: 104)

                    Label(
                        book.sourceKind == "owner_private_external"
                            ? (book.contentStatus == "snapshot" ? "这是私有消费的外部快照；正文来源与完整性状态见上方，不表示已获公共再发布许可。" : (book.contentStatus == "summary" ? "这里只提供来源记录摘要，不表示完整原文。" : (book.unavailableReason ?? "这里只提供原始来源链接，没有可验证的正文。")))
                            : (book.sourceKind == "public_source_index" ? "仅来源信息，未发布全文。这里只展示原样保存的元数据与字面来源 URL。" : (book.testSerial == true ? "正文为已审核的冻结发布版本；作者、来源与适用边界见正文。" : "正文为已批准的 Wiki 编研版；Raw 仅用于署名、引用与溯源。")),
                        systemImage: "quote.opening"
                    )
                    .font(.footnote)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .lineSpacing(5)
                    .padding(.top, 48)
                    .frame(maxWidth: 330, alignment: .leading)

                    if book.testSerial == true {
                        Label("测试连载 · \(book.seriesTitle ?? "Quantumn 每日连载") · \(book.issueDate ?? "")", systemImage: "testtube.2")
                            .font(.footnote.weight(.semibold))
                            .foregroundStyle(AppTheme.Colors.primary)
                            .padding(.top, 18)
                    }
                    if !book.isBodyUnavailable, book.sourceKind != "public_source_index" {
                        Button(chatButtonLabel) { openSelectedBookChat() }
                            .frame(minHeight: 44)
                            .accessibilityHint("切换到 Chat，并绑定当前已发布版本")
                            .accessibilityIdentifier("selected-book-chat-open.\(book.id)")
                    }

                    if !book.isBodyUnavailable,
                       ["owner_private_external", "public_source_index"].contains(book.sourceKind ?? ""),
                       let url = book.canonicalHTTPURL {
                        Link("查看原始来源", destination: url)
                            .font(.footnote.weight(.semibold))
                            .padding(.top, 14)
                    }

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
                    if book.isBodyUnavailable, let url = book.canonicalHTTPURL {
                        Link(destination: url) {
                            HStack(spacing: 10) {
                                Image(systemName: "arrow.up.right.square")
                                Text("打开原始来源")
                            }
                            .font(.body.weight(.semibold))
                            .foregroundStyle(Color.white)
                            .frame(maxWidth: .infinity, minHeight: 52)
                            .background(AppTheme.Colors.textPrimary)
                            .clipShape(Capsule())
                        }
                        .buttonStyle(SoftButtonStyle())
                        .accessibilityLabel("打开《\(book.title)》的原始来源")
                        .accessibilityIdentifier("publication-source-open.\(book.id)")
                    } else if !book.isBodyUnavailable {
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
                        .accessibilityValue(isSubscribed ? "subscribed" : "unsubscribed")
                        .accessibilityIdentifier("publication-subscription-control.\(book.id)")
                    }
                    HStack(spacing: 18) {
                        if isSubscribed {
                            Button("移出书架", action: onToggleSubscription)
                                .disabled(isBusy)
                                .accessibilityIdentifier("publication-subscription-remove.\(book.id)")
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
            KnowledgeBookReadingView(
                book: book,
                onScopeChange: { body, section in
                    selectedBookVersion = body.contentVersion
                    selectedBookSectionID = section.id
                    selectedBookSectionTitle = section.title
                },
                onDismiss: { showingReading = false }
            )
        }
    }

    private var chatButtonLabel: String {
        "围绕《\(book.title)》\(selectedBookSectionTitle.map { " · 最近定位章节：\($0)" } ?? "")向 Chat 提问"
    }

    private func openSelectedBookChat() {
        Task { @MainActor in
            var version = selectedBookVersion
            if version == nil { version = try? await api.fetchKnowledgeBookBody(id: book.id).contentVersion }
            guard let version else { return }
            appState.navigateToChatWithPrompt(
                book.sourceKind == "owner_private_external"
                    ? "请只依据我选择的外部来源，区分快照、摘要与未知信息后回答。"
                    : "请结合我选择的本期内容，先说明证据与适用边界，再回答我的问题。",
                contextScope: ChatContextScopeDTO(
                    mode: .platformOnly,
                    selectedBookId: book.id,
                    selectedBookVersion: version,
                    selectedBookSectionId: selectedBookSectionID
                )
            )
            onDismiss()
        }
    }

    private var editorialCover: some View {
        IllustratedBookCover(
            title: book.title,
            author: book.author,
            theme: book.coverTheme,
            variant: book.coverVariant,
            width: 176
        )
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

struct KnowledgeBookReaderLoad {
    let body: KnowledgeBookBodyDTO
    let subscriptions: [KnowledgeBookSubscriptionDTO]?
}

func loadKnowledgeBookReaderData(
    fetchBody: () async throws -> KnowledgeBookBodyDTO,
    fetchSubscriptions: () async throws -> [KnowledgeBookSubscriptionDTO]
) async throws -> KnowledgeBookReaderLoad {
    async let subscriptions = try? await fetchSubscriptions()
    let body = try await fetchBody()
    let loadedSubscriptions = await subscriptions
    try Task.checkCancellation()
    return KnowledgeBookReaderLoad(body: body, subscriptions: loadedSubscriptions)
}

private struct KnowledgeBookReadingView: View {
    @EnvironmentObject private var api: APIClient
    @ObservedObject private var noteStore = KnowledgeNoteStore.shared
    @State private var bookBody: KnowledgeBookBodyDTO?
    @State private var isLoading = true
    @State private var loadError: String?
    @State private var progressError: String?
    @State private var progress = 0.0
    @State private var originalProgress = 0.0
    @State private var lastSentProgress = 0.0
    @State private var hasProgressBaseline = false
    @State private var pendingProgressIndex: Int?
    @State private var selectedExcerpt = ""
    @State private var selectedSection: KnowledgeBookSectionDTO?
    @State private var annotationDraft = ""
    @State private var isWritingAnnotation = false
    @State private var saveMessage: String?
    @State private var showingQuestion = false
    @State private var showingAnnotations = false
    @State private var inspectedAnnotation: ReaderAnnotationEntry?
    let book: KnowledgeBookDTO
    let onScopeChange: (KnowledgeBookBodyDTO, KnowledgeBookSectionDTO) -> Void
    let onDismiss: () -> Void

    @MainActor
    private func loadBody() async {
        let account = KnowledgeNoteStore.shared.accountFingerprint
        isLoading = true
        loadError = nil
        hasProgressBaseline = false
        do {
            #if DEBUG
            if ProcessInfo.processInfo.arguments.contains("-bookReadingLongFixture") {
                let loaded = KnowledgeBookReaderLoad.longPreview
                bookBody = loaded.body
                progressError = "正文已加载，但阅读进度暂时无法同步。"
                isLoading = false
                return
            }
            #endif
            let loaded = try await loadKnowledgeBookReaderData(
                fetchBody: { try await api.fetchKnowledgeBookBody(id: book.id) },
                fetchSubscriptions: { try await api.fetchBookSubscriptions() }
            )
            guard !Task.isCancelled, account == KnowledgeNoteStore.shared.accountFingerprint else { return }
            bookBody = loaded.body
            if let subscriptions = loaded.subscriptions {
                hasProgressBaseline = true
                progressError = nil
                pendingProgressIndex = nil
                if let subscription = subscriptions.first(where: { $0.book.id == book.id }),
                   subscription.contentVersion == loaded.body.contentVersion {
                    progress = subscription.progress
                    originalProgress = subscription.progress
                    lastSentProgress = subscription.progress
                } else {
                    progress = 0
                    originalProgress = 0
                    lastSentProgress = 0
                }
            } else {
                progressError = "正文已加载，但阅读进度暂时无法同步。"
                pendingProgressIndex = nil
            }
        } catch {
            guard !Task.isCancelled, account == KnowledgeNoteStore.shared.accountFingerprint else { return }
            loadError = "正文暂时无法读取，请重试。"
        }
        isLoading = false
    }

    @MainActor
    private func recordReading(sectionIndex: Int) async {
        guard let bookBody, hasProgressBaseline else { return }
        let account = KnowledgeNoteStore.shared.accountFingerprint
        let next = Double(sectionIndex + 1) / Double(bookBody.sections.count)
        guard next > lastSentProgress else { return }
        progress = next
        do {
            _ = try await api.updateBookProgress(
                id: book.id, progress: next, contentVersion: bookBody.contentVersion
            )
            guard account == KnowledgeNoteStore.shared.accountFingerprint else { return }
            lastSentProgress = next
            pendingProgressIndex = nil
            progressError = nil
        } catch {
            guard account == KnowledgeNoteStore.shared.accountFingerprint else { return }
            pendingProgressIndex = sectionIndex
            progressError = "阅读进度未同步，点按重试。"
        }
    }

    @MainActor
    private func saveExcerpt() {
        guard let bookBody, let section = selectedSection else { return }
        let excerpt = String(selectedExcerpt.trimmingCharacters(in: .whitespacesAndNewlines).prefix(4_000))
        guard !excerpt.isEmpty else { return }
        persistExcerpt(
            excerpt,
            detail: annotationDraft.trimmingCharacters(in: .whitespacesAndNewlines),
            section: section,
            bookBody: bookBody
        )
    }

    @MainActor
    private func saveQuestionAnswer(_ question: String, answer: String) {
        guard let bookBody, let section = selectedSection else { return }
        let excerpt = String(selectedExcerpt.trimmingCharacters(in: .whitespacesAndNewlines).prefix(4_000))
        guard !excerpt.isEmpty else { return }
        let detail = "我的问题\n\(question)\n\nAI 回答摘要\n\(String(answer.prefix(2_000)))"
        persistExcerpt(excerpt, detail: detail, section: section, bookBody: bookBody)
    }

    @MainActor
    private func persistExcerpt(
        _ excerpt: String,
        detail: String,
        section: KnowledgeBookSectionDTO,
        bookBody: KnowledgeBookBodyDTO
    ) {
        let isEnglish = ReadingLanguagePresentation.isEnglish(excerpt)
        let quoteTitle = isEnglish ? "Book excerpt" : "书籍摘录"
        let annotationTitle = isEnglish ? "My annotation" : "我的批注"
        let quotedExcerpt = excerpt.replacingOccurrences(of: "\n", with: "\n> ")
        let noteBody = """
        > [!quote] \(quoteTitle)
        > \(quotedExcerpt)

        \(detail.isEmpty ? "" : "> [!note] \(annotationTitle)\n> \(detail.replacingOccurrences(of: "\n", with: "\n> "))")

        ---
        书籍标题：\(bookBody.title)
        章节标题：\(section.title)
        来源书籍 ID：`\(bookBody.bookId)`
        来源章节 ID：`\(section.id)`
        引用：`\(bookBody.citation)`
        """
        guard let note = KnowledgeNoteStore.shared.createNote(
            title: isEnglish ? "\(bookBody.title) | \(section.title) excerpt" : "\(bookBody.title)｜\(section.title)摘录",
            body: noteBody,
            tags: ["阅读批注", "quantum-books"]
        ) else { return }
        let account = KnowledgeNoteStore.shared.accountFingerprint
        let markdown = KnowledgeNoteStore.shared.markdown(for: note)
        let credentialGeneration = api.currentCredentialGeneration()
        Task {
            guard account == KnowledgeNoteStore.shared.accountFingerprint else { return }
            _ = try? await api.syncKnowledgeNote(
                id: note.id, markdown: markdown, updatedAt: note.updatedAt,
                credentialGeneration: credentialGeneration
            )
        }
        saveMessage = isEnglish ? "Saved to your notes" : "已保存到当前账号的笔记"
        annotationDraft = ""
        isWritingAnnotation = false
        selectedExcerpt = ""
        selectedSection = nil
    }

    @ToolbarContentBuilder
    private func readerToolbar(bookBody: KnowledgeBookBodyDTO?, proxy: ScrollViewProxy) -> some ToolbarContent {
        ToolbarItem(placement: .topBarLeading) {
            Button(action: onDismiss) {
                Image(systemName: "chevron.left")
                    .frame(width: 44, height: 44)
                    .background(Color.white.opacity(0.34), in: Circle())
            }
            .accessibilityLabel("返回书籍概述")
        }
        if let bookBody {
            ToolbarItemGroup(placement: .topBarTrailing) {
                Button { showingAnnotations = true } label: {
                    Image(systemName: "bookmark")
                        .frame(width: 44, height: 44)
                }
                .accessibilityLabel("查看我的批注")
                Menu {
                    ForEach(bookBody.sections) { section in
                        Button(section.title) {
                            onScopeChange(bookBody, section)
                            withAnimation {
                                proxy.scrollTo(section.id, anchor: UnitPoint(x: 0.5, y: 0.33))
                            }
                        }
                        .accessibilityIdentifier("publication-reader-nav.\(section.id)")
                    }
                } label: {
                    Label("目录", systemImage: "list.bullet")
                        .frame(minHeight: 44)
                }
                .accessibilityIdentifier("publication-reader-toc.\(book.id)")
            }
        }
    }

    private var readerPage: some View {
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

            if isLoading {
                ProgressView("正在读取已批准正文…")
                    .frame(maxWidth: .infinity, minHeight: 180)
            } else if let loadError {
                ContentUnavailableView(
                    "正文不可用", systemImage: "book.closed",
                    description: Text(loadError)
                )
                Button("重新加载") { Task { await loadBody() } }
                    .frame(minHeight: 44)
            } else if let bookBody {
                Text("第 \(bookBody.edition) 版 · 已读 \(Int(progress * 100))%")
                    .font(.system(.footnote, design: .serif, weight: .semibold))
                    .foregroundStyle(Color.brown.opacity(0.72))
                    .accessibilityValue("original=\(originalProgress);current=\(progress)")
                    .accessibilityIdentifier("publication-reader-progress.\(book.id)")
                if let progressError {
                    if let index = pendingProgressIndex {
                        Button(progressError) { Task { await recordReading(sectionIndex: index) } }
                            .padding(.top, 12)
                    } else {
                        Label(progressError, systemImage: "exclamationmark.arrow.triangle.2.circlepath")
                            .font(.footnote.weight(.semibold))
                            .padding(.top, 12)
                            .accessibilityIdentifier("publication-reader-progress-warning.\(book.id)")
                    }
                }
                LazyVStack(alignment: .leading, spacing: 44) {
                    ForEach(Array(bookBody.sections.enumerated()), id: \.element.id) { index, section in
                        readingSection(section, index: index, bookBody: bookBody)
                    }
                }
                .padding(.top, 22)
                .accessibilityElement(children: .contain)
                .accessibilityLabel("已发布正文内容")
                .accessibilityValue(String(
                    ([bookBody.title] + bookBody.sections.flatMap { [$0.title, $0.markdown] })
                        .joined(separator: "\n").prefix(1_000)
                ))
                .accessibilityIdentifier("publication-reader-content.\(book.id)")
                if let saveMessage {
                    Text(saveMessage).font(.footnote).foregroundStyle(Color.green)
                }
            }
            Spacer(minLength: 120)
        }
        .frame(maxWidth: 560, alignment: .leading)
        .padding(.horizontal, 34)
        .padding(.top, 42)
    }

    private func readingSection(
        _ section: KnowledgeBookSectionDTO,
        index: Int,
        bookBody: KnowledgeBookBodyDTO
    ) -> some View {
        let sectionAnnotations = annotations(for: section)
        return VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            ReadingSectionIllustration(
                index: index,
                title: section.title,
                text: section.markdown
            )
            HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            if !sectionAnnotations.isEmpty {
                RoundedRectangle(cornerRadius: 2)
                    .fill(AppTheme.Colors.quantumBlue)
                    .frame(width: 3)
                    .frame(minHeight: 44, maxHeight: .infinity)
            }
            SelectableReadingText(
                markdown: section.markdown,
                textColor: UIColor(Color(red: 0.23, green: 0.17, blue: 0.11)),
                highlights: sectionAnnotations.map { .init(id: $0.id, quote: $0.quote) },
                onAnnotationTap: { id in
                    inspectedAnnotation = sectionAnnotations.first { $0.id == id }
                },
                onAskSelection: { excerpt in
                    prepareSelection(excerpt, section: section, bookBody: bookBody)
                    showingQuestion = true
                },
                onHighlightSelection: { excerpt in
                    persistExcerpt(excerpt, detail: "", section: section, bookBody: bookBody)
                },
                onAnnotateSelection: { excerpt in
                    prepareSelection(excerpt, section: section, bookBody: bookBody)
                    isWritingAnnotation = true
                }
            ) { excerpt in
                prepareSelection(excerpt, section: section, bookBody: bookBody)
            }
            if let first = sectionAnnotations.first {
                Button { inspectedAnnotation = first } label: {
                    ZStack(alignment: .topTrailing) {
                        Image(systemName: "bubble.left.fill")
                            .font(.title3)
                            .foregroundStyle(AppTheme.Colors.quantumBlue)
                        Text("\(sectionAnnotations.count)")
                            .font(.system(size: 8, weight: .bold))
                            .foregroundStyle(.white)
                            .offset(x: 2, y: 2)
                    }
                    .frame(width: 30, height: 30)
                }
                .buttonStyle(SoftButtonStyle())
                .accessibilityLabel("查看本章批注，共 \(sectionAnnotations.count) 条")
            }
            }
            if index < bookBody.sections.count - 1 {
                HStack(spacing: 12) {
                    Rectangle().frame(height: 1)
                    Image(systemName: "leaf")
                    Rectangle().frame(height: 1)
                }
                .foregroundStyle(Color.brown.opacity(0.24))
                .padding(.vertical, AppTheme.Spacing.md)
                .accessibilityHidden(true)
            }
        }
        .id(section.id)
        .onAppear { Task { await recordReading(sectionIndex: index) } }
    }

    @ViewBuilder
    private var selectionDock: some View {
        if bookBody != nil,
           isWritingAnnotation,
           !selectedExcerpt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            ReaderSelectionActionDock(
                excerpt: selectedExcerpt,
                isEnglish: usesEnglishUI,
                annotationDraft: $annotationDraft,
                isWritingAnnotation: $isWritingAnnotation,
                onClose: {
                    selectedExcerpt = ""
                    selectedSection = nil
                    annotationDraft = ""
                    isWritingAnnotation = false
                },
                onAsk: { showingQuestion = true },
                onSave: saveExcerpt
            )
        }
    }

    private var usesEnglishUI: Bool {
        let source = bookBody.map {
            ([book.title, book.author] + $0.sections.prefix(2).flatMap { [$0.title, $0.markdown] })
                .joined(separator: "\n")
        } ?? "\(book.title) \(book.author)"
        return ReadingLanguagePresentation.isEnglish(source)
    }

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
            ScrollView {
                readerPage
            }
            .accessibilityIdentifier("publication-reader-body.\(book.id)")
            .safeAreaPadding(.top, 104)
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
            .safeAreaInset(edge: .bottom) { selectionDock }
            .toolbarBackground(Color(red: 0.96, green: 0.91, blue: 0.79), for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbar {
                readerToolbar(bookBody: bookBody, proxy: proxy)
            }
            .sheet(isPresented: $showingQuestion) {
                ReaderQuestionSheet(
                    excerpt: selectedExcerpt,
                    sourceTitle: bookBody?.title ?? book.title,
                    sourceSubtitle: selectedSection.map { "\($0.title) · \(book.author)" } ?? book.author,
                    onSaveAnswer: { question, answer in saveQuestionAnswer(question, answer: answer) }
                ) { question, sessionID in
                    guard let bookBody, let selectedSection else {
                        throw NSError(domain: "ReaderQuestion", code: 1, userInfo: [NSLocalizedDescriptionKey: "阅读上下文已失效，请重新选择文字。"])
                    }
                    return api.chatStream(
                        question: question,
                        sessionId: sessionID,
                        quotedContext: String(selectedExcerpt.prefix(2_000)),
                        contextScope: ChatContextScopeDTO(
                            mode: .platformOnly,
                            selectedBookId: book.id,
                            selectedBookVersion: bookBody.contentVersion,
                            selectedBookSectionId: selectedSection.id
                        )
                    )
                }
            }
            .sheet(isPresented: $showingAnnotations) {
                ReaderAnnotationCenterView(bookID: book.id, bookTitle: book.title)
            }
            .sheet(item: $inspectedAnnotation) { ReaderAnnotationDetailSheet(entry: $0) }
            .task(id: book.id) { await loadBody() }
            }
        }
    }

    private func annotations(for section: KnowledgeBookSectionDTO) -> [ReaderAnnotationEntry] {
        noteStore.notes.compactMap(ReaderAnnotationEntry.init(note:)).filter {
            $0.bookID == book.id && $0.sectionID == section.id
        }
    }

    private func prepareSelection(
        _ excerpt: String,
        section: KnowledgeBookSectionDTO,
        bookBody: KnowledgeBookBodyDTO
    ) {
        selectedExcerpt = excerpt
        selectedSection = section
        annotationDraft = ""
        isWritingAnnotation = false
        saveMessage = nil
        onScopeChange(bookBody, section)
    }
}

private struct ReadingSectionIllustration: View {
    let index: Int
    let title: String
    let text: String

    private var key: String { "\(title) \(text.prefix(320))".lowercased() }
    private var isEnglish: Bool { ReadingLanguagePresentation.isEnglish("\(title) \(text.prefix(800))") }
    private func matches(_ terms: [String]) -> Bool { terms.contains { key.contains($0) } }

    private var symbol: String {
        if matches(["数学", "证明", "公式", "定理", "math", "proof", "equation", "theorem"]) { return "function" }
        if matches(["科学", "研究", "技术", "science", "research", "technology", " ai "]) { return "atom" }
        if matches(["旅行", "城市", "路线", "travel", "journey", "city"]) { return "map.fill" }
        if matches(["历史", "年代", "history", "century"]) { return "clock.arrow.circlepath" }
        if matches(["文学", "故事", "诗", "literature", "story", "poem"]) { return "text.book.closed.fill" }
        return "leaf.fill"
    }

    private var colors: [Color] {
        switch symbol {
        case "function": return [AppTheme.Colors.mistSky, AppTheme.Colors.quantumViolet.opacity(0.32)]
        case "atom": return [AppTheme.Colors.mistMint, AppTheme.Colors.mistSky]
        case "map.fill": return [AppTheme.Colors.bentoAmber, AppTheme.Colors.mistRose]
        case "clock.arrow.circlepath": return [AppTheme.Colors.mistRose, AppTheme.Colors.bentoAmber.opacity(0.82)]
        default: return [AppTheme.Colors.mistMint, AppTheme.Colors.bentoAmber.opacity(0.72)]
        }
    }

    var body: some View {
        ZStack {
            LinearGradient(colors: colors, startPoint: .topLeading, endPoint: .bottomTrailing)
            Circle()
                .fill(Color.white.opacity(0.34))
                .frame(width: 168, height: 168)
                .offset(x: 116, y: -52)
            Circle()
                .stroke(Color.white.opacity(0.5), lineWidth: 1)
                .frame(width: 86, height: 86)
                .offset(x: 72, y: 54)
            HStack(spacing: AppTheme.Spacing.lg) {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                    Text(isEnglish ? "CHAPTER \(String(format: "%02d", index + 1))" : "章节 \(String(format: "%02d", index + 1))")
                        .font(AppTheme.Typography.micro.weight(.bold))
                        .tracking(1.2)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                    Text(title)
                        .font(.system(.title3, design: .serif, weight: .semibold))
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .lineLimit(2)
                }
                Spacer(minLength: 0)
                Image(systemName: symbol)
                    .font(.system(size: 34, weight: .medium))
                    .foregroundStyle(AppTheme.Colors.textPrimary.opacity(0.74))
                    .frame(width: 68, height: 68)
                    .background(Color.white.opacity(0.44), in: Circle())
            }
            .padding(AppTheme.Spacing.xl)
        }
        .frame(height: 128)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous)
                .stroke(Color.white.opacity(0.72), lineWidth: 1)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(isEnglish ? "Chapter illustration, \(title)" : "章节插图，\(title)")
    }
}

struct ReadingTextHighlight: Hashable {
    let id: String
    let quote: String
}

struct ReaderSelectionActionDock: View {
    let excerpt: String
    let isEnglish: Bool
    @Binding var annotationDraft: String
    @Binding var isWritingAnnotation: Bool
    let onClose: () -> Void
    let onAsk: () -> Void
    let onSave: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            Capsule()
                .fill(AppTheme.Colors.border.opacity(0.7))
                .frame(width: 38, height: 4)
                .frame(maxWidth: .infinity)

            HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                RoundedRectangle(cornerRadius: 2)
                    .fill(AppTheme.Colors.emberOrange)
                    .frame(width: 4, height: 48)
                VStack(alignment: .leading, spacing: 4) {
                    Text(isEnglish ? "SELECTED PASSAGE" : "已选择这段文字")
                        .font(AppTheme.Typography.micro.weight(.bold))
                        .tracking(0.8)
                        .foregroundStyle(AppTheme.Colors.emberOrange)
                    Text(excerpt)
                        .font(.system(.subheadline, design: .serif, weight: .medium))
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .lineLimit(3)
                }
                Spacer(minLength: 0)
                Button(action: onClose) {
                    Image(systemName: "xmark")
                        .font(.caption.weight(.bold))
                        .frame(width: 32, height: 32)
                        .background(AppTheme.Colors.surfaceTint, in: Circle())
                }
                .buttonStyle(SoftButtonStyle())
                .accessibilityLabel(isEnglish ? "Close text actions" : "关闭选字操作")
            }

            if isWritingAnnotation {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    Label(isEnglish ? "My margin note" : "我的页边批注", systemImage: "pencil.line")
                        .font(AppTheme.Typography.label)
                        .foregroundStyle(AppTheme.Colors.emberOrange)
                    TextField(isEnglish ? "Write what this passage makes you think…" : "像写读书笔记一样，记下你的想法…", text: $annotationDraft, axis: .vertical)
                        .lineLimit(3...6)
                        .padding(AppTheme.Spacing.md)
                        .background(Color.white.opacity(0.92), in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                        .overlay(alignment: .leading) {
                            Rectangle()
                                .fill(AppTheme.Colors.mistRose)
                                .frame(width: 3)
                                .padding(.vertical, 8)
                        }
                    HStack(spacing: AppTheme.Spacing.sm) {
                        Button(isEnglish ? "Cancel" : "取消") { isWritingAnnotation = false }
                            .frame(maxWidth: .infinity, minHeight: 46)
                            .background(AppTheme.Colors.surfaceTint, in: Capsule())
                        Button(action: onSave) {
                            Label(isEnglish ? "Save annotation" : "保存批注", systemImage: "bookmark.fill")
                                .frame(maxWidth: .infinity, minHeight: 46)
                                .foregroundStyle(AppTheme.Colors.textPrimary)
                                .background(AppTheme.Colors.mistMint, in: Capsule())
                        }
                        .disabled(annotationDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                    .buttonStyle(SoftButtonStyle())
                }
            } else {
                HStack(spacing: AppTheme.Spacing.sm) {
                    actionTile(
                        isEnglish ? "Ask Quantum" : "问 Quantum",
                        subtitle: isEnglish ? "Explain in this page" : "在本页内解释",
                        icon: "bubble.left.and.text.bubble.right.fill",
                        color: AppTheme.Colors.mistMint,
                        action: onAsk
                    )
                    actionTile(
                        isEnglish ? "Add a note" : "写批注",
                        subtitle: isEnglish ? "Mark it like a student" : "留下划线与页签",
                        icon: "pencil.line",
                        color: AppTheme.Colors.mistSky,
                        action: { isWritingAnnotation = true }
                    )
                }
            }
        }
        .padding(.horizontal, AppTheme.Spacing.lg)
        .padding(.top, AppTheme.Spacing.sm)
        .padding(.bottom, AppTheme.Spacing.lg)
        .background(.regularMaterial)
        .background(Color.white.opacity(0.72))
        .clipShape(UnevenRoundedRectangle(topLeadingRadius: 28, topTrailingRadius: 28))
        .overlay(alignment: .top) { Divider().opacity(0.45) }
        .shadow(color: Color.black.opacity(0.09), radius: 18, y: -3)
    }

    private func actionTile(
        _ title: String,
        subtitle: String,
        icon: String,
        color: Color,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: icon)
                    .font(.system(size: 18, weight: .semibold))
                    .frame(width: 34, height: 34)
                    .background(Color.white.opacity(0.72), in: Circle())
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(AppTheme.Typography.label)
                    Text(subtitle)
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                        .lineLimit(1)
                }
                Spacer(minLength: 0)
            }
            .foregroundStyle(AppTheme.Colors.textPrimary)
            .padding(.horizontal, AppTheme.Spacing.sm)
            .frame(maxWidth: .infinity, minHeight: 64)
            .background(color, in: RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        }
        .buttonStyle(SoftButtonStyle())
    }
}

struct SelectableReadingText: UIViewRepresentable {
    let markdown: String
    var textColor = UIColor.label
    var highlights: [ReadingTextHighlight] = []
    var onAnnotationTap: (String) -> Void = { _ in }
    var onAskSelection: (String) -> Void = { _ in }
    var onHighlightSelection: (String) -> Void = { _ in }
    var onAnnotateSelection: (String) -> Void = { _ in }
    let onSelection: (String) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(
            onSelection: onSelection,
            onAnnotationTap: onAnnotationTap,
            onAskSelection: onAskSelection,
            onHighlightSelection: onHighlightSelection,
            onAnnotateSelection: onAnnotateSelection
        )
    }

    func makeUIView(context: Context) -> UITextView {
        let view = UITextView()
        view.isEditable = false
        view.isScrollEnabled = false
        view.backgroundColor = .clear
        view.textContainerInset = .zero
        view.textContainer.lineFragmentPadding = 0
        view.adjustsFontForContentSizeCategory = true
        view.isSelectable = true
        view.tintColor = UIColor(AppTheme.Colors.quantumBlue)
        view.delegate = context.coordinator
        return view
    }

    func updateUIView(_ view: UITextView, context: Context) {
        context.coordinator.onSelection = onSelection
        context.coordinator.onAnnotationTap = onAnnotationTap
        context.coordinator.onAskSelection = onAskSelection
        context.coordinator.onHighlightSelection = onHighlightSelection
        context.coordinator.onAnnotateSelection = onAnnotateSelection
        let signature = highlights.map { "\($0.id):\($0.quote.hashValue)" }.joined(separator: "|")
        guard context.coordinator.source != markdown || context.coordinator.highlightSignature != signature else { return }
        context.coordinator.source = markdown
        context.coordinator.highlightSignature = signature
        let renderedMarkdown = InlineMathPresentation.segments(in: markdown)
            .map { $0.isMath ? MathFormulaPresentation.displayText($0.text) : $0.text }
            .joined()
        let attributed = (try? AttributedString(markdown: renderedMarkdown)) ?? AttributedString(renderedMarkdown)
        view.attributedText = NSAttributedString(attributed)
        view.font = UIFont.preferredFont(forTextStyle: .body)
        view.textColor = textColor
        let paragraph = NSMutableParagraphStyle()
        paragraph.lineSpacing = 7
        paragraph.paragraphSpacing = 14
        paragraph.lineBreakMode = .byWordWrapping
        view.textStorage.addAttribute(
            .paragraphStyle,
            value: paragraph,
            range: NSRange(location: 0, length: view.textStorage.length)
        )
        let source = view.textStorage.string as NSString
        for highlight in highlights {
            let renderedQuote = InlineMathPresentation.segments(in: highlight.quote)
                .map { $0.isMath ? MathFormulaPresentation.displayText($0.text) : $0.text }
                .joined()
            var searchRange = NSRange(location: 0, length: source.length)
            while searchRange.length > 0 {
                let range = source.range(of: renderedQuote, options: [], range: searchRange)
                guard range.location != NSNotFound else { break }
                guard let annotationURL = URL(string: "quantum-annotation://\(highlight.id)") else { break }
                view.textStorage.addAttributes([
                    .backgroundColor: UIColor(AppTheme.Colors.mistSky).withAlphaComponent(0.82),
                    .underlineStyle: NSUnderlineStyle.single.rawValue,
                    .underlineColor: UIColor(AppTheme.Colors.quantumBlue).withAlphaComponent(0.82),
                    .link: annotationURL
                ], range: range)
                let next = NSMaxRange(range)
                searchRange = NSRange(location: next, length: source.length - next)
            }
        }
        view.accessibilityHint = "Long press to select text. Tap an underlined passage to read its note."
    }

    func sizeThatFits(_ proposal: ProposedViewSize, uiView: UITextView, context: Context) -> CGSize? {
        guard let width = proposal.width else { return nil }
        return uiView.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude))
    }

    final class Coordinator: NSObject, UITextViewDelegate {
        var source = ""
        var highlightSignature = ""
        var onSelection: (String) -> Void
        var onAnnotationTap: (String) -> Void
        var onAskSelection: (String) -> Void
        var onHighlightSelection: (String) -> Void
        var onAnnotateSelection: (String) -> Void

        init(
            onSelection: @escaping (String) -> Void,
            onAnnotationTap: @escaping (String) -> Void,
            onAskSelection: @escaping (String) -> Void,
            onHighlightSelection: @escaping (String) -> Void,
            onAnnotateSelection: @escaping (String) -> Void
        ) {
            self.onSelection = onSelection
            self.onAnnotationTap = onAnnotationTap
            self.onAskSelection = onAskSelection
            self.onHighlightSelection = onHighlightSelection
            self.onAnnotateSelection = onAnnotateSelection
        }

        func textViewDidChangeSelection(_ textView: UITextView) {
            guard textView.selectedRange.length > 0 else { return }
            onSelection((textView.text as NSString).substring(with: textView.selectedRange))
        }

        func textView(
            _ textView: UITextView,
            editMenuForTextIn range: NSRange,
            suggestedActions: [UIMenuElement]
        ) -> UIMenu? {
            guard range.length > 0 else { return UIMenu(children: suggestedActions) }
            let excerpt = (textView.text as NSString).substring(with: range)
            let isEnglish = ReadingLanguagePresentation.isEnglish(excerpt)
            return UIMenu(children: [
                UIAction(title: isEnglish ? "Ask" : "提问", image: UIImage(systemName: "sparkles")) { [weak self] _ in
                    self?.onAskSelection(excerpt)
                },
                UIAction(title: isEnglish ? "Highlight" : "高亮", image: UIImage(systemName: "highlighter")) { [weak self] _ in
                    self?.onHighlightSelection(excerpt)
                },
                UIAction(title: isEnglish ? "Annotate" : "批注", image: UIImage(systemName: "note.text")) { [weak self] _ in
                    self?.onAnnotateSelection(excerpt)
                },
                UIAction(title: isEnglish ? "Copy" : "复制", image: UIImage(systemName: "doc.on.doc")) { _ in
                    UIPasteboard.general.string = excerpt
                }
            ])
        }

        func textView(
            _ textView: UITextView,
            shouldInteractWith URL: URL,
            in characterRange: NSRange,
            interaction: UITextItemInteraction
        ) -> Bool {
            guard URL.scheme == "quantum-annotation", let id = URL.host else { return true }
            onAnnotationTap(id)
            return false
        }
    }
}

enum ReadingLanguagePresentation {
    static func isEnglish(_ text: String) -> Bool {
        let letters = text.unicodeScalars.filter { CharacterSet.letters.contains($0) }
        guard !letters.isEmpty else { return false }
        return letters.filter { $0.isASCII }.count * 5 >= letters.count * 4
    }
}

struct ReaderQuestionSheet: View {
    let excerpt: String
    let sourceTitle: String
    let sourceSubtitle: String
    let onSaveAnswer: ((String, String) -> Void)?
    let ask: (String, String?) async throws -> AsyncThrowingStream<APIClient.StreamEvent, Error>
    @Environment(\.dismiss) private var dismiss
    @State private var question = ""
    @State private var lastQuestion = ""
    @State private var answer = ""
    @State private var sessionID: String?
    @State private var errorMessage: String?
    @State private var isAsking = false
    @State private var statusText = ""
    @FocusState private var isQuestionFocused: Bool

    private var isEnglish: Bool { ReadingLanguagePresentation.isEnglish(excerpt) }
    private var suggestions: [String] {
        isEnglish
            ? ["What does this passage mean?", "How does it connect to this chapter?", "Can you give a real-world example?"]
            : ["这段话是什么意思？", "它和本章主题有什么关系？", "能举一个现实例子吗？"]
    }

    init(
        excerpt: String,
        sourceTitle: String = "当前阅读",
        sourceSubtitle: String = "已基于选中文字",
        onSaveAnswer: ((String, String) -> Void)? = nil,
        ask: @escaping (String, String?) async throws -> AsyncThrowingStream<APIClient.StreamEvent, Error>
    ) {
        self.excerpt = excerpt
        self.sourceTitle = sourceTitle
        self.sourceSubtitle = sourceSubtitle
        self.onSaveAnswer = onSaveAnswer
        self.ask = ask
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                Capsule()
                    .fill(AppTheme.Colors.border)
                    .frame(width: 38, height: 5)
                    .frame(maxWidth: .infinity)

                HStack {
                    Text(isEnglish ? "Ask Quantum" : "向 Quantum 提问")
                        .font(.system(size: 22, weight: .semibold))
                    Spacer()
                    Button { dismiss() } label: {
                        Image(systemName: "xmark")
                            .font(.headline)
                            .frame(width: 42, height: 42)
                            .background(AppTheme.Colors.surfaceTint, in: Circle())
                    }
                    .buttonStyle(SoftButtonStyle())
                    .accessibilityLabel(isEnglish ? "Close" : "关闭")
                }

                Text("“\(excerpt)”")
                    .font(.system(.body, design: .serif, weight: .medium))
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                    .lineSpacing(5)
                    .padding(AppTheme.Spacing.md)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(AppTheme.Colors.mistSky.opacity(0.72), in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))

                questionComposer

                if answer.isEmpty && !isAsking {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: AppTheme.Spacing.sm) {
                            ForEach(suggestions, id: \.self) { suggestion in
                                Button(suggestion) { question = suggestion }
                                    .font(AppTheme.Typography.micro.weight(.semibold))
                                    .buttonStyle(.bordered)
                                    .tint(AppTheme.Colors.quantumBlue)
                            }
                        }
                    }
                }

                if isAsking || !answer.isEmpty { answerCard }

                if let errorMessage {
                    Label(errorMessage, systemImage: "exclamationmark.circle")
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.statusError)
                        .padding(AppTheme.Spacing.md)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(AppTheme.Colors.dangerSurface, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                }
            }
            .padding(.horizontal, AppTheme.Metrics.contentGutter)
            .padding(.top, AppTheme.Spacing.sm)
            .padding(.bottom, AppTheme.Spacing.xl)
            .contentShape(Rectangle())
            .onTapGesture { isQuestionFocused = false }
        }
        .accessibilityIdentifier("reader-question-sheet")
        .scrollDismissesKeyboard(.interactively)
        .background(Color(hex: "FFFEFB").ignoresSafeArea())
        .presentationDetents([.fraction(0.72), .large])
        .presentationDragIndicator(.hidden)
    }

    private var questionComposer: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            TextField(isEnglish ? "Ask a follow-up…" : "继续问这段内容…", text: $question, axis: .vertical)
                .lineLimit(2...5)
                .focused($isQuestionFocused)
                .accessibilityIdentifier("reader-question-input")
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.top, AppTheme.Spacing.md)
            HStack {
                Spacer()
                Text("\(question.count)/200")
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.textTertiary)
                Button { Task { await submit() } } label: {
                    Image(systemName: isAsking ? "hourglass" : "arrow.up")
                        .font(.headline.weight(.bold))
                        .foregroundStyle(Color.white)
                        .frame(width: 44, height: 44)
                        .background(AppTheme.Colors.quantumBlue, in: Circle())
                }
                .buttonStyle(SoftButtonStyle())
                .disabled(question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isAsking || question.count > 200)
                .accessibilityLabel(isEnglish ? "Send question" : "发送问题")
                .accessibilityIdentifier("reader-question-send")
            }
            .padding(.horizontal, AppTheme.Spacing.sm)
            .padding(.bottom, AppTheme.Spacing.sm)
        }
        .background(Color.white, in: RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        .overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.lg).stroke(AppTheme.Colors.border.opacity(0.72)) }
    }

    private var answerCard: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack {
                QuantumAvatarView(size: 30)
                Text(isEnglish ? "Quantum AI" : "AI 回答")
                    .font(AppTheme.Typography.cardTitle)
                Spacer()
                if isAsking { ProgressView().tint(AppTheme.Colors.quantumBlue) }
            }
            if !statusText.isEmpty {
                Text(statusText).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
            }
            MarkdownText(String(answer.suffix(4_000)))
                .font(AppTheme.Typography.body)
                .foregroundStyle(AppTheme.Colors.textPrimary)
                .lineSpacing(6)
                .textSelection(.enabled)

            HStack(spacing: AppTheme.Spacing.sm) {
                Image("book_cover_literature").resizable().scaledToFill().frame(width: 42, height: 52).clipped()
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                VStack(alignment: .leading, spacing: 2) {
                    Text(sourceTitle).font(AppTheme.Typography.label).lineLimit(1)
                    Text(sourceSubtitle).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary).lineLimit(1)
                }
                Spacer()
                Image(systemName: "arrow.up.right.square").foregroundStyle(AppTheme.Colors.textSecondary)
            }
            .padding(AppTheme.Spacing.sm)
            .background(AppTheme.Colors.surfaceTint.opacity(0.74), in: RoundedRectangle(cornerRadius: AppTheme.Radius.sm))

            if !answer.isEmpty, let onSaveAnswer {
                Button {
                    onSaveAnswer(lastQuestion, answer)
                    dismiss()
                } label: {
                    Label(isEnglish ? "Save as annotation" : "作为批注保存", systemImage: "bookmark")
                        .font(AppTheme.Typography.label)
                        .frame(maxWidth: .infinity, minHeight: 48)
                }
                .buttonStyle(.bordered)
                .tint(AppTheme.Colors.quantumBlue)
            }
        }
        .padding(AppTheme.Spacing.md)
        .background(Color.white, in: RoundedRectangle(cornerRadius: AppTheme.Radius.lg))
        .overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.lg).stroke(AppTheme.Colors.border.opacity(0.5)) }
    }

    @MainActor
    private func submit() async {
        let value = question.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return }
        isQuestionFocused = false
        lastQuestion = value
        isAsking = true
        answer = ""
        statusText = isEnglish ? "Reading the selected context…" : "正在阅读选中的上下文…"
        errorMessage = nil
        defer { isAsking = false }
        do {
            let stream = try await ask(value, sessionID)
            for try await event in stream {
                switch event {
                case .delta(let text):
                    answer += text
                    statusText = isEnglish ? "Writing the report…" : "正在整理成阅读报告…"
                case .status(_, let detail):
                    if !detail.isEmpty { statusText = detail }
                case .toolStart(_, _, let label):
                    if !label.isEmpty { statusText = label }
                case .answerPage(let page):
                    let pageText = page.blocks.map(\.content).joined(separator: "\n\n")
                    if !pageText.isEmpty { answer = pageText }
                case .clarify(let prompt, let choices, _, _, _, _, _):
                    answer = (["## \(prompt)"] + choices.map { "- \($0)" }).joined(separator: "\n")
                case .done(let id, let finalAnswer):
                    sessionID = id ?? sessionID
                    if let finalAnswer, !finalAnswer.isEmpty { answer = finalAnswer }
                    statusText = isEnglish ? "Report ready" : "解读完成"
                case .error(_, let message):
                    errorMessage = message.isEmpty ? (isEnglish ? "The question could not be completed." : "这次提问没有完成，请重试。") : message
                    return
                default:
                    break
                }
            }
            if answer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                errorMessage = isEnglish ? "No answer was returned. Please try again." : "没有收到回答，请重试。"
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct ReaderAnnotationEntry: Identifiable {
    let id: String
    let kind: String
    let quote: String
    let detail: String
    let date: String
    let bookID: String
    let sectionID: String
    let sectionTitle: String

    init(
        id: String, kind: String, quote: String, detail: String, date: String,
        bookID: String = "", sectionID: String = "", sectionTitle: String = "未分章"
    ) {
        self.id = id
        self.kind = kind
        self.quote = quote
        self.detail = detail
        self.date = date
        self.bookID = bookID
        self.sectionID = sectionID
        self.sectionTitle = sectionTitle
    }

    init?(note: KnowledgeNote) {
        guard note.tags.contains("书籍摘录") || note.tags.contains("阅读批注") else { return nil }
        let lines = note.body.components(separatedBy: .newlines)
        guard let bookID = Self.metadata("来源书籍 ID：", in: lines),
              let sectionID = Self.metadata("来源章节 ID：", in: lines),
              let quoteIndex = lines.firstIndex(where: { $0.hasPrefix("> [!quote]") })
        else { return nil }
        let noteIndex = lines.firstIndex(where: { $0.hasPrefix("> [!note]") })
        let dividerIndex = lines.firstIndex(of: "---") ?? lines.endIndex
        let quoteEnd = noteIndex ?? dividerIndex
        let quote = Self.calloutContent(lines[(quoteIndex + 1)..<quoteEnd], excludingMetadata: true)
        guard !quote.isEmpty else { return nil }
        let detail = noteIndex.map {
            Self.calloutContent(lines[($0 + 1)..<dividerIndex], excludingMetadata: false)
        } ?? ""
        let sectionTitle = Self.metadata("章节标题：", in: lines)
            ?? lines.compactMap { line -> String? in
                let value = line.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: "> ", with: "")
                guard value.hasPrefix("章节：") else { return nil }
                return value.dropFirst(3).components(separatedBy: " · ").first
            }.first
            ?? "未分章"
        self.init(
            id: note.id,
            kind: detail.isEmpty ? "高亮" : (detail.contains("AI 回答摘要") || detail.contains("AI answer") ? "问答" : "笔记"),
            quote: quote,
            detail: detail,
            date: note.updatedAt.formatted(date: .abbreviated, time: .shortened),
            bookID: bookID,
            sectionID: sectionID,
            sectionTitle: sectionTitle
        )
    }

    private static func metadata(_ prefix: String, in lines: [String]) -> String? {
        guard let line = lines.first(where: { $0.trimmingCharacters(in: .whitespaces).hasPrefix(prefix) }) else { return nil }
        return line.trimmingCharacters(in: .whitespaces)
            .dropFirst(prefix.count)
            .trimmingCharacters(in: CharacterSet(charactersIn: " `"))
    }

    private static func calloutContent(_ lines: ArraySlice<String>, excludingMetadata: Bool) -> String {
        lines.compactMap { raw -> String? in
            let trimmed = raw.trimmingCharacters(in: .whitespaces)
            guard !trimmed.isEmpty, !trimmed.hasPrefix("> [!") else { return nil }
            let value = trimmed.hasPrefix("> ") ? String(trimmed.dropFirst(2)) : trimmed
            if excludingMetadata && (value.hasPrefix("《") || value.hasPrefix("章节：")) { return nil }
            return value
        }.joined(separator: "\n")
    }
}

struct ReaderAnnotationCenterView: View {
    private enum Filter: String, CaseIterable, Identifiable {
        case all = "全部"
        case highlight = "高亮"
        case note = "笔记"
        case question = "问答"
        var id: Self { self }
    }

    let bookID: String
    let bookTitle: String
    let previewEntries: [ReaderAnnotationEntry]?
    @ObservedObject private var store = KnowledgeNoteStore.shared
    @Environment(\.dismiss) private var dismiss

    init(bookID: String = "", bookTitle: String, previewEntries: [ReaderAnnotationEntry]? = nil) {
        self.bookID = bookID
        self.bookTitle = bookTitle
        self.previewEntries = previewEntries
    }

    private var entries: [ReaderAnnotationEntry] {
        if let previewEntries { return previewEntries }
        return store.notes.compactMap(ReaderAnnotationEntry.init(note:)).filter { $0.bookID == bookID }
    }

    @State private var inspectedEntry: ReaderAnnotationEntry?
    @State private var filter: Filter = .all

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: AppTheme.Spacing.sm) {
                            ForEach(Filter.allCases) { item in
                                Button {
                                    filter = item
                                } label: {
                                    Text("\(item.rawValue) (\(count(for: item)))")
                                        .font(AppTheme.Typography.supporting.weight(.semibold))
                                        .foregroundStyle(filter == item ? AppTheme.Colors.quantumBlue : AppTheme.Colors.textSecondary)
                                        .padding(.horizontal, AppTheme.Spacing.md)
                                        .frame(minHeight: 38)
                                        .background(filter == item ? AppTheme.Colors.mistSky : AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
                                }
                                .buttonStyle(.plain)
                                .accessibilityAddTraits(filter == item ? .isSelected : [])
                            }
                        }
                    }
                    if filteredEntries.isEmpty {
                        ContentUnavailableView("还没有批注", systemImage: "bookmark", description: Text("在阅读器中选中文字即可提问或保存。"))
                    } else {
                        ForEach(groupedSections, id: \.0) { group in
                            annotationSection(group.0, entries: group.1)
                        }
                    }
                }
                .padding(AppTheme.Metrics.contentGutter)
            }
            .navigationTitle("我的批注")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("返回") { dismiss() } }
            }
            .sheet(item: $inspectedEntry) { ReaderAnnotationDetailSheet(entry: $0) }
        }
    }

    private var groupedSections: [(String, [ReaderAnnotationEntry])] {
        Dictionary(grouping: filteredEntries, by: \.sectionTitle)
            .sorted { $0.key.localizedStandardCompare($1.key) == .orderedAscending }
    }

    private var filteredEntries: [ReaderAnnotationEntry] {
        switch filter {
        case .all: entries
        case .highlight: entries.filter { $0.kind == "高亮" }
        case .note: entries.filter { $0.kind == "笔记" || $0.kind == "批注" }
        case .question: entries.filter { $0.kind == "问答" }
        }
    }

    private func count(for filter: Filter) -> Int {
        switch filter {
        case .all: entries.count
        case .highlight: entries.filter { $0.kind == "高亮" }.count
        case .note: entries.filter { $0.kind == "笔记" || $0.kind == "批注" }.count
        case .question: entries.filter { $0.kind == "问答" }.count
        }
    }

    private func annotationSection(_ title: String, entries: [ReaderAnnotationEntry]) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Text("\(title)  (\(entries.count))")
                .font(.headline.weight(.semibold))
            ForEach(entries) { entry in
                Button { inspectedEntry = entry } label: {
                    HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                    Image(systemName: icon(for: entry.kind))
                        .font(.headline)
                        .foregroundStyle(color(for: entry.kind))
                        .frame(width: 42, height: 42)
                        .background(color(for: entry.kind).opacity(0.12), in: RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
                    VStack(alignment: .leading, spacing: 4) {
                        Text(entry.quote)
                            .font(.system(.subheadline, design: .serif, weight: .medium))
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                            .lineLimit(3)
                        if !entry.detail.isEmpty {
                            Label(entry.detail, systemImage: "pencil.line")
                                .font(AppTheme.Typography.supporting)
                                .foregroundStyle(AppTheme.Colors.textSecondary)
                                .lineLimit(3)
                        }
                        Text("\(entry.kind) · \(entry.date)").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textTertiary)
                    }
                    Spacer(); Image(systemName: "ellipsis").font(.caption).foregroundStyle(AppTheme.Colors.textTertiary)
                    }
                    .padding(AppTheme.Spacing.md)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.lg))
                    .overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.lg).stroke(AppTheme.Colors.border.opacity(0.55)) }
                }
                .buttonStyle(SoftButtonStyle())
            }
        }
    }

    private func icon(for kind: String) -> String {
        kind == "高亮" ? "bookmark.fill" : kind == "问答" ? "bubble.left.and.text.bubble.right.fill" : "doc.text.fill"
    }

    private func color(for kind: String) -> Color {
        kind == "高亮" ? AppTheme.Colors.emberOrange : AppTheme.Colors.quantumBlue
    }
}

struct ReaderAnnotationDetailSheet: View {
    let entry: ReaderAnnotationEntry
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xl) {
                    HStack {
                        Label("我的批注", systemImage: "bookmark.fill")
                            .font(AppTheme.Typography.cardTitle)
                            .foregroundStyle(AppTheme.Colors.quantumBlue)
                        Spacer()
                        Text(entry.date).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textTertiary)
                    }
                    Text("“\(entry.quote)”")
                        .font(.system(.body, design: .serif, weight: .medium))
                        .padding(AppTheme.Spacing.md)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(AppTheme.Colors.mistSky.opacity(0.72), in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                    if let question = questionText {
                        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                            Text("我的问题").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textTertiary)
                            Text(question).font(AppTheme.Typography.body)
                            Text("AI 回答摘要").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textTertiary).padding(.top, AppTheme.Spacing.sm)
                            MarkdownText(answerText ?? "")
                                .font(AppTheme.Typography.body)
                                .lineSpacing(5)
                        }
                    } else if !entry.detail.isEmpty {
                        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                            Text("我的想法").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textTertiary)
                            Text(entry.detail).font(.system(.body, design: .serif)).lineSpacing(5)
                        }
                    }
                    Label(entry.sectionTitle, systemImage: "book.closed.fill")
                        .font(AppTheme.Typography.supporting.weight(.semibold))
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                        .padding(AppTheme.Spacing.md)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                }
                .padding(AppTheme.Metrics.contentGutter)
            }
            .background(AppTheme.Colors.background.ignoresSafeArea())
            .navigationTitle("读书批注")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { dismiss() } } }
        }
        .presentationDetents([.medium, .large])
    }

    private var questionText: String? {
        splitDetail.0
    }

    private var answerText: String? {
        splitDetail.1
    }

    private var splitDetail: (String?, String?) {
        guard let questionRange = entry.detail.range(of: "我的问题"),
              let answerRange = entry.detail.range(of: "AI 回答摘要") else { return (nil, nil) }
        let question = entry.detail[questionRange.upperBound..<answerRange.lowerBound]
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let answer = entry.detail[answerRange.upperBound...]
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return (question.isEmpty ? nil : question, answer.isEmpty ? nil : answer)
    }
}

#if DEBUG
struct ReaderAnnotationPrototypeHost: View {
    let pageID: String
    @State private var showingQuestion = false

    var body: some View {
        if pageID.hasSuffix("p04") {
            ReaderAnnotationCenterView(bookTitle: "我与地坛", previewEntries: Self.entries)
        } else {
            ReaderPrototypePage(stage: pageID.hasSuffix("p03") ? .saved : pageID.hasSuffix("p01") ? .selected : .plain)
                .sheet(isPresented: $showingQuestion) {
                    ReaderQuestionSheet(excerpt: "阳光很好，树叶在风里沙沙地响。") { _, _ in
                        AsyncThrowingStream { continuation in
                            continuation.yield(.delta("这句话通过声音和光线写出了宁静的瞬间。"))
                            continuation.yield(.done(sessionId: nil, answer: nil))
                            continuation.finish()
                        }
                    }
                }
                .onAppear { showingQuestion = pageID.hasSuffix("p02") }
        }
    }

    private static let entries = [
        ReaderAnnotationEntry(id: "a1", kind: "问答", quote: "阳光很好，树叶在风里沙沙地响。", detail: "这句话表达了怎样的情感？", date: "9月12日"),
        ReaderAnnotationEntry(id: "a2", kind: "高亮", quote: "北海的菊花开了，我们去看看吧。", detail: "", date: "9月10日"),
        ReaderAnnotationEntry(id: "a3", kind: "笔记", quote: "母爱的表达", detail: "母亲的沉默更有力量。", date: "9月10日"),
        ReaderAnnotationEntry(id: "a4", kind: "问答", quote: "城市与人的关系", detail: "如何理解城市对于个体的意义？", date: "9月3日"),
        ReaderAnnotationEntry(id: "a5", kind: "高亮", quote: "城墙在夜色中安静地延伸。", detail: "", date: "9月3日"),
        ReaderAnnotationEntry(id: "a6", kind: "笔记", quote: "自由与孤独", detail: "书中反复出现的孤独，是否也是一种自由？", date: "9月1日"),
    ]
}

private struct ReaderPrototypePage: View {
    enum Stage { case plain, selected, saved }
    let stage: Stage

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {
                        paragraph("母亲喜欢花，可自从我的腿瘫痪后，她侍弄的那些花都死了。")
                        paragraph("那年秋天，母亲推着我去地坛。")
                        ZStack(alignment: .topLeading) {
                            Text("阳光很好，树叶在风里沙沙地响。")
                                .font(.system(size: 20, design: .serif)).lineSpacing(12)
                                .padding(.vertical, 5)
                                .background(stage == .plain ? Color.clear : AppTheme.Colors.quantumBlue.opacity(0.18))
                            if stage == .selected {
                                HStack(spacing: 0) {
                                    action("提问", "sparkles")
                                    action("高亮", "highlighter")
                                    action("批注", "note.text")
                                    action("复制", "doc.on.doc")
                                }
                                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 9))
                                .shadow(radius: 9, y: 4)
                                .offset(x: 4, y: -50)
                            }
                        }
                        paragraph("她忽然对我说：“北海的菊花开了，我们去看看吧。”")
                        paragraph("我摇摇头。她沉默了一会儿，又说：“不，我推你去。”")
                        paragraph("那天的阳光，至今仍在我心里。")
                        if stage == .saved {
                            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                                Label("我的批注 · 9月12日", systemImage: "bookmark.fill")
                                    .font(.caption.weight(.semibold)).foregroundStyle(AppTheme.Colors.quantumBlue)
                                Text("“阳光很好，树叶在风里沙沙地响。”").font(.system(.body, design: .serif))
                                Text("我的问题：这句话表达了怎样的情感？").font(AppTheme.Typography.supporting)
                                Text("AI 回答摘要：以自然描写呈现宁静温暖的氛围，体现作者在困境中仍感受到生活的美好。")
                                    .font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
                            }
                            .padding(AppTheme.Spacing.md)
                            .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                            .overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.md).stroke(AppTheme.Colors.border) }
                        }
                    }
                    .padding(.horizontal, 34).padding(.top, 44)
                }
                VStack(spacing: 8) {
                    HStack { Text("68 / 245"); Spacer(); Text("28%") }.font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
                    ProgressView(value: 0.28)
                    HStack { Label("目录", systemImage: "list.bullet"); Spacer(); Text("上一章"); Text("下一章  ›") }.font(AppTheme.Typography.supporting)
                }
                .padding(AppTheme.Metrics.contentGutter).background(.ultraThinMaterial)
            }
            .navigationTitle("我与地坛")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    HStack { Button("字体") {}; Image(systemName: "bookmark"); Image(systemName: "ellipsis") }
                }
            }
        }
        .background(Color(red: 0.99, green: 0.98, blue: 0.95))
    }

    private func paragraph(_ text: String) -> some View {
        Text(text).font(.system(size: 20, design: .serif)).lineSpacing(12)
    }

    private func action(_ title: String, _ icon: String) -> some View {
        Button(action: {}) { VStack(spacing: 3) { Image(systemName: icon); Text(title).font(.caption) }.frame(width: 70, height: 52) }
            .buttonStyle(.plain)
    }
}

struct V4AgentManagementPrototypeHost: View {
    let pageID: String

    var body: some View {
        if pageID.hasSuffix("p02") {
            AgentKnowledgePreview()
        } else if pageID.hasSuffix("p03") {
            AgentToolsPreview()
        } else if pageID.hasSuffix("p04") {
            AgentToolDetailPreview()
        } else {
            AgentOverviewPreview()
        }
    }
}

private struct AgentOverviewPreview: View {
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                    HStack(spacing: AppTheme.Spacing.md) {
                        Image(systemName: "book.fill").font(.largeTitle).foregroundStyle(.white)
                            .frame(width: 68, height: 68).background(AppTheme.Colors.quantumGradient, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                        VStack(alignment: .leading) { Text("文献助手").font(AppTheme.Typography.screenTitle); Label("已启用", systemImage: "circle.fill").font(.caption).foregroundStyle(AppTheme.Colors.statusCompleted) }
                        Spacer(); Menu { Button("编辑") {}; Button("复制") {}; Button("删除", role: .destructive) {} } label: { Image(systemName: "ellipsis").frame(width: 44, height: 44).background(AppTheme.Colors.surfaceTint, in: Circle()) }
                    }
                    Text("检索、阅读与综述学术文献").font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary)
                    HStack { tab("概览", true); tab("知识", false); tab("工具", false) }
                    Text("帮助你高效检索、阅读和整理学术文献，生成结构化的综述与笔记。")
                        .font(AppTheme.Typography.body).foregroundStyle(AppTheme.Colors.textSecondary)
                    info("clock", "创建时间", "2024年12月9日")
                    info("person", "创建者", "我")
                    info("chart.bar", "使用次数", "427 次（近 30 天）")
                    info("tag", "适用场景", "课程学习、论文写作、科研探索")
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                        Text("快速操作").font(.headline)
                        Button("▶  开始对话") {}.buttonStyle(QuantumPrimaryButtonStyle())
                        Button("在新窗口打开", systemImage: "book") {}.buttonStyle(.bordered).frame(maxWidth: .infinity)
                    }
                    Button("删除智能体", systemImage: "trash", role: .destructive) {}
                        .buttonStyle(.bordered).tint(.red).frame(maxWidth: .infinity)
                }
                .padding(AppTheme.Metrics.contentGutter)
            }
        }
    }

    private func tab(_ title: String, _ active: Bool) -> some View {
        Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(active ? AppTheme.Colors.quantumBlue : AppTheme.Colors.textSecondary)
            .frame(maxWidth: .infinity, minHeight: 42).overlay(alignment: .bottom) { if active { Rectangle().fill(AppTheme.Colors.quantumBlue).frame(height: 2) } }
    }

    private func info(_ icon: String, _ title: String, _ value: String) -> some View {
        HStack { Image(systemName: icon).foregroundStyle(AppTheme.Icons.interactive).frame(width: 26); Text(title).foregroundStyle(AppTheme.Colors.textSecondary); Spacer(); Text(value) }.font(AppTheme.Typography.supporting)
    }
}

private struct AgentKnowledgePreview: View {
    private let sources = [
        ("doc.text.fill", "我的笔记", "12 篇笔记 · 个人", "全部可用"),
        ("book.fill", "机器学习（第2版）", "书籍 · 高等教育出版社", "仅检索"),
        ("doc.fill", "课程资料", "8 个文件 · 个人", "摘要可用"),
        ("globe", "学术网页", "3 个网站", "仅检索"),
    ]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                    HStack { Image(systemName: "magnifyingglass"); Text("搜索知识来源").foregroundStyle(AppTheme.Colors.textTertiary); Spacer() }
                        .padding(AppTheme.Spacing.md).background(AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
                    HStack { ForEach(["全部", "笔记", "书籍", "文件", "网页"], id: \.self) { item in Text(item).font(AppTheme.Typography.micro).frame(maxWidth: .infinity, minHeight: 32).background(item == "全部" ? AppTheme.Colors.mistSky : AppTheme.Colors.surfaceTint, in: Capsule()) } }
                    Text("已添加的知识来源（4）").font(.headline)
                    ForEach(sources, id: \.1) { source in
                        HStack(spacing: AppTheme.Spacing.md) {
                            Image(systemName: source.0).foregroundStyle(AppTheme.Icons.interactive).frame(width: 40, height: 40).background(AppTheme.Colors.mistSky, in: RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
                            VStack(alignment: .leading) { Text(source.1).font(.subheadline.weight(.semibold)); Text(source.2).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }
                            Spacer(); Text(source.3).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.statusCompleted); Image(systemName: "ellipsis")
                        }
                        .padding(AppTheme.Spacing.md).background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md)).overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.md).stroke(AppTheme.Colors.border) }
                    }
                    Button("添加知识来源", systemImage: "plus") {}.buttonStyle(.bordered).frame(maxWidth: .infinity)
                    VStack(spacing: AppTheme.Spacing.sm) { Image(systemName: "book.closed").font(.largeTitle).foregroundStyle(AppTheme.Colors.textTertiary); Text("还没有知识来源").font(.headline); Text("添加笔记、书籍、文件或网页\n让智能体基于你的知识提供更好的回答").multilineTextAlignment(.center).font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary); Button("添加第一个来源") {}.buttonStyle(.borderedProminent) }
                        .frame(maxWidth: .infinity).padding(AppTheme.Spacing.xl).background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                }
                .padding(AppTheme.Metrics.contentGutter)
            }
            .navigationTitle("知识管理").navigationBarTitleDisplayMode(.inline)
            .toolbar { Button(action: {}) { Image(systemName: "plus") } }
        }
    }
}

private struct AgentToolsPreview: View {
    @State private var enabled: Set<String> = ["网页搜索", "地图查询", "图像生成", "PDF 导出"]
    private let tools = [
        ("magnifyingglass", "网页搜索", "在互联网上检索最新信息", AppTheme.Colors.quantumBlue),
        ("map.fill", "地图查询", "查询地点、路线与周边信息", AppTheme.Colors.statusCompleted),
        ("photo.fill", "图像生成", "根据描述生成图片", AppTheme.Colors.quantumViolet),
        ("doc.fill", "PDF 导出", "将内容导出为 PDF", AppTheme.Colors.statusError),
        ("rectangle.stack.fill", "PPT 生成", "生成演示文稿大纲与幻灯片", AppTheme.Colors.emberOrange),
    ]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                    Text("内置工具").font(.headline)
                    Text("启用合适的工具，扩展智能体的能力。")
                        .font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary)
                    ForEach(tools, id: \.1) { tool in
                        VStack(spacing: AppTheme.Spacing.sm) {
                            HStack(spacing: AppTheme.Spacing.md) {
                                Image(systemName: tool.0).foregroundStyle(tool.3).frame(width: 44, height: 44).background(tool.3.opacity(0.1), in: RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
                                VStack(alignment: .leading) { Text(tool.1).font(.subheadline.weight(.semibold)); Text(tool.2).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }
                                Spacer(); Toggle("", isOn: Binding(get: { enabled.contains(tool.1) }, set: { value in if value { enabled.insert(tool.1) } else { enabled.remove(tool.1) } })).labelsHidden()
                            }
                            HStack { Text("权限：经确认"); Text("范围：学术相关"); Spacer(); Button("▶ 测试") {} }.font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
                        }
                        .padding(AppTheme.Spacing.md).background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md)).overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.md).stroke(AppTheme.Colors.border) }
                    }
                }
                .padding(AppTheme.Metrics.contentGutter)
            }
            .navigationTitle("工具能力").navigationBarTitleDisplayMode(.inline)
            .toolbar { Button("管理") {} }
        }
    }
}

private struct AgentToolDetailPreview: View {
    var body: some View {
        ZStack(alignment: .bottom) {
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                        HStack(spacing: AppTheme.Spacing.md) { Image(systemName: "magnifyingglass").font(.title).foregroundStyle(AppTheme.Icons.interactive).frame(width: 54, height: 54).background(AppTheme.Colors.mistSky, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md)); VStack(alignment: .leading) { Text("网页搜索").font(.headline); Label("已启用", systemImage: "circle.fill").font(.caption).foregroundStyle(AppTheme.Colors.statusCompleted); Text("在互联网上检索最新信息").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer(); Button("编辑") {} }
                        detail("权限级别", "自动使用")
                        detail("使用范围", "学术相关")
                        detail("使用上限", "每日最多 50 次")
                        Text("最近使用").font(.headline)
                        recent("为什么量子计算重要？", "今天 14:20 · 已完成")
                        recent("检索最新的 AI 教育应用案例", "12月9日 10:36 · 已完成")
                        recent("搜索相关论文与数据", "12月8日 21:17 · 失败")
                        HStack { Button("替换工具", systemImage: "arrow.triangle.2.circlepath") {}; Button("停用工具", systemImage: "nosign") {} }.buttonStyle(.bordered)
                        Button("删除工具", systemImage: "trash", role: .destructive) {}.buttonStyle(.bordered).tint(.red).frame(maxWidth: .infinity)
                    }
                    .padding(AppTheme.Metrics.contentGutter).padding(.bottom, 180)
                }
                .navigationTitle("工具详情").navigationBarTitleDisplayMode(.inline)
            }
            VStack(spacing: AppTheme.Spacing.md) {
                Text("确认删除此工具？").font(.headline)
                Text("删除后将无法恢复，历史使用记录也会被移除。").font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary)
                HStack { Button("取消") {}; Button("删除", role: .destructive) {}.buttonStyle(.borderedProminent).tint(.red) }.frame(maxWidth: .infinity)
            }
            .padding(AppTheme.Spacing.lg).frame(maxWidth: .infinity).background(.regularMaterial, in: UnevenRoundedRectangle(topLeadingRadius: 24, topTrailingRadius: 24)).shadow(radius: 20)
        }
    }

    private func detail(_ title: String, _ value: String) -> some View { HStack { Text(title); Spacer(); Text(value).foregroundStyle(AppTheme.Colors.textSecondary); Image(systemName: "chevron.right") }.font(AppTheme.Typography.supporting).padding(.vertical, 6) }
    private func recent(_ title: String, _ status: String) -> some View { HStack { VStack(alignment: .leading) { Text(title).font(.subheadline); Text(status).font(AppTheme.Typography.micro).foregroundStyle(status.contains("失败") ? AppTheme.Colors.statusError : AppTheme.Colors.statusCompleted) }; Spacer(); Image(systemName: "chevron.right") }.padding(.vertical, 5) }
}

struct V3SettingsMemoryPrototypeHost: View {
    let pageID: String

    var body: some View {
        NavigationStack {
            ZStack {
                QuantumMistBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                        if page == 1 { profile }
                        else if page == 2 { agentBuilder }
                        else if page == 3 { memoryCenter }
                        else { memoryDetail }
                    }
                    .padding(AppTheme.Metrics.contentGutter)
                    .padding(.bottom, 48)
                }
            }
            .navigationTitle(page == 1 ? "我的" : (page == 2 ? "创建智能体" : (page == 3 ? "记忆中心" : "记忆详情")))
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    @ViewBuilder private var profile: some View {
        HStack(spacing: 16) { Circle().fill(AppTheme.Colors.quantumGradient).frame(width: 82, height: 82).overlay { Image(systemName: "person.fill").font(.largeTitle).foregroundStyle(.white) }; VStack(alignment: .leading, spacing: 5) { Text("林小满").font(AppTheme.Typography.sectionTitle); Text("保持好奇，持续学习").foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer(); Image(systemName: "chevron.right") }
        HStack { Image(systemName: "crown.fill").foregroundStyle(AppTheme.Colors.statusWarning); VStack(alignment: .leading) { Text("Quantum Pro").font(AppTheme.Typography.cardTitle); Text("2025年12月12日到期").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer(); Button("管理") {}.buttonStyle(.bordered) }.padding().background(AppTheme.Colors.mistLilac, in: RoundedRectangle(cornerRadius: 16))
        Text("本月使用").font(AppTheme.Typography.cardTitle); HStack(alignment: .bottom, spacing: 8) { Text("320 / 1,000").font(.title2); Spacer(); ForEach([9, 14, 12, 18, 22, 30, 25, 38, 47, 64, 49, 72, 58, 85], id: \.self) { value in Capsule().fill(AppTheme.Colors.quantumGradient).frame(width: 9, height: CGFloat(value)) } }.padding().quantumCard()
        VStack(spacing: 0) { settingRow("偏好设置", "slider.horizontal.3"); Divider(); settingRow("隐私与数据", "shield"); Divider(); settingRow("帮助与反馈", "questionmark.circle"); Divider(); settingRow("退出登录", "rectangle.portrait.and.arrow.right", AppTheme.Colors.statusError) }.quantumCard()
    }

    @ViewBuilder private var agentBuilder: some View {
        HStack(spacing: 0) { ForEach(Array(["基本信息", "个性设定", "知识与工具", "完成"].enumerated()), id: \.offset) { index, title in VStack { Text("\(index + 1)").foregroundStyle(index == 0 ? .white : AppTheme.Colors.textSecondary).frame(width: 28, height: 28).background(index == 0 ? AppTheme.Colors.quantumBlue : AppTheme.Colors.surfaceTint, in: Circle()); Text(title).font(AppTheme.Typography.micro) }.frame(maxWidth: .infinity) } }
        Text("1. 它的目的是什么？").font(AppTheme.Typography.cardTitle); Text("帮助我整理课程资料，生成复习笔记…").foregroundStyle(AppTheme.Colors.textTertiary).padding().frame(maxWidth: .infinity, minHeight: 100, alignment: .topLeading).quantumCard()
        Text("2. 个性与语气").font(AppTheme.Typography.cardTitle); LazyVGrid(columns: [.init(.adaptive(minimum: 96))], spacing: 8) { ForEach(["专业严谨", "友好耐心", "简洁高效", "启发思考", "根据我的风格", "自定义"], id: \.self) { value in Text(value).font(AppTheme.Typography.micro).padding(.horizontal, 13).padding(.vertical, 9).background(value == "专业严谨" ? AppTheme.Colors.selectionTint : AppTheme.Colors.surfaceTint, in: Capsule()).overlay { Capsule().stroke(value == "专业严谨" ? AppTheme.Icons.interactive : .clear) } } }
        Text("3. 知识访问").font(AppTheme.Typography.cardTitle); HStack { knowledge("我的笔记", "已选择 12 项", "folder.fill"); knowledge("我的书架", "已选择 3 本", "books.vertical.fill"); knowledge("课程资料", "已选择", "leaf.fill") }
        Text("4. 工具能力").font(AppTheme.Typography.cardTitle); VStack(spacing: 0) { tool("网页搜索", "获取最新信息", true); Divider(); tool("内容总结", "整理与提炼", true); Divider(); tool("生成笔记", "创建结构化笔记", true) }.quantumCard()
        Text("5. 图标与颜色").font(AppTheme.Typography.cardTitle); HStack { ForEach([Color.blue, .purple, .green, .cyan, .orange], id: \.description) { color in Circle().fill(color.opacity(0.65)).frame(width: 48, height: 48) }; Circle().stroke(AppTheme.Colors.border).frame(width: 48, height: 48).overlay { Image(systemName: "plus") } }
        Button("保存智能体") {}.buttonStyle(QuantumPrimaryButtonStyle()).controlSize(.large).frame(maxWidth: .infinity)
    }

    @ViewBuilder private var memoryCenter: some View {
        TextField("搜索记忆…", text: .constant("")).textFieldStyle(.roundedBorder)
        ScrollView(.horizontal, showsIndicators: false) { HStack { chip("全部"); chip("笔记"); chip("书籍"); chip("对话"); chip("网页") } }
        ScrollView(.horizontal, showsIndicators: false) { HStack { chip("全部时间"); chip("近7天"); chip("近30天"); chip("近一年") } }
        Text("今天").font(AppTheme.Typography.cardTitle)
        memory("我更喜欢图像化的学习方式", "来自 对话 · 14:20", "bubble.left.fill", true)
        memory("期末准备：高数重点", "来自 笔记 · 10:36", "doc.text.fill", false)
        Text("本周").font(AppTheme.Typography.cardTitle)
        memory("想去日本交换学习", "来自 对话 · 12月10日", "bubble.left.fill", false)
        memory("对人工智能与教育的思考", "来自 网页 · 12月9日", "link", true)
        memory("喜欢安静的图书馆", "来自 笔记 · 12月8日", "leaf.fill", false)
        Text("更早").font(AppTheme.Typography.cardTitle)
        memory("TED：如何保持好奇心", "来自 书籍 · 11月28日", "books.vertical.fill", false)
    }

    @ViewBuilder private var memoryDetail: some View {
        HStack { Image(systemName: "leaf.fill").foregroundStyle(AppTheme.Colors.statusCompleted).frame(width: 54, height: 54).background(AppTheme.Colors.mistMint, in: RoundedRectangle(cornerRadius: 12)); VStack(alignment: .leading) { Text("对人工智能与教育的思考").font(AppTheme.Typography.label); Text("来自 网页 · 2024年12月9日 14:20").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer(); Image(systemName: "pin.fill").foregroundStyle(AppTheme.Colors.statusWarning) }
        Text("“技术的意义不在于替代人，\n而在于让更多人有机会成为更好的自己。”").font(.system(size: 21, design: .serif)).lineSpacing(8).padding().frame(maxWidth: .infinity).background(AppTheme.Colors.warningSurface, in: RoundedRectangle(cornerRadius: 14))
        HStack { Image(systemName: "link"); VStack(alignment: .leading) { Text("原始来源").font(AppTheme.Typography.micro); Text("AI 与教育的未来").font(AppTheme.Typography.label); Text("www.example.com").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer(); Image(systemName: "arrow.up.forward.app") }.padding().quantumCard()
        status("同步失败", "网络延迟，请检查网络后重试。")
        Text("管理").font(AppTheme.Typography.cardTitle); HStack { Button("编辑", systemImage: "pencil") {}; Button("取消置顶", systemImage: "pin.slash") {}; Button("删除", systemImage: "trash", role: .destructive) {} }.buttonStyle(.bordered)
        VStack(spacing: 12) { Text("确认删除此记忆？").font(AppTheme.Typography.cardTitle); Text("删除后将无法恢复，该记忆不会再用于智能体回答或个性化推荐。").font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary).multilineTextAlignment(.center); HStack { Button("取消") {}; Button("删除", role: .destructive) {}.buttonStyle(.borderedProminent).tint(.red) } }.padding().background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18))
        HStack { Image(systemName: "party.popper.fill").foregroundStyle(AppTheme.Colors.quantumViolet); VStack(alignment: .leading) { Text("智能体创建成功！").font(AppTheme.Typography.label); Text("你的专属学习伙伴已就绪").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer(); Button("开始对话") {}.buttonStyle(.borderedProminent) }.padding().background(AppTheme.Colors.mistLilac, in: RoundedRectangle(cornerRadius: 14))
    }

    private var page: Int { Int(pageID.suffix(2)) ?? 1 }
    private func settingRow(_ title: String, _ icon: String, _ color: Color = AppTheme.Colors.textPrimary) -> some View { HStack { Image(systemName: icon).foregroundStyle(color).frame(width: 28); Text(title).foregroundStyle(color); Spacer(); Image(systemName: "chevron.right") }.padding() }
    private func knowledge(_ title: String, _ detail: String, _ icon: String) -> some View { VStack(spacing: 6) { Image(systemName: icon).foregroundStyle(AppTheme.Icons.interactive); Text(title).font(AppTheme.Typography.micro); Text(detail).font(.system(size: 9)).foregroundStyle(AppTheme.Colors.textSecondary) }.frame(maxWidth: .infinity, minHeight: 78).background(AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: 10)) }
    private func tool(_ title: String, _ detail: String, _ enabled: Bool) -> some View { HStack { Image(systemName: "sparkles").foregroundStyle(AppTheme.Icons.interactive); VStack(alignment: .leading) { Text(title).font(AppTheme.Typography.label); Text(detail).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer(); Toggle("", isOn: .constant(enabled)).labelsHidden() }.padding() }
    private func chip(_ title: String) -> some View { Text(title).font(AppTheme.Typography.micro).padding(.horizontal, 13).padding(.vertical, 8).background(AppTheme.Colors.surfaceTint, in: Capsule()) }
    private func memory(_ title: String, _ detail: String, _ icon: String, _ pinned: Bool) -> some View { HStack { Image(systemName: icon).foregroundStyle(AppTheme.Icons.interactive).frame(width: 44, height: 44).background(AppTheme.Colors.selectionTint, in: RoundedRectangle(cornerRadius: 10)); VStack(alignment: .leading) { Text(title).font(AppTheme.Typography.label); Text(detail).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer(); if pinned { Image(systemName: "pin.fill").foregroundStyle(AppTheme.Colors.quantumBlue) }; Image(systemName: "ellipsis") }.padding().quantumCard() }
    private func status(_ title: String, _ detail: String) -> some View { HStack { Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(AppTheme.Colors.statusError); VStack(alignment: .leading) { Text(title).font(AppTheme.Typography.label); Text(detail).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer(); Button("重试") {} }.padding().background(AppTheme.Colors.dangerSurface, in: RoundedRectangle(cornerRadius: 12)) }
}

struct V3SubscriptionPrototypeHost: View {
    let pageID: String

    var body: some View {
        NavigationStack {
            ZStack { QuantumMistBackground(); ScrollView { VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) { if page == 1 { benefits } else if page == 2 { plans } else if page == 3 { application } else { governance } }.padding(AppTheme.Metrics.contentGutter).padding(.bottom, 50) } }
            .navigationTitle(page == 1 ? "我的权益" : (page == 2 ? "选择适合你的方案" : (page == 3 ? "申请进度" : "机构管理")))
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    @ViewBuilder private var benefits: some View {
        VStack(alignment: .leading, spacing: 9) { HStack { Text("教育版").font(AppTheme.Typography.sectionTitle); Text("在用中").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.statusCompleted).padding(6).background(AppTheme.Colors.successSurface, in: Capsule()) }; Text("面向认证的在校学生").foregroundStyle(AppTheme.Colors.textSecondary); Text("2024年9月1日 – 2025年8月31日").font(AppTheme.Typography.micro).padding(8).background(.white.opacity(0.75), in: RoundedRectangle(cornerRadius: 8)); Text("还有 312 天到期").font(AppTheme.Typography.micro) }.padding().frame(maxWidth: .infinity, alignment: .leading).background(LinearGradient(colors: [AppTheme.Colors.mistMint, AppTheme.Colors.mistSky], startPoint: .leading, endPoint: .trailing), in: RoundedRectangle(cornerRadius: 18))
        Text("包含的功能").font(AppTheme.Typography.cardTitle); HStack { feature("笔记", "无限创建", "note.text"); feature("AI 助理", "每月 500 次", "sparkles"); feature("云同步", "多设备同步", "icloud.and.arrow.up"); feature("书籍与阅读", "精品书库", "books.vertical") }
        Text("本月剩余配额").font(AppTheme.Typography.cardTitle); VStack(alignment: .leading, spacing: 8) { HStack { Text("AI 助理使用"); Spacer(); Text("320 / 500") }; ProgressView(value: 0.64).tint(AppTheme.Colors.quantumGradient) }.padding().quantumCard()
        setting("同步购买", "恢复已购项目", "arrow.triangle.2.circlepath"); setting("兑换代码", "输入优惠码或学校发放的代码", "plus.app")
    }

    @ViewBuilder private var plans: some View {
        Text("为不同的学习阶段，提供合适的支持。").foregroundStyle(AppTheme.Colors.textSecondary)
        planCard("免费版", "¥0", "永久免费", ["最多 50 条笔记", "基础阅读功能", "1GB 云存储"], false)
        planCard("教育版", "¥0", "完成认证", ["无限笔记与书架", "每月 500 次 AI 助理", "20GB 云存储", "精品学术书库"], true)
        planCard("专业版", "¥68/月", "或 ¥648/年", ["更高的 AI 配额", "100GB 云存储", "高级功能与优先支持"], false)
        Button("申请教育版") {}.buttonStyle(QuantumPrimaryButtonStyle()).controlSize(.large).frame(maxWidth: .infinity)
        Button("已有代码？立即兑换") {}.frame(maxWidth: .infinity)
    }

    @ViewBuilder private var application: some View {
        HStack { Image(systemName: "graduationcap.fill").font(.largeTitle).foregroundStyle(AppTheme.Colors.quantumBlue).frame(width: 64, height: 64).background(AppTheme.Colors.selectionTint, in: Circle()); VStack(alignment: .leading) { Text("教育版申请").font(AppTheme.Typography.sectionTitle); Text("提交于 2024年9月12日").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) } }.padding().quantumCard()
        ForEach(Array([("已提交", "我们已收到你的申请", true), ("学校审核中", "由你所在学校的管理员进行审核", true), ("审核通过", "通过后将自动升级权益", false), ("审核未通过", "可根据反馈补充信息并重新提交", false)].enumerated()), id: \.offset) { index, item in HStack(alignment: .top, spacing: 13) { Image(systemName: index == 0 ? "checkmark.circle.fill" : (index == 1 ? "circle.inset.filled" : "circle")).foregroundStyle(item.2 ? AppTheme.Icons.interactive : AppTheme.Icons.tertiary); VStack(alignment: .leading) { Text(item.0).font(AppTheme.Typography.label); Text(item.1).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary); if index == 1 { Text("预计 1–3 个工作日").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textTertiary) } } }.padding(.vertical, 8) }
        HStack { Image(systemName: "exclamationmark.circle.fill").foregroundStyle(AppTheme.Colors.statusWarning); VStack(alignment: .leading) { Text("需要补充信息").font(AppTheme.Typography.label); Text("请上传有效的学生证或在读证明，以便我们继续审核。").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer(); Image(systemName: "chevron.right") }.padding().background(AppTheme.Colors.warningSurface, in: RoundedRectangle(cornerRadius: 14))
        Button("补充材料") {}.buttonStyle(QuantumPrimaryButtonStyle()).controlSize(.large).frame(maxWidth: .infinity)
    }

    @ViewBuilder private var governance: some View {
        Picker("", selection: .constant(0)) { Text("待审核").tag(0); Text("方案管理").tag(1) }.pickerStyle(.segmented)
        TextField("搜索姓名、学号或邮箱", text: .constant("")).textFieldStyle(.roundedBorder)
        ScrollView(.horizontal, showsIndicators: false) { HStack { chip("全部 12"); chip("学生认证 9"); chip("教师 2"); chip("机构 1") } }
        ForEach([("陈同学", "chen@example.edu.cn", "计算机科学 · 大三", "1天前"), ("林同学", "lin@example.edu.cn", "新闻传播 · 大二", "2天前"), ("王同学", "wang@example.edu.cn", "经济学 · 大一", "3天前")], id: \.0) { item in VStack(spacing: 10) { HStack { Circle().fill(AppTheme.Colors.selectionTint).frame(width: 52, height: 52).overlay { Text(String(item.0.prefix(1))).font(AppTheme.Typography.cardTitle) }; VStack(alignment: .leading) { Text(item.0).font(AppTheme.Typography.label); Text(item.1).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary); Text(item.2).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textTertiary) }; Spacer(); Text(item.3).font(AppTheme.Typography.micro) }; HStack { Spacer(); Button("拒绝") {}.buttonStyle(.bordered); Button("通过") {}.buttonStyle(.borderedProminent) } }.padding().quantumCard() }
    }

    private var page: Int { Int(pageID.suffix(2)) ?? 1 }
    private func feature(_ title: String, _ detail: String, _ icon: String) -> some View { VStack(spacing: 7) { Image(systemName: icon).foregroundStyle(AppTheme.Icons.interactive); Text(title).font(AppTheme.Typography.micro); Text(detail).font(.system(size: 8)).foregroundStyle(AppTheme.Colors.textSecondary) }.frame(maxWidth: .infinity, minHeight: 88).background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 10)).overlay { RoundedRectangle(cornerRadius: 10).stroke(AppTheme.Colors.border) } }
    private func setting(_ title: String, _ detail: String, _ icon: String) -> some View { HStack { Image(systemName: icon).foregroundStyle(AppTheme.Icons.interactive); VStack(alignment: .leading) { Text(title).font(AppTheme.Typography.label); Text(detail).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer(); Image(systemName: "chevron.right") }.padding().quantumCard() }
    private func planCard(_ title: String, _ price: String, _ detail: String, _ features: [String], _ selected: Bool) -> some View { VStack(alignment: .leading, spacing: 11) { HStack { Image(systemName: selected ? "graduationcap.fill" : "leaf.fill").font(.title2).foregroundStyle(selected ? AppTheme.Colors.quantumViolet : AppTheme.Colors.statusCompleted); VStack(alignment: .leading) { Text(title).font(AppTheme.Typography.sectionTitle); Text(detail).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer(); Text(price).font(.title2.bold()); Image(systemName: selected ? "checkmark.circle.fill" : "circle").foregroundStyle(selected ? AppTheme.Icons.interactive : AppTheme.Icons.tertiary) }; ForEach(features, id: \.self) { Label($0, systemImage: "checkmark").font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.statusCompleted) } }.padding().background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 16)).overlay { RoundedRectangle(cornerRadius: 16).stroke(selected ? AppTheme.Icons.interactive : AppTheme.Colors.border, lineWidth: selected ? 2 : 1) } }
    private func chip(_ title: String) -> some View { Text(title).font(AppTheme.Typography.micro).padding(.horizontal, 12).padding(.vertical, 8).background(AppTheme.Colors.surfaceTint, in: Capsule()) }
}

extension SubscriptionCenterResponse {
    static var bookshelfPreview: Self {
        func book(
            _ id: String,
            _ title: String,
            author: String,
            _ summary: String,
            theme: String,
            variant: Int,
            sources: Int,
            format: String
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
                sourceCount: sources,
                publicationFormat: format
            )
        }

        let product = [
            book("product-map", "AI 产品全景图", author: "Quantum 研究团队", "从用户问题、能力边界到商业闭环，理解 AI 产品的完整结构。", theme: "product", variant: 0, sources: 18, format: "book"),
            book("subscription", "AI 原生研发手册", author: "Louis Claxton · Anthropic", "把意图、规格、验证和部署重组为 Agent 可执行的研发闭环。", theme: "product", variant: 1, sources: 12, format: "chapter"),
            book("agent-os", "LLM Knowledge Bases", author: "Andrej Karpathy", "从 Raw 原始材料到 Wiki 增量编译，理解面向 LLM 的知识库工作方式。", theme: "product", variant: 2, sources: 23, format: "article"),
        ]
        let strategy = [
            book("signals", "战略信号手册", author: "Quantum 研究团队", "识别市场变化、技术拐点与竞争动作中的高价值信号。", theme: "strategic-signal", variant: 3, sources: 31, format: "book"),
            book("competitor", "Claude 工程实践", author: "Anthropic", "从官方案例中提炼 Claude Code 的工程化方法与适用边界。", theme: "competitor", variant: 4, sources: 27, format: "chapter"),
            book("decision", "高质量决策框架", author: "Quantum 研究团队", "用假设、反例与证据强度降低复杂决策中的判断偏差。", theme: "methodology", variant: 5, sources: 16, format: "article"),
        ]
        let methodology = [
            book("effective-agents", "Building Effective AI Agents", author: "Anthropic", "从可组合工作流到自主 Agent，选择足够简单且可验证的构建方式。", theme: "methodology", variant: 0, sources: 14, format: "book"),
            book("qwen-agent", "千问 Agent 工程演进", author: "储旭（槿柏）", "梳理 Agent 平台从单体工具调用到工程化交付的演进路径。", theme: "methodology", variant: 2, sources: 9, format: "chapter"),
            book("harness", "Harness Engineering", author: "Louis Claxton · Anthropic", "用确定性约束、验证与反馈环路提升 Agent 交付质量。", theme: "methodology", variant: 4, sources: 17, format: "article"),
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

    static var sourcePreview: Self {
        var center = bookshelfPreview
        var source = KnowledgeBookDTO(
            id: "source-preview", title: "原始资料索引", author: "Stored attribution",
            authorSource: "raw", summary: "仅展示来源元数据，不包含正文。",
            coverTheme: "source", coverVariant: 0, coverVersion: 1,
            securityLevel: "green", knowledgeLevel: "source_metadata",
            freshness: "unknown", sourceCount: 1, sourceKind: "public_source_index",
            contentStatus: "metadata_only", canonicalUrl: "https://example.com/original",
            completeness: "full", publicationFormat: "source", readable: false
        )
        source.unavailableReason = "此条目只提供来源地址。"
        center.bookshelves = [KnowledgeBookshelfDTO(
            id: "knowledge/publication/follow-builders", title: "资料来源",
            securityLevel: "green", bookCount: 1, books: [source]
        )]
        return center
    }
}

extension KnowledgeBookReaderLoad {
    static var longPreview: Self {
        let paragraph = String(repeating: "这是用于验证长文阅读结构、正文存活和章节导航的明确演示段落。", count: 24)
        let sections = (0...100).map { index in
            KnowledgeBookSectionDTO(
                id: index == 0 ? "server-section-first" : (index == 50 ? "server-section-middle" : (index == 100 ? "server-section-last" : "server-section-\(index + 1)")),
                title: index == 0 ? "第一章 起点" : (index == 50 ? "第五十一节 中段" : (index == 100 ? "第一百零一节 终章" : "第\(index + 1)节 大型目录条目")),
                level: index.isMultiple(of: 2) ? 2 : 3,
                markdown: paragraph
            )
        }
        return Self(
            body: KnowledgeBookBodyDTO(
                bookId: "product-map", title: "AI 产品全景图", author: "Quantum 研究团队",
                contentVersion: "fixture-content-version-20260911", edition: 2,
                citation: "fixture://reader-long",
                sections: sections
            ),
            subscriptions: nil
        )
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
}
