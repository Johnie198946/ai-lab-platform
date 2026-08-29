//
//  APIClient.swift
//  AIPlatformApp
//
//  轻量网络层：URLSession + JWT Keychain + 401 重登 + 请求取消 + 离线降级标注。
//  双轨策略：联网调用真实后端 API，失败/离线自动切回本地 Mock 并在 UI 标注「演示数据」。
//

import Foundation
import Combine

// MARK: - 后端 API DTO（snake_case → camelCase 自动转换）

/// GET /api/v1/catalog 返回的分类目录项
public struct CatalogCategory: Codable, Identifiable, Hashable {
    public let category: String
    public let pathPrefix: String
    public let title: String
    public let docCount: Int
    public let open: Bool
    public var securityLevel: String? = nil
    public var ownerTenant: String? = nil
    public var entitlementKey: String? = nil
    public var accessState: String? = nil
    public var subscriptionState: String? = nil
    public var inWallet: Bool? = nil
    public var knowledgeLevel: String? = nil
    public var classificationStatus: String? = nil
    public var freshness: String? = nil
    public var sourceCount: Int? = nil

    public var id: String { category }
}

/// GET /api/v1/catalog 响应
public struct CatalogResponse: Codable {
    public let catalog: [CatalogCategory]
    public var policyVersion: String? = nil
    public var pendingReviewCount: Int? = nil
}

/// GET/PATCH /api/v1/me 返回的用户 Profile
public struct ProfileDTO: Codable {
    public let userId: String
    public let username: String
    public let avatarUrl: String?
    public let isSuperAdmin: Bool
    public let tenantKey: String
    public let subscriptions: [String]
    public let visibleDocs: Int
    public let chatCalls: Int
    public let tokenUsed: Int
    public let hasSessions: Bool
}

/// GET /api/v1/me/subscriptions 及订阅/退订返回
public struct SubscriptionsResponse: Codable {
    public let tenantKey: String
    public let categories: [String]
}

public struct KnowledgeAccessResponse: Codable {
    public let tenantKey: String
    public let organizationId: String
    public let planId: String
    public let planStatus: String
    public let policyVersion: String
    public let wallet: [String]
    public let yellowEntitlements: [String]
    public var activePackGrants: [KnowledgePackGrantDTO]? = nil
    public var packAllowance: Int? = nil
    public let effectiveCategories: [String]
    public let entitlementStale: Bool
}

public struct SubscriptionPlanFeaturesDTO: Codable, Hashable {
    public var knowledgeEntitlements: [String] = []
    public var applicationIds: [String] = []
    public var highlights: [String] = []

    private enum CodingKeys: String, CodingKey {
        case knowledgeEntitlements
        case applicationIds
        case highlights
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        knowledgeEntitlements = try container.decodeIfPresent([String].self, forKey: .knowledgeEntitlements) ?? []
        applicationIds = try container.decodeIfPresent([String].self, forKey: .applicationIds) ?? []
        highlights = try container.decodeIfPresent([String].self, forKey: .highlights) ?? []
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(knowledgeEntitlements, forKey: .knowledgeEntitlements)
        try container.encode(applicationIds, forKey: .applicationIds)
        try container.encode(highlights, forKey: .highlights)
    }
}

public struct SubscriptionPlanDTO: Codable, Identifiable, Hashable {
    public let id: String
    public let name: String
    public let description: String?
    public let durationDays: Int
    public let price: Double
    public let isActive: Bool
    public let requestQuota: Int
    public let tokenQuota: Int64
    public let quotaPeriodDays: Int
    public var features: SubscriptionPlanFeaturesDTO? = nil
    public var packAllowance: Int? = nil
    public var customOnly: Bool? = nil
    public var selectablePackIds: [String]? = nil
}

public struct KnowledgePackDTO: Codable, Identifiable, Hashable {
    public let id: String
    public let entitlementKey: String
    public let name: String
    public let description: String
    public let status: String
    public let isSelectable: Bool
    public let sortOrder: Int
    public let minimumDocumentCount: Int
    public let approvedDocumentCount: Int
    public let freshnessPercent: Int
    public let riskLabel: String
}

public struct KnowledgePackGrantDTO: Codable, Identifiable, Hashable {
    public let id: String
    public let knowledgePackId: String
    public let entitlementKey: String
    public let name: String
    public let status: String
    public let effectiveFrom: String
    public let effectiveUntil: String
}

public struct OrganizationSubscriptionDTO: Codable, Hashable {
    public let id: String
    public let planId: String
    public let planName: String
    public let status: String
    public let startDate: String
    public let effectiveUntil: String?
    public let entitlementVersion: Int
    public let knowledgeEntitlements: [String]
    public var packAllowance: Int? = nil
    public var activePackGrants: [KnowledgePackGrantDTO]? = nil
}

public struct SubscriptionRequestDTO: Codable, Identifiable, Hashable {
    public let id: String
    public let requestId: String
    public let organizationId: String
    public let applicationId: String
    public let targetPlanId: String
    public let targetPlanName: String
    public let requestedBy: String
    public let requestedEntitlements: [String]
    public var requestedPackIds: [String]? = nil
    public var approvedPackIds: [String]? = nil
    public let reason: String
    public let status: String
    public let reviewedBy: String
    public let reviewNote: String
    public let reviewedAt: String?
    public let createdAt: String?
    public let updatedAt: String?
    public var webhookDelivered: Bool? = nil
}

public struct SubscriptionCenterResponse: Codable {
    public let organizationId: String
    public let applicationId: String
    public let subscription: OrganizationSubscriptionDTO?
    public let requests: [SubscriptionRequestDTO]
    public let plans: [SubscriptionPlanDTO]
    public let isSuperAdmin: Bool
    public let pendingCount: Int
    public var knowledgePacks: [KnowledgePackDTO]? = nil
    public var activePackGrants: [KnowledgePackGrantDTO]? = nil
    public var packAllowance: Int? = nil
    public var knowledgePackSubscriptionEnabled: Bool? = nil
}

public struct SubscriptionRequestsResponse: Codable {
    public let applicationId: String
    public let requests: [SubscriptionRequestDTO]
}

private struct SubscribeCategoryRequest: Encodable {
    let category: String
}

private struct SubscriptionRequestCreateDTO: Encodable {
    let requestId: String
    let planId: String
    let requestedEntitlements: [String]
    let requestedPackIds: [String]
    let reason: String

    enum CodingKeys: String, CodingKey {
        case reason
        case requestId = "request_id"
        case planId = "plan_id"
        case requestedEntitlements = "requested_entitlements"
        case requestedPackIds = "requested_pack_ids"
    }
}

private struct SubscriptionReviewDTO: Encodable {
    let reviewNote: String
    let approvedPackIds: [String]?

    enum CodingKeys: String, CodingKey {
        case reviewNote = "review_note"
        case approvedPackIds = "approved_pack_ids"
    }
}

/// GET /api/knowledge/search 单条结果
public struct SearchDoc: Codable, Identifiable, Hashable {
    public let path: String
    public let title: String
    public let score: Double
    public let snippet: String
    public var knowledgePack: String? = nil
    public var knowledgeLevel: String? = nil
    public var classificationStatus: String? = nil
    public var securityLevel: String? = nil
    public var freshness: String? = nil
    public var sourceCount: Int? = nil

    public var id: String { path }

    /// 该文档所属类目（首段路径前缀；行业知识取 knowledge/行业知识/<domain> 两段）
    public var category: String {
        if let knowledgePack, !knowledgePack.isEmpty {
            return knowledgePack
        }
        let parts = path.split(separator: "/", omittingEmptySubsequences: false)
        if parts.count >= 3 && parts[0] == "knowledge" && parts[1] == "行业知识" {
            return "knowledge/行业知识/\(parts[2])"
        }
        return String(parts.first ?? "")
    }

    enum CodingKeys: String, CodingKey {
        case path, title, score, snippet
        case knowledgePack = "category"
        case knowledgeLevel
        case classificationStatus
        case securityLevel
        case freshness
        case sourceCount
    }
}

/// GET /api/knowledge/search 响应
public struct SearchResponse: Codable {
    public let query: String
    public let total: Int
    public let docs: [SearchDoc]
    public let entityHits: [String]
}

/// PATCH /api/v1/me 请求体
public struct ProfileUpdateRequest: Encodable {
    public let username: String?
    public let avatarUrl: String?

    public init(username: String?, avatarUrl: String?) {
        self.username = username
        self.avatarUrl = avatarUrl
    }
}

/// POST /api/chat 请求体（snake_case 序列化对齐后端 ChatRequest）
public struct ChatRequestDTO: Encodable {
    public let question: String
    public let requestId: String?
    public let sessionId: String?
    public let quotedContext: String?
    public let agentId: String?
    public let regenerate: Bool

    public init(question: String, requestId: String? = nil, sessionId: String? = nil, quotedContext: String? = nil, agentId: String? = nil, regenerate: Bool = false) {
        self.question = question
        self.requestId = requestId
        self.sessionId = sessionId
        self.quotedContext = quotedContext
        self.agentId = agentId
        self.regenerate = regenerate
    }

    enum CodingKeys: String, CodingKey {
        case question
        case requestId = "request_id"
        case sessionId = "session_id"
        case quotedContext = "quoted_context"
        case agentId = "agent_id"
        case regenerate
    }
}

/// POST /api/chat 响应（snake_case → camelCase 自动转换）
public struct ChatResponseDTO: Codable {
    public let question: String
    public let answer: String
    public let sessionId: String?
    public let reasoning: [ChatReasoningStepDTO]?
    /// 502 降级标记：true 时前端跳过 ReasoningCard、不入正常历史、渲染降级卡
    public let degraded: Bool?
    /// 澄清卡片载荷：非空时前端渲染 ClarifyCard（对齐 Hermes clarify 协议）
    public let clarify: ChatClarifyDTO?

    public init(question: String, answer: String, sessionId: String?, reasoning: [ChatReasoningStepDTO], degraded: Bool? = nil, clarify: ChatClarifyDTO? = nil) {
        self.question = question
        self.answer = answer
        self.sessionId = sessionId
        self.reasoning = reasoning
        self.degraded = degraded
        self.clarify = clarify
    }
}

/// 后端澄清卡片载荷（对应 backend ClarifyPayload：question / choices / multi_select）
public struct ChatClarifyDTO: Codable {
    public let question: String
    public let choices: [String]
    public let multiSelect: Bool

    enum CodingKeys: String, CodingKey {
        case question
        case choices
        case multiSelect = "multi_select"
    }
}

/// 单条真实推理步骤（对应后端 ReasoningStep：thought / tool_call / skill_load / agent_spawn）
public struct ChatReasoningStepDTO: Codable {
    public let type: String
    public let title: String
    public let detail: String
    public let status: String
}

public extension ChatReasoningStepDTO {
    /// DTO → 前端 UI 模型（未知 type 兜底为 toolCall，保证 4 类之外不崩溃）
    func toReasoningStep() -> ReasoningStep {
        ReasoningStep(
            type: ReasoningStepType(rawValue: type) ?? .toolCall,
            title: title,
            detail: detail,
            status: status
        )
    }
}

/// GET /api/chat/status/{session_id} 响应（长任务状态回读 + 断点 0ms 恢复）
/// 状态机：completed（附 answer + 完整 reasoning）/ running（附 latestStep + 已产生 steps）
///        / timeout / not_found
public struct ChatStatusDTO: Codable {
    public let status: String
    public let answer: String?
    public let reasoning: [ChatReasoningStepDTO]?
    public let latestStep: String?
    /// 是否已消费（completed 且水位线已推进）；consume=1 时后端顺带标记
    public let consumed: Bool?
}

/// POST /api/v1/register 响应（token 为可选：当前后端仅返回 user_id，预留生产 JWT）
public struct RegisterResponseDTO: Codable {
    public let success: Bool?
    public let message: String?
    public let userId: String?
    public let token: String?
}

/// GET /api/v1/topology 单节点（后端基线 Agent 注册表唯一真值来源）
public struct TopologyNodeDTO: Codable, Identifiable, Hashable {
    public let id: String
    public let name: String
    public let roleDesc: String
    public let tools: [String]
    public let status: String
}

/// GET /api/v1/topology 单条协同边
public struct TopologyEdgeDTO: Codable, Hashable {
    public let source: String
    public let target: String
    public let label: String?
}

/// GET /api/v1/topology 响应（节点 + 边，对话页与拓扑页同源消费）
public struct TopologyGraphDTO: Codable {
    public let nodes: [TopologyNodeDTO]
    public let edges: [TopologyEdgeDTO]
}

/// GET /api/v1/tenant-agents 单条租户 Agent 切片（对齐后端 TenantAgentOut）
public struct TenantAgentDTO: Codable, Identifiable, Hashable {
    public let id: String
    public let tenantId: String
    public let baseAgentId: String
    public let customName: String?
    public let privatePromptDelta: String
    public let subscribedKnowledgePacks: [String]
    public let customAvatar: String?
    public let isActive: Bool
    public let createdAt: String?
    public let ownerUserId: String?
    public let originWorkflowId: String?
    public let visibility: String?
    public let allowedTools: [String]?
    public let capabilityAgentIds: [String]?
    public let allowNetwork: Bool?
}

public struct AgentEvaluationRunDTO: Codable, Identifiable {
    public let id: String
    public let agentId: String
    public let status: String
    public let suite: [AgentEvaluationCaseDTO]
    public let results: [AgentEvaluationResultDTO]
    public let score: Double
    public let usage: WorkflowUsageDTO?
    public let errorMessage: String?
    public let events: [AgentEvaluationEventDTO]
}

public struct AgentEvaluationCaseDTO: Codable, Identifiable {
    public let id: String
    public let name: String
    public let prompt: String
}

public struct AgentEvaluationResultDTO: Codable, Identifiable {
    public let id: String
    public let name: String
    public let status: String
    public let score: Double
    public let detail: String
}

public struct AgentEvaluationEventDTO: Codable, Identifiable {
    public let id: Int
    public let seq: Int
    public let type: String
    public let message: String
    public let payload: AgentEvaluationEventPayloadDTO?
}

public struct AgentEvaluationEventPayloadDTO: Codable {
    public let category: String?
    public let status: String?
    public let tool: String?
    public let detail: String?
}

/// GET /api/v1/skills 响应（租户真实技能库）
public struct TenantSkillsDTO: Codable {
    public let tenantId: String
    public let skills: [TenantSkillDTO]
}

public struct TenantSkillDTO: Codable, Identifiable, Hashable {
    public let name: String
    public let description: String
    public let category: String
    public let createdAt: String?

    public var id: String { name }
}

/// POST /api/v1/tenant-agents 请求体（tenant_id 由后端派生，客户端不可指定）
public struct TenantAgentCreateDTO: Encodable {
    public let baseAgentId: String
    public let customName: String?
    public let privatePromptDelta: String?
    public let subscribedKnowledgePacks: [String]?
    public let customAvatar: String?
    public let isActive: Bool?

    public init(
        baseAgentId: String,
        customName: String? = nil,
        privatePromptDelta: String? = nil,
        subscribedKnowledgePacks: [String]? = nil,
        customAvatar: String? = nil,
        isActive: Bool? = nil
    ) {
        self.baseAgentId = baseAgentId
        self.customName = customName
        self.privatePromptDelta = privatePromptDelta
        self.subscribedKnowledgePacks = subscribedKnowledgePacks
        self.customAvatar = customAvatar
        self.isActive = isActive
    }

    enum CodingKeys: String, CodingKey {
        case baseAgentId = "base_agent_id"
        case customName = "custom_name"
        case privatePromptDelta = "private_prompt_delta"
        case subscribedKnowledgePacks = "subscribed_knowledge_packs"
        case customAvatar = "custom_avatar"
        case isActive = "is_active"
    }
}

// MARK: - 可执行工作流 V1

public struct WorkflowDTO: Codable, Identifiable, Hashable {
    public let id: String
    public let title: String
    public let description: String
    public let desiredOutput: String
    public let status: String
    public let activePlanId: String?
    public let clarificationSessionId: String?
    public let primaryAgentId: String?
    public let createdAt: String?
    public let updatedAt: String?
    public let latestExecution: WorkflowExecutionDTO?
    public let agent: WorkflowTaskAgentDTO?
}

public struct WorkflowCreateResponseDTO: Codable {
    public let workflow: WorkflowDTO
    public let clarificationSession: WorkflowClarificationSessionDTO
}

public struct WorkflowClarificationSessionDTO: Codable, Hashable {
    public let id: String
    public let workflowId: String
    public let phase: String
    public let roundNumber: Int
    public let lastEventSeq: Int
}

public struct WorkflowClarificationPayloadDTO: Codable, Hashable {
    public let question: String?
    public let choices: [String]?
    public let multiSelect: Bool?
    public let dimension: String?
    public let submitLabel: String?
    public let phase: String?
    public let agentId: String?
    public let planId: String?
    public let tool: String?
    public let detail: String?
    public let stepId: String?
    public let category: String?
    public let status: String?
    public let source: String?
    public let planningJobId: String?
}

public struct WorkflowSessionMessageDTO: Codable, Identifiable, Hashable {
    public let id: String
    public let seq: Int
    public let role: String
    public let messageType: String
    public let content: String
    public let payload: WorkflowClarificationPayloadDTO
    public let createdAt: String?
}

public struct WorkflowLifecycleEventDTO: Codable, Identifiable, Hashable {
    public let id: Int
    public let workflowId: String
    public let sessionId: String
    public let type: String
    public let message: String
    public let payload: WorkflowClarificationPayloadDTO
    public let createdAt: String?
}

public struct WorkflowClarificationSnapshotDTO: Codable {
    public let workflow: WorkflowDTO
    public let session: WorkflowClarificationSessionDTO
    public let messages: [WorkflowSessionMessageDTO]
    public let events: [WorkflowLifecycleEventDTO]
}

public struct WorkflowActiveActivityDTO: Codable {
    public let workflow: WorkflowDTO
    public let session: WorkflowClarificationSessionDTO
    public let latestEvent: WorkflowLifecycleEventDTO?
}

public struct WorkflowActiveExecutionDTO: Codable {
    public let workflow: WorkflowDTO
    public let execution: WorkflowExecutionDTO
}

public struct WorkflowAgentDelegationDTO: Codable, Hashable {
    public let maxConcurrentChildren: Int
    public let maxSpawnDepth: Int
}

public struct WorkflowAgentCompositionDTO: Codable, Hashable {
    public let capabilityAgentIds: [String]
    public let invokedAgentIds: [String]?
    public let delegation: WorkflowAgentDelegationDTO
    public let knowledgeScope: [String]
    public let planId: String
}

public struct WorkflowTaskAgentDTO: Codable, Identifiable, Hashable {
    public let id: String
    public let ownerUserId: String?
    public let originWorkflowId: String?
    public let customName: String?
    public let visibility: String
    public let compositionManifest: WorkflowAgentCompositionDTO
    public let subscribedKnowledgePacks: [String]
    public let isActive: Bool
}

public struct WorkflowAgentBuildResponseDTO: Codable {
    public let workflow: WorkflowDTO
    public let agent: WorkflowTaskAgentDTO
}

public struct WorkflowPlanDTO: Codable, Identifiable, Hashable {
    public let id: String
    public let workflowId: String
    public let version: Int
    public let goal: String
    public var deliverable: String
    public var allowNetwork: Bool
    public var maxTokens: Int
    public let estimatedTokens: Int
    public var knowledgeScope: [String]
    public let validationErrors: [String]
    public var dsl: WorkflowDSLDTO
    public let frozenAt: String?
    public let createdAt: String?
}

public struct WorkflowDSLDTO: Codable, Hashable {
    public var planId: String
    public var name: String
    public var nodes: [WorkflowPlanNodeDTO]
    public var edges: [WorkflowPlanEdgeDTO]
    public var version: String

    enum CodingKeys: String, CodingKey {
        case planId = "plan_id"
        case name, nodes, edges, version
    }

    private enum DecodingKeys: String, CodingKey {
        case planId, name, nodes, edges, version
    }

    public init(from decoder: Decoder) throws {
        // APIClient already applies convertFromSnakeCase, so decoding must use
        // the transformed key. CodingKeys remains snake_case for PATCH encoding.
        let container = try decoder.container(keyedBy: DecodingKeys.self)
        planId = try container.decodeIfPresent(String.self, forKey: .planId) ?? ""
        name = try container.decodeIfPresent(String.self, forKey: .name) ?? "执行计划"
        nodes = try container.decodeIfPresent([WorkflowPlanNodeDTO].self, forKey: .nodes) ?? []
        edges = try container.decodeIfPresent([WorkflowPlanEdgeDTO].self, forKey: .edges) ?? []
        version = try container.decodeIfPresent(String.self, forKey: .version) ?? "1.0.0"
    }
}

public struct WorkflowPlanNodeDTO: Codable, Identifiable, Hashable {
    public var id: String
    public var nodeType: String
    public var name: String?
    public var parameters: WorkflowNodeParametersDTO

    enum CodingKeys: String, CodingKey {
        case id
        case nodeType = "node_type"
        case name, parameters
    }

    private enum DecodingKeys: String, CodingKey {
        case id, nodeType, name, parameters
    }

    public init(
        id: String,
        nodeType: String,
        name: String?,
        parameters: WorkflowNodeParametersDTO
    ) {
        self.id = id
        self.nodeType = nodeType
        self.name = name
        self.parameters = parameters
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: DecodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        nodeType = try container.decode(String.self, forKey: .nodeType)
        name = try container.decodeIfPresent(String.self, forKey: .name)
        parameters = try container.decode(WorkflowNodeParametersDTO.self, forKey: .parameters)
    }
}

public struct WorkflowNodeParametersDTO: Codable, Hashable {
    public var agentId: String?
    public var query: String?
    public var instruction: String?
    public var outputFormat: String?
    public var knowledgeScope: [String]?
    public var allowNetwork: Bool?
    public var requiresReview: Bool?
    public var maxTokens: Int?
    public var revisionNote: String?

    enum CodingKeys: String, CodingKey {
        case agentId = "agent_id"
        case query, instruction
        case outputFormat = "output_format"
        case knowledgeScope = "knowledge_scope"
        case allowNetwork = "allow_network"
        case requiresReview = "requires_review"
        case maxTokens = "max_tokens"
        case revisionNote = "revision_note"
    }

    private enum DecodingKeys: String, CodingKey {
        case agentId, query, instruction, outputFormat, knowledgeScope
        case allowNetwork, requiresReview, maxTokens, revisionNote
    }

    public init(
        agentId: String? = nil,
        query: String? = nil,
        instruction: String? = nil,
        outputFormat: String? = nil,
        knowledgeScope: [String]? = nil,
        allowNetwork: Bool? = nil,
        requiresReview: Bool? = nil,
        maxTokens: Int? = nil,
        revisionNote: String? = nil
    ) {
        self.agentId = agentId
        self.query = query
        self.instruction = instruction
        self.outputFormat = outputFormat
        self.knowledgeScope = knowledgeScope
        self.allowNetwork = allowNetwork
        self.requiresReview = requiresReview
        self.maxTokens = maxTokens
        self.revisionNote = revisionNote
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: DecodingKeys.self)
        agentId = try container.decodeIfPresent(String.self, forKey: .agentId)
        query = try container.decodeIfPresent(String.self, forKey: .query)
        instruction = try container.decodeIfPresent(String.self, forKey: .instruction)
        outputFormat = try container.decodeIfPresent(String.self, forKey: .outputFormat)
        knowledgeScope = try container.decodeIfPresent([String].self, forKey: .knowledgeScope)
        allowNetwork = try container.decodeIfPresent(Bool.self, forKey: .allowNetwork)
        requiresReview = try container.decodeIfPresent(Bool.self, forKey: .requiresReview)
        maxTokens = try container.decodeIfPresent(Int.self, forKey: .maxTokens)
        revisionNote = try container.decodeIfPresent(String.self, forKey: .revisionNote)
    }
}

public struct WorkflowPlanEdgeDTO: Codable, Hashable {
    public var source: String
    public var target: String
    public var condition: String?
}

public struct WorkflowNodeRunDTO: Codable, Identifiable, Hashable {
    public let id: String
    public let nodeId: String
    public let nodeType: String
    public let name: String
    public let agentId: String
    public let status: String
    public let position: Int
    public let attempt: Int
    public let maxTokens: Int
    public let tokenUsed: Int
    public let inputTokens: Int?
    public let outputTokens: Int?
    public let reasoningTokens: Int?
    public let cacheReadTokens: Int?
    public let cacheWriteTokens: Int?
    public let apiCalls: Int?
    public let estimatedCostUsd: Double?
    public let modelUsed: String?
    public let providerUsed: String?
    public let outputSummary: String
    public let errorMessage: String?
}

public struct WorkflowExecutionDTO: Codable, Identifiable, Hashable {
    public let id: String
    public let workflowId: String
    public let planId: String
    public let status: String
    public let progress: Int
    public let tokenBudget: Int
    public let tokenUsed: Int
    public let inputTokens: Int?
    public let outputTokens: Int?
    public let reasoningTokens: Int?
    public let cacheReadTokens: Int?
    public let cacheWriteTokens: Int?
    public let apiCalls: Int?
    public let estimatedCostUsd: Double?
    public let modelUsed: String?
    public let providerUsed: String?
    public let routeReason: String?
    public let hermesSessionId: String?
    public let artifactCount: Int
    public let errorMessage: String?
    public let startedAt: String?
    public let finishedAt: String?
    public let createdAt: String?
    public let nodes: [WorkflowNodeRunDTO]
}

public struct WorkflowArtifactDTO: Codable, Identifiable, Hashable {
    public let id: String
    public let kind: String
    public let title: String
    public let relativePath: String
    public let contentHash: String
    public let sourceUrl: String?
    public let sourceKind: String?
    public let selectedForPublish: Bool
    public let publishedPath: String?
}

public struct WorkflowArtifactContentDTO: Codable {
    public let id: String
    public let title: String
    public let kind: String
    public let content: String
}

public struct WorkflowEventDTO: Codable, Identifiable {
    public let id: Int
    public let type: String
    public let message: String
    public let payload: WorkflowEventPayloadDTO?
    public let createdAt: String?
}

public struct WorkflowEventPayloadDTO: Codable {
    public let nodeId: String?
    public let usage: WorkflowUsageDTO?
    public let route: WorkflowRouteDTO?
    public let category: String?
    public let status: String?
    public let tool: String?
    public let detail: String?
    public let source: String?
    public let bridgeEventId: String?
    public let bridgeSeq: Int?
}

public struct WorkflowUsageDTO: Codable {
    public let inputTokens: Int?
    public let outputTokens: Int?
    public let reasoningTokens: Int?
    public let cacheReadTokens: Int?
    public let cacheWriteTokens: Int?
    public let totalTokens: Int?
    public let apiCalls: Int?
    public let estimatedCostUsd: Double?
}

public struct WorkflowRouteDTO: Codable {
    public let model: String?
    public let provider: String?
    public let reason: String?
}

public struct WorkflowCreateRequestDTO: Encodable {
    public let title: String
    public let description: String
    public let desiredOutput: String

    enum CodingKeys: String, CodingKey {
        case title, description
        case desiredOutput = "desired_output"
    }
}

public struct WorkflowPlanEditRequestDTO: Encodable {
    public let dsl: WorkflowDSLDTO
    public let deliverable: String
    public let allowNetwork: Bool
    public let maxTokens: Int
    public let knowledgeScope: [String]

    enum CodingKeys: String, CodingKey {
        case dsl, deliverable
        case allowNetwork = "allow_network"
        case maxTokens = "max_tokens"
        case knowledgeScope = "knowledge_scope"
    }
}

// MARK: - API 错误

public enum APIError: Error, LocalizedError {
    case invalidURL
    case unauthorized
    case server(Int, String)
    case network(String)
    case decoding(String)
    case timeout

    public var errorDescription: String? {
        switch self {
        case .invalidURL: return "无效的请求地址"
        case .unauthorized: return "登录态失效，请重新登录"
        case .server(let code, let msg):
            // 502/503：服务端部署窗口/过载，明确提示而非笼统"不可用"
            if code == 502 || code == 503 || code == 504 {
                return "服务端正在更新或繁忙，请稍后重试（\(code)）"
            }
            return "服务端错误 \(code): \(msg)"
        case .network(let msg): return "网络不可用: \(msg)"
        case .decoding(let msg): return "数据解析失败: \(msg)"
        case .timeout: return "响应超时，请重试"
        }
    }
}

public struct ActionableAPIError: Decodable, Hashable {
    public let code: String
    public let message: String
    public let action: String
    public let retryable: Bool
}

private struct ActionableAPIErrorEnvelope: Decodable {
    let detail: ActionableAPIError
}

public extension APIError {
    var actionable: ActionableAPIError? {
        guard case .server(_, let raw) = self,
              let data = raw.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode(ActionableAPIErrorEnvelope.self, from: data).detail
    }
}

// MARK: - Keychain 存取（JWT）

public enum KeychainStore {
    private static let service = "com.ailab.AIPlatformApp"
    private static let account = "auth.jwt"

    @discardableResult
    public static func save(_ value: String) -> Bool {
        let data = Data(value.utf8)
        let base: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(base as CFDictionary)
        var attributes = base
        attributes[kSecValueData as String] = data
        let status = SecItemAdd(attributes as CFDictionary, nil)
        if status == errSecSuccess { return true }
        // 模拟器/无 keychain 环境兜底到 UserDefaults
        UserDefaults.standard.set(value, forKey: "auth.jwt.fallback")
        return false
    }

    public static func load() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecSuccess, let data = result as? Data,
           let token = String(data: data, encoding: .utf8) {
            return token
        }
        return UserDefaults.standard.string(forKey: "auth.jwt.fallback")
    }

    public static func delete() {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(query as CFDictionary)
        UserDefaults.standard.removeObject(forKey: "auth.jwt.fallback")
    }
}

// MARK: - 轻量网络层

@MainActor
public final class APIClient: ObservableObject {
    public static let shared = APIClient()

    /// 离线/降级标注：true 时 UI 应展示「演示数据」Tag
    @Published public var isOfflineMode: Bool = false
    /// 401 触发：true 时根协调器应引导重新登录
    @Published public var needsReauth: Bool = false

    public var baseURL: URL
    private let session: URLSession
    private let chatSession: URLSession
    /// 交互式 Agent SSE 可能跨越多轮 Clarify，资源总时长必须独立于普通问答超时。
    private let streamSession: URLSession
    private let decoder: JSONDecoder

    public init(baseURL: URL = URL(string: "http://120.24.248.58")!) {
        self.baseURL = baseURL
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 30
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        // 模拟器/真机内测直连云端：禁用系统代理（127.0.0.1 代理在模拟器环回内不存在，
        // 继承代理会导致连接拒绝→误报后端不可达/静默加载失败）
        config.connectionProxyDictionary = [:]
        self.session = URLSession(configuration: config)

        // 对话专用会话：超时 200s（后端 HERMES_TIMEOUT=180s 兜底），避免被默认 15s resource 超时截断
        let chatConfig = URLSessionConfiguration.default
        chatConfig.timeoutIntervalForRequest = 200
        chatConfig.timeoutIntervalForResource = 220
        chatConfig.requestCachePolicy = .reloadIgnoringLocalCacheData
        chatConfig.connectionProxyDictionary = [:]
        self.chatSession = URLSession(configuration: chatConfig)

        // Drill-me 是一个持续连接：用户思考时间 + 多轮模型推理可能明显超过 220 秒。
        // request timeout 只约束连续无数据时长；resource timeout 给完整工作流 1 小时。
        let streamConfig = URLSessionConfiguration.default
        streamConfig.timeoutIntervalForRequest = 75
        streamConfig.timeoutIntervalForResource = 3_600
        streamConfig.requestCachePolicy = .reloadIgnoringLocalCacheData
        streamConfig.connectionProxyDictionary = [:]
        self.streamSession = URLSession(configuration: streamConfig)

        self.decoder = JSONDecoder()
        self.decoder.keyDecodingStrategy = .convertFromSnakeCase
    }

    // MARK: - JWT

    public func saveToken(_ token: String) {
        KeychainStore.save(token)
    }

    public func currentToken() -> String? {
        KeychainStore.load()
    }

    public func clearToken() {
        KeychainStore.delete()
    }

    /// 对路径片段做百分号编码（保留 "/" 以便多段类目，如 knowledge/行业知识/金融）
    private func encodedPath(_ component: String) -> String {
        component.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed)
            ?? component
    }

    // MARK: - 通用请求

    /// 瞬态网络错误（DNS 解析失败 / 连接拒绝 / 超时 / 连接丢失等），GET 幂等请求可自动重试 1 次。
    private static func isTransientNetworkError(_ urlError: URLError) -> Bool {
        switch urlError.code {
        case .cannotFindHost, .dnsLookupFailed, .cannotConnectToHost,
             .networkConnectionLost, .notConnectedToInternet, .timedOut,
             .secureConnectionFailed:
            return true
        default:
            return false
        }
    }

    /// 底层请求执行：统一处理 401（不重试→needsReauth）、状态码、离线降级标注与 GET 幂等单次重试。
    /// - Parameter reauthOn401: 401 是否触发全局重登（清 token + needsReauth）。
    ///   主链路请求传 true；辅助/探测请求（如断点状态回读）传 false——失败静默降级，不误踢登录页。
    private func perform(
        _ request: URLRequest,
        session: URLSession,
        canRetry: Bool,
        reauthOn401: Bool = true
    ) async throws -> Data {
        var attempt = 0
        while true {
            do {
                let (data, response) = try await session.data(for: request)
                guard let http = response as? HTTPURLResponse else {
                    throw APIError.network("无效响应")
                }
                if http.statusCode == 401 {
                    // 401 绝不重试：主链路清 token 置 needsReauth 引导登录；探测链路仅抛错由调用方降级
                    if reauthOn401 {
                        clearToken()
                        isOfflineMode = false
                        needsReauth = true
                    }
                    throw APIError.unauthorized
                }
                guard (200..<300).contains(http.statusCode) else {
                    throw APIError.server(
                        http.statusCode,
                        String(data: data, encoding: .utf8) ?? ""
                    )
                }
                isOfflineMode = false
                return data
            } catch let urlError as URLError where urlError.code == .cancelled {
                throw urlError  // 请求取消，原样上抛，不误标离线
            } catch let urlError as URLError {
                if canRetry && attempt == 0 && Self.isTransientNetworkError(urlError) {
                    attempt += 1
                    continue
                }
                if urlError.code == .timedOut {
                    isOfflineMode = false
                    throw APIError.timeout
                }
                isOfflineMode = true
                throw APIError.network(urlError.localizedDescription)
            }
        }
    }

    /// 发起请求并解码。401 自动清 token + 置 needsReauth；网络异常置 isOfflineMode。
    /// 调用方持有外层 Task 即可实现「请求取消」（URLSession.data(for:) 对 Task 取消敏感）。
    public func request<T: Decodable>(
        _ type: T.Type,
        path: String,
        method: String = "GET",
        body: Encodable? = nil
    ) async throws -> T {
        let url = baseURL
            .appendingPathComponent("api/v1")
            .appendingPathComponent(path)
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token = currentToken(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            request.httpBody = try JSONEncoder().encode(body)
        }

        // 仅 GET 幂等请求自动重试；POST/PATCH/DELETE 由 UI 触发手动重试
        let data = try await perform(request, session: session, canRetry: method == "GET")
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding(Self.describeDecodingError(error))
        }
    }

    private static func describeDecodingError(_ error: Error) -> String {
        guard let codingError = error as? DecodingError else { return error.localizedDescription }
        let context: DecodingError.Context
        switch codingError {
        case let .keyNotFound(_, value): context = value
        case let .typeMismatch(_, value): context = value
        case let .valueNotFound(_, value): context = value
        case let .dataCorrupted(value): context = value
        @unknown default: return error.localizedDescription
        }
        let path = context.codingPath.map(\.stringValue).joined(separator: ".")
        let location = path.isEmpty ? "根对象" : path
        return "\(context.debugDescription)（字段路径：\(location)）"
    }

    // MARK: - 业务接口

    public func fetchCatalog() async throws -> CatalogResponse {
        try await request(CatalogResponse.self, path: "catalog")
    }

    public func fetchSubscriptions() async throws -> [String] {
        let resp: SubscriptionsResponse = try await request(
            SubscriptionsResponse.self, path: "me/subscriptions"
        )
        return resp.categories
    }

    public func fetchKnowledgeAccess() async throws -> KnowledgeAccessResponse {
        try await request(KnowledgeAccessResponse.self, path: "me/knowledge-access")
    }

    public func subscribe(category: String) async throws -> [String] {
        let resp: SubscriptionsResponse = try await request(
            SubscriptionsResponse.self,
            path: "me/knowledge-wallet",
            method: "PUT",
            body: SubscribeCategoryRequest(category: category)
        )
        return resp.categories
    }

    public func unsubscribe(category: String) async throws -> [String] {
        let resp: SubscriptionsResponse = try await request(
            SubscriptionsResponse.self,
            path: "me/knowledge-wallet",
            method: "DELETE",
            body: SubscribeCategoryRequest(category: category)
        )
        return resp.categories
    }

    public func fetchSubscriptionCenter() async throws -> SubscriptionCenterResponse {
        try await request(SubscriptionCenterResponse.self, path: "subscription-center")
    }

    public func createSubscriptionRequest(
        planId: String,
        entitlementKeys: [String],
        packIds: [String] = [],
        reason: String,
        requestId: String = UUID().uuidString
    ) async throws -> SubscriptionRequestDTO {
        try await request(
            SubscriptionRequestDTO.self,
            path: "subscription-requests",
            method: "POST",
            body: SubscriptionRequestCreateDTO(
                requestId: requestId,
                planId: planId,
                requestedEntitlements: entitlementKeys,
                requestedPackIds: packIds,
                reason: reason
            )
        )
    }

    public func cancelSubscriptionRequest(id: String) async throws -> SubscriptionRequestDTO {
        try await request(
            SubscriptionRequestDTO.self,
            path: "subscription-requests/\(encodedPath(id))",
            method: "DELETE"
        )
    }

    public func fetchAdminSubscriptionRequests() async throws -> [SubscriptionRequestDTO] {
        let response: SubscriptionRequestsResponse = try await request(
            SubscriptionRequestsResponse.self,
            path: "admin/subscription-requests"
        )
        return response.requests
    }

    public func reviewSubscriptionRequest(
        id: String, approve: Bool, note: String = "", approvedPackIds: [String]? = nil
    ) async throws -> SubscriptionRequestDTO {
        try await request(
            SubscriptionRequestDTO.self,
            path: "admin/subscription-requests/\(encodedPath(id))/\(approve ? "approve" : "reject")",
            method: "POST",
            body: SubscriptionReviewDTO(reviewNote: note, approvedPackIds: approvedPackIds)
        )
    }

    public func search(query: String, limit: Int = 20) async throws -> [SearchDoc] {
        let url = baseURL
            .appendingPathComponent("api/knowledge/search")
        var components = URLComponents(
            url: url, resolvingAgainstBaseURL: false
        )
        components?.queryItems = [
            URLQueryItem(name: "q", value: query),
            URLQueryItem(name: "limit", value: String(limit)),
        ]
        guard let finalURL = components?.url else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: finalURL)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token = currentToken(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let data = try await perform(request, session: session, canRetry: true)
        return try decoder.decode(SearchResponse.self, from: data).docs
    }

    public func fetchMe() async throws -> ProfileDTO {
        try await request(ProfileDTO.self, path: "me")
    }

    public func patchMe(
        username: String?, avatarUrl: String?
    ) async throws -> ProfileDTO {
        try await request(
            ProfileDTO.self,
            path: "me",
            method: "PATCH",
            body: ProfileUpdateRequest(username: username, avatarUrl: avatarUrl)
        )
    }

    /// GET /api/v1/topology：基线 Agent 注册表（对话页选择栏 + 拓扑页 DAG 同源消费）
    public func fetchTopology() async throws -> TopologyGraphDTO {
        try await request(TopologyGraphDTO.self, path: "topology")
    }

    // MARK: - 租户 Agent 切片（与后端 /api/v1/tenant-agents 同源，需求3/4）

    public func fetchTenantAgents() async throws -> [TenantAgentDTO] {
        try await request([TenantAgentDTO].self, path: "tenant-agents")
    }

    /// GET /api/v1/skills：当前租户真实技能库（挂载目录扫描·非演示数据）
    public func fetchTenantSkills() async throws -> [TenantSkillDTO] {
        let dto: TenantSkillsDTO = try await request(TenantSkillsDTO.self, path: "skills")
        return dto.skills
    }

    /// POST /api/v1/tenant-agents：创建租户私有 Agent 切片（base_agent_id 限基线 4 个）
    public func createTenantAgent(_ body: TenantAgentCreateDTO) async throws -> TenantAgentDTO {
        try await request(TenantAgentDTO.self, path: "tenant-agents", method: "POST", body: body)
    }

    /// DELETE /api/v1/tenant-agents/{id}：删除租户切片（204 无响应体）
    public func deleteTenantAgent(id: String) async throws {
        let url = baseURL
            .appendingPathComponent("api/v1/tenant-agents")
            .appendingPathComponent(id)
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token = currentToken(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        _ = try await perform(request, session: session, canRetry: false)
    }

    public func startAgentEvaluation(agentId: String, requestId: String) async throws -> AgentEvaluationRunDTO {
        struct Body: Encodable {
            let requestId: String
            enum CodingKeys: String, CodingKey { case requestId = "request_id" }
        }
        let resolvedId = agentId.hasPrefix("db_") ? String(agentId.dropFirst(3)) : agentId
        return try await request(
            AgentEvaluationRunDTO.self,
            path: "tenant-agents/\(encodedPath(resolvedId))/evaluations",
            method: "POST",
            body: Body(requestId: requestId)
        )
    }

    public func fetchAgentEvaluation(id: String) async throws -> AgentEvaluationRunDTO {
        try await request(AgentEvaluationRunDTO.self, path: "agent-evaluations/\(encodedPath(id))")
    }

    // MARK: - 可执行工作流 V1

    public func fetchWorkflows() async throws -> [WorkflowDTO] {
        try await request([WorkflowDTO].self, path: "workflows")
    }

    public func fetchWorkflow(id: String) async throws -> WorkflowDTO {
        try await request(WorkflowDTO.self, path: "workflows/\(encodedPath(id))")
    }

    public func createWorkflow(
        title: String,
        description: String,
        desiredOutput: String
    ) async throws -> WorkflowCreateResponseDTO {
        try await request(
            WorkflowCreateResponseDTO.self,
            path: "workflows",
            method: "POST",
            body: WorkflowCreateRequestDTO(
                title: title,
                description: description,
                desiredOutput: desiredOutput
            )
        )
    }

    public func fetchWorkflowClarification(
        workflowId: String
    ) async throws -> WorkflowClarificationSnapshotDTO {
        try await request(
            WorkflowClarificationSnapshotDTO.self,
            path: "workflows/\(encodedPath(workflowId))/clarification"
        )
    }

    public func fetchActiveWorkflowActivities() async throws -> [WorkflowActiveActivityDTO] {
        try await request(
            [WorkflowActiveActivityDTO].self,
            path: "workflow-activities/active"
        )
    }

    public func fetchActiveWorkflowExecutions() async throws -> [WorkflowActiveExecutionDTO] {
        try await request(
            [WorkflowActiveExecutionDTO].self,
            path: "workflow-executions/active"
        )
    }

    public func respondToWorkflowClarification(
        workflowId: String,
        response: String
    ) async throws -> WorkflowClarificationSessionDTO {
        struct Body: Encodable { let response: String }
        return try await request(
            WorkflowClarificationSessionDTO.self,
            path: "workflows/\(encodedPath(workflowId))/clarification/respond",
            method: "POST",
            body: Body(response: response)
        )
    }

    public func workflowLifecycleEventStream(
        workflowId: String,
        after: Int = 0
    ) -> AsyncThrowingStream<WorkflowLifecycleEventDTO, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let url = baseURL
                        .appendingPathComponent("api/v1/workflows")
                        .appendingPathComponent(workflowId)
                        .appendingPathComponent("lifecycle-events")
                    var components = URLComponents(url: url, resolvingAgainstBaseURL: false)
                    components?.queryItems = [URLQueryItem(name: "after", value: String(after))]
                    guard let finalURL = components?.url else { throw APIError.invalidURL }
                    var request = URLRequest(url: finalURL)
                    request.httpMethod = "GET"
                    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    if let token = currentToken(), !token.isEmpty {
                        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                    }
                    let (bytes, response) = try await streamSession.bytes(for: request)
                    guard let http = response as? HTTPURLResponse,
                          (200..<300).contains(http.statusCode) else {
                        throw APIError.network("任务进度连接失败")
                    }
                    for try await line in bytes.lines where line.hasPrefix("data: ") {
                        guard let data = String(line.dropFirst(6)).data(using: .utf8) else { continue }
                        continuation.yield(try decoder.decode(WorkflowLifecycleEventDTO.self, from: data))
                    }
                    continuation.finish()
                } catch is CancellationError {
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    public func fetchWorkflowPlan(workflowId: String) async throws -> WorkflowPlanDTO {
        var plan = try await request(
            WorkflowPlanDTO.self,
            path: "workflows/\(encodedPath(workflowId))/plan"
        )
        if plan.dsl.planId.isEmpty { plan.dsl.planId = plan.id }
        return plan
    }

    public func updateWorkflowPlan(
        workflowId: String,
        plan: WorkflowPlanDTO
    ) async throws -> WorkflowPlanDTO {
        var updated = try await request(
            WorkflowPlanDTO.self,
            path: "workflows/\(encodedPath(workflowId))/plan",
            method: "PATCH",
            body: WorkflowPlanEditRequestDTO(
                dsl: plan.dsl,
                deliverable: plan.deliverable,
                allowNetwork: plan.allowNetwork,
                maxTokens: plan.maxTokens,
                knowledgeScope: plan.knowledgeScope
            )
        )
        if updated.dsl.planId.isEmpty { updated.dsl.planId = updated.id }
        return updated
    }

    public func replanWorkflow(
        workflowId: String,
        instruction: String
    ) async throws -> WorkflowClarificationSessionDTO {
        struct Body: Encodable { let instruction: String }
        return try await request(
            WorkflowClarificationSessionDTO.self,
            path: "workflows/\(encodedPath(workflowId))/replan",
            method: "POST",
            body: Body(instruction: instruction)
        )
    }

    public func retryWorkflowPlanning(workflowId: String) async throws -> WorkflowClarificationSessionDTO {
        try await request(
            WorkflowClarificationSessionDTO.self,
            path: "workflows/\(encodedPath(workflowId))/planning/retry",
            method: "POST"
        )
    }

    public func reopenWorkflowClarification(workflowId: String) async throws -> WorkflowClarificationSessionDTO {
        try await request(
            WorkflowClarificationSessionDTO.self,
            path: "workflows/\(encodedPath(workflowId))/clarification/reopen",
            method: "POST"
        )
    }

    public func approveWorkflowPlan(workflowId: String, requestId: String) async throws -> WorkflowAgentBuildResponseDTO {
        struct Body: Encodable {
            let comment: String
            let requestId: String
            enum CodingKeys: String, CodingKey { case comment; case requestId = "request_id" }
        }
        return try await request(
            WorkflowAgentBuildResponseDTO.self,
            path: "workflows/\(encodedPath(workflowId))/approve-plan",
            method: "POST",
            body: Body(comment: "iOS 计划确认", requestId: requestId)
        )
    }

    public func startWorkflow(workflowId: String, requestId: String) async throws -> WorkflowExecutionDTO {
        struct Body: Encodable {
            let comment: String
            let requestId: String
            enum CodingKeys: String, CodingKey { case comment; case requestId = "request_id" }
        }
        return try await request(
            WorkflowExecutionDTO.self,
            path: "workflows/\(encodedPath(workflowId))/start",
            method: "POST",
            body: Body(comment: "iOS 启动任务", requestId: requestId)
        )
    }

    public func fetchWorkflowExecution(id: String) async throws -> WorkflowExecutionDTO {
        try await request(
            WorkflowExecutionDTO.self,
            path: "workflow-executions/\(encodedPath(id))"
        )
    }

    public func workflowEventStream(
        executionId: String,
        after: Int = 0
    ) -> AsyncThrowingStream<WorkflowEventDTO, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    var components = URLComponents(url: baseURL
                        .appendingPathComponent("api/v1/workflow-executions")
                        .appendingPathComponent(executionId)
                        .appendingPathComponent("events"), resolvingAgainstBaseURL: false)
                    components?.queryItems = [URLQueryItem(name: "after", value: String(after))]
                    guard let url = components?.url else { throw APIError.invalidURL }
                    var request = URLRequest(url: url)
                    request.httpMethod = "GET"
                    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    if after > 0 { request.setValue(String(after), forHTTPHeaderField: "Last-Event-ID") }
                    if let token = currentToken(), !token.isEmpty {
                        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                    }
                    let (bytes, response) = try await streamSession.bytes(for: request)
                    guard let http = response as? HTTPURLResponse,
                          (200..<300).contains(http.statusCode) else {
                        throw APIError.network("工作流事件流连接失败")
                    }
                    for try await line in bytes.lines where line.hasPrefix("data: ") {
                        guard let data = String(line.dropFirst(6)).data(using: .utf8) else { continue }
                        continuation.yield(try decoder.decode(WorkflowEventDTO.self, from: data))
                    }
                    continuation.finish()
                } catch is CancellationError {
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    public func fetchWorkflowArtifacts(executionId: String) async throws -> [WorkflowArtifactDTO] {
        try await request(
            [WorkflowArtifactDTO].self,
            path: "workflow-executions/\(encodedPath(executionId))/artifacts"
        )
    }

    public func fetchWorkflowArtifactContent(
        executionId: String,
        artifactId: String
    ) async throws -> WorkflowArtifactContentDTO {
        try await request(
            WorkflowArtifactContentDTO.self,
            path: "workflow-executions/\(encodedPath(executionId))/artifacts/\(encodedPath(artifactId))/content"
        )
    }

    public func cancelWorkflowExecution(id: String) async throws -> WorkflowExecutionDTO {
        struct EmptyBody: Encodable {}
        return try await request(
            WorkflowExecutionDTO.self,
            path: "workflow-executions/\(encodedPath(id))/cancel",
            method: "POST",
            body: EmptyBody()
        )
    }

    public func retryWorkflowExecution(id: String) async throws -> WorkflowExecutionDTO {
        struct EmptyBody: Encodable {}
        return try await request(
            WorkflowExecutionDTO.self,
            path: "workflow-executions/\(encodedPath(id))/retry",
            method: "POST",
            body: EmptyBody()
        )
    }

    public func requestWorkflowRevision(
        executionId: String,
        nodeId: String,
        comment: String
    ) async throws -> WorkflowExecutionDTO {
        struct Body: Encodable {
            let nodeId: String
            let comment: String
            enum CodingKeys: String, CodingKey {
                case nodeId = "node_id"
                case comment
            }
        }
        return try await request(
            WorkflowExecutionDTO.self,
            path: "workflow-executions/\(encodedPath(executionId))/request-revision",
            method: "POST",
            body: Body(nodeId: nodeId, comment: comment)
        )
    }

    public func approveWorkflowOutput(
        executionId: String,
        artifactIds: [String]
    ) async throws {
        struct Body: Encodable {
            let artifactIds: [String]
            let comment: String
            enum CodingKeys: String, CodingKey {
                case artifactIds = "artifact_ids"
                case comment
            }
        }
        struct Response: Decodable { let published: [String] }
        let _: Response = try await request(
            Response.self,
            path: "workflow-executions/\(encodedPath(executionId))/approve-output",
            method: "POST",
            body: Body(artifactIds: artifactIds, comment: "iOS 成果复核通过")
        )
    }

    // MARK: - 对话 / 思维链

    /// POST /api/chat：真实问答 + 真实思维链（异步 data(for:)，URLRequest.timeoutInterval=200，
    /// Task.cancel 传播中断客户端等待；404 可区分（清 session_id 幂等重发一次），超时单独抛 `.timeout`）。
    public func chat(
        question: String,
        requestId: String? = nil,
        sessionId: String? = nil,
        quotedContext: String? = nil,
        agentId: String? = nil
    ) async throws -> ChatResponseDTO {
        let url = baseURL.appendingPathComponent("api/chat")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 200
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token = currentToken(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = try JSONEncoder().encode(
            ChatRequestDTO(
                question: question,
                requestId: requestId,
                sessionId: sessionId,
                quotedContext: quotedContext,
                agentId: agentId
            )
        )

        do {
            let (data, response) = try await chatSession.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                throw APIError.network("无效响应")
            }
            if http.statusCode == 401 {
                clearToken()
                isOfflineMode = false
                needsReauth = true
                throw APIError.unauthorized
            }
            guard (200..<300).contains(http.statusCode) else {
                throw APIError.server(http.statusCode, String(data: data, encoding: .utf8) ?? "")
            }
            isOfflineMode = false
            do {
                return try decoder.decode(ChatResponseDTO.self, from: data)
            } catch {
                throw APIError.decoding(error.localizedDescription)
            }
        } catch let urlError as URLError where urlError.code == .cancelled {
            throw urlError  // 请求取消：原样上抛，供调用方识别「已取消」
        } catch let urlError as URLError where urlError.code == .timedOut {
            throw APIError.timeout  // 客户端 200s 超时：专属「响应超时(180s)」提示
        } catch let urlError as URLError {
            isOfflineMode = true
            throw APIError.network(urlError.localizedDescription)
        }
    }

    // MARK: - v7 真实流式（SSE 事件流）

    /// 流式事件类型（对齐后端 bridge 事件协议）
    public enum StreamEvent {
        case delta(String)
        case thought(String)
        case toolStart(id: String, tool: String, label: String)
        case toolComplete(id: String, tool: String)
        case clarify(question: String, choices: [String], multiSelect: Bool, source: String, clarifyId: String?)
        case clarifyRejected
        case status(phase: String, detail: String)
        case done(sessionId: String?, answer: String?)
        case error(code: String, message: String)

        /// 从 SSE `data:` JSON 解析事件
        static func parse(_ json: [String: Any]) -> StreamEvent? {
            guard let type = json["type"] as? String else { return nil }
            switch type {
            case "delta":
                return .delta(json["content"] as? String ?? "")
            case "thought":
                return .thought(json["content"] as? String ?? "")
            case "tool_start":
                return .toolStart(
                    id: json["id"] as? String ?? "",
                    tool: json["tool"] as? String ?? "",
                    label: json["label"] as? String ?? ""
                )
            case "tool_complete":
                return .toolComplete(
                    id: json["id"] as? String ?? "",
                    tool: json["tool"] as? String ?? ""
                )
            case "clarify":
                return .clarify(
                    question: json["question"] as? String ?? "",
                    choices: json["choices"] as? [String] ?? [],
                    multiSelect: json["multi_select"] as? Bool ?? false,
                    source: json["source"] as? String ?? "bridge",
                    clarifyId: json["clarify_id"] as? String
                )
            case "clarify_rejected":
                return .clarifyRejected
            case "status":
                // 真实状态分相（boot/reasoning）：仅驱动 ThinkingPlaceholder 阶段文案
                return .status(
                    phase: json["phase"] as? String ?? "",
                    detail: json["detail"] as? String ?? ""
                )
            case "done":
                return .done(
                    sessionId: json["session_id"] as? String,
                    answer: json["answer"] as? String
                )
            case "error":
                return .error(
                    code: json["code"] as? String ?? "unknown",
                    message: json["message"] as? String ?? ""
                )
            default:
                return nil
            }
        }
    }

    /// POST /api/chat/stream：URLSession.bytes 逐行消费 SSE 事件流（真实流式）
    /// - Parameter quotedContext: 引用历史消息上下文（若有）
    /// - Returns: AsyncThrowingStream 事件流；客户端断连/取消时自动 POST /api/chat/stream/cancel 回收服务端
    public func chatStream(
        question: String,
        requestId: String? = nil,
        sessionId: String? = nil,
        quotedContext: String? = nil,
        regenerate: Bool = false,
        agentId: String? = nil
    ) -> AsyncThrowingStream<StreamEvent, Error> {
        AsyncThrowingStream { continuation in
            let url = baseURL.appendingPathComponent("api/chat/stream")
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.timeoutInterval = 60  // 空闲保活（30s keepalive 帧持续刷新）
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
            if let token = currentToken(), !token.isEmpty {
                request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            }
            request.httpBody = try? JSONEncoder().encode(
                ChatRequestDTO(
                    question: question,
                    requestId: requestId,
                    sessionId: sessionId,
                    quotedContext: quotedContext,
                    agentId: agentId,
                    regenerate: regenerate
                )
            )

            let consumeTask = Task {
                do {
                    let (bytes, response) = try await streamSession.bytes(for: request)
                    guard let http = response as? HTTPURLResponse else {
                        continuation.finish(throwing: APIError.network("无效响应"))
                        return
                    }
                    guard (200..<300).contains(http.statusCode) else {
                        continuation.finish(throwing: APIError.server(http.statusCode, "流式端点错误"))
                        return
                    }
                    var buffer = ""
                    for try await line in bytes.lines {
                        if line.hasPrefix(":") { continue }          // keepalive 注释帧
                        if line.hasPrefix("data: ") {
                            let payload = String(line.dropFirst(6))
                            if let data = payload.data(using: .utf8),
                               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                               let event = StreamEvent.parse(json) {
                                continuation.yield(event)
                            }
                        } else {
                            // 半行缓冲（SSE 行可能被 TCP 分包）
                            buffer += line
                            if buffer.hasPrefix("data: "),
                               let data = buffer.dropFirst(6).data(using: .utf8),
                               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                               let event = StreamEvent.parse(json) {
                                continuation.yield(event)
                                buffer = ""
                            }
                        }
                    }
                    continuation.finish()
                } catch is CancellationError {
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { @Sendable termination in
                consumeTask.cancel()
                // 仅用户主动取消时 interrupt；网络异常采用 detach + status 回读，避免误杀
                // 已经生成到最终确认单的 Agent。
                if case .cancelled = termination {
                    Task {
                        try? await self.cancelStream(sessionId: sessionId, agentId: agentId)
                    }
                }
            }
        }
    }

    /// POST /api/chat/stream/cancel：服务端 interrupt + 回收
    public func cancelStream(sessionId: String?, agentId: String? = nil) async throws {
        guard let sessionId, !sessionId.isEmpty else { return }
        let url = baseURL.appendingPathComponent("api/chat/stream/cancel")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 10
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = currentToken(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        struct Body: Encodable {
            let sessionId: String
            let agentId: String?
            enum CodingKeys: String, CodingKey { case sessionId = "session_id"; case agentId = "agent_id" }
        }
        request.httpBody = try? JSONEncoder().encode(Body(sessionId: sessionId, agentId: agentId))
        _ = try? await chatSession.data(for: request)
    }

    /// POST /api/chat/stream/clarify：提交澄清响应（解锁 agent 线程）
    /// - Parameter clarifyId: bridge clarify 事件携带的 ID；透传后后端按 ID 精确解锁对应阻塞线程（P0：多卡场景防错配）
    public func submitClarify(
        sessionId: String?,
        response: String,
        clarifyId: String? = nil,
        agentId: String? = nil
    ) async throws -> Bool {
        guard let sessionId, !sessionId.isEmpty else { return false }
        let url = baseURL.appendingPathComponent("api/chat/stream/clarify")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 10
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = currentToken(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        var body: [String: Any] = [
            "session_id": sessionId,
            "response": response,
        ]
        if let clarifyId, !clarifyId.isEmpty {
            body["clarify_id"] = clarifyId
        }
        if let agentId, !agentId.isEmpty {
            body["agent_id"] = agentId
        }
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        let data = try await perform(request, session: chatSession, canRetry: false)
        let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        return (json?["ok"] as? Bool) ?? false
    }

    /// GET /api/chat/status/{sessionId}：长任务状态回读 / 断点 0ms 探测。
    /// consume=true 时后端顺带将 completed 结果标记为已消费（断点续接后不会误命中旧答案）。
    public func fetchChatStatus(
        sessionId: String,
        consume: Bool = false,
        agentId: String? = nil
    ) async throws -> ChatStatusDTO {
        var url = baseURL
            .appendingPathComponent("api/chat/status")
            .appendingPathComponent(sessionId)
        if consume || agentId != nil {
            var comps = URLComponents(url: url, resolvingAgainstBaseURL: false)
            var items: [URLQueryItem] = []
            if consume { items.append(URLQueryItem(name: "consume", value: "1")) }
            if let agentId { items.append(URLQueryItem(name: "agent_id", value: agentId)) }
            comps?.queryItems = items
            if let u = comps?.url { url = u }
        }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = 15
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token = currentToken(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let data = try await perform(request, session: session, canRetry: true, reauthOn401: false)
        do {
            return try decoder.decode(ChatStatusDTO.self, from: data)
        } catch {
            throw APIError.decoding(error.localizedDescription)
        }
    }

    // MARK: - Token 用量 / 注册

    /// GET /api/v1/me/usage → (chat_calls, token_used)
    public func fetchUsage() async throws -> (chatCalls: Int, tokenUsed: Int) {
        struct UsageResponse: Codable {
            let tenantKey: String
            let chatCalls: Int
            let tokenUsed: Int
        }
        let resp: UsageResponse = try await request(UsageResponse.self, path: "me/usage")
        return (resp.chatCalls, resp.tokenUsed)
    }

    /// POST /api/v1/register：自助注册（Authen 代理）。开发态 Authen 未起 → 连接失败，由调用方降级开发模式。
    public func register(
        email: String,
        username: String,
        password: String,
        verificationCode: String
    ) async throws -> RegisterResponseDTO {
        struct RegisterBody: Encodable {
            let email: String
            let username: String
            let password: String
            let verificationCode: String

            enum CodingKeys: String, CodingKey {
                case email, username, password
                case verificationCode = "verification_code"
            }
        }
        return try await request(
            RegisterResponseDTO.self,
            path: "register",
            method: "POST",
            body: RegisterBody(
                email: email,
                username: username,
                password: password,
                verificationCode: verificationCode
            )
        )
    }

    /// POST /api/v1/dev-login：仅开发环境启用的免短信登录。
    public func developerLogin(phone: String, verificationCode: String) async throws -> RegisterResponseDTO {
        struct DevLoginBody: Encodable {
            let phone: String
            let verificationCode: String

            enum CodingKeys: String, CodingKey {
                case phone
                case verificationCode = "verification_code"
            }
        }
        return try await request(
            RegisterResponseDTO.self,
            path: "dev-login",
            method: "POST",
            body: DevLoginBody(phone: phone, verificationCode: verificationCode)
        )
    }
}
