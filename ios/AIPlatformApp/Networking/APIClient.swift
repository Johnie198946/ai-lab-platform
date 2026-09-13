//
//  APIClient.swift
//  AIPlatformApp
//
//  轻量网络层：URLSession + JWT Keychain + 401 重登 + 请求取消 + 离线降级标注。
//  双轨策略：联网调用真实后端 API，失败/离线自动切回本地 Mock 并在 UI 标注「演示数据」。
//

import Foundation
import Combine
import CryptoKit
import Security

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

public struct HermesMemoryDTO: Codable, Identifiable, Hashable, Sendable {
    public let id: String
    public let target: String
    public let content: String
}

public struct HermesMemoryCenterDTO: Codable, Hashable, Sendable {
    public let items: [HermesMemoryDTO]
    public let limits: [String: Int]
    public let usage: [String: Int]
    public let reviewIntervalTurns: Int
}

public struct HermesMemoryWriteRequest: Encodable, Sendable {
    public let target: String
    public let content: String
}

public struct CloudKnowledgeNoteDTO: Codable, Identifiable, Hashable, Sendable {
    public let noteId: String
    public let markdown: String
    public let contentHash: String
    public let updatedAt: String?
    public let archived: Bool
    public let mergedIntoNoteId: String?

    public var id: String { noteId }
}

public struct CloudKnowledgeNotesResponse: Codable, Sendable {
    public let items: [CloudKnowledgeNoteDTO]
    public let count: Int
    public let compileStatus: String
}

public struct KnowledgeNoteMergeRequestDTO: Encodable, Sendable {
    public let operationId: String
    public let targetNoteId: String
    public let targetBaseHash: String
    public let sourceVersions: [String: String]
    public let revisedContent: String

    enum CodingKeys: String, CodingKey {
        case operationId = "operation_id"
        case targetNoteId = "target_note_id"
        case targetBaseHash = "target_base_hash"
        case sourceVersions = "source_versions"
        case revisedContent = "revised_content"
    }
}

public struct KnowledgeNoteMergeResponseDTO: Decodable, Sendable {
    public let operationId: String
    public let targetNoteId: String
    public let status: String
    public let revisedHash: String
}

public struct UsageDailyDTO: Codable, Identifiable, Hashable {
    public var id: String { date }
    public let date: String
    public let calls: Int
    public let inputTokens: Int
    public let outputTokens: Int
    public let cacheReadTokens: Int?
    public let cacheWriteTokens: Int?
    public let totalTokens: Int
}

public struct UsageModelDTO: Codable, Identifiable, Hashable {
    public var id: String { "\(provider):\(model)" }
    public let provider: String
    public let model: String
    public let calls: Int
    public let inputTokens: Int
    public let outputTokens: Int
    public let cacheReadTokens: Int?
    public let cacheWriteTokens: Int?
    public let totalTokens: Int
    public let missingUsageCalls: Int
}

public struct UsageSummaryDTO: Codable, Hashable {
    public let days: Int
    public let totalCalls: Int
    public let successCalls: Int
    public let failedCalls: Int
    public let inputTokens: Int
    public let outputTokens: Int
    public let cacheReadTokens: Int?
    public let cacheWriteTokens: Int?
    public let totalTokens: Int
    public let missingUsageCalls: Int
    public let tokenTotalBasis: String?
    public let legacyUnverifiedTotalTokens: Int?
    public let legacyUnverifiedCalls: Int?
    public let unverifiedCalls: Int?
    public let reconciliationRequired: Bool?
    public let usageState: String?
    public let daily: [UsageDailyDTO]
    public let models: [UsageModelDTO]
    public let quota: TokenQuotaDTO?

    public var hasVerifiedTokenBasis: Bool { tokenTotalBasis == "verified_requests_only" }

    public var verifiedCalls: Int? {
        guard hasVerifiedTokenBasis, let unverifiedCalls else { return nil }
        return max(0, totalCalls - unverifiedCalls)
    }

    public var usageTitle: String {
        hasVerifiedTokenBasis ? "已核验用量" : "服务端用量账本"
    }

    public var usagePeriodCaption: String {
        "近 \(days) 天\(hasVerifiedTokenBasis ? "已核验用量" : "账本记录")"
    }

    public var coverageNotices: [String] {
        guard hasVerifiedTokenBasis else {
            return ["当前服务未标注核验口径；该数值仅为服务端用量账本"]
        }

        var notices: [String] = []
        if let legacyUnverifiedCalls, legacyUnverifiedCalls > 0 {
            notices.append("\(legacyUnverifiedCalls) 次历史记录待核验、不计入该数值")
        }
        if missingUsageCalls > 0 {
            notices.append("\(missingUsageCalls) 次调用缺少 Token usage，未计入该数值")
        }

        let unverified = unverifiedCalls ?? 0
        if totalCalls > 0, unverified >= totalCalls {
            notices.append("当前范围没有已核验覆盖；0 仅表示已核验子集，不代表整体用量为 0")
        } else if usageState == "partial" || reconciliationRequired == true || unverified > 0 {
            let count = unverified > 0 ? "\(unverified) 次" : "部分"
            notices.append("当前范围仅部分调用已核验；\(count)未核验调用不计入该数值")
        }
        return notices
    }
}

public struct TokenQuotaDTO: Codable, Hashable {
    public let limitTokens: Int
    public let usedTokens: Int
    public let remainingTokens: Int
    public let percentUsed: Double
    public let isExhausted: Bool
    public let periodKind: String
    public let periodStart: String
    public let periodEnd: String
}

/// GET /api/v1/me/subscriptions 及订阅/退订返回
public struct SubscriptionsResponse: Codable {
    public let tenantKey: String
    public let categories: [String]
}

public struct EffectiveKnowledgeDTO: Codable, Identifiable, Hashable {
    public let category: String
    public let title: String
    public let securityLevel: String
    public let source: String
    public let documentCount: Int

    public var id: String { category }
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
    public var baseKnowledge: BaseKnowledgeDTO? = nil
    public var tenantPrivateKnowledge: TenantPrivateKnowledgeDTO? = nil
    public let effectiveCategories: [String]
    public var effectiveKnowledge: [EffectiveKnowledgeDTO]? = nil
    public let entitlementStale: Bool
}

public struct BaseKnowledgeDTO: Codable, Hashable {
    public let status: String
    public let documentCount: Int
    public let minimumDocumentCount: Int
    public let categoryCount: Int
    public let minimumCategoryCount: Int
    public let categories: [String]
    public let lastCompiledAt: String?

    public var isReady: Bool { status == "ready" }
}

public struct TenantPrivateKnowledgeDTO: Codable, Hashable {
    public let documentCount: Int
    public let categoryCount: Int
    public let categories: [String]
}

public struct KnowledgeBookDTO: Codable, Identifiable, Hashable {
    public let id: String
    public let title: String
    public let author: String
    public let authorSource: String?
    public let summary: String
    public let coverTheme: String?
    public let coverVariant: Int?
    public let coverVersion: Int?
    public let securityLevel: String
    public let knowledgeLevel: String
    public let freshness: String
    public let sourceCount: Int
    public var seriesId: String? = nil
    public var seriesTitle: String? = nil
    public var issueId: String? = nil
    public var issueDate: String? = nil
    public var testSerial: Bool? = nil
    public var releaseAt: String? = nil
    public var actualReleaseAt: String? = nil
    public var editionId: String? = nil
    public var edition: Int? = nil
    public var sourceUrls: [String]? = nil
    public var sourceKind: String? = nil
    public var sourceKindLabel: String? = nil
    public var contentStatus: String? = nil
    public var canonicalUrl: String? = nil
    public var published: String? = nil
    public var institution: String? = nil
    public var groupLabel: String? = nil
    public var sourceId: Int? = nil
    public var bodyOrigin: String? = nil
    public var completeness: String? = nil
    public var publicationFormat: String? = nil
    public var editorialGenre: String? = nil
    public var sourceClassification: String? = nil
    public var readable: Bool? = nil
    public var unavailableReason: String? = nil

    public var isBodyUnavailable: Bool { readable == false || contentStatus == "metadata_only" }
    public var publicationTypeLabel: String? {
        let format = ["book": "完整书", "chapter": "连载章节", "article": "历史短文", "source": "资料来源"][publicationFormat ?? ""]
        let genre = ["tutorial": "教程", "research_report": "研究报告", "popular_science": "科普", "feature": "趣味文章", "critical_essay": "观点文章"][editorialGenre ?? ""]
        return genre.map { "\($0) · \(format ?? "文章")" } ?? format
    }
    public var canonicalHTTPURL: URL? {
        guard let canonicalUrl, let url = URL(string: canonicalUrl),
              ["http", "https"].contains(url.scheme?.lowercased() ?? ""),
              url.host?.isEmpty == false else { return nil }
        return url
    }
}

public struct KnowledgeBookshelfDTO: Codable, Identifiable, Hashable {
    public let id: String
    public let title: String
    public let securityLevel: String
    public let bookCount: Int
    public let books: [KnowledgeBookDTO]

    public var isSourceShelf: Bool {
        id == "knowledge/publication/follow-builders"
            || id.hasPrefix("owner-private/follow-builders/")
            || books.contains { ["public_source_index", "owner_private_external"].contains($0.sourceKind ?? "") }
    }
}

public struct KnowledgeBookshelvesResponse: Codable {
    public let bookshelves: [KnowledgeBookshelfDTO]
    public var publicCollections: [PublicKnowledgeCollectionDTO]? = nil
    public var ownerPrivateCollections: [OwnerPrivateCollectionDTO]? = nil
}

public struct PublicKnowledgeAuthorityDTO: Codable, Identifiable, Hashable {
    public var id: Int { rosterId }
    public let rosterId: Int
    public let recordedHandle: String
    public let recordedDisplayName: String
    public let recordedWebsiteUrl: String
    public let identityStatus: String
    public let websiteStatus: String
    public let sourceRelationshipStatus: String
    public let admissionStatus: String
    public let specificQualifications: [String]
}

public struct PublicKnowledgeCollectionDTO: Codable, Identifiable, Hashable {
    public let id: String
    public let title: String
    public let visibility: String
    public let authorityCount: Int
    public let sourceCount: Int
    public let authorities: [PublicKnowledgeAuthorityDTO]
    public let admissionDecision: String
}

public struct OwnerPrivateAuthorityDTO: Codable, Identifiable, Hashable {
    public var id: Int { rosterId }
    public let rosterId: Int
    public let handle: String
    public let displayName: String?
    public let organizationOrRole: String?
    public let officialEntry: String?
    public let verificationStatus: String?
    public let identityStatus: String
    public let identityAssessment: String
    public let identityNotes: [String]
    public let relationshipStatus: String
}

public struct OwnerPrivateCollectionDTO: Codable, Identifiable, Hashable {
    public let id: String
    public let title: String
    public let visibility: String
    public let authorityCount: Int
    public let sourceCount: Int
    public let authorities: [OwnerPrivateAuthorityDTO]
}

public struct KnowledgeBookSubscriptionDTO: Codable, Hashable {
    public let book: KnowledgeBookDTO
    public let edition: Int
    public let contentVersion: String?
    public let progress: Double
    public let subscribedAt: String
    public let lastReadAt: String
}

public struct KnowledgeBookSubscriptionsResponse: Codable {
    public let subscriptions: [KnowledgeBookSubscriptionDTO]
}

public struct KnowledgeBookSectionDTO: Codable, Identifiable, Hashable {
    public let id: String
    public let title: String
    public let level: Int
    public let markdown: String
}

public struct KnowledgeBookBodyDTO: Codable, Hashable {
    public let bookId: String
    public let title: String
    public let author: String
    public let contentVersion: String
    public let edition: Int
    public let citation: String
    public let sections: [KnowledgeBookSectionDTO]
    public var seriesId: String? = nil
    public var seriesTitle: String? = nil
    public var issueId: String? = nil
    public var issueDate: String? = nil
    public var testSerial: Bool? = nil
    public var releaseAt: String? = nil
    public var actualReleaseAt: String? = nil
    public var editionId: String? = nil
    public var sourceUrls: [String]? = nil
    public var sourceKind: String? = nil
    public var contentStatus: String? = nil
    public var canonicalUrl: String? = nil
    public var sourceSnapshotHash: String? = nil
    public var readableBodyHash: String? = nil
    public var bodyOrigin: String? = nil
    public var completeness: String? = nil
    public var sourceClassification: String? = nil
}

private struct KnowledgeBookSubscriptionWrite: Encodable {
    let bookId: String
    var edition: Int = 1

    private enum CodingKeys: String, CodingKey {
        case bookId = "book_id"
        case edition
    }
}

private struct KnowledgeBookProgressWrite: Encodable {
    let bookId: String
    let progress: Double
    let contentVersion: String

    private enum CodingKeys: String, CodingKey {
        case bookId = "book_id"
        case progress
        case contentVersion = "content_version"
    }
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
    public var availability: String? = nil
    public var isAvailable: Bool? = nil
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
    public var baseKnowledge: BaseKnowledgeDTO? = nil
    public var bookshelves: [KnowledgeBookshelfDTO]? = nil
    public var tenantPrivateKnowledge: TenantPrivateKnowledgeDTO? = nil
    public var knowledgePackSubscriptionEnabled: Bool? = nil
}

public struct SubscriptionRequestsResponse: Codable {
    public let applicationId: String
    public let requests: [SubscriptionRequestDTO]
}

public struct KnowledgePublicationCandidateDTO: Codable, Identifiable, Hashable {
    public let path: String
    public let title: String
    public let securityLevel: String
    public let entitlementKey: String
    public let ownerTenant: String
    public let knowledgeLevel: String
    public var id: String { path }
}

public struct KnowledgePublicationCandidatesResponse: Codable {
    public let items: [KnowledgePublicationCandidateDTO]
}

public struct KnowledgePublicationResultDTO: Codable {
    public let path: String
    public let securityLevel: String
    public let classificationStatus: String
    public let gatewayStatus: String
}

private struct KnowledgePublicationDecisionDTO: Encodable {
    let path: String
    let securityLevel: String
    let entitlementKey: String
    let ownerTenant: String

    enum CodingKeys: String, CodingKey {
        case path
        case securityLevel = "security_level"
        case entitlementKey = "entitlement_key"
        case ownerTenant = "owner_tenant"
    }
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

public enum ChatContextMode: String, Codable, Sendable {
    case auto
    case localOnly = "local_only"
    case platformOnly = "platform_only"
    case combined
}

public struct ChatLocalNoteDTO: Codable, Hashable, Sendable {
    public let id: String
    public let title: String
    public let markdown: String
    public let updatedAt: String?
    public let contentHash: String?
    public let tags: [String]
    public let aliases: [String]
    public let isPinned: Bool
    public let archived: Bool

    public init(id: String, title: String, markdown: String, updatedAt: String? = nil, contentHash: String? = nil, tags: [String] = [], aliases: [String] = [], isPinned: Bool = false, archived: Bool = false) {
        self.id = id
        self.title = title
        self.markdown = markdown
        self.updatedAt = updatedAt
        self.contentHash = contentHash
        self.tags = tags; self.aliases = aliases; self.isPinned = isPinned; self.archived = archived
    }

    enum CodingKeys: String, CodingKey {
        case id, title, markdown
        case updatedAt = "updated_at"
        case contentHash = "content_hash"
        case tags, aliases, archived
        case isPinned = "is_pinned"
    }
}

public struct ChatContextScopeDTO: Codable, Hashable, Sendable {
    public let mode: ChatContextMode
    public let localNotes: [ChatLocalNoteDTO]
    public let selectedBookId: String?
    public let selectedBookVersion: String?
    public let selectedBookSectionId: String?

    public init(
        mode: ChatContextMode = .auto,
        localNotes: [ChatLocalNoteDTO] = [],
        selectedBookId: String? = nil,
        selectedBookVersion: String? = nil,
        selectedBookSectionId: String? = nil
    ) {
        self.mode = mode
        self.localNotes = localNotes
        self.selectedBookId = selectedBookId
        self.selectedBookVersion = selectedBookVersion
        self.selectedBookSectionId = selectedBookSectionId
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        mode = container.contains(.mode) ? try container.decode(ChatContextMode.self, forKey: .mode) : .auto
        localNotes = container.contains(.localNotes) ? try container.decode([ChatLocalNoteDTO].self, forKey: .localNotes) : []
        selectedBookId = try container.decodeIfPresent(String.self, forKey: .selectedBookId)
        selectedBookVersion = try container.decodeIfPresent(String.self, forKey: .selectedBookVersion)
        selectedBookSectionId = try container.decodeIfPresent(String.self, forKey: .selectedBookSectionId)
    }

    enum CodingKeys: String, CodingKey {
        case mode
        case localNotes = "local_notes"
        case selectedBookId = "selected_book_id"
        case selectedBookVersion = "selected_book_version"
        case selectedBookSectionId = "selected_book_section_id"
    }
}

public struct KnowledgeNoteSyncResponseDTO: Codable, Hashable, Sendable {
    public let noteId: String
    public let contentHash: String
    public let changed: Bool
    public let syncStatus: String
    public let compileStatus: String
    public let privateIndexHash: String?
}

public struct KnowledgeNoteSyncStatusDTO: Codable, Hashable, Sendable {
    public let noteId: String
    public let contentHash: String
    public let syncStatus: String
}

public enum KnowledgeNoteStatusPolicy {
    public static func message(for status: KnowledgeNoteSyncStatusDTO, expectedContentHash: String) -> String {
        status.syncStatus == "synced" && status.contentHash == expectedContentHash
            ? "已保存并同步原始笔记，Wiki 状态待确认"
            : "已保存到本地，原始笔记同步待确认"
    }
}

public struct ClientSessionMessageDTO: Codable, Hashable, Sendable {
    public let id: String
    public let role: String
    public let content: String
    public let createdAt: String?

    public init(id: String, role: String, content: String, createdAt: String? = nil) {
        self.id = id
        self.role = role
        self.content = content
        self.createdAt = createdAt
    }

    enum CodingKeys: String, CodingKey {
        case id, role, content
        case createdAt = "created_at"
    }
}

public struct ClientSourceSessionDTO: Codable, Hashable, Sendable, Identifiable {
    public let sessionId: String
    public let title: String
    public let updatedAt: String?
    public let organizedAt: String?
    public let messages: [ClientSessionMessageDTO]
    public let truncated: Bool
    public var id: String { sessionId }

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case title, messages, truncated
        case updatedAt = "updated_at"
        case organizedAt = "organized_at"
    }
}

public struct ClientSessionContextDTO: Codable, Hashable, Sendable {
    public let sessionId: String
    public let messages: [ClientSessionMessageDTO]
    public let truncated: Bool
    /// Additional authenticated, read-only source sessions for a multi-session organization task.
    public let sourceSessions: [ClientSourceSessionDTO]
    /// Local-first notes are signed into the request context so Hermes can
    /// compare notes that have not completed background sync yet.
    public let localNotes: [ChatLocalNoteDTO]

    public init(sessionId: String, messages: [ClientSessionMessageDTO], truncated: Bool, sourceSessions: [ClientSourceSessionDTO] = [], localNotes: [ChatLocalNoteDTO] = []) {
        self.sessionId = sessionId
        self.messages = messages
        self.truncated = truncated
        self.sourceSessions = sourceSessions
        self.localNotes = localNotes
    }

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case messages, truncated
        case sourceSessions = "source_sessions"
        case localNotes = "local_notes"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        sessionId = try container.decode(String.self, forKey: .sessionId)
        messages = try container.decode([ClientSessionMessageDTO].self, forKey: .messages)
        truncated = try container.decodeIfPresent(Bool.self, forKey: .truncated) ?? false
        sourceSessions = try container.decodeIfPresent([ClientSourceSessionDTO].self, forKey: .sourceSessions) ?? []
        localNotes = try container.decodeIfPresent([ChatLocalNoteDTO].self, forKey: .localNotes) ?? []
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
    public let contextScope: ChatContextScopeDTO
    public let clientSessionContext: ClientSessionContextDTO?
    public let clientCapabilities: [String]

    public init(question: String, requestId: String? = nil, sessionId: String? = nil, quotedContext: String? = nil, agentId: String? = nil, regenerate: Bool = false, contextScope: ChatContextScopeDTO = ChatContextScopeDTO(), clientSessionContext: ClientSessionContextDTO? = nil, clientCapabilities: [String] = ["knowledge_action_v1", "answer_blocks_v1"]) {
        self.question = question
        self.requestId = requestId
        self.sessionId = sessionId
        self.quotedContext = quotedContext
        self.agentId = agentId
        self.regenerate = regenerate
        self.contextScope = contextScope
        self.clientSessionContext = clientSessionContext
        self.clientCapabilities = clientCapabilities
    }

    enum CodingKeys: String, CodingKey {
        case question
        case requestId = "request_id"
        case sessionId = "session_id"
        case quotedContext = "quoted_context"
        case agentId = "agent_id"
        case regenerate
        case contextScope = "context_scope"
        case clientSessionContext = "client_session_context"
        case clientCapabilities = "client_capabilities"
    }
}

public struct ChatPrewarmRequestDTO: Encodable {
    public let sessionId: String
    public let agentId: String?
    public let clientCapabilities: [String]

    public init(
        sessionId: String,
        agentId: String?,
        clientCapabilities: [String] = ["knowledge_action_v1", "answer_blocks_v1"]
    ) {
        self.sessionId = sessionId
        self.agentId = agentId
        self.clientCapabilities = clientCapabilities
    }

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case agentId = "agent_id"
        case clientCapabilities = "client_capabilities"
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
    public let resolvedAgent: ChatAgentRouteDTO?
    public let delegatedBy: String?
    public let feedbackReceipt: FeedbackReceiptDTO?

    public init(question: String, answer: String, sessionId: String?, reasoning: [ChatReasoningStepDTO], degraded: Bool? = nil, clarify: ChatClarifyDTO? = nil, resolvedAgent: ChatAgentRouteDTO? = nil, delegatedBy: String? = nil, feedbackReceipt: FeedbackReceiptDTO? = nil) {
        self.question = question
        self.answer = answer
        self.sessionId = sessionId
        self.reasoning = reasoning
        self.degraded = degraded
        self.clarify = clarify
        self.resolvedAgent = resolvedAgent
        self.delegatedBy = delegatedBy
        self.feedbackReceipt = feedbackReceipt
    }
}

public struct FeedbackReceiptDTO: Codable, Hashable {
    public let feedbackId: String
    public let signalType: String
    public let message: String
    public let revocable: Bool
}

public struct ChatAgentRouteDTO: Codable, Hashable {
    public let id: String
    public let name: String
    public let delegated: Bool
}

/// 后端澄清卡片载荷（对应 backend ClarifyPayload：question / choices / multi_select）
public struct ChatClarifyDTO: Codable {
    public let question: String
    public let choices: [String]
    public let multiSelect: Bool
    public let source: String?
    public let clarifyId: String?
    public let requestId: String?
    public let expiresInSeconds: Int?

    enum CodingKeys: String, CodingKey {
        case question
        case choices
        // APIClient 的 decoder 已启用 convertFromSnakeCase；这里必须保持 Swift 字段名，
        // 否则会二次转换并导致 multi_select 解码失败。
        case multiSelect
        case source
        case clarifyId
        case requestId
        case expiresInSeconds
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
    public let phase: String?
    public let answer: String?
    public let reasoning: [ChatReasoningStepDTO]?
    public let latestStep: String?
    public let clarify: ChatClarifyDTO?
    /// 是否已消费（completed 且水位线已推进）；consume=1 时后端顺带标记
    public let consumed: Bool?
    public let answerProjection: AnswerBlockPageDTO?

    public var loadedAnswer: String? {
        answer ?? answerProjection.map { $0.blocks.map(\.content).joined() }
    }
}

public struct AnswerBlockDTO: Codable, Sendable, Hashable {
    public let blockIndex: Int
    public let kind: String
    public let content: String
}

public struct AnswerBlockPageDTO: Codable, Sendable, Hashable {
    public let messageId: String
    public let revision: Int
    public let status: String
    public let blocks: [AnswerBlockDTO]
    public let bytes: Int
    public let loadedBlockCount: Int
    public let availableBlockCount: Int
    public let hasMore: Bool
    public let nextCursor: String?
    public var runId: String? = nil
}

public struct DurableChatRunDTO: Codable, Sendable {
    public let runId: String
    public let status: String
    public let eventSequence: Int
    public let partialAnswer: String?
    public let finalAnswer: String?
    public let queuePosition: Int
    public let attempt: Int
    public let errorCode: String
    public let answerProjection: AnswerBlockPageDTO?
}

public struct DurableChatReplayDTO: Decodable, Sendable {
    public let run: DurableChatRunDTO
    public let droppedEventCount: Int
    public let events: [APIClient.StreamEvent]

    public init(
        run: DurableChatRunDTO,
        droppedEventCount: Int,
        events: [APIClient.StreamEvent] = []
    ) {
        self.run = run
        self.droppedEventCount = droppedEventCount
        self.events = events
    }

    private enum CodingKeys: String, CodingKey {
        case run, droppedEventCount
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        run = try container.decode(DurableChatRunDTO.self, forKey: .run)
        droppedEventCount = try container.decode(Int.self, forKey: .droppedEventCount)
        events = []
    }
}

public struct ClarifySubmitResult: Codable, Sendable {
    public let ok: Bool
    public let state: String
    public let clarifyId: String?
}

/// POST /api/v1/register 响应（token 为可选：当前后端仅返回 user_id，预留生产 JWT）
public struct RegisterResponseDTO: Codable {
    public let success: Bool?
    public let message: String?
    public let userId: String?
    public let token: String?
}

public struct AuthCapabilityDTO: Codable {
    public let enabled: Bool
}

public struct OAuthCapabilitiesDTO: Codable {
    public let wechat: AuthCapabilityDTO
    public let alipay: AuthCapabilityDTO
}

public struct AuthCapabilitiesDTO: Codable {
    public let phone: AuthCapabilityDTO
    public let oauth: OAuthCapabilitiesDTO
}

public struct AgreementSectionDTO: Codable, Hashable, Identifiable {
    public let id: String
    public let title: String
    public let clauses: [String]
}

public struct AgreementDTO: Codable, Hashable {
    public let version: String
    public let title: String
    public let updatedAt: String
    public let sections: [AgreementSectionDTO]
}

public struct AgreementAcceptanceDTO: Codable, Hashable {
    public let agreementVersion: String?
    public let acceptedAt: String?
}

public struct AgreementAcceptanceBody: Encodable, Hashable {
    public let agreementVersion: String
    public let idempotencyKey: String
    public var source = "ios"

    enum CodingKeys: String, CodingKey {
        case agreementVersion = "agreement_version"
        case idempotencyKey = "idempotency_key"
        case source
    }
}

public struct LoginSessionDTO: Codable {
    public let success: Bool
    public let token: String
    public let userId: String
    public let tenantKey: String
    public let isNewUser: Bool?
}

public struct OAuthStartDTO: Codable {
    public let authorizationUrl: URL
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
    public let contentHash: String
    public let activationRevision: Int
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
    public let `extension`: String
    public let mimeType: String
    public let metadata: WorkflowArtifactMetadataDTO
}

public struct WorkflowArtifactMetadataDTO: Codable, Hashable {
    public let renderType: String?
    public let approvalGate: String?
    public let artifactVersion: Int?
    public let previewStatus: String?
    public let previewArtifactId: String?
    public let previewContentHash: String?
    public let previewError: String?
    public let parentArtifactId: String?
    public let parentContentHash: String?
    public let sampleArtifactId: String?
    public let sampleContentHash: String?
}

public struct DocumentReceiptDTO: Codable, Hashable {
    public let sourceId: String
    public let sourceRevision: Int
    public let filename: String
    public let contentType: String
    public let sizeBytes: Int64
    public let contentHash: String
    public let status: String
    public let textAvailable: Bool
    public let contributionStatus: String
    public let contributionError: String?
    public let noteId: String?
    public let noteStatus: String?
    public let parseError: DocumentParseErrorDTO?
}

public struct DocumentParseErrorDTO: Codable, Hashable { public let code: String; public let message: String }

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
    public let sourceDocumentId: String?

    enum CodingKeys: String, CodingKey {
        case title, description
        case desiredOutput = "desired_output"
        case sourceDocumentId = "source_document_id"
    }
}

public struct WorkflowPlanEditRequestDTO: Encodable {
    public let dsl: WorkflowDSLDTO
    public let deliverable: String
    public let allowNetwork: Bool
    public let maxTokens: Int
    public let knowledgeScope: [String]
    public let expectedHash: String
    public let expectedRevision: Int

    enum CodingKeys: String, CodingKey {
        case dsl, deliverable
        case allowNetwork = "allow_network"
        case maxTokens = "max_tokens"
        case knowledgeScope = "knowledge_scope"
        case expectedHash = "expected_hash"
        case expectedRevision = "expected_revision"
    }
}

// MARK: - API 错误

public enum APIError: Error, LocalizedError {
    case invalidURL
    case unauthorized
    case authenticationRejected(String)
    case knowledgeScopeChanged
    case server(Int, String)
    case network(String)
    case decoding(String)
    case timeout

    public var errorDescription: String? {
        switch self {
        case .invalidURL: return "无效的请求地址"
        case .unauthorized: return "登录态失效，请重新登录"
        case .authenticationRejected(let message): return message
        case .knowledgeScopeChanged:
            return "套餐或知识权限已变化，请刷新知识权限后重试"
        case .server(let code, let msg):
            if code == 429 && msg.contains("inference_quota_exceeded") {
                return "本月 Token 可用额度不足以启动本次请求，请在设置的 Token 监控中查看余额与重置时间"
            }
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

    /// 将后端结构化 403 统一映射为权限变化，避免把知识撤权误报为普通服务器错误。
    public static func fromHTTP(statusCode: Int, body: Data, fallback: String = "") -> APIError {
        let raw = String(data: body, encoding: .utf8) ?? fallback
        if statusCode == 403,
           raw.contains("knowledge_scope_denied") || raw.contains("套餐或知识权限已变化") {
            return .knowledgeScopeChanged
        }
        return .server(statusCode, raw)
    }

    /// 登录、验证码及 OAuth 探测请求没有既有登录态；其 401 必须保留后端原因，
    /// 不能误报成“登录态失效”。
    public static func authenticationFailure(body: Data) -> APIError {
        struct Envelope: Decodable { let detail: String }
        let detail = try? JSONDecoder().decode(Envelope.self, from: body).detail
        let message = detail?.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let message, !message.isEmpty else {
            return .authenticationRejected("认证失败，请检查验证码后重试")
        }
        return .authenticationRejected(message)
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
        var attributes = base
        attributes[kSecValueData as String] = data
        // 登录凭证需要跨进程重启保留，同时不随 iCloud/设备迁移导出。
        attributes[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let addStatus = SecItemAdd(attributes as CFDictionary, nil)
        let status: OSStatus
        if KeychainSavePolicy.shouldUpdate(after: addStatus) {
            status = SecItemUpdate(base as CFDictionary, [
                kSecValueData as String: data,
                kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
            ] as CFDictionary)
        } else {
            status = addStatus
        }
        // Authentication material must never fall back to UserDefaults.  That
        // store is neither a credential vault nor protected by Keychain access
        // controls.  Remove any token left by older builds and fail closed.
        UserDefaults.standard.removeObject(forKey: "auth.jwt.fallback")
        return status == errSecSuccess
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
            UserDefaults.standard.removeObject(forKey: "auth.jwt.fallback")
            return token
        }
        // Purge insecure legacy storage instead of reviving a bearer token from it.
        UserDefaults.standard.removeObject(forKey: "auth.jwt.fallback")
        return nil
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

public enum KeychainSavePolicy {
    public static func shouldUpdate(after addStatus: OSStatus) -> Bool {
        addStatus == errSecDuplicateItem
    }
}

public enum AgreementReplayPolicy {
    public static func canReplay(statusCode: Int, replayCount: Int) -> Bool {
        statusCode == 428 && replayCount == 0
    }
}

// MARK: - 轻量网络层

@MainActor
public final class APIClient: ObservableObject {
    public static let shared = APIClient()
    public static let clientContract = "ios-unified-agreement-v1"

    /// 离线/降级标注：true 时 UI 应展示「演示数据」Tag
    @Published public var isOfflineMode: Bool = false
    /// 401 触发：true 时根协调器应引导重新登录
    @Published public var needsReauth: Bool = false
    @Published public var requiredAgreementVersion: String?

    public var baseURL: URL
    private let session: URLSession
    private let chatSession: URLSession
    /// 交互式 Agent SSE 可能跨越多轮 Clarify，资源总时长必须独立于普通问答超时。
    private let streamSession: URLSession
    private let decoder: JSONDecoder
    private let persistsCredentials: Bool
    /// Keep the freshly issued bearer token in memory as the request-time source
    /// of truth. Keychain remains the cross-launch persistence layer, but an
    /// immediate `/me` request must not depend on a second Security-framework
    /// lookup succeeding in the same login transaction.
    private var cachedToken: String?
    private var credentialGeneration: UInt64 = 0
    private var agreementWaiters: [CheckedContinuation<Bool, Never>] = []
    private var knowledgeNoteSyncTails: [String: (
        token: UUID, contentHash: String, task: Task<KnowledgeNoteSyncResponseDTO, Error>
    )] = [:]
    private var knowledgeNoteSyncHashes: [String: String] = [:]

    public convenience init(baseURL: URL = URL(string: "https://120.24.248.58")!) {
        self.init(
            baseURL: baseURL,
            sessionConfiguration: .default,
            initialToken: KeychainStore.load(),
            persistsCredentials: true
        )
    }

    convenience init(
        baseURL: URL,
        sessionConfiguration: URLSessionConfiguration,
        inMemoryToken: String
    ) {
        self.init(
            baseURL: baseURL,
            sessionConfiguration: sessionConfiguration,
            initialToken: inMemoryToken,
            persistsCredentials: false
        )
    }

    private init(
        baseURL: URL,
        sessionConfiguration: URLSessionConfiguration,
        initialToken: String?,
        persistsCredentials: Bool
    ) {
        self.baseURL = baseURL
        self.cachedToken = initialToken
        self.persistsCredentials = persistsCredentials
        let config = sessionConfiguration
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

    @discardableResult
    public func saveToken(_ token: String) -> Bool {
        resetKnowledgeNoteSyncLanes()
        guard persistsCredentials else {
            cachedToken = token
            credentialGeneration &+= 1
            return true
        }
        guard KeychainStore.save(token) else {
            cachedToken = nil
            credentialGeneration &+= 1
            return false
        }
        cachedToken = token
        credentialGeneration &+= 1
        return true
    }

    public func currentToken() -> String? {
        guard persistsCredentials else { return cachedToken }
#if DEBUG
        if let token = ProcessInfo.processInfo.environment["AI_LAB_E2E_TOKEN"], !token.isEmpty {
            return token
        }
#endif
        if let cachedToken, !cachedToken.isEmpty {
            return cachedToken
        }
        let persisted = KeychainStore.load()
        cachedToken = persisted
        return persisted
    }

    public func clearToken() {
        resetKnowledgeNoteSyncLanes()
        cachedToken = nil
        credentialGeneration &+= 1
        if persistsCredentials {
            KeychainStore.delete()
        }
    }

    public func currentCredentialGeneration() -> UInt64 { credentialGeneration }

    private func resetKnowledgeNoteSyncLanes() {
        knowledgeNoteSyncTails.values.forEach { $0.task.cancel() }
        knowledgeNoteSyncTails.removeAll()
        knowledgeNoteSyncHashes.removeAll()
    }

    /// 对路径片段做百分号编码（保留 "/" 以便多段类目，如 knowledge/行业知识/金融）
    private func encodedPath(_ component: String) -> String {
        component.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed)
            ?? component
    }

    private func applyClientContract(to request: inout URLRequest, includeAuthorization: Bool = true) {
        request.setValue(Self.clientContract, forHTTPHeaderField: "X-Client-Contract")
        if includeAuthorization, let token = currentToken(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
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
        reauthOn401: Bool = true,
        credentialGeneration expectedGeneration: UInt64? = nil,
        anonymous: Bool = false
    ) async throws -> Data {
        let requestGeneration = expectedGeneration ?? credentialGeneration
        guard anonymous || requestGeneration == credentialGeneration else { throw CancellationError() }
        var attempt = 0
        while true {
            do {
                let (data, response) = try await session.data(for: request)
                guard anonymous || requestGeneration == credentialGeneration else { throw CancellationError() }
                guard let http = response as? HTTPURLResponse else {
                    throw APIError.network("无效响应")
                }
                if http.statusCode == 401 {
                    // 401 绝不重试：主链路清 token 置 needsReauth 引导登录；
                    // 登录/探测链路保留服务端原因，避免把验证码错误误报为登录态失效。
                    if reauthOn401 {
                        clearToken()
                        isOfflineMode = false
                        needsReauth = true
                        throw APIError.unauthorized
                    }
                    throw APIError.authenticationFailure(body: data)
                }
                guard (200..<300).contains(http.statusCode) else {
                    throw APIError.fromHTTP(statusCode: http.statusCode, body: data)
                }
                isOfflineMode = false
                return data
            } catch let urlError as URLError where urlError.code == .cancelled {
                guard anonymous || requestGeneration == credentialGeneration else { throw CancellationError() }
                throw urlError  // 请求取消，原样上抛，不误标离线
            } catch let urlError as URLError {
                guard anonymous || requestGeneration == credentialGeneration else { throw CancellationError() }
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
        body: Encodable? = nil,
        queryItems: [URLQueryItem] = [],
        reauthOn401: Bool = true,
        credentialGeneration expectedGeneration: UInt64? = nil,
        anonymous: Bool = false
    ) async throws -> T {
        let requestGeneration = expectedGeneration ?? credentialGeneration
        guard anonymous || requestGeneration == credentialGeneration else { throw CancellationError() }
        var components = URLComponents(
            url: baseURL
            .appendingPathComponent("api/v1")
            .appendingPathComponent(path),
            resolvingAgainstBaseURL: false
        )
        if !queryItems.isEmpty {
            components?.queryItems = queryItems
        }
        guard let url = components?.url else {
            throw APIError.network("无效的请求地址")
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        applyClientContract(to: &request, includeAuthorization: !anonymous)
        if let body {
            request.httpBody = try JSONEncoder().encode(body)
        }

        // 仅 GET 幂等请求自动重试；POST/PATCH/DELETE 由 UI 触发手动重试
        let data: Data
        do {
            data = try await perform(
                request, session: session, canRetry: method == "GET", reauthOn401: reauthOn401,
                credentialGeneration: requestGeneration, anonymous: anonymous
            )
        } catch APIError.server(let status, let raw)
            where AgreementReplayPolicy.canReplay(statusCode: status, replayCount: 0) {
            guard let version = Self.agreementVersion(from: raw) else {
                throw APIError.server(status, raw)
            }
            guard anonymous || requestGeneration == credentialGeneration else { throw CancellationError() }
            requiredAgreementVersion = version
            let accepted = await withCheckedContinuation { agreementWaiters.append($0) }
            guard accepted, anonymous || requestGeneration == credentialGeneration else { throw CancellationError() }
            // A protected request is replayed exactly once after explicit acceptance.
            data = try await perform(
                request, session: session, canRetry: false, reauthOn401: reauthOn401,
                credentialGeneration: requestGeneration, anonymous: anonymous
            )
        }
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding(Self.describeDecodingError(error))
        }
    }

    private static func agreementVersion(from raw: String) -> String? {
        struct Envelope: Decodable {
            struct Detail: Decodable { let currentVersion: String }
            let detail: Detail
        }
        guard let data = raw.data(using: .utf8) else { return nil }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try? decoder.decode(Envelope.self, from: data).detail.currentVersion
    }

    public func resolveAgreementRequirement(accepted: Bool) {
        requiredAgreementVersion = nil
        let waiters = agreementWaiters
        agreementWaiters.removeAll()
        waiters.forEach { $0.resume(returning: accepted) }
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

    // MARK: - Native Hermes memory

    public func fetchHermesMemory() async throws -> HermesMemoryCenterDTO {
        try await request(HermesMemoryCenterDTO.self, path: "me/memory")
    }

    public func addHermesMemory(target: String, content: String) async throws -> HermesMemoryCenterDTO {
        try await request(
            HermesMemoryCenterDTO.self,
            path: "me/memory",
            method: "POST",
            body: HermesMemoryWriteRequest(target: target, content: content)
        )
    }

    public func replaceHermesMemory(memoryId: String, content: String) async throws -> HermesMemoryCenterDTO {
        struct Body: Encodable { let content: String }
        return try await request(
            HermesMemoryCenterDTO.self,
            path: "me/memory/\(encodedPath(memoryId))",
            method: "PUT",
            body: Body(content: content)
        )
    }

    public func removeHermesMemory(memoryId: String) async throws -> HermesMemoryCenterDTO {
        try await request(
            HermesMemoryCenterDTO.self,
            path: "me/memory/\(encodedPath(memoryId))",
            method: "DELETE"
        )
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

    public func fetchKnowledgeBookshelves() async throws -> KnowledgeBookshelvesResponse {
        try await request(KnowledgeBookshelvesResponse.self, path: "knowledge-bookshelves")
    }

    public func fetchBookSubscriptions() async throws -> [KnowledgeBookSubscriptionDTO] {
        let response = try await request(
            KnowledgeBookSubscriptionsResponse.self, path: "me/book-subscriptions"
        )
        return response.subscriptions
    }

    public func fetchKnowledgeBookBody(id: String) async throws -> KnowledgeBookBodyDTO {
        try await request(KnowledgeBookBodyDTO.self, path: "knowledge-books/\(encodedPath(id))")
    }

    public func subscribeBook(id: String) async throws -> KnowledgeBookSubscriptionDTO {
        try await request(
            KnowledgeBookSubscriptionDTO.self,
            path: "me/book-subscriptions",
            method: "PUT",
            body: KnowledgeBookSubscriptionWrite(bookId: id)
        )
    }

    public func unsubscribeBook(id: String) async throws {
        struct Response: Decodable { let deleted: Bool }
        _ = try await request(
            Response.self,
            path: "me/book-subscriptions",
            method: "DELETE",
            body: KnowledgeBookSubscriptionWrite(bookId: id)
        )
    }

    public func updateBookProgress(
        id: String, progress: Double, contentVersion: String
    ) async throws -> KnowledgeBookSubscriptionDTO {
        try await request(
            KnowledgeBookSubscriptionDTO.self,
            path: "me/book-subscriptions/progress",
            method: "PATCH",
            body: KnowledgeBookProgressWrite(
                bookId: id, progress: progress, contentVersion: contentVersion
            )
        )
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

    public func fetchKnowledgePublicationCandidates() async throws -> [KnowledgePublicationCandidateDTO] {
        let response: KnowledgePublicationCandidatesResponse = try await request(
            KnowledgePublicationCandidatesResponse.self,
            path: "admin/knowledge-publication"
        )
        return response.items
    }

    public func approveKnowledgePublication(
        path: String,
        securityLevel: String,
        entitlementKey: String,
        ownerTenant: String
    ) async throws -> KnowledgePublicationResultDTO {
        try await request(
            KnowledgePublicationResultDTO.self,
            path: "admin/knowledge-publication/approve",
            method: "POST",
            body: KnowledgePublicationDecisionDTO(
                path: path,
                securityLevel: securityLevel,
                entitlementKey: entitlementKey,
                ownerTenant: ownerTenant
            )
        )
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
        applyClientContract(to: &request)
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

    public func fetchTenantAgents(ownedOnly: Bool = false) async throws -> [TenantAgentDTO] {
        try await request(
            [TenantAgentDTO].self,
            path: "tenant-agents",
            queryItems: ownedOnly ? [URLQueryItem(name: "owned_only", value: "true")] : []
        )
    }

    /// GET /api/v1/skills：当前租户真实技能库（挂载目录扫描·非演示数据）
    public func fetchTenantSkills(ownedOnly: Bool = false) async throws -> [TenantSkillDTO] {
        let dto: TenantSkillsDTO = try await request(
            TenantSkillsDTO.self,
            path: "skills",
            queryItems: ownedOnly ? [URLQueryItem(name: "owned_only", value: "true")] : []
        )
        return dto.skills
    }

    /// POST /api/v1/tenant-agents：创建租户私有 Agent 切片（base_agent_id 限基线 4 个）
    public func createTenantAgent(_ body: TenantAgentCreateDTO) async throws -> TenantAgentDTO {
        try await request(TenantAgentDTO.self, path: "tenant-agents", method: "POST", body: body)
    }

    public func updateTenantAgent(id: String, body: TenantAgentCreateDTO) async throws -> TenantAgentDTO {
        try await request(TenantAgentDTO.self, path: "tenant-agents/\(encodedPath(id))", method: "PATCH", body: body)
    }

    /// DELETE /api/v1/tenant-agents/{id}：删除租户切片（204 无响应体）
    public func deleteTenantAgent(id: String) async throws {
        let url = baseURL
            .appendingPathComponent("api/v1/tenant-agents")
            .appendingPathComponent(id)
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        applyClientContract(to: &request)
        _ = try await perform(request, session: session, canRetry: false)
    }

    /// DELETE /api/v1/skills/{name}：仅删除当前认证租户的自制 Skill。
    public func deleteTenantSkill(name: String) async throws {
        let url = baseURL
            .appendingPathComponent("api/v1/skills")
            .appendingPathComponent(name)
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        applyClientContract(to: &request)
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

    public func deleteWorkflow(id: String) async throws {
        let url = baseURL
            .appendingPathComponent("api/v1/workflows")
            .appendingPathComponent(id)
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        applyClientContract(to: &request)
        _ = try await perform(request, session: session, canRetry: false)
    }

    public func createWorkflow(
        title: String,
        description: String,
        desiredOutput: String,
        sourceDocumentId: String? = nil
    ) async throws -> WorkflowCreateResponseDTO {
        try await request(
            WorkflowCreateResponseDTO.self,
            path: "workflows",
            method: "POST",
            body: WorkflowCreateRequestDTO(
                title: title,
                description: description,
                desiredOutput: desiredOutput,
                sourceDocumentId: sourceDocumentId
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
                    applyClientContract(to: &request)
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
                knowledgeScope: plan.knowledgeScope,
                expectedHash: plan.contentHash,
                expectedRevision: plan.activationRevision
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
                    applyClientContract(to: &request)
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

    public func uploadDocument(data: Data, filename: String, contentType: String, fileOptOut: Bool = false) async throws -> DocumentReceiptDTO {
        let url = baseURL.appendingPathComponent("api/v1/documents")
        var request = URLRequest(url: url); request.httpMethod = "POST"; request.httpBody = data
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        request.setValue(filename.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? "document", forHTTPHeaderField: "X-File-Name")
        request.setValue(SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined(), forHTTPHeaderField: "X-Content-Hash")
        if fileOptOut { request.setValue("true", forHTTPHeaderField: "X-File-Opt-Out") }
        applyClientContract(to: &request)
        let response = try await perform(request, session: session, canRetry: false)
        return try decoder.decode(DocumentReceiptDTO.self, from: response)
    }

    public func fetchDocument(sourceId: String) async throws -> DocumentReceiptDTO {
        try await request(
            DocumentReceiptDTO.self,
            path: "documents/\(encodedPath(sourceId))"
        )
    }

    public func downloadAuthenticated(path: String, expectedHash: String) async throws -> Data {
        let url = baseURL.appendingPathComponent("api/v1").appendingPathComponent(path)
        var request = URLRequest(url: url); request.httpMethod = "GET"; request.setValue("application/octet-stream", forHTTPHeaderField: "Accept"); applyClientContract(to: &request)
        let data = try await perform(request, session: session, canRetry: true)
        let actual = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        guard actual == expectedHash.lowercased() else { throw APIError.network("文件完整性校验失败") }
        return data
    }

    public func fetchAuthenticatedText(path: String) async throws -> String {
        let url = baseURL.appendingPathComponent("api/v1").appendingPathComponent(path)
        var request = URLRequest(url: url); request.httpMethod = "GET"; request.setValue("text/plain", forHTTPHeaderField: "Accept"); applyClientContract(to: &request)
        let data = try await perform(request, session: session, canRetry: true)
        guard let text = String(data: data, encoding: .utf8) else { throw APIError.decoding("文本编码无效") }
        return text
    }

    public func reviewPresentationStage(executionId: String, artifact: WorkflowArtifactDTO, decision: String, comment: String, slideNumber: Int? = nil) async throws -> WorkflowExecutionDTO {
        struct Body: Encodable {
            let artifactId, expectedHash: String; let artifactVersion: Int; let decision, comment: String; let slideNumber: Int?
            enum CodingKeys: String, CodingKey { case artifactId = "artifact_id", expectedHash = "expected_hash", artifactVersion = "artifact_version", decision, comment, slideNumber = "slide_number" }
        }
        return try await request(WorkflowExecutionDTO.self, path: "workflow-executions/\(encodedPath(executionId))/review-stage", method: "POST", body: Body(artifactId: artifact.id, expectedHash: artifact.contentHash, artifactVersion: artifact.metadata.artifactVersion ?? 1, decision: decision, comment: comment, slideNumber: slideNumber))
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

    @discardableResult
    public func syncKnowledgeNote(
        id: String,
        markdown: String,
        updatedAt: Date,
        baseHash: String? = nil,
        credentialGeneration: UInt64
    ) async throws -> KnowledgeNoteSyncResponseDTO {
        let key = "\(credentialGeneration):\(id)"
        let predecessor = knowledgeNoteSyncTails[key]
        let knownHash = knowledgeNoteSyncHashes[key]
        let contentHash = SHA256.hash(data: Data(markdown.utf8))
            .map { String(format: "%02x", $0) }
            .joined()
        let token = UUID()
        let task = Task { @MainActor [weak self] in
            _ = try? await predecessor?.task.value
            guard let self else { throw CancellationError() }
            return try await self.performKnowledgeNoteSync(
                id: id, markdown: markdown, updatedAt: updatedAt,
                contentHash: contentHash,
                baseHash: baseHash ?? predecessor?.contentHash ?? knownHash,
                credentialGeneration: credentialGeneration
            )
        }
        knowledgeNoteSyncTails[key] = (token, contentHash, task)
        do {
            let response = try await task.value
            if knowledgeNoteSyncTails[key]?.token == token {
                knowledgeNoteSyncTails.removeValue(forKey: key)
                knowledgeNoteSyncHashes[key] = response.contentHash
            }
            return response
        } catch {
            if knowledgeNoteSyncTails[key]?.token == token {
                knowledgeNoteSyncTails.removeValue(forKey: key)
            }
            throw error
        }
    }

    private func performKnowledgeNoteSync(
        id: String,
        markdown: String,
        updatedAt: Date,
        contentHash: String,
        baseHash: String?,
        credentialGeneration: UInt64
    ) async throws -> KnowledgeNoteSyncResponseDTO {
        struct Body: Encodable {
            let markdown: String
            let contentHash: String
            let baseHash: String?
            let updatedAt: String
            enum CodingKeys: String, CodingKey {
                case markdown
                case contentHash = "content_hash"
                case baseHash = "base_hash"
                case updatedAt = "updated_at"
            }
        }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return try await request(
            KnowledgeNoteSyncResponseDTO.self,
            path: "me/knowledge-notes/\(encodedPath(id))",
            method: "PUT",
            body: Body(
                markdown: markdown,
                contentHash: contentHash,
                baseHash: baseHash,
                updatedAt: formatter.string(from: updatedAt)
            ),
            credentialGeneration: credentialGeneration
        )
    }

    public func fetchKnowledgeNoteStatus(
        id: String, credentialGeneration: UInt64
    ) async throws -> KnowledgeNoteSyncStatusDTO {
        try await request(
            KnowledgeNoteSyncStatusDTO.self,
            path: "me/knowledge-notes/\(encodedPath(id))/status",
            credentialGeneration: credentialGeneration
        )
    }

    public func fetchKnowledgeNotes(includeArchived: Bool = true) async throws -> CloudKnowledgeNotesResponse {
        try await request(
            CloudKnowledgeNotesResponse.self,
            path: "me/knowledge-notes",
            queryItems: [
                URLQueryItem(name: "include_archived", value: includeArchived ? "true" : "false")
            ]
        )
    }

    public func mergeKnowledgeNotes(_ body: KnowledgeNoteMergeRequestDTO) async throws -> KnowledgeNoteMergeResponseDTO {
        try await request(
            KnowledgeNoteMergeResponseDTO.self,
            path: "me/knowledge-notes/merge",
            method: "POST",
            body: body
        )
    }

    public func archiveKnowledgeNote(
        id: String,
        mergedIntoNoteId: String,
        expectedContentHash: String? = nil
    ) async throws {
        struct Body: Encodable {
            let mergedIntoNoteId: String
            let expectedContentHash: String?
            enum CodingKeys: String, CodingKey {
                case mergedIntoNoteId = "merged_into_note_id"
                case expectedContentHash = "expected_content_hash"
            }
        }
        struct Response: Decodable { let archiveStatus: String }
        let _: Response = try await request(
            Response.self,
            path: "me/knowledge-notes/\(encodedPath(id))/archive",
            method: "POST",
            body: Body(
                mergedIntoNoteId: mergedIntoNoteId,
                expectedContentHash: expectedContentHash
            )
        )
    }

    public func restoreKnowledgeNote(id: String) async throws {
        struct Body: Encodable {}
        struct Response: Decodable { let archiveStatus: String }
        let _: Response = try await request(
            Response.self,
            path: "me/knowledge-notes/\(encodedPath(id))/restore",
            method: "POST",
            body: Body()
        )
    }

    public func trashKnowledgeNote(id: String) async throws {
        struct Body: Encodable {}
        struct Response: Decodable { let trashStatus: String }
        let _: Response = try await request(
            Response.self,
            path: "me/knowledge-notes/\(encodedPath(id))/trash",
            method: "POST",
            body: Body()
        )
    }

    public struct KnowledgeActionCommitResponse: Decodable, Sendable {
        public let actionId: String
        public let status: String
        public let resultNoteIds: [String]
    }

    public func commitKnowledgeAction(
        id: String,
        capability: String,
        actionDigest: String,
        status: String,
        resultNoteIds: [String],
        errorCode: String? = nil
    ) async throws -> KnowledgeActionCommitResponse {
        struct Body: Encodable {
            let capability: String
            let actionDigest: String
            let resultDigest: String
            let resultNoteIds: [String]
            let status: String
            let errorCode: String?
            enum CodingKeys: String, CodingKey {
                case capability, status
                case actionDigest = "action_digest"
                case resultDigest = "result_digest"
                case resultNoteIds = "result_note_ids"
                case errorCode = "error_code"
            }
        }
        let resultObject: [String: Any] = ["result_note_ids": resultNoteIds]
        let data = try JSONSerialization.data(withJSONObject: resultObject, options: [.sortedKeys, .withoutEscapingSlashes])
        let resultDigest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        return try await request(
            KnowledgeActionCommitResponse.self,
            path: "me/knowledge-actions/\(encodedPath(id))/commit",
            method: "POST",
            body: Body(
                capability: capability,
                actionDigest: actionDigest,
                resultDigest: resultDigest,
                resultNoteIds: resultNoteIds,
                status: status,
                errorCode: errorCode
            )
        )
    }

    public func resumeKnowledgeActionSync(
        id: String,
        actionDigest: String,
        status: String,
        resultNoteIds: [String],
        errorCode: String? = nil
    ) async throws -> KnowledgeActionCommitResponse {
        struct Body: Encodable {
            let actionDigest: String
            let resultDigest: String
            let resultNoteIds: [String]
            let status: String
            let errorCode: String?
            enum CodingKeys: String, CodingKey {
                case status
                case actionDigest = "action_digest"
                case resultDigest = "result_digest"
                case resultNoteIds = "result_note_ids"
                case errorCode = "error_code"
            }
        }
        let resultObject: [String: Any] = ["result_note_ids": resultNoteIds]
        let data = try JSONSerialization.data(withJSONObject: resultObject, options: [.sortedKeys, .withoutEscapingSlashes])
        let resultDigest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        return try await request(
            KnowledgeActionCommitResponse.self,
            path: "me/knowledge-actions/\(encodedPath(id))/resume-sync",
            method: "POST",
            body: Body(
                actionDigest: actionDigest,
                resultDigest: resultDigest,
                resultNoteIds: resultNoteIds,
                status: status,
                errorCode: errorCode
            )
        )
    }

    public func discardKnowledgeAction(id: String, capability: String, actionDigest: String) async throws {
        struct Body: Encodable {
            let capability: String
            let actionDigest: String
            enum CodingKeys: String, CodingKey {
                case capability
                case actionDigest = "action_digest"
            }
        }
        let _: KnowledgeActionCommitResponse = try await request(
            KnowledgeActionCommitResponse.self,
            path: "me/knowledge-actions/\(encodedPath(id))/discard",
            method: "POST",
            body: Body(capability: capability, actionDigest: actionDigest)
        )
    }

    /// POST /api/chat：真实问答 + 真实思维链（异步 data(for:)，URLRequest.timeoutInterval=200，
    /// Task.cancel 传播中断客户端等待；404 可区分（清 session_id 幂等重发一次），超时单独抛 `.timeout`）。
    public func chat(
        question: String,
        requestId: String? = nil,
        sessionId: String? = nil,
        quotedContext: String? = nil,
        agentId: String? = nil,
        contextScope: ChatContextScopeDTO = ChatContextScopeDTO(),
        clientSessionContext: ClientSessionContextDTO? = nil
    ) async throws -> ChatResponseDTO {
        let url = baseURL.appendingPathComponent("api/chat")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 200
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        applyClientContract(to: &request)
        request.httpBody = try JSONEncoder().encode(
            ChatRequestDTO(
                question: question,
                requestId: requestId,
                sessionId: sessionId,
                quotedContext: quotedContext,
                agentId: agentId,
                contextScope: contextScope,
                clientSessionContext: clientSessionContext
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
                throw APIError.fromHTTP(statusCode: http.statusCode, body: data)
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
    public enum StreamEvent: Sendable {
        case runCursor(runId: String, eventSequence: Int)
        case delta(String)
        case thought(String)
        case toolStart(id: String, tool: String, label: String)
        case toolComplete(id: String, tool: String)
        case clarify(question: String, choices: [String], multiSelect: Bool, source: String, clarifyId: String?, requestId: String?, expiresInSeconds: Int?)
        case clarifyExpired(clarifyId: String?, requestId: String?)
        case clarifyRejected
        case status(phase: String, detail: String)
        case feedbackReceipt(id: String, signalType: String, message: String, revocable: Bool)
        case memoryReceipt(id: String, message: String)
        case agentRoute(id: String, name: String, delegated: Bool, delegatedBy: String?)
        case noteDraft(id: String, title: String, markdown: String, tags: [String], sourceSessionId: String?, sourceMessageIds: [String], accountScope: String?, mergeCandidates: [NoteMergeCandidate], mergedTitle: String?, mergedMarkdown: String?, mergedTags: [String], operation: String?, targetNoteId: String?, targetNoteTitle: String?, targetContentHash: String?)
        case knowledgeActionDraft(KnowledgeActionBlock)
        case knowledgeNavigation(KnowledgeNavigationTarget)
        case answerPage(AnswerBlockPageDTO)
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
                    clarifyId: json["clarify_id"] as? String,
                    requestId: json["request_id"] as? String,
                    expiresInSeconds: json["expires_in_seconds"] as? Int
                )
            case "clarify_expired":
                return .clarifyExpired(
                    clarifyId: json["clarify_id"] as? String,
                    requestId: json["request_id"] as? String
                )
            case "clarify_rejected":
                return .clarifyRejected
            case "status":
                // 真实状态分相（boot/reasoning）：仅驱动 ThinkingPlaceholder 阶段文案
                return .status(
                    phase: json["phase"] as? String ?? "",
                    detail: json["detail"] as? String ?? ""
                )
            case "feedback_receipt":
                return .feedbackReceipt(
                    id: json["feedback_id"] as? String ?? "",
                    signalType: json["signal_type"] as? String ?? "inferred",
                    message: json["message"] as? String ?? "已作为产品改进反馈记录；输入‘撤销刚才的反馈’可撤销",
                    revocable: json["revocable"] as? Bool ?? false
                )
            case "memory_receipt":
                return .memoryReceipt(
                    id: json["memory_id"] as? String ?? "",
                    message: json["message"] as? String ?? "Quantum 已更新长期记忆"
                )
            case "agent_route":
                let agent = json["agent"] as? [String: Any] ?? [:]
                return .agentRoute(
                    id: agent["id"] as? String ?? "",
                    name: agent["name"] as? String ?? "专属 Agent",
                    delegated: agent["delegated"] as? Bool ?? false,
                    delegatedBy: json["delegated_by"] as? String
                )
            case "note_draft":
                let mergeCandidates = (json["merge_candidates"] as? [[String: Any]] ?? []).compactMap { item -> NoteMergeCandidate? in
                    guard let id = item["id"] as? String, !id.isEmpty else { return nil }
                    return NoteMergeCandidate(
                        id: id,
                        title: item["title"] as? String ?? "无标题",
                        snippet: item["snippet"] as? String ?? "",
                        updatedAt: item["updated_at"] as? String
                    )
                }
                return .noteDraft(
                    id: json["draft_id"] as? String ?? "",
                    title: json["title"] as? String ?? "无标题",
                    markdown: json["markdown"] as? String ?? "",
                    tags: json["tags"] as? [String] ?? [],
                    sourceSessionId: json["source_session_id"] as? String,
                    sourceMessageIds: json["source_message_ids"] as? [String] ?? [],
                    accountScope: json["account_scope"] as? String,
                    mergeCandidates: mergeCandidates,
                    mergedTitle: json["merged_title"] as? String,
                    mergedMarkdown: json["merged_markdown"] as? String,
                    mergedTags: json["merged_tags"] as? [String] ?? [],
                    operation: json["operation"] as? String,
                    targetNoteId: json["target_note_id"] as? String,
                    targetNoteTitle: json["target_note_title"] as? String,
                    targetContentHash: json["target_content_hash"] as? String
                )
            case "knowledge_action_draft":
                let steps = (json["steps"] as? [[String: Any]] ?? []).compactMap { item -> KnowledgeActionStep? in
                    guard let kind = item["kind"] as? String, !kind.isEmpty else { return nil }
                    return KnowledgeActionStep(
                        kind: kind,
                        targetNoteId: item["target_note_id"] as? String,
                        sourceNoteIds: item["source_note_ids"] as? [String] ?? [],
                        title: item["title"] as? String,
                        markdown: item["markdown"] as? String,
                        tags: item["tags"] as? [String] ?? [],
                        pinned: item["pinned"] as? Bool,
                        linkTitle: item["link_title"] as? String,
                        originalContentHash: item["original_content_hash"] as? String,
                        sourceContentHashes: (item["source_content_hashes"] as? [String: Any] ?? [:])
                            .mapValues { $0 as? String }
                    )
                }
                let navigationJSON = json["suggested_navigation"] as? [String: Any]
                let navigation = navigationJSON.flatMap { value -> KnowledgeNavigationTarget? in
                    guard let destination = value["destination"] as? String else { return nil }
                    return KnowledgeNavigationTarget(
                        destination: destination,
                        noteId: value["note_id"] as? String,
                        query: value["query"] as? String
                    )
                }
                let scopeJSON = json["account_scope"] as? [String: Any]
                let accountScope = scopeJSON.map {
                    "\($0["tenant_namespace"] as? String ?? ""):\($0["user_namespace"] as? String ?? "")"
                }
                return .knowledgeActionDraft(KnowledgeActionBlock(
                    id: json["action_id"] as? String ?? "",
                    summary: json["summary"] as? String ?? "知识库修改",
                    steps: steps,
                    beforePreview: json["before_preview"] as? String ?? "",
                    afterPreview: json["after_preview"] as? String ?? "",
                    markdownDiff: json["markdown_diff"] as? String ?? "",
                    riskLevel: json["risk_level"] as? String ?? "low",
                    actionDigest: json["action_digest"] as? String ?? "",
                    transientCapability: json["knowledge_action_capability"] as? String,
                    expiresAt: json["expires_at"] as? Int ?? 0,
                    accountScope: accountScope,
                    suggestedNavigation: navigation
                ))
            case "knowledge_navigation":
                guard let destination = json["destination"] as? String else { return nil }
                return .knowledgeNavigation(KnowledgeNavigationTarget(
                    destination: destination,
                    noteId: json["note_id"] as? String,
                    query: json["query"] as? String
                ))
            case "answer_page":
                let blockDecoder = JSONDecoder()
                blockDecoder.keyDecodingStrategy = .convertFromSnakeCase
                guard let data = try? JSONSerialization.data(withJSONObject: json),
                      let page = try? blockDecoder.decode(AnswerBlockPageDTO.self, from: data)
                else { return nil }
                return .answerPage(page)
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

    public func prewarmChat(sessionId: String, agentId: String?) async throws {
        let url = baseURL.appendingPathComponent("api/chat/prewarm")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        applyClientContract(to: &request)
        request.httpBody = try JSONEncoder().encode(
            ChatPrewarmRequestDTO(sessionId: sessionId, agentId: agentId)
        )
        _ = try await perform(
            request, session: session, canRetry: false, reauthOn401: false
        )
    }

    /// POST /api/chat/stream：URLSession.bytes 逐行消费 SSE 事件流（真实流式）
    /// - Parameter quotedContext: 引用历史消息上下文（若有）
    /// - Returns: AsyncThrowingStream 事件流。传输层取消只会断开订阅；不会取消服务端 Run。
    ///   服务端 Bridge 会将断开的 Run detach 后继续执行，调用方需通过 status 恢复。
    ///   只有明确的用户取消操作才应调用 ``cancelStream``。
    public func chatStream(
        question: String,
        requestId: String? = nil,
        sessionId: String? = nil,
        quotedContext: String? = nil,
        regenerate: Bool = false,
        agentId: String? = nil,
        contextScope: ChatContextScopeDTO = ChatContextScopeDTO(),
        clientSessionContext: ClientSessionContextDTO? = nil
    ) -> AsyncThrowingStream<StreamEvent, Error> {
        AsyncThrowingStream { continuation in
            let url = baseURL.appendingPathComponent("api/chat/stream")
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.timeoutInterval = 60  // 空闲保活（30s keepalive 帧持续刷新）
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
            applyClientContract(to: &request)
            request.httpBody = try? JSONEncoder().encode(
                ChatRequestDTO(
                    question: question,
                    requestId: requestId,
                    sessionId: sessionId,
                    quotedContext: quotedContext,
                    agentId: agentId,
                    regenerate: regenerate,
                    contextScope: contextScope,
                    clientSessionContext: clientSessionContext
                )
            )

            // APIClient 作为 ObservableObject 受 MainActor 隔离，但 SSE 解码是持续的
            // 网络/JSON 工作，不应继承主线程执行器。快照 URLSession 后放到 detached
            // task，避免长回答期间与 SwiftUI 渲染、滚动及输入竞争主线程。
            let activeStreamSession = streamSession
            let consumeTask = Task.detached(priority: .userInitiated) {
                do {
                    let (bytes, response) = try await activeStreamSession.bytes(for: request)
                    guard let http = response as? HTTPURLResponse else {
                        continuation.finish(throwing: APIError.network("无效响应"))
                        return
                    }
                    guard (200..<300).contains(http.statusCode) else {
                        continuation.finish(throwing: http.statusCode == 403
                            ? APIError.knowledgeScopeChanged
                            : APIError.server(http.statusCode, "流式端点错误"))
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
                                if let runId = json["run_id"] as? String, !runId.isEmpty {
                                    continuation.yield(.runCursor(
                                        runId: runId,
                                        eventSequence: json["event_sequence"] as? Int ?? 0
                                    ))
                                }
                                continuation.yield(event)
                            }
                        } else {
                            // 半行缓冲（SSE 行可能被 TCP 分包）
                            buffer += line
                            if buffer.hasPrefix("data: "),
                               let data = buffer.dropFirst(6).data(using: .utf8),
                               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                               let event = StreamEvent.parse(json) {
                                if let runId = json["run_id"] as? String, !runId.isEmpty {
                                    continuation.yield(.runCursor(
                                        runId: runId,
                                        eventSequence: json["event_sequence"] as? Int ?? 0
                                    ))
                                }
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
                // AsyncSequence 的 .cancelled 同时覆盖 SwiftUI owner 释放、Tab/scene
                // 生命周期变化和真正的用户取消，不能据此推断用户意图。这里只断开
                // URLSession；Bridge 会 detach worker，结果由 status 端点恢复。
                _ = termination
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
        applyClientContract(to: &request)
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
    ) async throws -> ClarifySubmitResult {
        guard let sessionId, !sessionId.isEmpty else {
            return ClarifySubmitResult(ok: false, state: "no_pending", clarifyId: clarifyId)
        }
        let url = baseURL.appendingPathComponent("api/chat/stream/clarify")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 10
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        applyClientContract(to: &request)
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
        return try decoder.decode(ClarifySubmitResult.self, from: data)
    }

    public func fetchDurableChatRun(
        runId: String,
        after eventSequence: Int
    ) async throws -> DurableChatReplayDTO {
        let url = baseURL
            .appendingPathComponent("api/chat/runs")
            .appendingPathComponent(encodedPath(runId))
        var components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        components?.queryItems = [
            URLQueryItem(name: "after", value: String(max(0, eventSequence))),
            URLQueryItem(name: "answer_blocks_v1", value: "true")
        ]
        guard let resolved = components?.url else { throw APIError.invalidURL }
        var request = URLRequest(url: resolved)
        request.timeoutInterval = 20
        applyClientContract(to: &request)
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw APIError.network("无效响应")
        }
        guard (200..<300).contains(http.statusCode) else {
            throw http.statusCode == 401
                ? APIError.unauthorized
                : APIError.server(http.statusCode, "Run 回放失败")
        }
        return try Self.decodeDurableChatReplay(data)
    }

    static func decodeDurableChatReplay(_ data: Data) throws -> DurableChatReplayDTO {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let replay = try decoder.decode(DurableChatReplayDTO.self, from: data)
        let root = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        let events = (root?["events"] as? [[String: Any]] ?? []).compactMap(StreamEvent.parse)
        return DurableChatReplayDTO(
            run: replay.run,
            droppedEventCount: replay.droppedEventCount,
            events: events
        )
    }

    public func fetchAnswerBlocks(
        runId: String, cursor: String?, maxBlocks: Int = 10
    ) async throws -> AnswerBlockPageDTO {
        let url = baseURL.appendingPathComponent("api/chat/runs")
            .appendingPathComponent(encodedPath(runId)).appendingPathComponent("blocks")
        var components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        var items = [URLQueryItem(name: "max_blocks", value: String(min(max(maxBlocks, 1), 20)))]
        if let cursor { items.append(URLQueryItem(name: "cursor", value: cursor)) }
        components?.queryItems = items
        guard let resolved = components?.url else { throw APIError.invalidURL }
        var request = URLRequest(url: resolved)
        request.timeoutInterval = 20
        applyClientContract(to: &request)
        let data = try await perform(request, session: session, canRetry: true, reauthOn401: false)
        return try decoder.decode(AnswerBlockPageDTO.self, from: data)
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
        var comps = URLComponents(url: url, resolvingAgainstBaseURL: false)
        var items: [URLQueryItem] = [URLQueryItem(name: "answer_blocks_v1", value: "true")]
        if consume { items.append(URLQueryItem(name: "consume", value: "1")) }
        if let agentId { items.append(URLQueryItem(name: "agent_id", value: agentId)) }
        comps?.queryItems = items
        if let u = comps?.url { url = u }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = 15
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        applyClientContract(to: &request)
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

    /// GET /api/v1/usage/summary — 当前登录用户的服务端 LLM 用量账本。
    public func fetchUsageSummary(days: Int = 30) async throws -> UsageSummaryDTO {
        var components = URLComponents(
            url: baseURL
                .appendingPathComponent("api/v1")
                .appendingPathComponent("usage/summary"),
            resolvingAgainstBaseURL: false
        )
        components?.queryItems = [URLQueryItem(name: "days", value: String(days))]
        guard let url = components?.url else { throw APIError.invalidURL }
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "GET"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Accept")
        applyClientContract(to: &urlRequest)
        let data = try await perform(urlRequest, session: session, canRetry: true)
        do {
            return try decoder.decode(UsageSummaryDTO.self, from: data)
        } catch {
            throw APIError.decoding(Self.describeDecodingError(error))
        }
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

    public func fetchAuthCapabilities() async throws -> AuthCapabilitiesDTO {
        try await request(
            AuthCapabilitiesDTO.self,
            path: "auth/capabilities",
            reauthOn401: false,
            anonymous: true
        )
    }

    public func fetchAgreement(allowCache: Bool = true) async throws -> AgreementDTO {
        do {
            let agreement = try await request(
                AgreementDTO.self,
                path: "legal/agreement",
                queryItems: [URLQueryItem(name: "locale", value: "zh-CN")],
                reauthOn401: false
            )
            if agreement.sections.map(\.id) == ["service", "privacy", "knowledge-contribution"],
               let data = try? JSONEncoder().encode(agreement) {
                UserDefaults.standard.set(data, forKey: "legal.agreement.zh-CN.cache")
                return agreement
            }
            throw APIError.decoding("协议章节不完整")
        } catch {
            guard allowCache,
                  let data = UserDefaults.standard.data(forKey: "legal.agreement.zh-CN.cache"),
                  let cached = try? JSONDecoder().decode(AgreementDTO.self, from: data),
                  cached.sections.map(\.id) == ["service", "privacy", "knowledge-contribution"]
            else { throw error }
            return cached
        }
    }

    public func fetchAgreementAcceptance() async throws -> AgreementAcceptanceDTO {
        try await request(AgreementAcceptanceDTO.self, path: "me/agreement-acceptance")
    }

    public func acceptAgreement(
        version: String, idempotencyKey: String
    ) async throws -> AgreementAcceptanceDTO {
        try await request(
            AgreementAcceptanceDTO.self,
            path: "me/agreement-acceptance",
            method: "PUT",
            body: AgreementAcceptanceBody(
                agreementVersion: version, idempotencyKey: idempotencyKey
            ),
            reauthOn401: false
        )
    }

    public func sendPhoneCode(phone: String) async throws {
        struct Body: Encodable { let phone: String }
        struct Response: Decodable { let success: Bool }
        let _: Response = try await request(
            Response.self,
            path: "auth/phone/send-code",
            method: "POST",
            body: Body(phone: phone),
            reauthOn401: false
        )
    }

    public func loginWithPhone(phone: String, code: String) async throws -> LoginSessionDTO {
        struct Body: Encodable { let phone: String; let code: String }
        return try await request(
            LoginSessionDTO.self,
            path: "auth/phone/login",
            method: "POST",
            body: Body(phone: phone, code: code),
            reauthOn401: false
        )
    }

    /// POST /api/v1/dev-login：服务端显式开启时，开发者账号免短信登录。
    public func developerLogin(phone: String, verificationCode: String) async throws -> LoginSessionDTO {
        struct Body: Encodable {
            let phone: String
            let verificationCode: String

            enum CodingKeys: String, CodingKey {
                case phone
                case verificationCode = "verification_code"
            }
        }
        return try await request(
            LoginSessionDTO.self,
            path: "dev-login",
            method: "POST",
            body: Body(phone: phone, verificationCode: verificationCode),
            reauthOn401: false
        )
    }

    public func startOAuth(provider: String) async throws -> OAuthStartDTO {
        try await request(
            OAuthStartDTO.self,
            path: "auth/oauth/\(provider)/start",
            queryItems: [URLQueryItem(name: "client", value: "ios")],
            reauthOn401: false
        )
    }

    public func completeOAuth(ticket: String) async throws -> LoginSessionDTO {
        struct Body: Encodable { let ticket: String }
        return try await request(
            LoginSessionDTO.self,
            path: "auth/oauth/complete",
            method: "POST",
            body: Body(ticket: ticket),
            reauthOn401: false
        )
    }
}
