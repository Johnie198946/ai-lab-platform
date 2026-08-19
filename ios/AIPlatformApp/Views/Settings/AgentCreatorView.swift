//
//  AgentCreatorView.swift
//  AIPlatformApp
//
//  设置页：创建智能体（替换「提炼工作台」）。一行输入用途 + 一键创建 + 0.8s 骨架卡动画 → 结果卡。
//  本地模板引擎生成 AgentNode（0 LLM 成本）；去对话 = 本地 Mock 对话；不持久化（演示语义）。
//

import SwiftUI

// MARK: - 本地模板引擎（0 LLM 成本）

public enum LocalAgentTemplateEngine {
    public struct Template {
        public let name: String
        public let roleCategory: String
        public let summary: String
        /// 继承的基线 profile（后端白名单：main_agent / supervision / coder / knowledge）
        public let baseAgentId: String
    }

    public static func build(from purpose: String) -> AgentNode {
        let t = match(purpose)
        return AgentNode(
            id: "agent_" + UUID().uuidString.prefix(8),
            name: t.name,
            roleCategory: t.roleCategory,
            systemPromptSummary: t.summary,
            status: .idle,
            position: CGPoint(x: 0, y: 0),
            subscribedKnowledge: []
        )
    }

    public static func match(_ purpose: String) -> Template {
        let p = purpose
        if p.contains("制造") || p.contains("产线") || p.contains("SMT") || p.contains("质检") {
            return Template(
                name: "制造诊断 Sentinel",
                roleCategory: "根因诊断 · 制造",
                summary: "结合产线 IoT 遥测与 SMT 专家知识库，对设备异常进行因果推断，输出告警定级与处置工单。",
                baseAgentId: "main_agent"
            )
        }
        if p.contains("金融") || p.contains("对账") || p.contains("风控") || p.contains("清算") {
            return Template(
                name: "金融对账 Agent",
                roleCategory: "对账风控 · 金融",
                summary: "面向高并发清结算系统的幂等性校验与三方对账差异核销，输出防重放协议与差异报告。",
                baseAgentId: "coder"
            )
        }
        if p.contains("竞品") || p.contains("情报") || p.contains("监测") {
            return Template(
                name: "竞品情报雷达",
                roleCategory: "情报监测 · 竞品",
                summary: "增量追踪竞品动态、定价与开源策略，生成结构化情报卡片并回写竞品情报知识库。",
                baseAgentId: "knowledge"
            )
        }
        if p.contains("审计") || p.contains("合规") || p.contains("内控") {
            return Template(
                name: "审计合规哨兵",
                roleCategory: "合规审计 · 内控",
                summary: "全流程审计写操作与参数下发，校验 ABAC 权限与变更影响域，输出合规红线清单。",
                baseAgentId: "supervision"
            )
        }
        return Template(
            name: "通用协同 Agent",
            roleCategory: "通用 · 任务分诊",
            summary: "基于已订阅知识库进行任务分诊与多智能体编排，输出结构化执行方案。",
            baseAgentId: "main_agent"
        )
    }
}

// MARK: - 创建智能体视图

public struct AgentCreatorView: View {
    @EnvironmentObject private var appState: AppState

    @State private var purposeText: String = ""
    @State private var isCreating: Bool = false
    @State private var createdAgent: AgentNode? = nil
    @State private var creationFailed: Bool = false
    @State private var creationError: String? = nil

    private let presetPurposes = [
        "检查制造产线异常",
        "金融对账风控",
        "竞品情报监测",
        "审计合规审查",
    ]

    public init() {}

    public var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            header

            // 一行输入
            HStack(spacing: AppTheme.Spacing.sm) {
                TextField("一句话描述用途…", text: $purposeText, axis: .vertical)
                    .lineLimit(1...2)
                    .font(.system(size: 14))
                    .padding(.horizontal, AppTheme.Spacing.sm)
                    .padding(.vertical, AppTheme.Spacing.sm)
                    .background(AppTheme.Colors.secondaryBackground)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))

                Button(action: createAgent) {
                    HStack(spacing: 4) {
                        if isCreating {
                            ProgressView()
                                .tint(AppTheme.Colors.onPrimary)
                        }
                        Text("创建")
                            .font(.system(size: 13, weight: .bold))
                    }
                    .padding(.horizontal, AppTheme.Spacing.md)
                    .padding(.vertical, 10)
                    .foregroundColor(AppTheme.Colors.onPrimary)
                    .background(AppTheme.Colors.primary)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                }
                .buttonStyle(SoftButtonStyle())
                .disabled(isCreating || purposeText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }

            // 预设用途
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: AppTheme.Spacing.xs) {
                    ForEach(presetPurposes, id: \.self) { preset in
                        Button(action: {
                            purposeText = preset
                        }) {
                            Text(preset)
                                .font(.system(size: 11))
                                .foregroundColor(AppTheme.Colors.textSecondary)
                                .padding(.horizontal, AppTheme.Spacing.sm)
                                .padding(.vertical, 5)
                                .background(AppTheme.Colors.secondaryBackground)
                                .clipShape(Capsule())
                        }
                        .buttonStyle(SoftButtonStyle())
                    }
                }
            }

            // 结果区
            if isCreating {
                skeletonCard
            } else if let agent = createdAgent {
                resultCard(agent)
            }
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    private var header: some View {
        HStack {
            Image(systemName: "sparkles.rectangle.stack.fill")
                .font(.system(size: 13))
                    .foregroundColor(AppTheme.Icons.intelligence)
            Text("创建智能体")
                .font(.system(size: 15, weight: .bold))
                .foregroundColor(AppTheme.Colors.textPrimary)
            Spacer()
            Text("基线派生 · 云端切片")
                .font(.system(size: 10, weight: .bold))
                .foregroundColor(AppTheme.Colors.accent)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(AppTheme.Colors.accent.opacity(0.12))
                .clipShape(Capsule())
        }
    }

    // 0.8s 骨架卡动画
    private var skeletonCard: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            HStack(spacing: AppTheme.Spacing.sm) {
                skeletonBlock(width: 44, height: 44, corner: AppTheme.Radius.md)
                VStack(alignment: .leading, spacing: 6) {
                    skeletonBlock(width: 140, height: 14, corner: 4)
                    skeletonBlock(width: 90, height: 10, corner: 4)
                }
            }
            skeletonBlock(width: nil, height: 12, corner: 4)
            skeletonBlock(width: 200, height: 12, corner: 4)
            Text("正在生成智能体…")
                .font(.system(size: 11))
                .foregroundColor(AppTheme.Colors.textTertiary)
                .padding(.top, 2)
        }
        .padding(AppTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.Colors.secondaryBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    private func skeletonBlock(width: CGFloat?, height: CGFloat, corner: CGFloat) -> some View {
        RoundedRectangle(cornerRadius: corner)
            .fill(AppTheme.Colors.tertiaryBackground)
            .frame(width: width, height: height)
            .frame(maxWidth: width == nil ? .infinity : nil)
    }

    private func resultCard(_ agent: AgentNode) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Divider().padding(.vertical, 2)

            HStack(spacing: AppTheme.Spacing.md) {
                ZStack {
                    Circle()
                        .fill(AppTheme.Colors.primary)
                        .frame(width: 44, height: 44)
                    Image(systemName: "cpu.fill")
                        .font(.system(size: 20))
                        .foregroundColor(AppTheme.Icons.onAccent)
                }
                VStack(alignment: .leading, spacing: 3) {
                    Text(agent.name)
                        .font(.system(size: 15, weight: .bold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                    Text(agent.roleCategory)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(AppTheme.Colors.accent)
                }
                Spacer()
            }

            Text(agent.systemPromptSummary)
                .font(.system(size: 12))
                .foregroundColor(AppTheme.Colors.textSecondary)
                .lineSpacing(2)

            Button(action: goToChat) {
                HStack(spacing: 4) {
                    Image(systemName: "bubble.left.and.bubble.right.fill")
                        .font(.system(size: 11))
                    Text("去对话")
                        .font(.system(size: 13, weight: .bold))
                }
                .frame(maxWidth: .infinity)
                .frame(height: 36)
                .foregroundColor(AppTheme.Colors.primary)
                .background(AppTheme.Colors.primary.opacity(0.12))
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            }
            .buttonStyle(SoftButtonStyle())

            Text(creationFailed ? (creationError ?? "创建失败，请稍后重试") : "已写入云端 · 真实数据")
                .font(.system(size: 10))
                .foregroundColor(creationFailed ? AppTheme.Colors.securityRed : AppTheme.Colors.textTertiary)
                .frame(maxWidth: .infinity, alignment: .center)
        }
    }

    // MARK: - Actions

    private func createAgent() {
        let purpose = purposeText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !purpose.isEmpty else { return }
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        #endif
        isCreating = true
        createdAgent = nil
        creationFailed = false
        creationError = nil

        let template = LocalAgentTemplateEngine.match(purpose)
        let body = TenantAgentCreateDTO(
            baseAgentId: template.baseAgentId,
            customName: template.name,
            privatePromptDelta: template.summary
        )

        Task { @MainActor in
            do {
                // 直写云端 PostgreSQL（201），base_agent_id 由后端白名单校验（非法 422）
                let dto = try await APIClient.shared.createTenantAgent(body)
                isCreating = false
                createdAgent = AgentNode(
                    id: dto.id,
                    name: dto.customName ?? dto.baseAgentId,
                    roleCategory: template.roleCategory,
                    systemPromptSummary: dto.privatePromptDelta.isEmpty ? template.summary : dto.privatePromptDelta,
                    status: .idle,
                    position: CGPoint(x: 0, y: 0)
                )
                #if os(iOS)
                UINotificationFeedbackGenerator().notificationOccurred(.success)
                #endif
            } catch {
                // 云端失败：诚实报错，绝不落本地演示数据
                isCreating = false
                creationFailed = true
                creationError = "创建失败：\(error.localizedDescription)"
                #if os(iOS)
                UINotificationFeedbackGenerator().notificationOccurred(.error)
                #endif
            }
        }
    }

    private func goToChat() {
        guard let agent = createdAgent else { return }
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        #endif
        appState.navigateToChatWithPrompt(
            "已加载智能体「\(agent.name)」System Directive：\n\(agent.systemPromptSummary)"
        )
    }
}

// MARK: - Xcode #Preview

#Preview("AgentCreatorView - Light") {
    AgentCreatorView()
        .environmentObject(AppState())
        .padding()
}

#Preview("AgentCreatorView - Dark") {
    AgentCreatorView()
        .environmentObject(AppState())
        .preferredColorScheme(.dark)
        .padding()
}
