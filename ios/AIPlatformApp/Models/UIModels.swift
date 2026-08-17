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

/// 澄清卡片数据块（单选/多选 + 自定义输入 + 已提交态）
public struct ClarifyBlock: Identifiable, Sendable, Hashable {
    public let id: String
    /// 后端澄清 ID（bridge clarify 事件携带）：提交时透传，精确解锁阻塞的 agent 线程（P0 修复）
    public var clarifyId: String?
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
        reasoningDuration: Int? = nil
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

    public init(_ m: ChatMessage) {
        self.id = m.id
        self.role = m.role.rawValue
        self.content = m.content
        self.createdAt = m.createdAt
        self.pending = m.pending
        self.degraded = m.degraded
        self.isDemoSample = m.isDemoSample
        self.reasoningDuration = m.reasoningDuration
    }

    public func toChatMessage(sessionId: String) -> ChatMessage {
        ChatMessage(
            id: id,
            sessionId: sessionId,
            role: MessageRole(rawValue: role) ?? .assistant,
            content: content,
            createdAt: createdAt,
            isDemoSample: isDemoSample,
            pending: pending,
            degraded: degraded,
            reasoningDuration: reasoningDuration
        )
    }
}

/// 单个会话的落盘记录（标题 + 更新时间 + 消息数组）。
public struct SessionRecord: Codable, Sendable {
    public let id: String
    public var title: String
    public var updatedAt: Date
    public var messages: [PersistedMessage]

    public init(id: String, title: String, updatedAt: Date, messages: [PersistedMessage]) {
        self.id = id
        self.title = title
        self.updatedAt = updatedAt
        self.messages = messages
    }
}

/// 多会话状态管理器（@MainActor 严格串行，iPhone 单窗口）。
/// - 内存 `sessions: [String: [ChatMessage]]` 字典隔离
/// - 消息级原子落盘：Documents/Sessions/<id>.json（tmp + rename，杜绝断电损坏）
/// - pending 标记：响应前 true / 完成后 false；冷启动恢复 updatedAt 最新会话为 active
@MainActor
public final class SessionManager: ObservableObject {
    public static let shared = SessionManager()

    @Published public private(set) var sessions: [String: [ChatMessage]] = [:]
    @Published public private(set) var activeSessionId: String? = nil
    @Published public private(set) var sessionTitles: [String: String] = [:]
    @Published public private(set) var sessionUpdatedAt: [String: Date] = [:]

    private let fm = FileManager.default

    /// Documents/Sessions/<id>.json
    private var directory: URL {
        let docs = fm.urls(for: .documentDirectory, in: .userDomainMask).first
            ?? fm.temporaryDirectory
        return docs.appendingPathComponent("Sessions", isDirectory: true)
    }

    private static let encoder: JSONEncoder = {
        let e = JSONEncoder()
        e.dateEncodingStrategy = .iso8601
        e.outputFormatting = [.sortedKeys]
        return e
    }()

    private static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .iso8601
        return d
    }()

    private init() {
        loadAll()
    }

    // MARK: - 冷启动恢复

    private func loadAll() {
        try? fm.createDirectory(at: directory, withIntermediateDirectories: true)
        guard let files = try? fm.contentsOfDirectory(
            at: directory,
            includingPropertiesForKeys: [.contentModificationDateKey],
            options: [.skipsHiddenFiles]
        ) else { return }

        var loaded: [String: [ChatMessage]] = [:]
        var titles: [String: String] = [:]
        var updated: [String: Date] = [:]
        var latestId: String? = nil
        var latestDate: Date = .distantPast

        for url in files where url.pathExtension == "json" {
            guard let data = try? Data(contentsOf: url),
                  let rec = try? Self.decoder.decode(SessionRecord.self, from: data) else { continue }
            let msgs = rec.messages.map { $0.toChatMessage(sessionId: rec.id) }
            loaded[rec.id] = msgs
            titles[rec.id] = rec.title
            updated[rec.id] = rec.updatedAt
            if rec.updatedAt > latestDate {
                latestDate = rec.updatedAt
                latestId = rec.id
            }
        }

        sessions = loaded
        sessionTitles = titles
        sessionUpdatedAt = updated
        // 恢复 updatedAt 最新的会话为 activeSessionId
        activeSessionId = latestId
    }

    // MARK: - 会话生命周期

    public func activeSessionID() -> String {
        if let active = activeSessionId, sessions[active] != nil { return active }
        return createSession()
    }

    @discardableResult
    public func createSession() -> String {
        let id = UUID().uuidString
        sessions[id] = []
        sessionTitles[id] = "新会话"
        sessionUpdatedAt[id] = Date()
        activeSessionId = id
        persist(id: id)
        return id
    }

    public func switchTo(_ id: String) {
        if sessions[id] == nil { sessions[id] = [] }
        activeSessionId = id
    }

    /// 删除会话：本地级联清理（内存 + 磁盘文件）。
    public func deleteSession(_ id: String) {
        sessions.removeValue(forKey: id)
        sessionTitles.removeValue(forKey: id)
        sessionUpdatedAt.removeValue(forKey: id)
        try? fm.removeItem(at: fileURL(id))
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
        sessions.keys.max { (sessionUpdatedAt[$0] ?? .distantPast) < (sessionUpdatedAt[$1] ?? .distantPast) }
    }

    // MARK: - 消息读写（消息级原子落盘）

    public func messages(for id: String) -> [ChatMessage] {
        sessions[id] ?? []
    }

    public var activeMessages: [ChatMessage] {
        guard let id = activeSessionId else { return [] }
        return sessions[id] ?? []
    }

    public func title(for id: String) -> String {
        sessionTitles[id] ?? "新会话"
    }

    /// 整会话写入（消息级事件触发单次落盘，非 chunk 级）。标题按首条 user 前 20 字规则刷新。
    public func setMessages(_ messages: [ChatMessage], for id: String) {
        sessions[id] = messages
        refreshTitle(for: id, messages: messages)
        sessionUpdatedAt[id] = Date()
        persist(id: id)
    }

    /// 组装 API 上下文：强制过滤 .interrupted / .system / degraded，仅保留纯净 user/assistant 问答对。
    public func apiContextMessages(for id: String) -> [ChatMessage] {
        (sessions[id] ?? []).filter {
            ($0.role == .user || $0.role == .assistant) && !$0.degraded
        }
    }

    /// 会话屏障：在途请求被切换拦截时，在原会话把 pending 占位替换为 .interrupted（不静默丢弃）。
    public func markInterrupted(sessionId: String) {
        guard var msgs = sessions[sessionId], !msgs.isEmpty else { return }
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
        guard var msgs = sessions[sessionId] else { return }
        if let idx = msgs.firstIndex(where: { $0.id == requestId }) {
            msgs[idx].content = response.answer
            msgs[idx].pending = false
            msgs[idx].isStreaming = false
            msgs[idx].degraded = response.degraded == true
            // 后台完成不渲染逐步推理动画；用户切回时看到折叠推理卡/全文
            msgs[idx].blocks = []
        } else {
            msgs.append(ChatMessage(
                sessionId: sessionId, role: .assistant,
                content: response.answer, pending: false,
                degraded: response.degraded == true
            ))
        }
        setMessages(msgs, for: sessionId)
    }

    /// 断点续接已完成（status=completed）时，把结果写归属会话（切走后由 applyCompletedStatus 调用）。
    public func applyCompletedStatus(sessionId: String, requestId: String, answer: String) {
        guard var msgs = sessions[sessionId] else { return }
        if let idx = msgs.firstIndex(where: { $0.id == requestId }) {
            msgs[idx].content = answer
            msgs[idx].pending = false
            msgs[idx].isStreaming = false
            msgs[idx].degraded = false
        } else {
            msgs.append(ChatMessage(
                sessionId: sessionId, role: .assistant,
                content: answer, pending: false
            ))
        }
        setMessages(msgs, for: sessionId)
    }

    /// 切走后任务失败：把 degraded 卡写归属会话（不中断、不静默）。
    public func applyDegraded(sessionId: String, requestId: String, text: String) {
        guard var msgs = sessions[sessionId] else { return }
        if let idx = msgs.firstIndex(where: { $0.id == requestId }) {
            msgs[idx].content = text
            msgs[idx].pending = false
            msgs[idx].isStreaming = false
            msgs[idx].degraded = true
        } else {
            msgs.append(ChatMessage(
                sessionId: sessionId, role: .assistant,
                content: text, pending: false, degraded: true
            ))
        }
        setMessages(msgs, for: sessionId)
    }

    private func refreshTitle(for id: String, messages: [ChatMessage]) {
        guard let firstUser = messages.first(where: { $0.role == .user }) else {
            sessionTitles[id] = "新会话"
            return
        }
        let text = firstUser.content.trimmingCharacters(in: .whitespacesAndNewlines)
        sessionTitles[id] = text.isEmpty ? "新会话" : String(text.prefix(20))
    }

    // MARK: - 原子落盘（tmp + rename）

    private func fileURL(_ id: String) -> URL {
        directory.appendingPathComponent("\(id).json")
    }

    private func persist(id: String) {
        try? fm.createDirectory(at: directory, withIntermediateDirectories: true)
        guard let msgs = sessions[id] else { return }
        let rec = SessionRecord(
            id: id,
            title: sessionTitles[id] ?? "新会话",
            updatedAt: sessionUpdatedAt[id] ?? Date(),
            messages: msgs.map(PersistedMessage.init)
        )
        guard let data = try? Self.encoder.encode(rec) else { return }
        let url = fileURL(id)
        let tmp = directory.appendingPathComponent("\(id).json.tmp")
        try? data.write(to: tmp, options: .atomic)
        if fm.fileExists(atPath: url.path) {
            _ = try? fm.replaceItemAt(url, withItemAt: tmp)
        } else {
            try? fm.moveItem(at: tmp, to: url)
        }
    }
}

// MARK: - Topology Graph Models
public enum AgentNodeStatus: String, Codable, Sendable {
    case idle = "idle"
    case running = "running"
    case completed = "completed"
    case error = "error"
    case demo = "演示"
    
    public var indicatorColor: Color {
        switch self {
        case .idle: return AppTheme.Colors.statusIdle
        case .running: return AppTheme.Colors.statusRunning
        case .completed: return AppTheme.Colors.statusCompleted
        case .error: return AppTheme.Colors.statusError
        case .demo: return AppTheme.Colors.quantumCyan
        }
    }
    
    public var labelText: String {
        switch self {
        case .idle: return "就绪 (Idle)"
        case .running: return "执行中 (Running)"
        case .completed: return "完成 (Completed)"
        case .error: return "异常 (Error)"
        case .demo: return "演示 (Demo)"
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
                status: AgentNodeStatus(rawValue: n.status) ?? .demo,
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

public extension Notification.Name {
    /// 租户 Agent 切片列表变更广播：对话式创建成功 / 删除后触发拓扑页静默刷新。
    static let tenantAgentsDidUpdate = Notification.Name("tenantAgentsDidUpdate")
}

@MainActor
public final class AppState: ObservableObject {
    @Published public var isLoggedIn: Bool = false
    @Published public var isGuestMode: Bool = false
    @Published public var currentProfile: TenantProfile
    @Published public var activeTab: Int = 0
    @Published public var selectedAgentId: String = "main_agent"
    @Published public var pendingChatPrompt: String? = nil
    /// 内存会话级 session_id（不持久化磁盘；404/401 清重发；账号切换清空）
    @Published public var chatSessionId: String? = nil
    /// 开发态（后端 dev 载荷 / 连接失败）→ 顶部导航栏下「开发模式·免鉴权」蓝 banner
    @Published public var isDevMode: Bool = false
    
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
        self.chatSessionId = nil
        self.isDevMode = false
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
