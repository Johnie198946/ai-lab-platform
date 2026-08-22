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
        submittedSelection: String = ""
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
public enum MessageBlock: Identifiable, Sendable, Hashable {
    case code(CodeSnippet)
    case formula(String)
    case chart(ChartBlock)
    case image(ImageBlock)
    case table(TableBlock)
    case attachment(AttachmentBlock)
    case reasoning([ReasoningStep])
    case clarify(ClarifyBlock)

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
    }

    public func toClarifyBlock(defaultSessionId: String) -> ClarifyBlock {
        ClarifyBlock(
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
            submittedSelection: submittedSelection
        )
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

    private let store: ChatHistoryStore
    private var persistedFingerprints: [String: [String: Int]] = [:]
    /// All SQLite writes share one background tail so rapid SSE/UI updates stay ordered
    /// without blocking the MainActor before the network request starts.
    private var persistenceTail: Task<Void, Never>? = nil

    private init() {
        do { store = try ChatHistoryStore(performLegacyMigration: false) }
        catch { fatalError("Chat history database unavailable: \(error)") }
        loadMetadata()
        Task.detached(priority: .utility) { [weak self] in
            // A separate WAL connection avoids sharing a transaction with foreground page writes.
            _ = try? ChatHistoryStore()
            await self?.reloadMetadata()
        }
    }

    public init(store: ChatHistoryStore) {
        self.store = store
        loadMetadata()
    }

    private func loadMetadata() {
        guard let summaries = try? store.summaries() else { return }
        sessionTitles = Dictionary(uniqueKeysWithValues: summaries.map { ($0.id, $0.title) })
        sessionUpdatedAt = Dictionary(uniqueKeysWithValues: summaries.map { ($0.id, $0.updatedAt) })
        sessionAgentIds = Dictionary(uniqueKeysWithValues: summaries.map { ($0.id, $0.agentId) })
        sessionAgentNames = Dictionary(uniqueKeysWithValues: summaries.map { ($0.id, $0.agentName) })
        sessionMessageCounts = Dictionary(uniqueKeysWithValues: summaries.map { ($0.id, $0.messageCount) })
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

    public func switchTo(_ id: String) {
        if sessionTitles[id] == nil {
            try? store.createSession(id: id, agentId: "main_agent", agentName: "Main 智能编排")
            loadMetadata()
        }
        activeSessionId = id
    }

    public func deleteSession(_ id: String) {
        try? store.delete(id)
        sessions.removeValue(forKey: id)
        sessionTitles.removeValue(forKey: id)
        sessionUpdatedAt.removeValue(forKey: id)
        sessionAgentIds.removeValue(forKey: id)
        sessionAgentNames.removeValue(forKey: id)
        sessionMessageCounts.removeValue(forKey: id)
        persistedFingerprints.removeValue(forKey: id)
        if activeSessionId == id {
            activeSessionId = latestSessionID()
            if activeSessionId == nil { _ = createSession() }
        }
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
    @Published public var activeTab: Int = 0
    @Published public var selectedAgentId: String = "main_agent"
    @Published public var selectedAgentName: String = "Main 智能编排"
    @Published public var pendingChatAgent: ChatAgentSelection? = nil
    @Published public var pendingChatPrompt: String? = nil
    @Published public var pendingWorkflowId: String? = nil
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
        self.activeTab = activeTab
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
        self.chatSessionId = nil
        self.isDevMode = false
    }
    
    public func navigateToChatWithPrompt(_ prompt: String) {
        self.pendingChatPrompt = prompt
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
