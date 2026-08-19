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
    @State private var selectedPlanID: String?
    @State private var selectedPackIDs: Set<String> = []
    @State private var inspectedPack: KnowledgePackDTO?

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
                        knowledgePacksSection(center)
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
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if let center { stickyApplicationBar(center) }
        }
        .sheet(item: $inspectedPack) { pack in
            knowledgePackDetail(pack)
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            HStack(spacing: AppTheme.Spacing.md) {
                Image(systemName: "building.2.fill")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundStyle(AppTheme.Colors.onPrimary)
                    .frame(width: 44, height: 44)
                    .background(AppTheme.Colors.primary)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                VStack(alignment: .leading, spacing: 2) {
                    Text("组织订阅中心")
                        .font(AppTheme.Typography.sectionTitle)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    Text("套餐决定额度，知识包决定受限知识范围")
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                        .lineLimit(1)
                }
                Spacer()
            }

            Text("绿色公共知识始终可用；黄色知识包需随组织套餐申请；红色私有知识不会在这里出售。")
                .font(AppTheme.Typography.supporting)
                .foregroundStyle(AppTheme.Colors.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(AppTheme.Spacing.lg)
        .subscriptionSurface()
    }

    private func currentPlanCard(_ center: SubscriptionCenterResponse) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            HStack {
                Label("当前权益", systemImage: "checkmark.shield.fill")
                    .font(AppTheme.Typography.label)
                    .foregroundStyle(AppTheme.Colors.statusCompleted)
                Spacer()
                Text("以组织为单位")
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
                let grants = subscription.activePackGrants ?? center.activePackGrants ?? []
                let allowance = subscription.packAllowance ?? center.packAllowance ?? 0
                HStack(spacing: 0) {
                    entitlementMetric(value: allowance < 0 ? "定制" : "\(grants.count)/\(allowance)", label: "知识包")
                    Divider().frame(height: 34)
                    entitlementMetric(value: "V\(subscription.entitlementVersion)", label: "权益版本")
                    Divider().frame(height: 34)
                    entitlementMetric(value: subscription.effectiveUntil?.dateOnly ?? "长期", label: "有效期")
                }
                .padding(.vertical, AppTheme.Spacing.sm)
                .background(AppTheme.Colors.secondaryBackground)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                if !grants.isEmpty {
                    Label(grants.map(\.name).joined(separator: "、"), systemImage: "books.vertical.fill")
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                }
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
                planFact(icon: "square.stack.3d.up.fill", text: isCustom ? "知识包按合同配置" : "最多 \(allowance) 个知识包")
            }

            Button {
                select(plan, center: center)
            } label: {
                busyLabel(
                    id: plan.id,
                    title: isCurrent ? "当前套餐" : (isCustom ? "联系管理员" : (pending == nil ? (isSelected ? "已选择" : "选择套餐") : "等待管理员审批")),
                    systemImage: isCurrent || isSelected ? "checkmark" : (isCustom ? "person.badge.key.fill" : (pending == nil ? "checkmark.circle" : "clock.fill"))
                )
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .tint(AppTheme.Colors.primary)
            .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
            .disabled(isCurrent || isCustom || pending != nil || busyID != nil)
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

    @ViewBuilder
    private func knowledgePacksSection(_ center: SubscriptionCenterResponse) -> some View {
        let packs = (center.knowledgePacks ?? []).sorted { $0.sortOrder < $1.sortOrder }
        let launchPacks = packs.filter { $0.status != "incubating" }
        let candidatePacks = packs.filter { $0.status == "incubating" }
        let readyCount = packs.filter { $0.status == "published" && $0.isSelectable }.count
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            sectionHeader(
                step: "02",
                title: "选择知识包",
                subtitle: "按需添加黄色受限知识；绿色与红色知识不在此计费"
            )

            if packs.isEmpty {
                ContentUnavailableView("暂无已登记知识包", systemImage: "square.stack.3d.up.slash", description: Text("完成首批 K5 治理后会在这里开放。"))
                    .frame(minHeight: 160)
            } else {
                HStack(spacing: AppTheme.Spacing.sm) {
                    Label("\(launchPacks.count) 个首发包", systemImage: "square.stack.3d.up.fill")
                    Spacer()
                    Text(readyCount == 0 ? "全部建设中" : "\(readyCount) 个可申请")
                        .foregroundStyle(readyCount == 0 ? AppTheme.Colors.textTertiary : AppTheme.Colors.statusCompleted)
                }
                .font(AppTheme.Typography.micro.weight(.semibold))
                .foregroundStyle(AppTheme.Colors.textSecondary)

                if readyCount == 0 {
                    Label("知识包正在完成 K5 来源与权限复核。你仍可先选择套餐，开放后再添加知识包。", systemImage: "info.circle.fill")
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                        .padding(AppTheme.Spacing.md)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(AppTheme.Colors.secondaryBackground)
                        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                }

                ScrollView(.horizontal) {
                    LazyHStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                        ForEach(launchPacks) { pack in
                            knowledgePackCard(pack, center: center)
                                .frame(width: 286)
                        }
                    }
                    .scrollTargetLayout()
                }
                .scrollIndicators(.hidden)
                .scrollTargetBehavior(.viewAligned)
                .contentMargins(.horizontal, 1, for: .scrollContent)

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

    private func knowledgePackCard(_ pack: KnowledgePackDTO, center: SubscriptionCenterResponse) -> some View {
        let selected = selectedPackIDs.contains(pack.id)
        let active = (center.activePackGrants ?? []).contains { $0.knowledgePackId == pack.id && $0.status == "active" }
        let pending = center.requests.contains { ($0.requestedPackIds ?? []).contains(pack.id) && $0.status == "pending" }
        let governanceReady = pack.status == "published" && pack.isSelectable && pack.approvedDocumentCount >= pack.minimumDocumentCount

        return Button {
            inspectedPack = pack
        } label: {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                HStack(alignment: .top) {
                    Image(systemName: active ? "checkmark.seal.fill" : "books.vertical.fill")
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(active ? AppTheme.Colors.statusCompleted : AppTheme.Colors.primary)
                        .frame(width: 40, height: 40)
                        .background(AppTheme.Colors.primary.opacity(0.10))
                        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
                    VStack(alignment: .leading, spacing: 3) {
                        Text(pack.name)
                            .font(AppTheme.Typography.cardTitle)
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                        Text(pack.riskLabel)
                            .font(AppTheme.Typography.micro)
                            .foregroundStyle(AppTheme.Colors.textTertiary)
                            .lineLimit(1)
                    }
                    Spacer()
                    Text(active ? "已开通" : (pending ? "审批中" : (governanceReady ? (selected ? "已加入" : "可申请") : "建设中")))
                        .font(AppTheme.Typography.micro.weight(.semibold))
                        .foregroundStyle(active ? AppTheme.Colors.statusCompleted : (pending ? AppTheme.Colors.statusWarning : (governanceReady ? AppTheme.Colors.primary : AppTheme.Colors.textTertiary)))
                }

                Text(pack.description)
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)

                VStack(alignment: .leading, spacing: 5) {
                    HStack {
                        Text("K5 治理进度")
                        Spacer()
                        Text("\(pack.approvedDocumentCount)/\(pack.minimumDocumentCount)")
                    }
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.textTertiary)
                    ProgressView(value: Double(pack.approvedDocumentCount), total: Double(max(pack.minimumDocumentCount, 1)))
                        .tint(governanceReady ? AppTheme.Colors.statusCompleted : AppTheme.Colors.primary)
                }

                HStack {
                    Label("新鲜度 \(pack.freshnessPercent)%", systemImage: "clock.arrow.circlepath")
                    Spacer()
                    Label(selected ? "已加入申请" : "查看详情", systemImage: selected ? "checkmark.circle.fill" : "chevron.right")
                        .foregroundStyle(selected ? AppTheme.Colors.statusCompleted : AppTheme.Colors.primary)
                }
                .font(AppTheme.Typography.micro.weight(.semibold))
                .foregroundStyle(AppTheme.Colors.textSecondary)
            }
            .padding(AppTheme.Spacing.lg)
            .frame(maxWidth: .infinity, minHeight: 238, alignment: .topLeading)
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(selected ? AppTheme.Colors.primary : AppTheme.Colors.border, lineWidth: selected ? 2 : 0.75)
            }
            .shadow(color: Color.black.opacity(0.07), radius: 10, y: 5)
        }
        .buttonStyle(.plain)
        .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
        .accessibilityLabel("\(pack.name)，\(active ? "已开通" : (governanceReady ? "可申请" : "建设中"))")
        .accessibilityHint("点按查看知识包范围和治理详情")
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
                    Text("尚未达到发布门槛")
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textTertiary)
                }
                Spacer()
                Text("建设中")
                    .font(AppTheme.Typography.micro.weight(.semibold))
                    .foregroundStyle(AppTheme.Colors.textTertiary)
                Image(systemName: "chevron.right")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(AppTheme.Colors.textTertiary)
            }
            .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(pack.name)，建设中")
        .accessibilityHint("点按查看治理详情")
    }

    private func knowledgePackDetail(_ pack: KnowledgePackDTO) -> some View {
        let governanceReady = pack.status == "published"
            && pack.isSelectable
            && pack.approvedDocumentCount >= pack.minimumDocumentCount
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
                        detailRow(label: "正式 K5 条目", value: "\(pack.approvedDocumentCount)/\(pack.minimumDocumentCount)", icon: "doc.text.fill")
                        detailRow(label: "内容新鲜度", value: "\(pack.freshnessPercent)%", icon: "clock.arrow.circlepath")
                        detailRow(label: "授权标识", value: pack.entitlementKey, icon: "key.fill")
                    }
                    .padding(AppTheme.Spacing.lg)
                    .subscriptionSurface()

                    Label(
                        canToggle
                            ? "该知识包可随当前套餐提交审批。"
                            : (governanceReady ? "请先选择支持该知识包的套餐。" : "完成来源、权限和新鲜度复核后才会开放申请。"),
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
           plan.customOnly != true {
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
            if let highlightedEntitlementKey,
               let pack = (response.knowledgePacks ?? []).first(where: { $0.entitlementKey == highlightedEntitlementKey }) {
                inspectedPack = pack
                if let plan = response.plans.first(where: { ($0.selectablePackIds ?? []).contains(pack.id) && $0.customOnly != true }) {
                    selectedPlanID = plan.id
                }
            }
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

    private func apply(for plan: SubscriptionPlanDTO) {
        guard busyID == nil else { return }
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
