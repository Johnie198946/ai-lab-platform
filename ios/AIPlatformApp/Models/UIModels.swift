//
//  UIModels.swift
//  AIPlatformApp
//
//  Strongly Typed Frontend Data Models, State Handlers & Mock Datasets
//  Swift 6 / iOS 17+ Sendable & Identifiable Conformance
//

import SwiftUI
import Combine
import CryptoKit

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

public enum CuteDisplayNames {
    private static let names = ["棉花糖小兔", "奶油小熊", "星星布丁", "云朵团子", "桃桃软糖", "月亮小鹿"]

    public static func name(for userID: String) -> String {
        guard !userID.isEmpty else { return names[0] }
        let value = userID.utf8.reduce(0) { ($0 &* 31) &+ Int($1) }
        return names[abs(value) % names.count]
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
    /// 会话切换屏障：在途请求被切换拦截时，在原会话落盘的显式中断标记（不参与 API 上下文组装）
    case interrupted = "interrupted"
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

// MARK: - 澄清选项卡片（对齐 Hermes clarify 协议：question / choices / multi_select）

/// 单条澄清选项
public struct ClarifyOption: Identifiable, Sendable, Hashable {
    public let id: String
    public var label: String

    public init(id: String = UUID().uuidString, label: String) {
        self.id = id
        self.label = label
    }
}

public enum ClarifySubmissionState: String, Codable, Sendable, Hashable {
    case pending, submitting, accepted, continuing, rejected, expired, reconciling
}

/// 澄清卡片数据块（单选/多选 + 自定义输入 + 已提交态）
public struct ClarifyBlock: Identifiable, Sendable, Hashable {
    public let id: String
    /// 后端澄清 ID（bridge clarify 事件携带）：提交时透传，精确解锁阻塞的 agent 线程（P0 修复）
    public var clarifyId: String?
    public var requestId: String?
    public var sessionId: String?
    public var agentId: String?
    public var expiresInSeconds: Int?
    public var submissionState: ClarifySubmissionState
    public var question: String
    public var choices: [ClarifyOption]
    /// true = 多选（Checkbox），false = 单选（Radio）
    public var multiSelect: Bool
    public var submitLabel: String
    /// 澄清来源：bridge = Hermes clarify 工具（点选后 submitClarify 解锁 agent）；preclassified = 本地规则预分诊卡片（点选后发起新一轮对话）
    public var source: String
    /// 已提交标记：提交后禁用重复点选，并记录最终选择文本
    public var isSubmitted: Bool
    public var submittedSelection: String
    /// 客户端交互草稿随消息落盘；收起、切会话或冷启动均不会丢失。
    public var draftSelectionIDs: [String]
    public var draftCustomText: String
    public var isCollapsed: Bool

    public init(
        id: String = UUID().uuidString,
        clarifyId: String? = nil,
        requestId: String? = nil,
        sessionId: String? = nil,
        agentId: String? = nil,
        expiresInSeconds: Int? = nil,
        submissionState: ClarifySubmissionState = .pending,
        question: String,
        choices: [String],
        multiSelect: Bool = false,
        submitLabel: String = "确认选择",
        source: String = "bridge",
        isSubmitted: Bool = false,
        submittedSelection: String = "",
        draftSelectionIDs: [String] = [],
        draftCustomText: String = "",
        isCollapsed: Bool = false
    ) {
        self.id = id
        self.clarifyId = clarifyId
        self.requestId = requestId
        self.sessionId = sessionId
        self.agentId = agentId
        self.expiresInSeconds = expiresInSeconds
        self.submissionState = submissionState
        self.question = question
        self.choices = choices.map { ClarifyOption(label: $0) }
        self.multiSelect = multiSelect
        self.submitLabel = submitLabel
        self.source = source
        self.isSubmitted = isSubmitted
        self.submittedSelection = submittedSelection
        self.draftSelectionIDs = draftSelectionIDs
        self.draftCustomText = draftCustomText
        self.isCollapsed = isCollapsed
    }

    /// 提交结果回填（由 ChatView 在用户点选确认后调用，防重复提交）
    public mutating func markSubmitted(selection: String) {
        self.isSubmitted = true
        self.submittedSelection = selection
        self.submissionState = .accepted
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

/// 设置页「我创建的智能体」本地持久化模型（已废弃：设置页仅消费云端真实数据）

/// 统一消息块（7 case），彻底收敛扁平 codeBlocks/formulaBlocks
public enum NoteDraftState: String, Codable, Sendable, Hashable {
    case awaitingConfirmation
    case saved
    case savedLocally
    case discarded
}

public struct NoteMergeCandidate: Identifiable, Codable, Sendable, Hashable {
    public let id: String
    public let title: String
    public let snippet: String
    public let updatedAt: String?

    public init(id: String, title: String, snippet: String, updatedAt: String? = nil) {
        self.id = id
        self.title = title
        self.snippet = snippet
        self.updatedAt = updatedAt
    }
}

public struct NoteDraftBlock: Identifiable, Codable, Sendable, Hashable {
    public let id: String
    public var title: String
    public var markdown: String
    public var tags: [String]
    public let sourceSessionId: String?
    public let sourceMessageIds: [String]
    public let accountScope: String?
    public var state: NoteDraftState
    public var savedNoteId: String?
    public var mergeCandidates: [NoteMergeCandidate]?
    public var mergedTitle: String?
    public var mergedMarkdown: String?
    public var mergedTags: [String]?
    /// `update` means this draft replaces one authenticated existing note after confirmation.
    /// Optional for backwards-compatible decoding of persisted chat history.
    public var operation: String?
    public var targetNoteId: String?
    public var targetNoteTitle: String?
    public var targetContentHash: String?

    public init(id: String, title: String, markdown: String, tags: [String], sourceSessionId: String?, sourceMessageIds: [String], accountScope: String? = nil, state: NoteDraftState = .awaitingConfirmation, savedNoteId: String? = nil, mergeCandidates: [NoteMergeCandidate]? = nil, mergedTitle: String? = nil, mergedMarkdown: String? = nil, mergedTags: [String]? = nil, operation: String? = nil, targetNoteId: String? = nil, targetNoteTitle: String? = nil, targetContentHash: String? = nil) {
        self.id = id
        self.title = title
        self.markdown = markdown
        self.tags = tags
        self.sourceSessionId = sourceSessionId
        self.sourceMessageIds = sourceMessageIds
        self.accountScope = accountScope
        self.state = state
        self.savedNoteId = savedNoteId
        self.mergeCandidates = mergeCandidates
        self.mergedTitle = mergedTitle
        self.mergedMarkdown = mergedMarkdown
        self.mergedTags = mergedTags
        self.operation = operation
        self.targetNoteId = targetNoteId
        self.targetNoteTitle = targetNoteTitle
        self.targetContentHash = targetContentHash
    }

    public var isUpdate: Bool { operation == "update" && targetNoteId != nil }
}

public enum KnowledgeActionState: String, Codable, Sendable, Hashable {
    case proposed, applying, synced, discarded, stale, failed
    case localApplied = "local_applied"
    case syncPending = "sync_pending"
}

public struct KnowledgeActionStep: Codable, Sendable, Hashable, Identifiable {
    public var id: String { "\(kind):\(targetNoteId ?? title ?? "new")" }
    public let kind: String
    public let targetNoteId: String?
    public let sourceNoteIds: [String]
    public let title: String?
    public let markdown: String?
    public let tags: [String]
    public let pinned: Bool?
    public let linkTitle: String?
    public let originalContentHash: String?
    public let sourceContentHashes: [String: String?]?

    public init(kind: String, targetNoteId: String? = nil, sourceNoteIds: [String] = [], title: String? = nil, markdown: String? = nil, tags: [String] = [], pinned: Bool? = nil, linkTitle: String? = nil, originalContentHash: String? = nil, sourceContentHashes: [String: String?]? = nil) {
        self.kind = kind; self.targetNoteId = targetNoteId; self.sourceNoteIds = sourceNoteIds
        self.title = title; self.markdown = markdown; self.tags = tags; self.pinned = pinned
        self.linkTitle = linkTitle; self.originalContentHash = originalContentHash
        self.sourceContentHashes = sourceContentHashes
    }
}

public struct KnowledgeNavigationTarget: Codable, Sendable, Hashable {
    public let destination: String
    public let noteId: String?
    public let query: String?
}

public struct KnowledgeActionBlock: Identifiable, Codable, Sendable, Hashable {
    public let id: String
    public let summary: String
    public let steps: [KnowledgeActionStep]
    public let beforePreview: String
    public let afterPreview: String
    public let markdownDiff: String
    public let riskLevel: String
    public let actionDigest: String
    /// Short-lived bearer is intentionally excluded from Codable persistence.
    public var transientCapability: String?
    public let expiresAt: Int
    public let accountScope: String?
    public let suggestedNavigation: KnowledgeNavigationTarget?
    public var state: KnowledgeActionState
    public var resultNoteIds: [String]
    public var errorMessage: String?

    enum CodingKeys: String, CodingKey {
        case id, summary, steps, beforePreview, afterPreview, markdownDiff, riskLevel
        case actionDigest, expiresAt, accountScope, suggestedNavigation, state
        case resultNoteIds, errorMessage
    }

    public init(id: String, summary: String, steps: [KnowledgeActionStep], beforePreview: String = "", afterPreview: String = "", markdownDiff: String = "", riskLevel: String = "low", actionDigest: String, transientCapability: String?, expiresAt: Int, accountScope: String? = nil, suggestedNavigation: KnowledgeNavigationTarget? = nil, state: KnowledgeActionState = .proposed, resultNoteIds: [String] = [], errorMessage: String? = nil) {
        self.id = id; self.summary = summary; self.steps = steps
        self.beforePreview = beforePreview; self.afterPreview = afterPreview
        self.markdownDiff = markdownDiff; self.riskLevel = riskLevel
        self.actionDigest = actionDigest; self.transientCapability = transientCapability
        self.expiresAt = expiresAt; self.accountScope = accountScope
        self.suggestedNavigation = suggestedNavigation; self.state = state
        self.resultNoteIds = resultNoteIds; self.errorMessage = errorMessage
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        summary = try c.decode(String.self, forKey: .summary)
        steps = try c.decode([KnowledgeActionStep].self, forKey: .steps)
        beforePreview = try c.decodeIfPresent(String.self, forKey: .beforePreview) ?? ""
        afterPreview = try c.decodeIfPresent(String.self, forKey: .afterPreview) ?? ""
        markdownDiff = try c.decodeIfPresent(String.self, forKey: .markdownDiff) ?? ""
        riskLevel = try c.decodeIfPresent(String.self, forKey: .riskLevel) ?? "low"
        actionDigest = try c.decode(String.self, forKey: .actionDigest)
        transientCapability = nil
        expiresAt = try c.decodeIfPresent(Int.self, forKey: .expiresAt) ?? 0
        accountScope = try c.decodeIfPresent(String.self, forKey: .accountScope)
        suggestedNavigation = try c.decodeIfPresent(KnowledgeNavigationTarget.self, forKey: .suggestedNavigation)
        state = try c.decodeIfPresent(KnowledgeActionState.self, forKey: .state) ?? .stale
        resultNoteIds = try c.decodeIfPresent([String].self, forKey: .resultNoteIds) ?? []
        errorMessage = try c.decodeIfPresent(String.self, forKey: .errorMessage)
        if state == .proposed || state == .applying { state = .stale }
    }
}

public enum MessageBlock: Identifiable, Sendable, Hashable {
    case code(CodeSnippet)
    case formula(String)
    case chart(ChartBlock)
    case image(ImageBlock)
    case table(TableBlock)
    case attachment(AttachmentBlock)
    case reasoning([ReasoningStep])
    case clarify(ClarifyBlock)
    case noteDraft(NoteDraftBlock)
    case knowledgeAction(KnowledgeActionBlock)

    public var id: String {
        switch self {
        case .code(let s): return "code_\(s.id)"
        case .formula(let f): return "formula_\(f.hashValue)"
        case .chart(let c): return "chart_\(c.id)"
        case .image(let i): return "image_\(i.id)"
        case .table(let t): return "table_\(t.id)"
        case .attachment(let a): return "attachment_\(a.id)"
        case .reasoning(let steps): return "reasoning_" + steps.map(\.id).joined(separator: "_")
        case .clarify(let c): return "clarify_\(c.id)"
        case .noteDraft(let draft): return "note_draft_\(draft.id)"
        case .knowledgeAction(let action): return "knowledge_action_\(action.id)"
        }
    }
}

public extension ChatMessage {
    /// 取消息中的澄清卡片块（无则 nil）。ChatView 据此将消息渲染为 ClarifyCard 而非普通气泡。
    var clarifyBlock: ClarifyBlock? {
        for block in blocks {
            if case .clarify(let c) = block {
                return c
            }
        }
        return nil
    }

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
            case .clarify(let c): return "[澄清·\(c.question)]"
            case .noteDraft(let draft): return "[笔记草稿·\(draft.title)]"
            case .knowledgeAction(let action): return "[知识操作·\(action.summary)]"
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
    /// 在途占位标记：请求发起时 true，收到完整应答/异常/降级/中断时 false（冷启动自愈孤儿会话）
    public var pending: Bool
    /// 502 降级标记：degraded=true 的消息跳过 ReasoningCard、不入 API 上下文、渲染降级卡
    public var degraded: Bool
    /// ChatGPT 风格思考胶囊真实耗时（秒）：流式完成时原子落盘，历史冷启动真实回显；无记录时优雅降级
    public var reasoningDuration: Int?
    public var executingAgentId: String?
    public var executingAgentName: String?
    public var delegatedBy: String?

    public init(
        id: String = UUID().uuidString,
        sessionId: String = "session_default",
        role: MessageRole,
        content: String,
        createdAt: Date = Date(),
        isStreaming: Bool = false,
        blocks: [MessageBlock] = [],
        quotedContext: QuotedContext? = nil,
        isDemoSample: Bool = false,
        pending: Bool = false,
        degraded: Bool = false,
        reasoningDuration: Int? = nil,
        executingAgentId: String? = nil,
        executingAgentName: String? = nil,
        delegatedBy: String? = nil
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
        self.pending = pending
        self.degraded = degraded
        self.reasoningDuration = reasoningDuration
        self.executingAgentId = executingAgentId
        self.executingAgentName = executingAgentName
        self.delegatedBy = delegatedBy
    }
}

// MARK: - 会话持久化（消息级原子落盘 + 冷启动恢复）

/// 落盘消息 DTO：仅持久化会话恢复所需的核心字段（角色/正文/时间/pending/degraded/演示标注）。
/// 富媒体 blocks 为演示态，不参与落盘（本轮范围：iPhone 单窗口会话管理，诚实标注）。
public struct PersistedMessage: Codable, Sendable {
    public let id: String
    public let role: String
    public let content: String
    public let createdAt: Date
    public let pending: Bool
    public let degraded: Bool
    public let isDemoSample: Bool
    public let reasoningDuration: Int?
    public let executingAgentId: String?
    public let executingAgentName: String?
    public let delegatedBy: String?
    public let clarify: PersistedClarify?
    public let noteDraft: NoteDraftBlock?
    public let knowledgeAction: KnowledgeActionBlock?

    public init(_ m: ChatMessage) {
        self.id = m.id
        self.role = m.role.rawValue
        self.content = m.content
        self.createdAt = m.createdAt
        self.pending = m.pending
        self.degraded = m.degraded
        self.isDemoSample = m.isDemoSample
        self.reasoningDuration = m.reasoningDuration
        self.executingAgentId = m.executingAgentId
        self.executingAgentName = m.executingAgentName
        self.delegatedBy = m.delegatedBy
        self.clarify = m.clarifyBlock.map(PersistedClarify.init)
        self.noteDraft = m.blocks.compactMap {
            if case .noteDraft(let draft) = $0 { return draft }
            return nil
        }.first
        self.knowledgeAction = m.blocks.compactMap {
            if case .knowledgeAction(let action) = $0 { return action }
            return nil
        }.first
    }

    public func toChatMessage(sessionId: String) -> ChatMessage {
        var message = ChatMessage(
            id: id,
            sessionId: sessionId,
            role: MessageRole(rawValue: role) ?? .assistant,
            content: content,
            createdAt: createdAt,
            isDemoSample: isDemoSample,
            pending: pending,
            degraded: degraded,
            reasoningDuration: reasoningDuration,
            executingAgentId: executingAgentId,
            executingAgentName: executingAgentName,
            delegatedBy: delegatedBy
        )
        if let clarify {
            message.blocks = [.clarify(clarify.toClarifyBlock(defaultSessionId: sessionId))]
        }
        if let noteDraft {
            message.blocks.append(.noteDraft(noteDraft))
        }
        if let knowledgeAction {
            message.blocks.append(.knowledgeAction(knowledgeAction))
        }
        return message
    }
}

/// 可交互 Clarify 的最小恢复快照；普通展示 blocks 仍不落盘。
public struct PersistedClarify: Codable, Sendable {
    public let id: String
    public let clarifyId: String?
    public let requestId: String?
    public let sessionId: String?
    public let agentId: String?
    public let expiresInSeconds: Int?
    public let submissionState: ClarifySubmissionState?
    public let question: String
    public let choices: [String]
    public let multiSelect: Bool
    public let submitLabel: String
    public let source: String
    public let isSubmitted: Bool
    public let submittedSelection: String
    public let draftSelectionIDs: [String]?
    public let draftSelectionLabels: [String]?
    public let draftCustomText: String?
    public let isCollapsed: Bool?

    public init(_ block: ClarifyBlock) {
        id = block.id
        clarifyId = block.clarifyId
        requestId = block.requestId
        sessionId = block.sessionId
        agentId = block.agentId
        expiresInSeconds = block.expiresInSeconds
        submissionState = block.submissionState
        question = block.question
        choices = block.choices.map(\.label)
        multiSelect = block.multiSelect
        submitLabel = block.submitLabel
        source = block.source
        isSubmitted = block.isSubmitted
        submittedSelection = block.submittedSelection
        draftSelectionIDs = block.draftSelectionIDs
        draftSelectionLabels = block.draftSelectionIDs.compactMap { id in
            block.choices.first(where: { $0.id == id })?.label
        }
        draftCustomText = block.draftCustomText
        isCollapsed = block.isCollapsed
    }

    public func toClarifyBlock(defaultSessionId: String) -> ClarifyBlock {
        var block = ClarifyBlock(
            id: id,
            clarifyId: clarifyId,
            requestId: requestId,
            sessionId: sessionId ?? defaultSessionId,
            agentId: agentId,
            expiresInSeconds: expiresInSeconds,
            submissionState: submissionState ?? (isSubmitted ? .accepted : .pending),
            question: question,
            choices: choices,
            multiSelect: multiSelect,
            submitLabel: submitLabel,
            source: source,
            isSubmitted: isSubmitted,
            submittedSelection: submittedSelection,
            draftSelectionIDs: [],
            draftCustomText: draftCustomText ?? "",
            isCollapsed: isCollapsed ?? false
        )
        if let draftSelectionLabels {
            block.draftSelectionIDs = block.choices.filter { draftSelectionLabels.contains($0.label) }.map(\.id)
        } else {
            // Backward compatibility for snapshots written before labels were persisted.
            block.draftSelectionIDs = draftSelectionIDs ?? []
        }
        return block
    }
}

public enum TopicSessionState: String, Codable, Sendable, Hashable {
    case active, queued, ending, ended
}

/// Existing chat session metadata for a focused thread. This is not a second runtime.
public struct TopicSessionMetadata: Codable, Sendable, Hashable, Identifiable {
    public var id: String { sessionId }
    public let sessionId: String
    public let parentSessionId: String
    public let sourceMessageId: String
    public let sourceText: String
    public let sourceBlockSummary: String?
    public let createdAt: Date
    public var state: TopicSessionState

    public init(sessionId: String, parentSessionId: String, sourceMessageId: String, sourceText: String, sourceBlockSummary: String?, createdAt: Date = Date(), state: TopicSessionState) {
        self.sessionId = sessionId
        self.parentSessionId = parentSessionId
        self.sourceMessageId = sourceMessageId
        self.sourceText = sourceText
        self.sourceBlockSummary = sourceBlockSummary
        self.createdAt = createdAt
        self.state = state
    }
}

/// 单个会话的落盘记录（标题 + 更新时间 + 消息数组）。
public struct SessionRecord: Codable, Sendable {
    public let id: String
    public var title: String
    public var updatedAt: Date
    public var messages: [PersistedMessage]
    public var agentId: String?
    public var agentName: String?

    public init(
        id: String, title: String, updatedAt: Date, messages: [PersistedMessage],
        agentId: String? = nil, agentName: String? = nil
    ) {
        self.id = id
        self.title = title
        self.updatedAt = updatedAt
        self.messages = messages
        self.agentId = agentId
        self.agentName = agentName
    }
}

/// 多会话状态管理器。内存只缓存当前可见页，正文由 SQLite 分页持久化。
@MainActor
public final class SessionManager: ObservableObject {
    public static let shared = SessionManager()

    @Published public private(set) var sessions: [String: [ChatMessage]] = [:]
    @Published public private(set) var activeSessionId: String? = nil
    @Published public private(set) var sessionTitles: [String: String] = [:]
    @Published public private(set) var sessionUpdatedAt: [String: Date] = [:]
    @Published public private(set) var sessionAgentIds: [String: String] = [:]
    @Published public private(set) var sessionAgentNames: [String: String] = [:]
    @Published public private(set) var sessionMessageCounts: [String: Int] = [:]
    @Published public private(set) var topicSessions: [String: TopicSessionMetadata] = [:]

    private var store: ChatHistoryStore
    private var accountFingerprint = "unconfigured"
    private var persistedFingerprints: [String: [String: Int]] = [:]
    /// All SQLite writes share one background tail so rapid SSE/UI updates stay ordered
    /// without blocking the MainActor before the network request starts.
    private var persistenceTail: Task<Void, Never>? = nil

    private init() {
        do { store = try ChatHistoryStore(databaseURL: Self.historyURL(fingerprint: accountFingerprint), performLegacyMigration: false) }
        catch { fatalError("Chat history database unavailable: \(error)") }
        loadMetadata()
    }

    public init(store: ChatHistoryStore) {
        self.store = store
        loadMetadata()
    }

    public func activateAccount(tenantKey: String, userId: String) {
        let fingerprint = "\(Self.namespace(tenantKey))-\(Self.namespace(userId))"
        guard fingerprint != accountFingerprint else { return }
        persistenceTail?.cancel()
        persistenceTail = nil
        guard let nextStore = try? ChatHistoryStore(
            databaseURL: Self.historyURL(fingerprint: fingerprint),
            performLegacyMigration: false
        ) else { return }
        store = nextStore
        accountFingerprint = fingerprint
        sessions.removeAll()
        sessionTitles.removeAll()
        sessionUpdatedAt.removeAll()
        sessionAgentIds.removeAll()
        sessionAgentNames.removeAll()
        sessionMessageCounts.removeAll()
        topicSessions.removeAll()
        persistedFingerprints.removeAll()
        activeSessionId = nil
        loadMetadata()
    }

    public func deactivateAccount() {
        persistenceTail?.cancel()
        persistenceTail = nil
        sessions.removeAll()
        sessionTitles.removeAll()
        sessionUpdatedAt.removeAll()
        sessionAgentIds.removeAll()
        sessionAgentNames.removeAll()
        sessionMessageCounts.removeAll()
        topicSessions.removeAll()
        persistedFingerprints.removeAll()
        activeSessionId = nil
        accountFingerprint = "unconfigured"
    }

    private static func namespace(_ value: String) -> String {
        SHA256.hash(data: Data(value.utf8)).prefix(10)
            .map { String(format: "%02x", $0) }.joined()
    }

    private static func historyURL(fingerprint: String) -> URL {
        let fm = FileManager.default
        let docs = fm.urls(for: .documentDirectory, in: .userDomainMask).first
            ?? fm.temporaryDirectory
        return docs.appendingPathComponent(
            "ChatHistory/accounts/\(fingerprint)/history.sqlite"
        )
    }

    private func loadMetadata() {
        guard let summaries = try? store.summaries() else { return }
        sessionTitles = Dictionary(uniqueKeysWithValues: summaries.map { ($0.id, $0.title) })
        sessionUpdatedAt = Dictionary(uniqueKeysWithValues: summaries.map { ($0.id, $0.updatedAt) })
        sessionAgentIds = Dictionary(uniqueKeysWithValues: summaries.map { ($0.id, $0.agentId) })
        sessionAgentNames = Dictionary(uniqueKeysWithValues: summaries.map { ($0.id, $0.agentName) })
        sessionMessageCounts = Dictionary(uniqueKeysWithValues: summaries.map { ($0.id, $0.messageCount) })
        topicSessions = Dictionary(uniqueKeysWithValues: summaries.compactMap { summary in
            summary.topic.map { ($0.sessionId, $0) }
        })
        activeSessionId = summaries.first?.id
    }

    // MARK: - 会话生命周期

    public func activeSessionID() -> String {
        if let active = activeSessionId, sessionTitles[active] != nil { return active }
        return createSession()
    }

    @discardableResult
    public func createSession(
        agentId: String = "main_agent", agentName: String = "Main 智能编排"
    ) -> String {
        let id = UUID().uuidString
        sessions[id] = []
        sessionTitles[id] = "新会话"
        sessionUpdatedAt[id] = Date()
        sessionAgentIds[id] = agentId
        sessionAgentNames[id] = agentName
        sessionMessageCounts[id] = 0
        activeSessionId = id
        try? store.createSession(id: id, agentId: agentId, agentName: agentName)
        return id
    }

    public static let maximumActiveTopics = 3

    @discardableResult
    public func startTopic(parentSessionId: String, sourceMessage: ChatMessage) -> TopicSessionMetadata {
        let previousSessionId = activeSessionId
        let activeCount = topicSessions.values.filter { $0.state == .active || $0.state == .ending }.count
        let id = createSession(agentId: agentId(for: parentSessionId), agentName: agentName(for: parentSessionId))
        let quote = sourceMessage.quoteContext
        let topic = TopicSessionMetadata(
            sessionId: id,
            parentSessionId: parentSessionId,
            sourceMessageId: sourceMessage.id,
            sourceText: quote.text,
            sourceBlockSummary: quote.blockSummary,
            state: activeCount < Self.maximumActiveTopics ? .active : .queued
        )
        topicSessions[id] = topic
        try? store.updateTopic(topic)
        // createSession owns the normal session lifecycle and temporarily selects it;
        // restore the caller so the coordinator performs the only visible switch.
        if let previousSessionId { activeSessionId = previousSessionId }
        return topic
    }

    public var visibleTopics: [TopicSessionMetadata] {
        topicSessions.values
            .filter { $0.state != .ended }
            .sorted { $0.createdAt < $1.createdAt }
    }

    public func markTopicEnding(_ sessionId: String) {
        guard var topic = topicSessions[sessionId], topic.state == .active else { return }
        topic.state = .ending
        topicSessions[sessionId] = topic
        try? store.updateTopic(topic)
    }

    public func finishTopic(_ sessionId: String) {
        guard var topic = topicSessions[sessionId] else { return }
        topic.state = .ended
        topicSessions[sessionId] = topic
        try? store.updateTopic(topic)
        promoteNextTopicIfNeeded()
    }

    private func promoteNextTopicIfNeeded() {
        let occupied = topicSessions.values.filter { $0.state == .active || $0.state == .ending }.count
        guard occupied < Self.maximumActiveTopics,
              var next = topicSessions.values.filter({ $0.state == .queued }).min(by: { $0.createdAt < $1.createdAt }) else { return }
        next.state = .active
        topicSessions[next.sessionId] = next
        try? store.updateTopic(next)
    }

    public func topicQuote(for sessionId: String) -> QuotedContext? {
        guard let topic = topicSessions[sessionId] else { return nil }
        return QuotedContext(text: topic.sourceText, blockSummary: topic.sourceBlockSummary)
    }

    public func switchTo(_ id: String) {
        if sessionTitles[id] == nil {
            try? store.createSession(id: id, agentId: "main_agent", agentName: "Main 智能编排")
            loadMetadata()
        }
        activeSessionId = id
    }

    public func deleteSession(_ id: String) {
        let removedTopicOccupied = topicSessions[id].map { $0.state == .active || $0.state == .ending } ?? false
        try? store.delete(id)
        sessions.removeValue(forKey: id)
        sessionTitles.removeValue(forKey: id)
        sessionUpdatedAt.removeValue(forKey: id)
        sessionAgentIds.removeValue(forKey: id)
        sessionAgentNames.removeValue(forKey: id)
        sessionMessageCounts.removeValue(forKey: id)
        topicSessions.removeValue(forKey: id)
        persistedFingerprints.removeValue(forKey: id)
        if activeSessionId == id {
            activeSessionId = latestSessionID()
            if activeSessionId == nil { _ = createSession() }
        }
        if removedTopicOccupied { promoteNextTopicIfNeeded() }
    }

    /// 按 updatedAt 倒序的会话 id 列表（供抽屉排序）。
    public func sortedSessionIDs() -> [String] {
        sessionUpdatedAt.keys.sorted {
            (sessionUpdatedAt[$0] ?? .distantPast) > (sessionUpdatedAt[$1] ?? .distantPast)
        }
    }

    private func latestSessionID() -> String? {
        sessionUpdatedAt.keys.max { (sessionUpdatedAt[$0] ?? .distantPast) < (sessionUpdatedAt[$1] ?? .distantPast) }
    }

    public func messages(for id: String) -> [ChatMessage] {
        if let cached = sessions[id] { return cached }
        return latestPage(for: id).messages
    }

    public var activeMessages: [ChatMessage] {
        guard let id = activeSessionId else { return [] }
        return messages(for: id)
    }

    public func title(for id: String) -> String {
        sessionTitles[id] ?? "新会话"
    }

    public func agentId(for id: String) -> String {
        sessionAgentIds[id] ?? "main_agent"
    }

    public func agentName(for id: String) -> String {
        sessionAgentNames[id] ?? "Main 智能编排"
    }

    public func messageCount(for id: String) -> Int { sessionMessageCounts[id] ?? 0 }

    public func latestPage(for id: String) -> StoredMessagePage {
        let page = (try? store.latest(sessionId: id)) ?? StoredMessagePage(messages: [], hasOlder: false, hasNewer: false)
        cacheVisibleMessages(page.messages, for: id)
        return page
    }

    public func pageBefore(_ messageId: String, sessionId: String) -> StoredMessagePage {
        let page = (try? store.before(sessionId: sessionId, messageId: messageId)) ?? latestPage(for: sessionId)
        cacheVisibleMessages(page.messages, for: sessionId)
        return page
    }

    public func pageAfter(_ messageId: String, sessionId: String) -> StoredMessagePage {
        let page = (try? store.after(sessionId: sessionId, messageId: messageId)) ?? latestPage(for: sessionId)
        cacheVisibleMessages(page.messages, for: sessionId)
        return page
    }

    public func clientSessionContext(for sessionId: String) -> ClientSessionContextDTO {
        let result = (try? store.contextMessages(sessionId: sessionId)) ?? ([], false)
        var byId = Dictionary(uniqueKeysWithValues: result.0.map { ($0.id, $0) })
        for message in sessions[sessionId] ?? [] { byId[message.id] = message }
        var source = byId.values.sorted { $0.createdAt < $1.createdAt }
        var truncated = result.1
        if source.count > 200 {
            source = Array(source.suffix(200))
            truncated = true
        }
        var characters = 0
        var bounded: [ChatMessage] = []
        for message in source.reversed() {
            if !bounded.isEmpty && characters + message.content.count > 120_000 {
                truncated = true
                break
            }
            bounded.append(message)
            characters += message.content.count
        }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let messages = bounded.reversed().compactMap { message -> ClientSessionMessageDTO? in
            guard !message.pending, !message.degraded, !message.isDemoSample,
                  !message.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  message.role == .user || message.role == .assistant else { return nil }
            return ClientSessionMessageDTO(
                id: message.id,
                role: message.role == .user ? "user" : "assistant",
                content: String(message.content.prefix(12_000)),
                createdAt: formatter.string(from: message.createdAt)
            )
        }
        return ClientSessionContextDTO(
            sessionId: sessionId,
            messages: Array(messages),
            truncated: truncated
        )
    }

    public func setMessages(_ messages: [ChatMessage], for id: String) {
        sessions[id] = messages
        let known = persistedFingerprints[id] ?? [:]
        let dirty = messages.filter { known[$0.id] != fingerprint($0) }
        guard !dirty.isEmpty else { return }

        let fingerprints = Dictionary(
            uniqueKeysWithValues: dirty.map { ($0.id, fingerprint($0)) }
        )
        let previous = persistenceTail
        let store = self.store
        persistenceTail = Task.detached(priority: .utility) { [weak self] in
            await previous?.value
            guard !Task.isCancelled else { return }
            guard let count = try? store.upsert(dirty, sessionId: id) else { return }
            let summary = try? store.summary(sessionId: id)
            await self?.finishPersistence(
                sessionId: id,
                fingerprints: fingerprints,
                messageCount: count,
                summary: summary
            )
        }
    }

    private func finishPersistence(
        sessionId: String,
        fingerprints: [String: Int],
        messageCount: Int,
        summary: StoredSessionSummary?
    ) {
        var known = persistedFingerprints[sessionId] ?? [:]
        for (messageId, storedFingerprint) in fingerprints {
            guard let current = sessions[sessionId]?.first(where: { $0.id == messageId }),
                  fingerprint(current) == storedFingerprint else { continue }
            known[messageId] = storedFingerprint
        }
        persistedFingerprints[sessionId] = known
        sessionMessageCounts[sessionId] = messageCount
        guard let summary else { return }
        sessionTitles[sessionId] = summary.title
        sessionUpdatedAt[sessionId] = summary.updatedAt
        sessionAgentIds[sessionId] = summary.agentId
        sessionAgentNames[sessionId] = summary.agentName
    }

    /// Test/lifecycle barrier for callers that need durable completion explicitly.
    public func flushPendingPersistence() async {
        await persistenceTail?.value
    }

    public func previousUserMessage(before messageId: String, sessionId: String) -> ChatMessage? {
        try? store.previousUser(sessionId: sessionId, before: messageId)
    }

    public func truncateMessages(from messageId: String, sessionId: String) {
        try? store.truncate(sessionId: sessionId, from: messageId)
        sessionMessageCounts[sessionId] = (try? store.count(sessionId)) ?? 0
        persistedFingerprints[sessionId]?.removeAll()
    }

    public func clearSession(_ id: String) {
        try? store.clear(id)
        sessions[id] = []
        persistedFingerprints[id] = [:]
        refreshMetadata(for: id)
    }

    /// 会话屏障：在途请求被切换拦截时，在原会话把 pending 占位替换为 .interrupted（不静默丢弃）。
    public func markInterrupted(sessionId: String) {
        var msgs = latestPage(for: sessionId).messages
        if let idx = msgs.lastIndex(where: { $0.role == .assistant && $0.pending }) {
            msgs[idx].role = .interrupted
            msgs[idx].content = Self.interruptedText
            msgs[idx].pending = false
            msgs[idx].isStreaming = false
            msgs[idx].degraded = false
        } else {
            msgs.append(ChatMessage(sessionId: sessionId, role: .interrupted, content: Self.interruptedText))
        }
        setMessages(msgs, for: sessionId)
    }

    public static let interruptedText = "⚠️ 响应已中断（会话切换）"

    // MARK: - Hermes 式后台完成：切换会话不中断在途任务，结果落盘到归属会话

    /// 把归属会话中 requestId 对应的 pending 占位替换为真实响应（切走后由 handleSuccess 调用）。
    public func applyResponse(sessionId: String, requestId: String, response: ChatResponseDTO) {
        let message = (try? store.message(sessionId: sessionId, id: requestId)).map { existing in
            var updated = existing
            updated.content = response.answer; updated.pending = false; updated.isStreaming = false
            updated.degraded = response.degraded == true; updated.executingAgentId = response.resolvedAgent?.id
            updated.executingAgentName = response.resolvedAgent?.name; updated.delegatedBy = response.delegatedBy
            updated.blocks = []
            return updated
        } ?? ChatMessage(
                sessionId: sessionId, role: .assistant,
                content: response.answer, pending: false,
                degraded: response.degraded == true,
                executingAgentId: response.resolvedAgent?.id,
                executingAgentName: response.resolvedAgent?.name,
                delegatedBy: response.delegatedBy
            )
        updateStoredMessage(message, sessionId: sessionId)
    }

    /// 断点续接已完成（status=completed）时，把结果写归属会话（切走后由 applyCompletedStatus 调用）。
    public func applyCompletedStatus(sessionId: String, requestId: String, answer: String) {
        let message = (try? store.message(sessionId: sessionId, id: requestId)).map { existing in
            var updated = existing; updated.content = answer; updated.pending = false
            updated.isStreaming = false; updated.degraded = false; return updated
        } ?? ChatMessage(sessionId: sessionId, role: .assistant, content: answer, pending: false)
        updateStoredMessage(message, sessionId: sessionId)
    }

    /// 切走后任务失败：把 degraded 卡写归属会话（不中断、不静默）。
    public func applyDegraded(sessionId: String, requestId: String, text: String) {
        let message = (try? store.message(sessionId: sessionId, id: requestId)).map { existing in
            var updated = existing; updated.content = text; updated.pending = false
            updated.isStreaming = false; updated.degraded = true; return updated
        } ?? ChatMessage(sessionId: sessionId, role: .assistant, content: text, pending: false, degraded: true)
        updateStoredMessage(message, sessionId: sessionId)
    }

    private func updateStoredMessage(_ message: ChatMessage, sessionId: String) {
        guard (try? store.upsert([message], sessionId: sessionId)) != nil else { return }
        persistedFingerprints[sessionId, default: [:]][message.id] = fingerprint(message)
        if var cached = sessions[sessionId], let index = cached.firstIndex(where: { $0.id == message.id }) {
            cached[index] = message; sessions[sessionId] = cached
        }
        refreshMetadata(for: sessionId)
    }

    private func refreshMetadata(for id: String) {
        guard let summary = try? store.summaries().first(where: { $0.id == id }) else { return }
        sessionTitles[id] = summary.title; sessionUpdatedAt[id] = summary.updatedAt
        sessionAgentIds[id] = summary.agentId; sessionAgentNames[id] = summary.agentName
        sessionMessageCounts[id] = summary.messageCount
    }

    public func cacheVisibleMessages(_ messages: [ChatMessage], for id: String) {
        sessions[id] = messages
        var known = persistedFingerprints[id] ?? [:]
        for message in messages { known[message.id] = fingerprint(message) }
        persistedFingerprints[id] = known
    }

    public func storedMessage(id: String, sessionId: String) -> ChatMessage? {
        try? store.message(sessionId: sessionId, id: id)
    }

    public func updateMessage(_ message: ChatMessage, sessionId: String) {
        updateStoredMessage(message, sessionId: sessionId)
    }

    public func reloadMetadata() {
        let active = activeSessionId
        loadMetadata()
        if let active, sessionTitles[active] != nil {
            activeSessionId = active
        }
    }

    private func fingerprint(_ message: ChatMessage) -> Int {
        var hasher = Hasher()
        hasher.combine(message.role.rawValue); hasher.combine(message.content); hasher.combine(message.createdAt)
        hasher.combine(message.pending); hasher.combine(message.degraded); hasher.combine(message.isDemoSample)
        hasher.combine(message.reasoningDuration); hasher.combine(message.executingAgentId)
        hasher.combine(message.executingAgentName); hasher.combine(message.delegatedBy)
        hasher.combine(message.blocks); hasher.combine(message.quotedContext)
        return hasher.finalize()
    }
}

// MARK: - Topology Graph Models
public enum AgentNodeStatus: String, Codable, Sendable {
    case idle = "idle"
    case running = "running"
    case completed = "completed"
    case error = "error"
    
    public init(fromRaw statusStr: String) {
        switch statusStr.lowercased() {
        case "running", "运行中", "执行中": self = .running
        case "completed", "完成": self = .completed
        case "error", "异常", "失败": self = .error
        default: self = .idle
        }
    }
    
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
        case .idle: return "就绪"
        case .running: return "执行中"
        case .completed: return "完成"
        case .error: return "异常"
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
    public var tools: [String]
    
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
        outputDeps: [String] = [],
        tools: [String] = []
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
        self.tools = tools
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

// MARK: - 后端拓扑 DTO → 前端图模型映射（注册表为唯一真值来源）

public extension TopologyGraphDTO {
    /// 将后端基线 Agent 注册表映射为前端拓扑图（依赖从边推导，节点位置按简单树状布局派生）。
    func toTopologyGraph() -> TopologyGraph {
        var inputDeps: [String: [String]] = [:]
        var outputDeps: [String: [String]] = [:]
        for e in edges {
            inputDeps[e.target, default: []].append(e.source)
            outputDeps[e.source, default: []].append(e.target)
        }
        let nameById = Dictionary(uniqueKeysWithValues: self.nodes.map { ($0.id, $0.name) })

        let nodes: [AgentNode] = self.nodes.enumerated().map { idx, n in
            AgentNode(
                id: n.id,
                name: n.name,
                roleCategory: n.roleDesc,
                systemPromptSummary: n.roleDesc,
                status: AgentNodeStatus(fromRaw: n.status),
                position: TopologyGraphDTO.layoutPosition(index: idx, total: self.nodes.count),
                subscribedKnowledge: [],
                inputDeps: (inputDeps[n.id] ?? []).compactMap { nameById[$0] },
                outputDeps: (outputDeps[n.id] ?? []).compactMap { nameById[$0] },
                tools: n.tools
            )
        }

        let agentEdges: [AgentEdge] = edges.map {
            AgentEdge(sourceNodeId: $0.source, targetNodeId: $0.target, label: $0.label)
        }
        return TopologyGraph(nodes: nodes, edges: agentEdges)
    }

    /// 简单布局：首节点（根/main）置左，其余节点右侧纵向均布。
    static func layoutPosition(index: Int, total: Int) -> CGPoint {
        if index == 0 {
            return CGPoint(x: 30, y: 140)
        }
        let children = max(total - 1, 1)
        let childIdx = CGFloat(index - 1)
        let step: CGFloat = 100
        let startY = 140 - (CGFloat(children) - 1) * step / 2
        return CGPoint(x: 210, y: startY + childIdx * step)
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
// MARK: - Global App State

public extension Notification.Name {
    /// 租户 Agent 切片列表变更广播：对话式创建成功 / 删除后触发拓扑页静默刷新。
    static let tenantAgentsDidUpdate = Notification.Name("tenantAgentsDidUpdate")
    /// 服务端租户知识权益/策略版本变化，要求刷新权限并重新建立会话。
    static let knowledgeAccessDidChange = Notification.Name("knowledgeAccessDidChange")
    static let localAccountDidChange = Notification.Name("localAccountDidChange")
}

public struct ChatAgentSelection: Identifiable, Equatable, Sendable {
    public let id: UUID
    public let agentId: String
    public let agentName: String
    public let prompt: String?

    public init(agentId: String, agentName: String, prompt: String? = nil) {
        self.id = UUID()
        self.agentId = agentId
        self.agentName = agentName
        self.prompt = prompt
    }
}

@MainActor
public final class AppState: ObservableObject {
    @Published public var isLoggedIn: Bool = false
    @Published public var isGuestMode: Bool = false
    @Published public var currentProfile: TenantProfile
    @Published public var currentTenantKey: String = "demo" {
        didSet {
            activateLocalAccount()
        }
    }
    @Published public var currentUserId: String = "demo-user" {
        didSet {
            activateLocalAccount()
        }
    }
    @Published public var activeTab: Int = 0
    @Published public var selectedAgentId: String = "main_agent"
    @Published public var selectedAgentName: String = "Main 智能编排"
    @Published public var pendingChatAgent: ChatAgentSelection? = nil
    @Published public var pendingChatPrompt: String? = nil
    @Published public var pendingChatContextScope: ChatContextScopeDTO? = nil
    @Published public var pendingWorkflowId: String? = nil
    @Published public var pendingKnowledgeNavigation: KnowledgeNavigationTarget? = nil
    @Published public var pendingTopicSessionId: String? = nil
    /// 内存会话级 session_id（不持久化磁盘；404/401 清重发；账号切换清空）
    @Published public var chatSessionId: String? = nil
    /// 开发态（后端 dev 载荷 / 连接失败）→ 顶部导航栏下「开发模式·免鉴权」蓝 banner
    @Published public var isDevMode: Bool = false
    
    public init(
        isLoggedIn: Bool = true,
        isGuestMode: Bool = false,
        currentProfile: TenantProfile = MockData.tenantProfile,
        activeTab: Int = 0
    ) {
        self.isLoggedIn = isLoggedIn
        self.isGuestMode = isGuestMode
        self.currentProfile = currentProfile
        self.currentTenantKey = currentProfile.tenantId
        self.activeTab = activeTab
        activateLocalAccount(notify: false)
    }

    private func activateLocalAccount(notify: Bool = true) {
        pendingKnowledgeNavigation = nil
        KnowledgeNoteStore.shared.activate(
            tenantKey: currentTenantKey, userId: currentUserId
        )
        SessionManager.shared.activateAccount(
            tenantKey: currentTenantKey, userId: currentUserId
        )
        if notify {
            NotificationCenter.default.post(name: .localAccountDidChange, object: nil)
        }
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
        self.currentTenantKey = "guest_tenant"
        self.currentUserId = "guest"
        KnowledgeNoteStore.shared.activate(tenantKey: "guest_tenant", userId: "guest")
    }
    
    public func logout() {
        self.isLoggedIn = false
        self.isGuestMode = false
        self.chatSessionId = nil
        self.pendingChatContextScope = nil
        self.pendingKnowledgeNavigation = nil
        self.isDevMode = false
        KnowledgeNoteStore.shared.deactivate()
        SessionManager.shared.deactivateAccount()
        NotificationCenter.default.post(name: .localAccountDidChange, object: nil)
    }
    
    public func navigateToChatWithPrompt(_ prompt: String, contextScope: ChatContextScopeDTO? = nil) {
        self.pendingChatPrompt = prompt
        self.pendingChatContextScope = contextScope
        self.activeTab = 0 // Switch to Chat tab
    }

    public func openChat(agentId: String, agentName: String, prompt: String? = nil) {
        selectedAgentId = agentId
        selectedAgentName = agentName
        pendingChatAgent = ChatAgentSelection(
            agentId: agentId, agentName: agentName, prompt: prompt
        )
        activeTab = 0
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
}
