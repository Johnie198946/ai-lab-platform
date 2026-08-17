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

    @State private var showingProfileEdit: Bool = false
    /// 云端真实数据（无任何演示数据）：拓扑/设置同源消费
    @State private var cloudAgents: [TenantAgentDTO] = []
    @State private var cloudSkills: [TenantSkillDTO] = []

    public init() {}

    public var body: some View {
        NavigationStack {
            ZStack {
                AppTheme.Colors.groupedBackground
                    .ignoresSafeArea()

                ScrollView {
                    VStack(spacing: AppTheme.Spacing.lg) {

                        // 1. 用户与租户身份卡（点击编辑）
                        tenantProfileCard
                            .padding(.horizontal, AppTheme.Spacing.md)
                            .padding(.top, AppTheme.Spacing.sm)

                        // 2. Token 极简卡
                        TokenSummaryCard()
                            .padding(.horizontal, AppTheme.Spacing.md)

                        // 3. 创建智能体（替换提炼工作台）
                        AgentCreatorView()
                            .padding(.horizontal, AppTheme.Spacing.md)

                        // 3.5 我创建的智能体 + 我制作的技能（演示数据·不可交互）
                        VStack(spacing: AppTheme.Spacing.md) {
                            createdAgentsSection()
                            createdSkillsSection()
                        }
                        .padding(.horizontal, AppTheme.Spacing.md)

                        // 4. 平台定时任务区块已移除（后续统一对接 Hermes cronjob 体系，需求6）

                        // 5. 平台与账号操作
                        accountActionsSection
                            .padding(.horizontal, AppTheme.Spacing.md)
                            .padding(.bottom, AppTheme.Spacing.xl)
                    }
                }
            }
            .navigationTitle("个人与设置")
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
            }
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
            HStack(spacing: AppTheme.Spacing.md) {
                // Avatar（SF Symbol 头像）
                ZStack {
                    Circle()
                        .fill(AppTheme.Colors.primary)
                        .frame(width: 56, height: 56)
                    Image(systemName: appState.currentProfile.avatarUrl ?? "person.crop.circle.fill")
                        .font(.system(size: 28))
                        .foregroundColor(AppTheme.Colors.onPrimary)
                }

                VStack(alignment: .leading, spacing: 4) {
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
                        .foregroundColor(AppTheme.Colors.primary)
                }

                Spacer()

                Image(systemName: "pencil")
                    .font(.system(size: 13))
                    .foregroundColor(AppTheme.Colors.textTertiary)
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
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
            .foregroundColor(AppTheme.Colors.textTertiary)
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
                        .foregroundColor(AppTheme.Colors.textTertiary)
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
                .foregroundColor(AppTheme.Colors.securityRed)
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

// MARK: - Xcode #Preview

#Preview("SettingsView - Light") {
    SettingsView()
        .environmentObject(AppState())
}

#Preview("SettingsView - Dark") {
    SettingsView()
        .environmentObject(AppState())
        .preferredColorScheme(.dark)
}
