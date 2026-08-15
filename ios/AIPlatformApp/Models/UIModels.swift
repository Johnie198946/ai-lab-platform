//
//  UIModels.swift
//  AIPlatformApp
//
//  Strongly Typed Frontend Data Models, State Handlers & Mock Datasets
//  Swift 6 / iOS 17+ Sendable & Identifiable Conformance
//

import SwiftUI
import Combine

// MARK: - User & Tenant Profile
public enum UserRole: String, Codable, Sendable, CaseIterable {
    case masterAdmin = "master_admin"
    case tenantAdmin = "tenant_admin"
    case tenantMember = "tenant_member"
    case guest = "guest"
    
    public var displayName: String {
        switch self {
        case .masterAdmin: return "超级主权管理员 (Master Admin)"
        case .tenantAdmin: return "租户管理员 (Tenant Admin)"
        case .tenantMember: return "行业租户成员 (Tenant Member)"
        case .guest: return "免登录游客 (Guest)"
        }
    }
}

public struct TenantProfile: Identifiable, Codable, Sendable, Hashable {
    public let id: String
    public var name: String
    public var tenantId: String
    public var role: UserRole
    public var avatarUrl: String?
    public var concurrencyLimit: Int
    public var tokenQuotaUsage: Double // 0.0 to 1.0 (e.g. 0.65 = 65%)
    public var isVipLane: Bool
    
    public init(
        id: String = UUID().uuidString,
        name: String,
        tenantId: String,
        role: UserRole,
        avatarUrl: String? = nil,
        concurrencyLimit: Int = 5,
        tokenQuotaUsage: Double = 0.42,
        isVipLane: Bool = false
    ) {
        self.id = id
        self.name = name
        self.tenantId = tenantId
        self.role = role
        self.avatarUrl = avatarUrl
        self.concurrencyLimit = concurrencyLimit
        self.tokenQuotaUsage = tokenQuotaUsage
        self.isVipLane = isVipLane
    }
}

// MARK: - Chat & Messages
public enum MessageRole: String, Codable, Sendable {
    case user = "user"
    case assistant = "assistant"
    case system = "system"
}

public struct CodeSnippet: Identifiable, Codable, Sendable, Hashable {
    public let id: String
    public var language: String
    public var code: String
    
    public init(id: String = UUID().uuidString, language: String, code: String) {
        self.id = id
        self.language = language
        self.code = code
    }
}

// MARK: - Rich Media Message Blocks (7-case unified model)

/// 富媒体块类型：图表面板仅支持 line / bar（单色系，不挪用红黄绿警示色）
public enum ChartType: String, Sendable, Hashable {
    case line
    case bar
}

public struct ChartPoint: Identifiable, Sendable, Hashable {
    public let id: String
    public var label: String   // x 轴标签
    public var value: Double   // y 轴数值

    public init(id: String = UUID().uuidString, label: String, value: Double) {
        self.id = id
        self.label = label
        self.value = value
    }
}

public struct ChartSeries: Identifiable, Sendable, Hashable {
    public let id: String
    public var name: String
    public var points: [ChartPoint]

    public init(id: String = UUID().uuidString, name: String, points: [ChartPoint]) {
        self.id = id
        self.name = name
        self.points = points
    }
}

public struct ChartBlock: Identifiable, Sendable, Hashable {
    public let id: String
    public var title: String
    public var chartType: ChartType
    public var series: [ChartSeries]
    public var summary: String

    public init(
        id: String = UUID().uuidString,
        title: String,
        chartType: ChartType,
        series: [ChartSeries],
        summary: String = ""
    ) {
        self.id = id
        self.title = title
        self.chartType = chartType
        self.series = series
        self.summary = summary
    }
}

public struct ImageBlock: Identifiable, Sendable, Hashable {
    public let id: String
    public var assetName: String   // 本地资源名（Assets.xcassets），imageData 为空时使用
    public var imageData: Data?    // 运行时照片数据（已降采样 JPEG），非空时优先渲染
    public var caption: String

    public init(id: String = UUID().uuidString, assetName: String, imageData: Data? = nil, caption: String = "") {
        self.id = id
        self.assetName = assetName
        self.imageData = imageData
        self.caption = caption
    }
}

public struct TableBlock: Identifiable, Sendable, Hashable {
    public let id: String
    public var title: String
    public var headers: [String]
    public var rows: [[String]]

    public init(id: String = UUID().uuidString, title: String, headers: [String], rows: [[String]]) {
        self.id = id
        self.title = title
        self.headers = headers
        self.rows = rows
    }
}

/// 附件文件类型（对应文档图标）
public enum AttachmentFileType: String, Sendable, Hashable {
    case word
    case pdf
    case ppt
    case excel
    case generic
}

public struct AttachmentBlock: Identifiable, Sendable, Hashable {
    public let id: String
    public var fileName: String
    public var fileType: AttachmentFileType
    public var fileSize: String

    public init(id: String = UUID().uuidString, fileName: String, fileType: AttachmentFileType, fileSize: String) {
        self.id = id
        self.fileName = fileName
        self.fileType = fileType
        self.fileSize = fileSize
    }
}

/// 推理步骤类型（与后端 reasoning_extractor 的 type 字符串对齐）
public enum ReasoningStepType: String, Sendable, Hashable {
    case thought = "thought"
    case toolCall = "tool_call"
    case skillLoad = "skill_load"
    case agentSpawn = "agent_spawn"
}

public struct ReasoningStep: Identifiable, Sendable, Hashable {
    public let id: String
    public var type: ReasoningStepType
    public var title: String
    public var detail: String
    public var status: String

    public init(
        id: String = UUID().uuidString,
        type: ReasoningStepType,
        title: String,
        detail: String = "",
        status: String = "done"
    ) {
        self.id = id
        self.type = type
        self.title = title
        self.detail = detail
        self.status = status
    }
}

/// 引用上下文（正文 + 富媒体卡片摘要；严禁携带 reasoning 块内容）
public struct QuotedContext: Sendable, Hashable {
    public var text: String
    public var blockSummary: String?

    public init(text: String, blockSummary: String? = nil) {
        self.text = text
        self.blockSummary = blockSummary
    }
}

/// 平台定时任务卡（纯前端轻量演示模型：三字段只读，零执行史）
public struct ScheduledTask: Identifiable, Sendable, Hashable {
    public let id: String
    public let name: String
    public let schedule: String
    public let enabled: Bool

    public init(id: String = UUID().uuidString, name: String, schedule: String, enabled: Bool = false) {
        self.id = id
        self.name = name
        self.schedule = schedule
        self.enabled = enabled
    }
}

/// 设置页「我创建的智能体」演示态模型（纯静态字段：名称/职责/创建时间/版本，去 live 语义）
public struct CreatedAgent: Identifiable, Sendable, Hashable {
    public let id: String
    public let name: String
    public let responsibility: String
    public let createdAt: String
    public let version: String

    public init(id: String = UUID().uuidString, name: String, responsibility: String, createdAt: String, version: String) {
        self.id = id
        self.name = name
        self.responsibility = responsibility
        self.createdAt = createdAt
        self.version = version
    }
}

/// 设置页「我制作的技能」演示态模型（纯静态字段：名称/职责/创建时间/版本，去 live 语义）
public struct CreatedSkill: Identifiable, Sendable, Hashable {
    public let id: String
    public let name: String
    public let responsibility: String
    public let createdAt: String
    public let version: String

    public init(id: String = UUID().uuidString, name: String, responsibility: String, createdAt: String, version: String) {
        self.id = id
        self.name = name
        self.responsibility = responsibility
        self.createdAt = createdAt
        self.version = version
    }
}

/// 统一消息块（7 case），彻底收敛扁平 codeBlocks/formulaBlocks
public enum MessageBlock: Identifiable, Sendable, Hashable {
    case code(CodeSnippet)
    case formula(String)
    case chart(ChartBlock)
    case image(ImageBlock)
    case table(TableBlock)
    case attachment(AttachmentBlock)
    case reasoning([ReasoningStep])

    public var id: String {
        switch self {
        case .code(let s): return "code_\(s.id)"
        case .formula(let f): return "formula_\(f.hashValue)"
        case .chart(let c): return "chart_\(c.id)"
        case .image(let i): return "image_\(i.id)"
        case .table(let t): return "table_\(t.id)"
        case .attachment(let a): return "attachment_\(a.id)"
        case .reasoning(let steps): return "reasoning_" + steps.map(\.id).joined(separator: "_")
        }
    }
}

public extension ChatMessage {
    /// 构造引用上下文：仅正文 + 富媒体卡片摘要，显式剔除 reasoning 块（防思维链污染引用）。
    var quoteContext: QuotedContext {
        let summaries: [String] = blocks.compactMap { block in
            switch block {
            case .code(let s): return "[代码·\(s.language)]"
            case .formula: return "[公式]"
            case .chart(let c): return "[图表·\(c.title)]"
            case .image(let i): return "[图片·\(i.caption.isEmpty ? i.assetName : i.caption)]"
            case .table(let t): return "[表格·\(t.title)]"
            case .attachment(let a): return "[附件·\(a.fileName)]"
            case .reasoning: return nil   // 显式剔除 reasoning
            }
        }
        let blockSummary = summaries.isEmpty ? nil : summaries.joined(separator: " ")
        return QuotedContext(text: content, blockSummary: blockSummary)
    }
}

public struct ChatMessage: Identifiable, Sendable, Hashable {
    public let id: String
    public var sessionId: String
    public var role: MessageRole
    public var content: String
    public var createdAt: Date
    public var isStreaming: Bool
    public var blocks: [MessageBlock]
    public var quotedContext: QuotedContext?
    /// 富媒体演示样例标注（剧本/混合态卡片标注「演示样例」，防误解）
    public var isDemoSample: Bool

    public init(
        id: String = UUID().uuidString,
        sessionId: String = "session_default",
        role: MessageRole,
        content: String,
        createdAt: Date = Date(),
        isStreaming: Bool = false,
        blocks: [MessageBlock] = [],
        quotedContext: QuotedContext? = nil,
        isDemoSample: Bool = false
    ) {
        self.id = id
        self.sessionId = sessionId
        self.role = role
        self.content = content
        self.createdAt = createdAt
        self.isStreaming = isStreaming
        self.blocks = blocks
        self.quotedContext = quotedContext
        self.isDemoSample = isDemoSample
    }
}

// MARK: - Topology Graph Models
public enum AgentNodeStatus: String, Codable, Sendable {
    case idle = "idle"
    case running = "running"
    case completed = "completed"
    case error = "error"
    
    public var indicatorColor: Color {
        switch self {
        case .idle: return AppTheme.Colors.statusIdle
        case .running: return AppTheme.Colors.statusRunning
        case .completed: return AppTheme.Colors.statusCompleted
        case .error: return AppTheme.Colors.statusError
        }
    }
    
    public var labelText: String {
        switch self {
        case .idle: return "就绪 (Idle)"
        case .running: return "执行中 (Running)"
        case .completed: return "完成 (Completed)"
        case .error: return "异常 (Error)"
        }
    }
}

public struct AgentNode: Identifiable, Codable, Sendable, Hashable {
    public let id: String
    public var name: String
    public var roleCategory: String
    public var systemPromptSummary: String
    public var status: AgentNodeStatus
    public var x: CGFloat
    public var y: CGFloat
    public var subscribedKnowledge: [String]
    public var inputDeps: [String]
    public var outputDeps: [String]
    
    public var position: CGPoint {
        get { CGPoint(x: x, y: y) }
        set {
            x = newValue.x
            y = newValue.y
        }
    }
    
    public init(
        id: String,
        name: String,
        roleCategory: String,
        systemPromptSummary: String,
        status: AgentNodeStatus = .idle,
        position: CGPoint,
        subscribedKnowledge: [String] = [],
        inputDeps: [String] = [],
        outputDeps: [String] = []
    ) {
        self.id = id
        self.name = name
        self.roleCategory = roleCategory
        self.systemPromptSummary = systemPromptSummary
        self.status = status
        self.x = position.x
        self.y = position.y
        self.subscribedKnowledge = subscribedKnowledge
        self.inputDeps = inputDeps
        self.outputDeps = outputDeps
    }
}

public struct AgentEdge: Identifiable, Codable, Sendable, Hashable {
    public let id: String
    public var sourceNodeId: String
    public var targetNodeId: String
    public var label: String?
    
    public init(
        id: String = UUID().uuidString,
        sourceNodeId: String,
        targetNodeId: String,
        label: String? = nil
    ) {
        self.id = id
        self.sourceNodeId = sourceNodeId
        self.targetNodeId = targetNodeId
        self.label = label
    }
}

public struct TopologyGraph: Codable, Sendable, Hashable {
    public var nodes: [AgentNode]
    public var edges: [AgentEdge]
    
    public init(nodes: [AgentNode] = [], edges: [AgentEdge] = []) {
        self.nodes = nodes
        self.edges = edges
    }
}

// MARK: - Red / Yellow / Green Knowledge Market
public enum SecurityLevel: String, Codable, Sendable, CaseIterable {
    case red = "red"        // 🔴 私有绝密 (Private Confidential)
    case yellow = "yellow"  // 🟡 受限共享 (Restricted Sharing)
    case green = "green"    // 🟢 全员公开 (Public Open)
    
    public var badgeTitle: String {
        switch self {
        case .red: return "私有绝密"
        case .yellow: return "受限共享"
        case .green: return "全员公开"
        }
    }
    
    public var color: Color {
        switch self {
        case .red: return AppTheme.Colors.securityRed
        case .yellow: return AppTheme.Colors.securityYellow
        case .green: return AppTheme.Colors.securityGreen
        }
    }
    
    public var iconName: String {
        switch self {
        case .red: return "lock.shield.fill"
        case .yellow: return "person.badge.shield.checkmark.fill"
        case .green: return "globe.badge.chevron.backward"
        }
    }
}

public enum SubscriptionStatus: String, Codable, Sendable {
    case none = "none"
    case pending = "pending"
    case approved = "approved"
    
    public var displayText: String {
        switch self {
        case .none: return "未订阅"
        case .pending: return "审批中"
        case .approved: return "已授权"
        }
    }
}

public struct KnowledgeItem: Identifiable, Codable, Sendable, Hashable {
    public let id: String
    public var title: String
    public var domain: String
    public var tenantId: String
    public var securityLevel: SecurityLevel
    public var isSubscribed: Bool
    public var subscriptionStatus: SubscriptionStatus
    public var summary: String
    public var updatedAt: Date
    public var lineage: String?
    
    public init(
        id: String,
        title: String,
        domain: String,
        tenantId: String = "public",
        securityLevel: SecurityLevel,
        isSubscribed: Bool = false,
        subscriptionStatus: SubscriptionStatus = .none,
        summary: String,
        updatedAt: Date = Date(),
        lineage: String? = nil
    ) {
        self.id = id
        self.title = title
        self.domain = domain
        self.tenantId = tenantId
        self.securityLevel = securityLevel
        self.isSubscribed = isSubscribed
        self.subscriptionStatus = subscriptionStatus
        self.summary = summary
        self.updatedAt = updatedAt
        self.lineage = lineage
    }
}

// MARK: - Prompt Refinement Studio Draft
public struct PromptRefinementDraft: Identifiable, Codable, Sendable, Hashable {
    public let id: String
    public var originalText: String
    public var refinedSystemDirective: String
    public var explanation: String
    public var tags: [String]
    
    public init(
        id: String = UUID().uuidString,
        originalText: String,
        refinedSystemDirective: String,
        explanation: String,
        tags: [String] = []
    ) {
        self.id = id
        self.originalText = originalText
        self.refinedSystemDirective = refinedSystemDirective
        self.explanation = explanation
        self.tags = tags
    }
}

// MARK: - Global App State
@MainActor
public final class AppState: ObservableObject {
    @Published public var isLoggedIn: Bool = false
    @Published public var isGuestMode: Bool = false
    @Published public var currentProfile: TenantProfile
    @Published public var activeTab: Int = 0
    @Published public var selectedAgentId: String = "main_agent"
    @Published public var pendingChatPrompt: String? = nil
    
    public init(
        isLoggedIn: Bool = true,
        isGuestMode: Bool = false,
        currentProfile: TenantProfile = MockData.tenantProfile
    ) {
        self.isLoggedIn = isLoggedIn
        self.isGuestMode = isGuestMode
        self.currentProfile = currentProfile
    }
    
    public func loginAsGuest() {
        self.isGuestMode = true
        self.isLoggedIn = true
        self.currentProfile = TenantProfile(
            name: "游客体验官",
            tenantId: "guest_tenant",
            role: .guest,
            concurrencyLimit: 2,
            tokenQuotaUsage: 0.15,
            isVipLane: false
        )
    }
    
    public func logout() {
        self.isLoggedIn = false
        self.isGuestMode = false
    }
    
    public func navigateToChatWithPrompt(_ prompt: String) {
        self.pendingChatPrompt = prompt
        self.activeTab = 0 // Switch to Chat tab
    }
}

// MARK: - Comprehensive Mock Data Set
public enum MockData {
    
    public static let tenantProfile = TenantProfile(
        name: "陈工 (研发中台)",
        tenantId: "xFusion_MO_Tenant",
        role: .tenantAdmin,
        concurrencyLimit: 5,
        tokenQuotaUsage: 0.68,
        isVipLane: false
    )
    
    public static let adminProfile = TenantProfile(
        name: "SuperAdmin (Sovereign)",
        tenantId: "master_sovereign",
        role: .masterAdmin,
        concurrencyLimit: 50,
        tokenQuotaUsage: 0.22,
        isVipLane: true
    )
    
    public static let messages: [ChatMessage] = [
        ChatMessage(
            role: .user,
            content: "帮我查询制造产线 SMT 贴片机的异常告警，并给出 Root Cause 分析与修复脚本。"
        ),
        ChatMessage(
            role: .assistant,
            content: "已检索 [[制造/SMT设备健康指标]] 与实时 Telemetry 流。系统检测到 **SMT-03 贴片头真空吸嘴负压不足 (P < 45kPa)**，触发降速告警。",
            blocks: [
                .code(
                    CodeSnippet(
                        language: "python",
                        code: """
                        import requests
                        
                        def auto_recalibrate_nozzle(machine_id: str):
                            payload = {"action": "clean_purge", "pressure_target_kpa": 65.0}
                            resp = requests.post(f"https://iot.plant.internal/api/v1/smt/{machine_id}/calibrate", json=payload)
                            return resp.json()["status"] == "SUCCESS"
                        """
                    )
                ),
                .formula(
                    "P_{loss} = \\frac{\\Delta P}{P_0} = \\frac{65 - 42}{65} \\approx 35.38\\% \\ge \\theta_{alert}"
                )
            ]
        ),
        ChatMessage(
            role: .user,
            content: "如果需要将质检 Agent 串联到这个诊断流程之后，拓扑结构应该怎么变更？"
        ),
        ChatMessage(
            role: .assistant,
            content: "根据平台只读拓扑安全铁律，画布不可直接手动拖拽。我已为您生成变更提案：将 `QA-Inspector` 挂载在 `SMT-Diagnostic` 输出之后。您确认执行后，后端编排引擎将通过 DAG 无环拓扑自动热加载更新。"
        )
    ]
    
    // MARK: 富媒体演示剧本（竞品周报风格·首条主动发送注入）
    
    /// 演示用真实思维链步骤（thought / tool_call / skill_load / agent_spawn 四类齐全）
    public static let demoReasoningSteps: [ReasoningStep] = [
        ReasoningStep(type: .thought, title: "思考过程", detail: "定位竞品周报主题，圈定本周检索范围与关键竞品对象。"),
        ReasoningStep(type: .skillLoad, title: "加载技能: blogwatcher", detail: "监控竞品博客与 RSS 动态源"),
        ReasoningStep(type: .toolCall, title: "调用工具: web_search", detail: "查询 OpenAI / Anthropic / DeepSeek 本周动态"),
        ReasoningStep(type: .toolCall, title: "调用工具: read_file", detail: "读取竞品周报模板与既有对标口径"),
        ReasoningStep(type: .agentSpawn, title: "分派子代理任务", detail: "子任务内部步骤暂不展开")
    ]
    
    /// 首条主动消息触发的 4 卡剧本回复（Chart / Image / Table / Attachment + 真实链）
    public static func richMediaDemoReply(for prompt: String) -> ChatMessage {
        let chart = ChartBlock(
            title: "近 6 月主流竞品热度走势",
            chartType: .line,
            series: [
                ChartSeries(name: "OpenAI", points: [
                    ChartPoint(label: "2月", value: 62),
                    ChartPoint(label: "3月", value: 68),
                    ChartPoint(label: "4月", value: 71),
                    ChartPoint(label: "5月", value: 78),
                    ChartPoint(label: "6月", value: 84),
                    ChartPoint(label: "7月", value: 90)
                ]),
                ChartSeries(name: "Anthropic", points: [
                    ChartPoint(label: "2月", value: 48),
                    ChartPoint(label: "3月", value: 55),
                    ChartPoint(label: "4月", value: 60),
                    ChartPoint(label: "5月", value: 66),
                    ChartPoint(label: "6月", value: 72),
                    ChartPoint(label: "7月", value: 79)
                ])
            ],
            summary: "头部竞品热度持续上行，推理成本下探推动商业模型收敛。"
        )
        let image = ImageBlock(assetName: "demo_weekly_overview", caption: "本周 AI 竞品动态速览")
        let table = TableBlock(
            title: "竞品动态一览（本周）",
            headers: ["竞品", "动向", "影响"],
            rows: [
                ["OpenAI", "发布新一代推理模型", "推理成本下降"],
                ["Anthropic", "开放长上下文 API", "企业落地提速"],
                ["DeepSeek", "开源轻量蒸馏模型", "私有化门槛降低"]
            ]
        )
        let attachment = AttachmentBlock(
            fileName: "AI竞品周报_2026W33.pdf",
            fileType: .pdf,
            fileSize: "2.4 MB"
        )
        return ChatMessage(
            role: .assistant,
            content: "关于「\(prompt)」——以下是本周竞品周报速览（演示样例，正式数据随真实检索链路接入）。",
            blocks: [
                .chart(chart),
                .image(image),
                .table(table),
                .attachment(attachment),
                .reasoning(demoReasoningSteps)
            ],
            isDemoSample: true
        )
    }
    
    /// 设置页底部「平台定时任务（演示）」三字段只读数据
    public static let scheduledTasks: [ScheduledTask] = [
        ScheduledTask(name: "竞品监控日报", schedule: "每日 08:00"),
        ScheduledTask(name: "知识库周报编译", schedule: "每周日 22:00"),
        ScheduledTask(name: "成本审计月报", schedule: "每月 1 日 10:00")
    ]

    /// 设置页「我创建的智能体」演示态（纯静态字段，显式标注不可交互；后端列表 API 后续轮）
    public static let createdAgents: [CreatedAgent] = [
        CreatedAgent(name: "制造诊断 Sentinel", responsibility: "产线 IoT 遥测与 SMT 专家知识库因果推断", createdAt: "2026-08-12", version: "v1.3"),
        CreatedAgent(name: "金融对账 Agent", responsibility: "清结算幂等校验与三方对账差异核销", createdAt: "2026-08-09", version: "v0.9"),
        CreatedAgent(name: "竞品情报雷达", responsibility: "竞品动态增量追踪与结构化情报卡片回写", createdAt: "2026-08-15", version: "v1.0")
    ]

    /// 设置页「我制作的技能」演示态（纯静态字段，显式标注不可交互）
    public static let createdSkills: [CreatedSkill] = [
        CreatedSkill(name: "SMT 健康诊断", responsibility: "贴片机负压告警阈值与根因排查清单", createdAt: "2026-08-11", version: "v1.1"),
        CreatedSkill(name: "审计红线核查", responsibility: "ABAC 权限与变更影响域合规校验", createdAt: "2026-08-13", version: "v0.8"),
        CreatedSkill(name: "竞品周报编译", responsibility: "竞品情报汇总与结构化周报生成", createdAt: "2026-08-14", version: "v1.2")
    ]
    
    public static let topologyGraph: TopologyGraph = {
        let n1 = AgentNode(
            id: "node_ingest",
            name: "Data Ingester",
            roleCategory: "数据采集",
            systemPromptSummary: "负责多协议工业传感器与实时 MQTT 数据流清洗、脱敏与初步分诊。",
            status: .completed,
            position: CGPoint(x: 180, y: 80),
            subscribedKnowledge: ["工业协议标准", "MQTT网关规范"],
            inputDeps: [],
            outputDeps: ["node_diag"]
        )
        
        let n2 = AgentNode(
            id: "node_diag",
            name: "SMT Diagnostic",
            roleCategory: "根因诊断",
            systemPromptSummary: "结合 SMT 制造专家知识库与贝叶斯网络，对贴片机气压/震动异常进行因果推断。",
            status: .running,
            position: CGPoint(x: 180, y: 220),
            subscribedKnowledge: ["SMT设备健康指标", "故障排查树"],
            inputDeps: ["node_ingest"],
            outputDeps: ["node_qa", "node_audit"]
        )
        
        let n3 = AgentNode(
            id: "node_qa",
            name: "QA Inspector",
            roleCategory: "质检风控",
            systemPromptSummary: "基于 AOI 光学检测图像特征比对，评估缺陷漏检率并生成整改指令。",
            status: .idle,
            position: CGPoint(x: 80, y: 360),
            subscribedKnowledge: ["AOI缺陷图谱"],
            inputDeps: ["node_diag"],
            outputDeps: []
        )
        
        let n4 = AgentNode(
            id: "node_audit",
            name: "Audit Sentinel",
            roleCategory: "合规审计",
            systemPromptSummary: "全流程审计写操作与参数下发，校验 ABAC 权限与变更影响域。",
            status: .idle,
            position: CGPoint(x: 280, y: 360),
            subscribedKnowledge: ["企业合规审查红线"],
            inputDeps: ["node_diag"],
            outputDeps: []
        )
        
        let edges = [
            AgentEdge(sourceNodeId: "node_ingest", targetNodeId: "node_diag", label: "清洗后流"),
            AgentEdge(sourceNodeId: "node_diag", targetNodeId: "node_qa", label: "诊断信号"),
            AgentEdge(sourceNodeId: "node_diag", targetNodeId: "node_audit", label: "审计埋点")
        ]
        
        return TopologyGraph(nodes: [n1, n2, n3, n4], edges: edges)
    }()
    
    public static let knowledgeItems: [KnowledgeItem] = [
        KnowledgeItem(
            id: "kb_pvt_001",
            title: "xFusion 内部产线核心机密与排产算法",
            domain: "制造",
            tenantId: "xFusion_MO_Tenant",
            securityLevel: .red,
            isSubscribed: true,
            subscriptionStatus: .approved,
            summary: "绝密私有资产，包含独家工艺参数与产线调度优化模型，物理隔离存储，禁止任何外部租户订阅。"
        ),
        KnowledgeItem(
            id: "kb_rst_002",
            title: "四大事务所审计合规底稿标准库",
            domain: "审计",
            tenantId: "public",
            securityLevel: .yellow,
            isSubscribed: false,
            subscriptionStatus: .none,
            summary: "受限共享资产，包含普华/德勤等跨国审计案例与风控 checklist，需提交订阅申请由超级管理员审批。"
        ),
        KnowledgeItem(
            id: "kb_rst_003",
            title: "TokenOps 算力池化调度与 RoAI 成本模型",
            domain: "TokenOps",
            tenantId: "public",
            securityLevel: .yellow,
            isSubscribed: false,
            subscriptionStatus: .pending,
            summary: "受限共享资产，包含企业级 vGPU 切片、QoS 抢占与大模型算力成本精细化核算引擎规范。"
        ),
        KnowledgeItem(
            id: "kb_pub_004",
            title: "Apple HIG 与 SwiftUI 原生工程最佳实践",
            domain: "通用",
            tenantId: "public",
            securityLevel: .green,
            isSubscribed: true,
            subscriptionStatus: .approved,
            summary: "全员公开通用条目，收录 iOS 17+ 架构设计、Dynamic Type 适配与无障碍规范，可一键自由订阅。"
        ),
        KnowledgeItem(
            id: "kb_pub_005",
            title: "金融行业分布式对账与防重放协议",
            domain: "金融",
            tenantId: "public",
            securityLevel: .green,
            isSubscribed: false,
            subscriptionStatus: .none,
            summary: "全员公开通用条目，介绍高并发清结算系统幂等性设计与三方对账差异核销机制。"
        )
    ]
    
    public static let promptRefinement = PromptRefinementDraft(
        originalText: "帮我写一个专门检查制造产线异常的助手，要严谨点，别瞎说。",
        refinedSystemDirective: """
        ## Role & Objective
        你是一名企业级制造产线质量监控与根因诊断专家（Manufacturing QA & Diagnostic Sentinel）。
        
        ## Core Constraints
        1. 严格基于当前产线 IoT Telemetry 遥测数据与已订阅知识库（[[SMT设备健康指标]]）推理。
        2. 严禁任何未经遥测验证的幻觉推断；置信度低于 0.85 时必须显式提示人工复核。
        3. 遵守只读拓扑安全铁律，涉及设备写操作必须生成待审批工单。
        
        ## Workflow
        1. 接收告警事件 ➔ 2. 提取传感器特征（气压/震动/温升）➔ 3. 计算偏离度 ➔ 4. 输出诊断结论与修复建议。
        
        ## Output Format
        采用标准 Markdown 结构输出：【告警定级】、【根因推断】、【计算依据公式】、【建议处置指令】。
        """,
        explanation: "将口语化泛化需求重构为符合企业安全标准的结构化 System Directive，注入了角色约束、因果推理规范与输出标准模板。",
        tags: ["制造", "QA质检", "工业安全", "结构化Prompt"]
    )
}
