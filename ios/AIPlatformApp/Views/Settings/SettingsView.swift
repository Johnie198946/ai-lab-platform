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

                        // 4. 平台定时任务（演示·三字段只读）
                        scheduledTasksSection
                            .padding(.horizontal, AppTheme.Spacing.md)

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

    // MARK: - 3.5 我创建的智能体 + 我制作的技能（演示数据·不可交互）

    private func createdAgentsSection() -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            artifactHeader(icon: "sparkles", title: "我创建的智能体", accent: AppTheme.Colors.quantumViolet)
            ForEach(MockData.createdAgents) { agent in
                artifactRow(
                    name: agent.name,
                    responsibility: agent.responsibility,
                    createdAt: agent.createdAt,
                    version: agent.version,
                    accent: AppTheme.Colors.quantumViolet
                )
            }
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    private func createdSkillsSection() -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            artifactHeader(icon: "bolt.fill", title: "我制作的技能", accent: AppTheme.Colors.quantumCyan)
            ForEach(MockData.createdSkills) { skill in
                artifactRow(
                    name: skill.name,
                    responsibility: skill.responsibility,
                    createdAt: skill.createdAt,
                    version: skill.version,
                    accent: AppTheme.Colors.quantumCyan
                )
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
            Text("演示数据·不可交互")
                .font(.system(size: 10, weight: .bold))
                .foregroundColor(AppTheme.Colors.textTertiary)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(AppTheme.Colors.tertiaryBackground)
                .clipShape(Capsule())
            Spacer()
        }
    }

    /// 纯静态字段卡：名称 / 职责 / 创建时间 / 版本（去 live 语义，无运行状态/调试入口）
    private func artifactRow(name: String, responsibility: String, createdAt: String, version: String, accent: Color) -> some View {
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
                Text(version)
                    .font(.system(size: 11, weight: .semibold, design: .monospaced))
                    .foregroundColor(accent)
            }
            Text(responsibility)
                .font(.system(size: 12))
                .foregroundColor(AppTheme.Colors.textSecondary)
                .lineSpacing(1)
            Text("创建于 \(createdAt)")
                .font(.system(size: 11))
                .foregroundColor(AppTheme.Colors.textTertiary)
        }
        .padding(AppTheme.Spacing.sm)
        .background(AppTheme.Colors.secondaryBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
    }

    // MARK: - 4. 平台定时任务（演示·三字段只读）

    private var scheduledTasksSection: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            HStack(spacing: 6) {
                Image(systemName: "clock.arrow.circlepath")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.primary)
                Text("平台定时任务")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.textPrimary)
                Text("演示")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(AppTheme.Colors.primary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(AppTheme.Colors.primary.opacity(0.08))
                    .clipShape(Capsule())
                Spacer()
            }

            ForEach(MockData.scheduledTasks) { task in
                scheduledTaskRow(task)
            }
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    private func scheduledTaskRow(_ task: ScheduledTask) -> some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: "calendar.badge.clock")
                .font(.system(size: 15))
                .foregroundColor(AppTheme.Colors.textSecondary)

            VStack(alignment: .leading, spacing: 2) {
                Text(task.name)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(AppTheme.Colors.textPrimary)
                Text(task.schedule)
                    .font(.system(size: 11))
                    .foregroundColor(AppTheme.Colors.textTertiary)
            }

            Spacer()

            // 三字段只读展示：开关禁用
            Toggle("", isOn: .constant(task.enabled))
                .labelsHidden()
                .disabled(true)
                .scaleEffect(0.8)
        }
        .padding(.vertical, AppTheme.Spacing.xs)
        .padding(.horizontal, AppTheme.Spacing.sm)
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
