//
//  SettingsView.swift
//  AIPlatformApp
//
//  个人中心：个人信息卡（点击编辑 sheet）→ Token 极简卡 → 创建智能体 → 账号操作。
//  提炼工作台（Prompt Refinement Studio）已下线，由「创建智能体」替换。
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

                        weeklyUsageOverview
                            .padding(.horizontal, AppTheme.Metrics.contentGutter)

                        // 1. 用户与租户身份卡（点击编辑）
                        tenantProfileCard
                            .padding(.horizontal, AppTheme.Metrics.contentGutter)

                        // 2. 知识订阅与套餐
                        subscriptionEntryCard
                            .padding(.horizontal, AppTheme.Metrics.contentGutter)

                        // 3. Token 极简卡
                        TokenSummaryCard()
                            .padding(.horizontal, AppTheme.Metrics.contentGutter)

                        // 3. 创建智能体（替换提炼工作台）
                        AgentCreatorView()
                            .padding(.horizontal, AppTheme.Metrics.contentGutter)

                        // 3.5 我创建的智能体 + 我制作的技能（演示数据·不可交互）
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
                if let list = try? await APIClient.shared.fetchTenantAgents() {
                    cloudAgents = list
                }
                if let skills = try? await APIClient.shared.fetchTenantSkills() {
                    cloudSkills = skills
                }
                subscriptionSummary = try? await api.fetchSubscriptionCenter()
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

    private var weeklyUsageOverview: some View {
        let values: [CGFloat] = [0.28, 0.52, 0.39, 0.76]
        let labels = ["第 1 周", "第 2 周", "第 3 周", "本周"]

        return VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("用量趋势")
                        .font(AppTheme.Typography.supporting)
                        .foregroundColor(AppTheme.Colors.textSecondary)
                    Text("76%")
                        .font(.system(size: 36, weight: .semibold, design: .rounded))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                    Text("本周预算峰值")
                        .font(AppTheme.Typography.micro)
                        .foregroundColor(AppTheme.Colors.textTertiary)
                }
                Spacer()
                Label("较上月 -12%", systemImage: "arrow.down.right")
                    .font(AppTheme.Typography.micro)
                    .foregroundColor(AppTheme.Colors.statusCompleted)
                    .padding(.horizontal, 9)
                    .padding(.vertical, 6)
                    .background(AppTheme.Colors.successSurface)
                    .clipShape(Capsule())
            }

            HStack(alignment: .bottom, spacing: 12) {
                ForEach(values.indices, id: \.self) { index in
                    VStack(spacing: 7) {
                        GeometryReader { proxy in
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .fill(index == values.indices.last ? AnyShapeStyle(AppTheme.Colors.quantumGradient) : AnyShapeStyle(AppTheme.Colors.secondaryBackground))
                                .frame(height: max(20, proxy.size.height * values[index]))
                                .frame(maxHeight: .infinity, alignment: .bottom)
                                .overlay(alignment: .bottom) {
                                    Text("\(Int(values[index] * 100))%")
                                        .font(.system(size: 10, weight: .bold))
                                        .foregroundColor(index == values.indices.last ? .white : AppTheme.Colors.textSecondary)
                                        .padding(.bottom, 8)
                                }
                        }
                        .frame(height: 112)

                        Text(labels[index])
                            .font(.system(size: 10, weight: .medium))
                            .foregroundColor(AppTheme.Colors.textTertiary)
                            .lineLimit(1)
                    }
                    .frame(maxWidth: .infinity)
                }
            }
        }
        .padding(AppTheme.Spacing.xl)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous)
                .stroke(AppTheme.Colors.border, lineWidth: 0.75)
        }
        .shadow(color: Color(hex: "6B5A8A").opacity(0.10), radius: 20, y: 8)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("本周 Token 预算峰值百分之 76，较上月下降 12%")
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

                    Text("租户标识: \(appState.currentProfile.tenantId)")
                        .font(.system(size: 12))
                        .foregroundColor(AppTheme.Colors.textSecondary)

                    Text(appState.currentProfile.role.displayName)
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

    // MARK: - 3.5 我创建的智能体 + 我制作的技能（纯云端真实数据）

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
                emptyArtifactHint("尚未创建智能体，使用上方「创建智能体」或在对话中提出「创建一个…的agent」")
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
                        onDelete: {}
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
    private func artifactRow(name: String, responsibility: String, createdAt: String, accent: Color, onDelete: @escaping () -> Void) -> some View {
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
                }
                .buttonStyle(SoftButtonStyle())
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

            Text("Quantum Platform v1.0 (Build 2026.08.16)")
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

    private let highlightedEntitlementKey: String?

    @State private var center: SubscriptionCenterResponse?
    @State private var adminRequests: [SubscriptionRequestDTO] = []
    @State private var isLoading = true
    @State private var busyID: String?
    @State private var errorMessage: String?
    @State private var successMessage: String?
    @State private var requestIDsByPlan: [String: String] = [:]

    public init(highlightedEntitlementKey: String? = nil) {
        self.highlightedEntitlementKey = highlightedEntitlementKey
    }

    public var body: some View {
        ZStack {
            QuantumMistBackground()

            ScrollView {
                LazyVStack(spacing: AppTheme.Spacing.lg) {
                    header

                    if isLoading, center == nil {
                        ProgressView("正在同步组织套餐与知识权益…")
                            .frame(maxWidth: .infinity, minHeight: 180)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                    } else if let center {
                        currentPlanCard(center)
                        requestSection(center.requests)
                        plansSection(center)
                        if center.isSuperAdmin {
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
        .navigationTitle("知识订阅")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .task { await load() }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            HStack {
                Image(systemName: "building.2.crop.circle")
                    .font(.system(size: 28, weight: .semibold))
                    .foregroundStyle(AppTheme.Colors.primary)
                VStack(alignment: .leading, spacing: 2) {
                    Text("组织知识权益")
                        .font(AppTheme.Typography.sectionTitle)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    Text(center.map { "组织 \($0.organizationId)" } ?? "以当前登录组织为准")
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                        .lineLimit(1)
                }
                Spacer()
            }

            Text("套餐由管理员审批后生效。知识钱包只控制默认检索偏好，不会绕过知识权限。")
                .font(AppTheme.Typography.supporting)
                .foregroundStyle(AppTheme.Colors.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(AppTheme.Spacing.xl)
        .subscriptionSurface()
    }

    private func currentPlanCard(_ center: SubscriptionCenterResponse) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            Label("当前套餐", systemImage: "checkmark.shield.fill")
                .font(AppTheme.Typography.label)
                .foregroundStyle(AppTheme.Colors.statusCompleted)

            if let subscription = center.subscription {
                HStack(alignment: .firstTextBaseline) {
                    Text(subscription.planName)
                        .font(AppTheme.Typography.sectionTitle)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    Spacer()
                    Text(subscription.status == "active" ? "已生效" : subscription.status)
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.statusCompleted)
                }
                Text(subscription.effectiveUntil.map { "有效期至 \($0.dateOnly)" } ?? "长期有效")
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                Text("权益版本 \(subscription.entitlementVersion) · 已包含 \(subscription.knowledgeEntitlements.count) 个受限知识类目")
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.textTertiary)
            } else {
                Text("尚未开通组织套餐")
                    .font(AppTheme.Typography.cardTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Text("绿色公共知识仍可直接使用；黄色受限知识需要选择套餐并提交审批。")
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            }
        }
        .padding(AppTheme.Spacing.xl)
        .subscriptionSurface()
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
            let leftHighlighted = lhs.features?.knowledgeEntitlements.contains(highlightedEntitlementKey ?? "") == true
            let rightHighlighted = rhs.features?.knowledgeEntitlements.contains(highlightedEntitlementKey ?? "") == true
            return leftHighlighted == rightHighlighted ? lhs.price < rhs.price : leftHighlighted
        }

        return VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            VStack(alignment: .leading, spacing: 3) {
                Text("可选套餐")
                    .font(AppTheme.Typography.sectionTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                if let highlightedEntitlementKey {
                    Text("已优先显示包含“\(highlightedEntitlementKey)”的套餐")
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.primary)
                }
            }

            if sortedPlans.isEmpty {
                ContentUnavailableView("暂无可申请套餐", systemImage: "creditcard", description: Text("下拉刷新，或联系平台管理员配置套餐。"))
                    .frame(minHeight: 180)
            } else {
                ForEach(sortedPlans) { plan in
                    planCard(plan, center: center)
                }
            }
        }
    }

    private func planCard(_ plan: SubscriptionPlanDTO, center: SubscriptionCenterResponse) -> some View {
        let entitlements = plan.features?.knowledgeEntitlements ?? []
        let isHighlighted = highlightedEntitlementKey.map(entitlements.contains) == true
        let isCurrent = center.subscription?.planId == plan.id && center.subscription?.status == "active"
        let pending = center.requests.first { $0.targetPlanId == plan.id && $0.status == "pending" }

        return VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Text(plan.name)
                            .font(AppTheme.Typography.cardTitle)
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                        if isHighlighted {
                            Text("包含目标知识")
                                .font(AppTheme.Typography.micro)
                                .foregroundStyle(AppTheme.Colors.onPrimary)
                                .padding(.horizontal, 7)
                                .padding(.vertical, 3)
                                .background(AppTheme.Colors.primary)
                                .clipShape(Capsule())
                        }
                    }
                    if let description = plan.description, !description.isEmpty {
                        Text(description)
                            .font(AppTheme.Typography.supporting)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                    }
                }
                Spacer(minLength: AppTheme.Spacing.md)
                Text(plan.price == 0 ? "免费" : plan.price.formatted(.currency(code: "CNY")))
                    .font(AppTheme.Typography.cardTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
            }

            HStack(spacing: AppTheme.Spacing.lg) {
                Label("\(plan.requestQuota) 次请求", systemImage: "arrow.triangle.2.circlepath")
                Label(tokenQuota(plan.tokenQuota), systemImage: "sparkles")
                Label("\(plan.durationDays) 天", systemImage: "calendar")
            }
            .font(AppTheme.Typography.micro)
            .foregroundStyle(AppTheme.Colors.textSecondary)

            if !entitlements.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("包含的受限知识")
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textTertiary)
                    ForEach(entitlements.prefix(4), id: \.self) { entitlement in
                        Label(entitlement, systemImage: "lock.open.fill")
                            .font(AppTheme.Typography.micro)
                            .foregroundStyle(entitlement == highlightedEntitlementKey ? AppTheme.Colors.primary : AppTheme.Colors.textSecondary)
                            .lineLimit(2)
                    }
                    if entitlements.count > 4 {
                        Text("另有 \(entitlements.count - 4) 个类目")
                            .font(AppTheme.Typography.micro)
                            .foregroundStyle(AppTheme.Colors.textTertiary)
                    }
                }
            }

            Button {
                apply(for: plan, highlightedKey: isHighlighted ? highlightedEntitlementKey : nil)
            } label: {
                busyLabel(
                    id: plan.id,
                    title: isCurrent ? "当前套餐" : (pending == nil ? "提交组织申请" : "等待管理员审批"),
                    systemImage: isCurrent ? "checkmark" : (pending == nil ? "paperplane.fill" : "clock.fill")
                )
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .tint(AppTheme.Colors.primary)
            .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
            .disabled(isCurrent || pending != nil || busyID != nil)
        }
        .padding(AppTheme.Spacing.xl)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                .stroke(isHighlighted ? AppTheme.Colors.primary : AppTheme.Colors.border, lineWidth: isHighlighted ? 2 : 0.75)
        }
        .accessibilityElement(children: .contain)
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
                            .tint(AppTheme.Colors.statusError)

                            Button { review(request, approve: true) } label: {
                                busyLabel(id: "approve-\(request.id)", title: "批准", systemImage: "checkmark")
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.borderedProminent)
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
            Button { Task { await load() } } label: {
                Label("重试", systemImage: "arrow.clockwise")
                    .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget)
            }
            .buttonStyle(.bordered)
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
            let response = try await api.fetchSubscriptionCenter()
            center = response
            if response.isSuperAdmin {
                adminRequests = try await api.fetchAdminSubscriptionRequests()
            } else {
                adminRequests = []
            }
        } catch {
            errorMessage = actionableMessage(for: error)
        }
        isLoading = false
    }

    private func apply(for plan: SubscriptionPlanDTO, highlightedKey: String?) {
        guard busyID == nil else { return }
        Task {
            busyID = plan.id
            defer { busyID = nil }
            do {
                let requestID = requestIDsByPlan[plan.id] ?? UUID().uuidString
                requestIDsByPlan[plan.id] = requestID
                _ = try await api.createSubscriptionRequest(
                    planId: plan.id,
                    entitlementKeys: highlightedKey.map { [$0] } ?? [],
                    reason: highlightedKey.map { "申请使用知识类目：\($0)" } ?? "从 iOS 知识订阅中心提交",
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
                    note: approve ? "iOS 订阅中心批准" : "iOS 订阅中心拒绝"
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
