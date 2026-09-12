import XCTest
import SwiftUI
import SQLite3
import Combine
#if canImport(UIKit)
import UIKit
#endif
import Security
@testable import AIPlatformApp

private final class LockedErrorBox: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [Error] = []

    func append(_ error: Error) {
        lock.lock()
        storage.append(error)
        lock.unlock()
    }

    var isEmpty: Bool {
        lock.lock()
        defer { lock.unlock() }
        return storage.isEmpty
    }
}

private final class APIContractURLProtocol: URLProtocol, @unchecked Sendable {
    struct CapturedRequest {
        let request: URLRequest
        let body: Data?
    }

    private static let lock = NSLock()
    private static var capturedRequests: [CapturedRequest] = []

    static func reset() {
        lock.lock()
        capturedRequests = []
        lock.unlock()
    }

    static func requests() -> [CapturedRequest] {
        lock.lock()
        defer { lock.unlock() }
        return capturedRequests
    }

    override class func canInit(with request: URLRequest) -> Bool { true }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let requestBody = Self.bodyData(from: request)
        Self.lock.lock()
        Self.capturedRequests.append(CapturedRequest(request: request, body: requestBody))
        Self.lock.unlock()

        let path = request.url?.path ?? ""
        let method = request.httpMethod ?? ""
        let isContractOrigin = request.url?.scheme == "https"
            && request.url?.host == "contract.invalid"
        let responseBody: Data
        var responseStatus = 200
        var responseError: URLError?
        switch (isContractOrigin, method, path) {
        case (true, "GET", "/api/v1/auth/capabilities"):
            // TEST FIXTURE: delayed public success exposes credential-generation races.
            responseBody = Data(#"{"phone":{"enabled":true},"oauth":{"wechat":{"enabled":false},"alipay":{"enabled":true}}}"#.utf8)
        case (true, "GET", "/api/v1/workflow-activities/active"):
            responseStatus = 401
            responseBody = Data(#"{"detail":"test fixture unauthorized"}"#.utf8)
        case (true, "GET", "/api/v1/legal/agreement"):
            responseBody = Data(#"{"version":"2026-09-06","title":"服务协议","updated_at":"2026-09-06T00:00:00Z","sections":[{"id":"service","title":"用户服务协议","clauses":["服务条款"]},{"id":"privacy","title":"隐私保护条款","clauses":["隐私条款"]},{"id":"knowledge-contribution","title":"知识共建协议","clauses":["共建条款"]}]}"#.utf8)
        case (true, "PUT", "/api/v1/me/agreement-acceptance"):
            let body = (try? JSONSerialization.jsonObject(with: requestBody ?? Data())) as? [String: Any]
            if body?["idempotency_key"] as? String == "simulate-failure" {
                responseStatus = 503
                responseBody = Data(#"{"detail":{"code":"unavailable"}}"#.utf8)
            } else {
                responseBody = Data(#"{"agreement_version":"2026-09-06","accepted_at":"2026-09-06T08:00:00Z"}"#.utf8)
            }
        case (true, "PUT", "/api/v1/me/book-subscriptions"),
             (true, "PATCH", "/api/v1/me/book-subscriptions/progress"):
            responseBody = Self.subscriptionResponse
        case (true, "DELETE", "/api/v1/me/book-subscriptions"):
            responseBody = Data(#"{"deleted":true}"#.utf8)
        case (true, "PUT", let notePath) where notePath.hasPrefix("/api/v1/me/knowledge-notes/"):
            let body = String(data: requestBody ?? Data(), encoding: .utf8) ?? ""
            let object = (try? JSONSerialization.jsonObject(with: requestBody ?? Data())) as? [String: Any]
            let contentHash = object?["content_hash"] as? String ?? String(repeating: "a", count: 64)
            responseStatus = body.contains("delayed-401") ? 401 : 200
            responseError = body.contains("lost-response") ? URLError(.timedOut) : nil
            responseBody = Data("{\"note_id\":\"note-1\",\"content_hash\":\"\(contentHash)\",\"changed\":true,\"sync_status\":\"synced\",\"compile_status\":\"pending\",\"private_index_hash\":null}".utf8)
        default:
            responseBody = Data(#"{"detail":"unexpected contract request"}"#.utf8)
        }
        let isAllowed = !(String(data: responseBody, encoding: .utf8)?.contains("unexpected contract") ?? true)
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: isAllowed ? responseStatus : 418,
            httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
        let deliver = { [self] in
            if let responseError {
                client?.urlProtocol(self, didFailWithError: responseError)
                return
            }
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: responseBody)
            client?.urlProtocolDidFinishLoading(self)
        }
        if path == "/api/v1/auth/capabilities" || path.hasPrefix("/api/v1/me/knowledge-notes/") {
            DispatchQueue.global().asyncAfter(deadline: .now() + 0.1, execute: deliver)
        } else {
            deliver()
        }
    }

    override func stopLoading() {}

    private static func bodyData(from request: URLRequest) -> Data? {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return nil }
        stream.open()
        defer { stream.close() }
        var body = Data()
        var buffer = [UInt8](repeating: 0, count: 1_024)
        while true {
            let count = stream.read(&buffer, maxLength: buffer.count)
            guard count > 0 else { break }
            body.append(contentsOf: buffer.prefix(count))
        }
        return body
    }

    private static let subscriptionResponse = Data(#"{"book":{"id":"kn-1","title":"AI Lab 顶层设计","author":"AI Lab","author_source":"curated","summary":"架构说明","cover_theme":"product","cover_variant":2,"cover_version":1,"security_level":"green","knowledge_level":"K5","freshness":"current","source_count":3},"edition":1,"content_version":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","progress":0.42,"subscribed_at":"2026-09-06T08:00:00Z","last_read_at":"2026-09-06T08:10:00Z"}"#.utf8)
}

final class WorkflowLifecycleDTOTests: XCTestCase {
    func testUsageSummaryDecodesCacheBreakdownWithoutInference() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let payload = Data(#"{"days":30,"total_calls":2,"success_calls":2,"failed_calls":0,"input_tokens":90,"output_tokens":10,"cache_read_tokens":0,"cache_write_tokens":7,"total_tokens":123,"missing_usage_calls":0,"token_total_basis":"verified_requests_only","legacy_unverified_total_tokens":45,"legacy_unverified_calls":1,"unverified_calls":1,"reconciliation_required":true,"usage_state":"partial","daily":[{"date":"2026-09-12","calls":2,"input_tokens":90,"output_tokens":10,"cache_read_tokens":4,"cache_write_tokens":null,"total_tokens":123}],"models":[{"provider":"fixture","model":"fixture-model","calls":2,"input_tokens":90,"output_tokens":10,"cache_read_tokens":null,"cache_write_tokens":7,"total_tokens":123,"missing_usage_calls":0}],"quota":null}"#.utf8)

        let summary = try decoder.decode(UsageSummaryDTO.self, from: payload)

        XCTAssertEqual(summary.totalTokens, 123)
        XCTAssertEqual(summary.cacheReadTokens, 0)
        XCTAssertEqual(summary.cacheWriteTokens, 7)
        XCTAssertEqual(summary.daily.first?.cacheReadTokens, 4)
        XCTAssertNil(summary.daily.first?.cacheWriteTokens)
        XCTAssertNil(summary.models.first?.cacheReadTokens)
        XCTAssertEqual(summary.models.first?.cacheWriteTokens, 7)
        XCTAssertEqual(summary.tokenTotalBasis, "verified_requests_only")
        XCTAssertEqual(summary.legacyUnverifiedTotalTokens, 45)
        XCTAssertEqual(summary.legacyUnverifiedCalls, 1)
        XCTAssertEqual(summary.unverifiedCalls, 1)
        XCTAssertEqual(summary.reconciliationRequired, true)
        XCTAssertEqual(summary.usageState, "partial")
        XCTAssertEqual(summary.usageTitle, "已核验用量")
        XCTAssertEqual(summary.usagePeriodCaption, "近 30 天已核验用量")
        XCTAssertTrue(summary.coverageNotices.contains("1 次历史记录待核验、不计入该数值"))
        XCTAssertTrue(summary.coverageNotices.contains("当前范围仅部分调用已核验；1 次未核验调用不计入该数值"))
    }

    func testUsageSummaryKeepsMissingCacheBreakdownUnavailable() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let payload = Data(#"{"days":7,"total_calls":1,"success_calls":1,"failed_calls":0,"input_tokens":80,"output_tokens":20,"total_tokens":150,"missing_usage_calls":0,"daily":[{"date":"2026-09-11","calls":1,"input_tokens":80,"output_tokens":20,"total_tokens":150}],"models":[{"provider":"legacy","model":"legacy-model","calls":1,"input_tokens":80,"output_tokens":20,"total_tokens":150,"missing_usage_calls":0}],"quota":null}"#.utf8)

        let summary = try decoder.decode(UsageSummaryDTO.self, from: payload)

        XCTAssertEqual(summary.totalTokens, 150)
        XCTAssertNil(summary.cacheReadTokens)
        XCTAssertNil(summary.cacheWriteTokens)
        XCTAssertNil(summary.daily.first?.cacheReadTokens)
        XCTAssertNil(summary.daily.first?.cacheWriteTokens)
        XCTAssertNil(summary.models.first?.cacheReadTokens)
        XCTAssertNil(summary.models.first?.cacheWriteTokens)
        XCTAssertNil(summary.tokenTotalBasis)
        XCTAssertNil(summary.usageState)
        XCTAssertEqual(summary.usageTitle, "服务端用量账本")
        XCTAssertEqual(summary.usagePeriodCaption, "近 7 天账本记录")
        XCTAssertEqual(summary.coverageNotices, ["当前服务未标注核验口径；该数值仅为服务端用量账本"])
    }

    func testUsageSummaryDoesNotPresentUnverifiedZeroAsOverallZero() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let payload = Data(#"{"days":30,"total_calls":3,"success_calls":3,"failed_calls":0,"input_tokens":0,"output_tokens":0,"total_tokens":0,"missing_usage_calls":3,"token_total_basis":"verified_requests_only","legacy_unverified_total_tokens":900,"legacy_unverified_calls":3,"unverified_calls":3,"reconciliation_required":true,"usage_state":"partial","daily":[],"models":[],"quota":null}"#.utf8)

        let summary = try decoder.decode(UsageSummaryDTO.self, from: payload)

        XCTAssertEqual(summary.usageTitle, "已核验用量")
        XCTAssertTrue(summary.coverageNotices.contains("3 次历史记录待核验、不计入该数值"))
        XCTAssertTrue(summary.coverageNotices.contains("3 次调用缺少 Token usage，未计入该数值"))
        XCTAssertTrue(summary.coverageNotices.contains("当前范围没有已核验覆盖；0 仅表示已核验子集，不代表整体用量为 0"))
    }

    @MainActor
    func testTokenSummaryCacheBreakdownScreenshotFixtures() throws {
        #if canImport(UIKit)
        let summary = UsageSummaryDTO(
            days: 30, totalCalls: 2, successCalls: 2, failedCalls: 0,
            inputTokens: 90, outputTokens: 10, cacheReadTokens: 0, cacheWriteTokens: 7,
            totalTokens: 123, missingUsageCalls: 0,
            tokenTotalBasis: "verified_requests_only", legacyUnverifiedTotalTokens: 0,
            legacyUnverifiedCalls: 0, unverifiedCalls: 0,
            reconciliationRequired: false, usageState: "complete",
            daily: [], models: [], quota: nil
        )
        attachScreenshot(
            TokenSummaryCard(summary: summary).preferredColorScheme(.light).padding(),
            name: "token-summary-cache-breakdown-light-fixture",
            height: 760
        )
        attachScreenshot(
            TokenSummaryCard(summary: UsageSummaryDTO(
                days: 30, totalCalls: 2, successCalls: 2, failedCalls: 0,
                inputTokens: 90, outputTokens: 10, cacheReadTokens: nil, cacheWriteTokens: nil,
                totalTokens: 123, missingUsageCalls: 0,
                tokenTotalBasis: nil, legacyUnverifiedTotalTokens: nil,
                legacyUnverifiedCalls: nil, unverifiedCalls: nil,
                reconciliationRequired: nil, usageState: nil,
                daily: [], models: [], quota: nil
            )).preferredColorScheme(.light).padding(),
            name: "token-summary-cache-breakdown-unavailable-light-fixture",
            height: 760
        )
        #else
        throw XCTSkip("UIKit screenshot attachments require the iOS test host")
        #endif
    }

    func testHermesMemoryCenterDecodesNativeProfileContract() throws {
        let payload = Data(#"{"items":[{"id":"mem_abc","target":"user","content":"偏好结论先行"}],"limits":{"user":1375,"memory":2200},"usage":{"user":6,"memory":0},"review_interval_turns":10}"#.utf8)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let center = try decoder.decode(HermesMemoryCenterDTO.self, from: payload)

        XCTAssertEqual(center.items.first?.id, "mem_abc")
        XCTAssertEqual(center.items.first?.target, "user")
        XCTAssertEqual(center.limits["memory"], 2_200)
        XCTAssertEqual(center.reviewIntervalTurns, 10)
    }

    func testNativeChatPresentationUsesTruthfulSingleRunningState() {
        let steps = [
            ReasoningStep(
                id: "tool-1", type: .toolCall, title: "查阅公开资料",
                detail: "正在比对公开时间线", status: "running"
            )
        ]
        let presentation = ChatRunningPresentation(
            assistantName: nil,
            phase: "reasoning",
            phaseDetail: nil,
            progress: nil,
            steps: steps
        )
        let message = ChatMessage(
            role: .assistant, content: "部分正文", isStreaming: true,
            blocks: [.reasoning(steps)], pending: true
        )
        let emptyPending = ChatMessage(
            role: .assistant, content: "", blocks: [.reasoning(steps)], pending: true
        )

        XCTAssertEqual(presentation.assistantName, "Quantumn 助手")
        XCTAssertEqual(presentation.title, "正在查阅资料")
        XCTAssertEqual(presentation.detail, "正在比对公开时间线")
        XCTAssertFalse(presentation.assistantName.contains("(name)"))
        XCTAssertEqual(message.reasoningSteps, steps)
        XCTAssertFalse(message.showsSeparateRecoveryHint)
        XCTAssertTrue(emptyPending.usesPendingPlaceholder)
        XCTAssertEqual(emptyPending.reasoningSteps, steps)
    }

    func testNativeReaderShowsWaitingPartialAndCompletedContentStates() {
        let partial = AnswerBlockDTO(blockIndex: 0, kind: "markdown", content: "已到达正文")

        XCTAssertEqual(
            LongAnswerSheet.presentationState(content: "", serverBlocks: [], isRunning: true),
            .waiting
        )
        XCTAssertEqual(
            LongAnswerSheet.presentationState(content: "", serverBlocks: [partial], isRunning: true),
            .partial
        )
        XCTAssertEqual(
            LongAnswerSheet.presentationState(content: "完整正文", serverBlocks: [], isRunning: false),
            .completed
        )
        XCTAssertEqual(
            LongAnswerSheet.presentationState(content: "", serverBlocks: [], isRunning: false),
            .empty
        )
        XCTAssertFalse(QuantumReaderWaitingView.shouldAnimate(reduceMotion: true))
        XCTAssertTrue(QuantumReaderWaitingView.shouldAnimate(reduceMotion: false))
    }

    @MainActor
    func testNativeQuantumnSyntheticScreenshotFixtures() throws {
        #if canImport(UIKit)
        attachScreenshot(
            ThinkingPlaceholderView(
                seconds: 12,
                phase: "reasoning",
                phaseDetail: "正在比对公开时间线",
                steps: [
                    ReasoningStep(
                        type: .toolCall, title: "查阅公开资料",
                        detail: "正在比对公开时间线", status: "running"
                    )
                ],
                onCancel: {}
            ),
            name: "quantumn-running-card",
            height: 300
        )
        attachScreenshot(QuantumReaderWaitingView(), name: "quantumn-reader-waiting", height: 520)
        attachScreenshot(
            LongAnswerSheet(
                messageId: "fixture-complete",
                content: "# 已完成原文\n\n这是用于原生组件截图检查的合成正文。",
                serverBlocks: [], availableBlockCount: 1,
                hasMore: false, isRunning: false, fetchFull: nil
            ),
            name: "quantumn-reader-complete",
            height: 760
        )
        #else
        throw XCTSkip("UIKit screenshot attachments require the iOS test host")
        #endif
    }

    #if canImport(UIKit)
    @MainActor
    private func attachScreenshot<Content: View>(
        _ content: Content,
        name: String,
        height: CGFloat
    ) {
        let size = CGSize(width: 375, height: height)
        let controller = UIHostingController(
            rootView: content
                .frame(width: size.width, height: size.height)
                .background(AppTheme.Colors.background)
        )
        controller.view.bounds = CGRect(origin: .zero, size: size)
        controller.view.backgroundColor = .clear
        controller.view.setNeedsLayout()
        controller.view.layoutIfNeeded()
        let image = UIGraphicsImageRenderer(size: size).image { _ in
            controller.view.drawHierarchy(in: controller.view.bounds, afterScreenUpdates: true)
        }
        let attachment = XCTAttachment(image: image)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
    #endif
    @MainActor
    func testBookWritesMatchBackendWireContract() async throws {
        APIContractURLProtocol.reset()
        defer { APIContractURLProtocol.reset() }

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [APIContractURLProtocol.self]
        let client = APIClient(
            baseURL: try XCTUnwrap(URL(string: "https://contract.invalid")),
            sessionConfiguration: configuration,
            inMemoryToken: "[REDACTED]"
        )
        let contentVersion = String(repeating: "a", count: 64)

        let subscription = try await client.subscribeBook(id: "kn-1")
        let progress = try await client.updateBookProgress(
            id: "kn-1", progress: 0.42, contentVersion: contentVersion
        )
        try await client.unsubscribeBook(id: "kn-1")

        XCTAssertEqual(subscription.contentVersion, contentVersion)
        XCTAssertEqual(progress.book.authorSource, "curated")

        let requests = APIContractURLProtocol.requests()
        XCTAssertEqual(requests.count, 3)
        XCTAssertEqual(
            requests.map { "\($0.request.httpMethod ?? "") \($0.request.url?.path ?? "")" },
            [
                "PUT /api/v1/me/book-subscriptions",
                "PATCH /api/v1/me/book-subscriptions/progress",
                "DELETE /api/v1/me/book-subscriptions",
            ]
        )
        for captured in requests {
            let request = captured.request
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer [REDACTED]")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-Client-Contract"), APIClient.clientContract)
            XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")
        }

        let bodies = try requests.map { captured in
            try XCTUnwrap(
                JSONSerialization.jsonObject(with: try XCTUnwrap(captured.body)) as? [String: Any]
            )
        }
        XCTAssertEqual(Set(bodies[0].keys), Set(["book_id", "edition"]))
        XCTAssertEqual(bodies[0]["book_id"] as? String, "kn-1")
        XCTAssertEqual(bodies[0]["edition"] as? Int, 1)
        XCTAssertEqual(Set(bodies[1].keys), Set(["book_id", "progress", "content_version"]))
        XCTAssertEqual(bodies[1]["content_version"] as? String, contentVersion)
        XCTAssertEqual(try XCTUnwrap(bodies[1]["progress"] as? Double), 0.42, accuracy: 0.001)
        XCTAssertEqual(bodies[2]["book_id"] as? String, "kn-1")
    }

    func testLoginConsentPolicyInvalidatesSelectionWhenVersionChanges() {
        XCTAssertTrue(LoginConsentPolicy.hasValidAgreementVersion("service-v1"))
        XCTAssertFalse(LoginConsentPolicy.hasValidAgreementVersion(""))
        XCTAssertFalse(LoginConsentPolicy.hasValidAgreementVersion(" service-v1"))
        XCTAssertTrue(LoginConsentPolicy.isAccepted(
            selectedVersion: "service-v1", currentVersion: "service-v1"
        ))
        XCTAssertFalse(LoginConsentPolicy.isAccepted(
            selectedVersion: "service-v1", currentVersion: "service-v2"
        ))
        XCTAssertFalse(LoginConsentPolicy.isAccepted(selectedVersion: nil, currentVersion: "service-v1"))
    }

    @MainActor
    func testUnifiedAgreementDTOAndSnakeCaseAcceptanceNetworkContract() async throws {
        APIContractURLProtocol.reset()
        defer { APIContractURLProtocol.reset() }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [APIContractURLProtocol.self]
        let client = APIClient(
            baseURL: try XCTUnwrap(URL(string: "https://contract.invalid")),
            sessionConfiguration: configuration,
            inMemoryToken: "[REDACTED]"
        )
        let agreement = try await client.fetchAgreement()
        XCTAssertEqual(agreement.sections.map(\.title), [
            "用户服务协议", "隐私保护条款", "知识共建协议",
        ])
        _ = try await client.acceptAgreement(version: agreement.version, idempotencyKey: "request-id")
        let requests = APIContractURLProtocol.requests()
        XCTAssertEqual(requests.map { $0.request.url?.path }, [
            "/api/v1/legal/agreement", "/api/v1/me/agreement-acceptance",
        ])
        let body = try XCTUnwrap(
            JSONSerialization.jsonObject(with: try XCTUnwrap(requests.last?.body)) as? [String: Any]
        )
        XCTAssertEqual(Set(body.keys), ["agreement_version", "idempotency_key", "source"])
        XCTAssertNil(body["knowledge_contribution_enabled"])
        XCTAssertEqual(
            requests.last?.request.value(forHTTPHeaderField: "X-Client-Contract"),
            APIClient.clientContract
        )
    }

    @MainActor
    func testAcceptanceFailureRetainsInMemoryCredentialAndReplayIsBounded() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [APIContractURLProtocol.self]
        let client = APIClient(
            baseURL: try XCTUnwrap(URL(string: "https://contract.invalid")),
            sessionConfiguration: configuration,
            inMemoryToken: "[REDACTED]"
        )
        do {
            _ = try await client.acceptAgreement(
                version: "2026-09-06", idempotencyKey: "simulate-failure"
            )
            XCTFail("Expected acceptance failure")
        } catch APIError.server(503, _) {}
        XCTAssertNotNil(client.currentToken())
        XCTAssertTrue(AgreementReplayPolicy.canReplay(statusCode: 428, replayCount: 0))
        XCTAssertFalse(AgreementReplayPolicy.canReplay(statusCode: 428, replayCount: 1))
        XCTAssertFalse(AgreementReplayPolicy.canReplay(statusCode: 409, replayCount: 0))
        XCTAssertTrue(KeychainSavePolicy.shouldUpdate(after: errSecDuplicateItem))
        XCTAssertFalse(KeychainSavePolicy.shouldUpdate(after: errSecMissingEntitlement))
    }

    @MainActor
    func testLate401CannotClearReplacementCredential() async throws {
        APIContractURLProtocol.reset()
        defer { APIContractURLProtocol.reset() }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [APIContractURLProtocol.self]
        let client = APIClient(
            baseURL: try XCTUnwrap(URL(string: "https://contract.invalid")),
            sessionConfiguration: configuration,
            inMemoryToken: "token-a"
        )
        let generation = client.currentCredentialGeneration()
        let pending = Task {
            try await client.syncKnowledgeNote(
                id: "note-1", markdown: "delayed-401", updatedAt: Date(),
                credentialGeneration: generation
            )
        }
        try await Task.sleep(nanoseconds: 20_000_000)
        XCTAssertTrue(client.saveToken("token-b"))
        do {
            _ = try await pending.value
            XCTFail("Expected stale response cancellation")
        } catch is CancellationError {}
        XCTAssertEqual(client.currentToken(), "token-b")
        XCTAssertFalse(client.needsReauth)
    }

    @MainActor
    func testPublicAuthCapabilitiesSurviveConcurrentProtected401WithoutAuthorization() async throws {
        APIContractURLProtocol.reset()
        defer { APIContractURLProtocol.reset() }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [APIContractURLProtocol.self]
        let client = APIClient(
            baseURL: try XCTUnwrap(URL(string: "https://contract.invalid")),
            sessionConfiguration: configuration,
            inMemoryToken: "stale-token"
        )

        let capabilitiesTask = Task { try await client.fetchAuthCapabilities() }
        try await Task.sleep(nanoseconds: 20_000_000)
        do {
            _ = try await client.request(
                AuthCapabilitiesDTO.self,
                path: "workflow-activities/active"
            )
            XCTFail("Expected protected test fixture to return 401")
        } catch APIError.unauthorized {}

        let capabilities = try await capabilitiesTask.value
        XCTAssertTrue(capabilities.phone.enabled)
        XCTAssertFalse(capabilities.oauth.wechat.enabled)
        XCTAssertTrue(capabilities.oauth.alipay.enabled)

        let request = try XCTUnwrap(APIContractURLProtocol.requests().first {
            $0.request.url?.path == "/api/v1/auth/capabilities"
        }?.request)
        XCTAssertEqual(request.httpMethod, "GET")
        XCTAssertEqual(request.url?.absoluteString, "https://contract.invalid/api/v1/auth/capabilities")
        XCTAssertNil(request.value(forHTTPHeaderField: "Authorization"))
    }

    @MainActor
    func testCancellingPublicAuthCapabilitiesRemainsCancellation() async throws {
        APIContractURLProtocol.reset()
        defer { APIContractURLProtocol.reset() }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [APIContractURLProtocol.self]
        let client = APIClient(
            baseURL: try XCTUnwrap(URL(string: "https://contract.invalid")),
            sessionConfiguration: configuration,
            inMemoryToken: "stale-token"
        )

        let task = Task { try await client.fetchAuthCapabilities() }
        try await Task.sleep(nanoseconds: 20_000_000)
        task.cancel()
        do {
            _ = try await task.value
            XCTFail("Expected task cancellation")
        } catch is CancellationError {
        } catch let error as URLError {
            XCTAssertEqual(error.code, .cancelled)
        }
    }

    @MainActor
    func testStaleKnowledgeSaveCannotStartWithReplacementCredential() async throws {
        APIContractURLProtocol.reset()
        defer { APIContractURLProtocol.reset() }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [APIContractURLProtocol.self]
        let client = APIClient(
            baseURL: try XCTUnwrap(URL(string: "https://contract.invalid")),
            sessionConfiguration: configuration,
            inMemoryToken: "token-a"
        )
        let generation = client.currentCredentialGeneration()
        XCTAssertTrue(client.saveToken("token-b"))
        do {
            _ = try await client.syncKnowledgeNote(
                id: "note-1", markdown: "old-account-markdown", updatedAt: Date(),
                credentialGeneration: generation
            )
            XCTFail("Expected stale request cancellation")
        } catch is CancellationError {}
        XCTAssertTrue(APIContractURLProtocol.requests().isEmpty)
    }

    @MainActor
    func testDelayedSuccessCannotAcknowledgeReplacementAccount() async throws {
        APIContractURLProtocol.reset()
        defer { APIContractURLProtocol.reset() }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [APIContractURLProtocol.self]
        let client = APIClient(
            baseURL: try XCTUnwrap(URL(string: "https://contract.invalid")),
            sessionConfiguration: configuration,
            inMemoryToken: "token-a"
        )
        let generation = client.currentCredentialGeneration()
        let pending = Task {
            try await client.syncKnowledgeNote(
                id: "note-1", markdown: "delayed-success", updatedAt: Date(),
                credentialGeneration: generation
            )
        }
        try await Task.sleep(nanoseconds: 20_000_000)
        XCTAssertTrue(client.saveToken("token-b"))
        do {
            _ = try await pending.value
            XCTFail("Expected stale response cancellation")
        } catch is CancellationError {}
        XCTAssertEqual(client.currentToken(), "token-b")
    }

    @MainActor
    func testOverlappingKnowledgeSavesSerializeAndUsePriorHashCAS() async throws {
        APIContractURLProtocol.reset()
        defer { APIContractURLProtocol.reset() }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [APIContractURLProtocol.self]
        let client = APIClient(
            baseURL: try XCTUnwrap(URL(string: "https://contract.invalid")),
            sessionConfiguration: configuration,
            inMemoryToken: "token-a"
        )
        let generation = client.currentCredentialGeneration()
        let first = Task {
            try await client.syncKnowledgeNote(
                id: "note-1", markdown: "version-one", updatedAt: Date(),
                credentialGeneration: generation
            )
        }
        try await Task.sleep(nanoseconds: 10_000_000)
        let second = Task {
            try await client.syncKnowledgeNote(
                id: "note-1", markdown: "version-two", updatedAt: Date(),
                credentialGeneration: generation
            )
        }
        try await Task.sleep(nanoseconds: 20_000_000)
        XCTAssertEqual(APIContractURLProtocol.requests().count, 1)
        _ = try await first.value
        _ = try await second.value

        let requests = APIContractURLProtocol.requests()
        XCTAssertEqual(requests.count, 2)
        let firstBody = try XCTUnwrap(
            JSONSerialization.jsonObject(with: try XCTUnwrap(requests[0].body)) as? [String: Any]
        )
        let secondBody = try XCTUnwrap(
            JSONSerialization.jsonObject(with: try XCTUnwrap(requests[1].body)) as? [String: Any]
        )
        XCTAssertNil(firstBody["base_hash"])
        XCTAssertEqual(secondBody["base_hash"] as? String, firstBody["content_hash"] as? String)
    }

    @MainActor
    func testLostPredecessorResponseStillRequiresItsIntendedHash() async throws {
        APIContractURLProtocol.reset()
        defer { APIContractURLProtocol.reset() }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [APIContractURLProtocol.self]
        let client = APIClient(
            baseURL: try XCTUnwrap(URL(string: "https://contract.invalid")),
            sessionConfiguration: configuration,
            inMemoryToken: "token-a"
        )
        let generation = client.currentCredentialGeneration()
        let first = Task {
            try await client.syncKnowledgeNote(
                id: "note-1", markdown: "lost-response-version-one", updatedAt: Date(),
                credentialGeneration: generation
            )
        }
        try await Task.sleep(nanoseconds: 10_000_000)
        let second = Task {
            try await client.syncKnowledgeNote(
                id: "note-1", markdown: "version-two", updatedAt: Date(),
                credentialGeneration: generation
            )
        }
        do {
            _ = try await first.value
            XCTFail("Expected predecessor transport failure")
        } catch APIError.timeout {}
        _ = try await second.value

        let requests = APIContractURLProtocol.requests()
        XCTAssertEqual(requests.count, 2)
        let firstBody = try XCTUnwrap(
            JSONSerialization.jsonObject(with: try XCTUnwrap(requests[0].body)) as? [String: Any]
        )
        let secondBody = try XCTUnwrap(
            JSONSerialization.jsonObject(with: try XCTUnwrap(requests[1].body)) as? [String: Any]
        )
        XCTAssertEqual(secondBody["base_hash"] as? String, firstBody["content_hash"] as? String)
    }

    func testLoginConsentErrorsAreBoundedAndDoNotLeakRawResponses() {
        XCTAssertEqual(
            LoginConsentPolicy.failureMessage(for: APIError.server(422, "secret request payload")),
            "协议选择未被服务接受，请重新确认。"
        )
        XCTAssertEqual(
            LoginConsentPolicy.failureMessage(for: APIError.server(503, "private upstream detail")),
            "协议服务暂时不可用，请稍后重试。"
        )
        XCTAssertFalse(
            LoginConsentPolicy.failureMessage(for: APIError.decoding("internal field path"))
                .contains("internal")
        )
    }

    func testKnowledgeMergeRequestEncodesOnlyAtomicTransactionContract() throws {
        let request = KnowledgeNoteMergeRequestDTO(
            operationId: "operation-1", targetNoteId: "target-1",
            targetBaseHash: String(repeating: "a", count: 64),
            sourceVersions: ["source-1": String(repeating: "b", count: 64)],
            revisedContent: "# Revised"
        )
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: Any]
        )
        XCTAssertEqual(Set(object.keys), Set([
            "operation_id", "target_note_id", "target_base_hash", "source_versions", "revised_content"
        ]))
        XCTAssertEqual(object["operation_id"] as? String, "operation-1")
        XCTAssertEqual((object["source_versions"] as? [String: String])?["source-1"], String(repeating: "b", count: 64))
    }

    func testAnswerPageStreamEventParsesBoundedProjection() throws {
        let event = try XCTUnwrap(APIClient.StreamEvent.parse([
            "type": "answer_page",
            "message_id": "message-1",
            "revision": 2,
            "status": "running",
            "blocks": [["block_index": 0, "kind": "markdown", "content": "第一段\n\n"]],
            "bytes": 10,
            "loaded_block_count": 1,
            "available_block_count": 3,
            "has_more": true,
            "next_cursor": "signed.cursor",
        ]))
        guard case .answerPage(let page) = event else {
            return XCTFail("expected answer page")
        }
        XCTAssertEqual(page.messageId, "message-1")
        XCTAssertEqual(page.revision, 2)
        XCTAssertEqual(page.blocks.first?.content, "第一段\n\n")
        XCTAssertTrue(page.hasMore)
        XCTAssertEqual(page.nextCursor, "signed.cursor")
    }

    func testAnswerBlocksPersistAcrossHistoryRoundTrip() throws {
        let block = AnswerBlockDTO(blockIndex: 7, kind: "code_segment", content: "print(1)\n")
        let message = ChatMessage(
            id: "message-blocks", role: .assistant, content: block.content,
            answerRevision: 3, answerNextCursor: "cursor", answerHasMore: true,
            answerAvailableBlockCount: 9, answerBlocks: [block]
        )

        let restored = try JSONDecoder().decode(
            PersistedMessage.self, from: JSONEncoder().encode(PersistedMessage(message))
        ).toChatMessage(sessionId: "session")

        XCTAssertEqual(restored.answerRevision, 3)
        XCTAssertEqual(restored.answerBlocks, [block])
        XCTAssertTrue(restored.answerHasMore)
    }
    private func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    func testKnowledgeBookshelfDecodesReaderMetadata() throws {
        let data = Data(#"{"id":"knowledge/product/public","title":"产品知识","security_level":"green","book_count":1,"books":[{"id":"kn-1","title":"AI Lab 顶层设计","author":"Anthropic","author_source":"raw","summary":"从产品目标到系统边界。","cover_theme":"product","cover_variant":3,"cover_version":1,"security_level":"green","knowledge_level":"K5","freshness":"current","source_count":2}]}"#.utf8)

        let shelf = try decoder().decode(KnowledgeBookshelfDTO.self, from: data)

        XCTAssertEqual(shelf.bookCount, 1)
        XCTAssertEqual(shelf.books.first?.title, "AI Lab 顶层设计")
        XCTAssertEqual(shelf.books.first?.sourceCount, 2)
        XCTAssertEqual(shelf.books.first?.coverTheme, "product")
        XCTAssertEqual(shelf.books.first?.coverVariant, 3)
        XCTAssertEqual(shelf.books.first?.author, "Anthropic")
        XCTAssertEqual(shelf.books.first?.authorSource, "raw")
    }

    func testDailyPublicationDTOFieldsDecode() throws {
        let data = Data(#"{"id":"publication-1","title":"第一期","author":"Quantumn","summary":"测试","security_level":"green","knowledge_level":"editorial","freshness":"daily","source_count":1,"series_id":"ai-history","series_title":"AI的前世今生","issue_id":"issue-1","issue_date":"2026-09-08","test_serial":true,"release_at":"2026-09-08T04:00:00+00:00","actual_release_at":"2026-09-08T04:00:01+00:00","edition_id":"edition-1","edition":1,"source_urls":["https://example.com/source"],"publication_format":"chapter","editorial_genre":"popular_science","completeness":"full"}"#.utf8)
        let book = try decoder().decode(KnowledgeBookDTO.self, from: data)
        XCTAssertEqual(book.seriesId, "ai-history")
        XCTAssertEqual(book.issueDate, "2026-09-08")
        XCTAssertEqual(book.testSerial, true)
        XCTAssertEqual(book.sourceUrls, ["https://example.com/source"])
        XCTAssertEqual(book.publicationFormat, "chapter")
        XCTAssertEqual(book.editorialGenre, "popular_science")
        XCTAssertEqual(book.publicationTypeLabel, "科普 · 连载章节")
    }

    func testPublicationFormatLabelsDoNotInferFromCompleteness() throws {
        func decoded(_ fields: String) throws -> KnowledgeBookDTO {
            try decoder().decode(KnowledgeBookDTO.self, from: Data("""
            {"id":"kn","title":"Title","author":"Author","summary":"Summary","security_level":"green","knowledge_level":"K5","freshness":"current","source_count":1\(fields.isEmpty ? "" : ",\(fields)")}
            """.utf8))
        }

        XCTAssertEqual(try decoded(#""publication_format":"book""#).publicationTypeLabel, "完整书")
        XCTAssertEqual(try decoded(#""publication_format":"article""#).publicationTypeLabel, "历史短文")
        XCTAssertEqual(try decoded(#""publication_format":"source""#).publicationTypeLabel, "资料来源")
        XCTAssertNil(try decoded(#""completeness":"full""#).publicationTypeLabel)
        XCTAssertNil(try decoded("").publicationFormat)
    }

    func testPublicFollowBuildersMetadataAndQuarantinedRosterDecode() throws {
        let data = Data(#"{"bookshelves":[{"id":"knowledge/publication/follow-builders","title":"Follow Builders 公开来源索引","security_level":"green","book_count":1,"books":[{"id":"follow-builders-public-source-0123456789abcdef01234567","title":"Stored title","author":"Stored attribution","summary":"Recorded metadata; unverified","security_level":"green","knowledge_level":"source_metadata","freshness":"unknown","source_count":1,"source_kind":"public_source_index","content_status":"metadata_only","canonical_url":"https://example.com/source","completeness":"full","publication_format":"source","readable":false}]}],"public_collections":[{"id":"follow-builders-public","title":"Follow Builders 公开来源索引","visibility":"public","authority_count":1,"source_count":1,"admission_decision":"conditional","authorities":[{"roster_id":21,"recorded_handle":"palantir","recorded_display_name":"Palantir Technologies","recorded_website_url":"https://www.palantir.com/insights/","identity_status":"conflicting_identity_do_not_treat_as_official_x_account","website_status":"recorded website","source_relationship_status":"not established","admission_status":"website_entry_only_x_mapping_quarantined","specific_qualifications":["wrong X profile"]}]}],"owner_private_collections":[]}"#.utf8)
        let response = try decoder().decode(KnowledgeBookshelvesResponse.self, from: data)
        let book = try XCTUnwrap(response.bookshelves.first?.books.first)
        let collection = try XCTUnwrap(response.publicCollections?.first)
        let authority = try XCTUnwrap(collection.authorities.first)
        XCTAssertEqual(book.sourceKind, "public_source_index")
        XCTAssertEqual(book.knowledgeLevel, "source_metadata")
        XCTAssertEqual(book.contentStatus, "metadata_only")
        XCTAssertEqual(book.canonicalUrl, "https://example.com/source")
        XCTAssertEqual(book.publicationTypeLabel, "资料来源")
        XCTAssertFalse(book.readable ?? true)
        XCTAssertEqual(book.canonicalHTTPURL?.absoluteString, "https://example.com/source")
        XCTAssertTrue(book.isBodyUnavailable)
        XCTAssertTrue(response.bookshelves[0].isSourceShelf)
        var unsafeBook = book
        unsafeBook.canonicalUrl = "javascript:alert(1)"
        XCTAssertNil(unsafeBook.canonicalHTTPURL)
        XCTAssertEqual(collection.visibility, "public")
        XCTAssertEqual(authority.identityStatus, "conflicting_identity_do_not_treat_as_official_x_account")
        XCTAssertEqual(authority.sourceRelationshipStatus, "not established")
        XCTAssertEqual(authority.admissionStatus, "website_entry_only_x_mapping_quarantined")
    }

    func testReaderBodySurvivesSubscriptionFailure() async throws {
        let body = try decoder().decode(
            KnowledgeBookBodyDTO.self,
            from: Data(#"{"book_id":"kn-1","title":"Readable","author":"Author","content_version":"v1","edition":1,"citation":"source","sections":[{"id":"s1","title":"One","level":1,"markdown":"Body"}]}"#.utf8)
        )

        let loaded = try await loadKnowledgeBookReaderData(
            fetchBody: { body },
            fetchSubscriptions: { throw URLError(.cannotConnectToHost) }
        )

        XCTAssertEqual(loaded.body, body)
        XCTAssertNil(loaded.subscriptions)

        do {
            _ = try await loadKnowledgeBookReaderData(
                fetchBody: { throw URLError(.badServerResponse) },
                fetchSubscriptions: { [] }
            )
            XCTFail("Primary body failure must remain fatal")
        } catch {
            XCTAssertEqual((error as? URLError)?.code, .badServerResponse)
        }
    }

    func testKnowledgeBookSubscriptionDecodesBookAndProgress() throws {
        let data = Data(#"{"book":{"id":"kn-1","title":"AI Lab 顶层设计","author":"Anthropic","author_source":"raw","summary":"从产品目标到系统边界。","cover_theme":"product","cover_variant":3,"cover_version":1,"security_level":"green","knowledge_level":"K5","freshness":"current","source_count":2},"edition":1,"progress":0.42,"subscribed_at":"2026-09-06T07:00:00Z","last_read_at":"2026-09-06T07:10:00Z"}"#.utf8)

        let item = try decoder().decode(KnowledgeBookSubscriptionDTO.self, from: data)

        XCTAssertEqual(item.book.author, "Anthropic")
        XCTAssertEqual(item.edition, 1)
        XCTAssertEqual(item.progress, 0.42, accuracy: 0.001)
    }

    func testChatRequestEncodesExplicitLocalOnlyNoteScope() throws {
        let request = ChatRequestDTO(
            question: "整理本地待办",
            contextScope: ChatContextScopeDTO(
                mode: .localOnly,
                localNotes: [ChatLocalNoteDTO(
                    id: "note-1",
                    title: "本地会议",
                    markdown: "# 本地会议\n- [ ] 回信"
                )]
            )
        )
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: Any]
        )
        let scope = try XCTUnwrap(object["context_scope"] as? [String: Any])
        XCTAssertEqual(scope["mode"] as? String, "local_only")
        let notes = try XCTUnwrap(scope["local_notes"] as? [[String: Any]])
        XCTAssertEqual(notes.first?["title"] as? String, "本地会议")
    }

    func testChatRequestEncodesCurrentServerBookSectionScope() throws {
        let request = ChatRequestDTO(
            question: "解释当前章节",
            contextScope: ChatContextScopeDTO(
                mode: .platformOnly,
                selectedBookId: "book-server-id",
                selectedBookVersion: "content-version-server-value",
                selectedBookSectionId: "server-section-middle"
            )
        )
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: Any]
        )
        let scope = try XCTUnwrap(object["context_scope"] as? [String: Any])
        XCTAssertEqual(scope["selected_book_id"] as? String, "book-server-id")
        XCTAssertEqual(scope["selected_book_version"] as? String, "content-version-server-value")
        XCTAssertEqual(scope["selected_book_section_id"] as? String, "server-section-middle")
    }

    func testLegacySelectedBookScopeStillDecodes() throws {
        // Request DTOs own snake_case CodingKeys; do not apply a second key conversion.
        let scope = try JSONDecoder().decode(
            ChatContextScopeDTO.self,
            from: Data(#"{"mode":"platform_only","selected_book_id":"legacy-book"}"#.utf8)
        )
        XCTAssertEqual(scope.localNotes, [])
        XCTAssertEqual(scope.selectedBookId, "legacy-book")
        XCTAssertNil(scope.selectedBookVersion)
        XCTAssertNil(scope.selectedBookSectionId)
        XCTAssertThrowsError(try JSONDecoder().decode(
            ChatContextScopeDTO.self,
            from: Data(#"{"mode":"platform_only","local_notes":null}"#.utf8)
        ))
    }

    func testChatRequestEncodesClientSessionContextWithoutTenantClaims() throws {
        let request = ChatRequestDTO(
            question: "总结并保存",
            requestId: "request-1234",
            sessionId: "session-1",
            clientSessionContext: ClientSessionContextDTO(
                sessionId: "session-1",
                messages: [ClientSessionMessageDTO(
                    id: "m1", role: "user", content: "超聚变是一家公司"
                )],
                truncated: false
            )
        )
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: Any]
        )
        let context = try XCTUnwrap(object["client_session_context"] as? [String: Any])
        XCTAssertEqual(context["session_id"] as? String, "session-1")
        XCTAssertNil(object["tenant_key"])
        XCTAssertNil(object["user_id"])
    }

    func testChatPrewarmRequestUsesServerSessionContract() throws {
        let request = ChatPrewarmRequestDTO(
            sessionId: "session-1", agentId: "main_agent"
        )
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: Any]
        )
        XCTAssertEqual(object["session_id"] as? String, "session-1")
        XCTAssertEqual(object["agent_id"] as? String, "main_agent")
        XCTAssertEqual(
            object["client_capabilities"] as? [String],
            ["knowledge_action_v1", "answer_blocks_v1"]
        )
    }

    func testPendingPlaceholderNeverHidesVisiblePartialAnswer() {
        let empty = ChatMessage(role: .assistant, content: "", isStreaming: true, pending: true)
        let partial = ChatMessage(role: .assistant, content: "已经生成的内容", isStreaming: true, pending: true)
        XCTAssertTrue(empty.usesPendingPlaceholder)
        XCTAssertFalse(partial.usesPendingPlaceholder)
    }

    func testReasoningStepMutationSkipsRepeatedStreamingState() {
        let original = [
            ReasoningStep(
                type: .thought,
                title: "正在生成回答…",
                detail: "",
                status: "running"
            )
        ]

        let noChange = ReasoningStepMutation.applying({ steps in
            steps[0].title = "正在生成回答…"
            steps[0].status = "running"
        }, to: original)
        let changed = ReasoningStepMutation.applying({ steps in
            steps[0].status = "done"
        }, to: original)

        XCTAssertNil(noChange)
        XCTAssertEqual(changed?.first?.status, "done")
    }

    func testTerminalMessageSettlesGeneratingAnswerReasoning() {
        var message = ChatMessage(
            role: .assistant,
            content: "完整回答",
            isStreaming: false,
            blocks: [.reasoning([
                ReasoningStep(
                    type: .thought,
                    title: "正在生成回答…",
                    detail: "",
                    status: "running"
                )
            ])],
            pending: false
        )

        message.settleReasoningForCompletion()

        guard case .reasoning(let steps) = message.blocks.first else {
            return XCTFail("reasoning block missing")
        }
        XCTAssertEqual(steps.first?.title, "回答已生成")
        XCTAssertEqual(steps.first?.status, "done")
    }

    func testTerminalMessagePreservesCompletedReasoningCopy() {
        var message = ChatMessage(
            role: .assistant,
            content: "完整回答",
            blocks: [.reasoning([
                ReasoningStep(type: .toolCall, title: "检索完成", detail: "来源", status: "done")
            ])]
        )

        let original = message.blocks
        message.settleReasoningForCompletion()

        XCTAssertEqual(message.blocks, original)
    }

    func testKnowledgeAccessDecodesRuntimeEffectiveKnowledge() throws {
        let data = Data("""
        {
          "tenant_key": "tenant-a",
          "organization_id": "org-a",
          "plan_id": "",
          "plan_status": "inactive",
          "policy_version": "policy-12345678",
          "wallet": [],
          "yellow_entitlements": [],
          "effective_categories": ["public"],
          "effective_knowledge": [{
            "category": "public",
            "title": "公共知识",
            "security_level": "green",
            "source": "public",
            "document_count": 3
          }],
          "entitlement_stale": false
        }
        """.utf8)
        let access = try decoder().decode(KnowledgeAccessResponse.self, from: data)
        XCTAssertEqual(access.effectiveKnowledge?.map(\.category), ["public"])
        XCTAssertEqual(access.effectiveKnowledge?.first?.documentCount, 3)
        XCTAssertFalse(access.entitlementStale)
    }

    func testStreamingTextChunksKeepCompletedPrefixesStable() {
        let initial = String(repeating: "鹿儿岛内容", count: 1_000)
        let first = StreamTextChunker.chunks(initial, size: 256)
        let second = StreamTextChunker.chunks(initial + "新增尾段", size: 256)
        XCTAssertGreaterThan(first.count, 1)
        XCTAssertEqual(Array(second.prefix(first.count - 1)), Array(first.prefix(first.count - 1)))
        XCTAssertEqual(second.joined(), initial + "新增尾段")
    }

    func testMarkdownParserReusesBoundedMessageCache() {
        let key = "streaming-\(UUID().uuidString)"
        let first = MarkdownBlockParser.shared.parse("第一段", messageId: key)
        let cached = MarkdownBlockParser.shared.parse("已变化但仍在流式", messageId: key)
        let completed = MarkdownBlockParser.shared.parse(
            "已变化但仍在流式",
            messageId: "done-\(UUID().uuidString)"
        )

        XCTAssertEqual(cached, first)
        XCTAssertNotEqual(completed, first)
    }

    func testMarkdownParserKeepsRepeatedBlocksInSourceOrder() {
        let blocks = MarkdownBlockParser.shared.parse(
            "重复段落\n\n重复段落\n\n---\n\n---",
            messageId: "repeated-\(UUID().uuidString)"
        )

        XCTAssertEqual(blocks.count, 4)
        XCTAssertEqual(blocks[0], blocks[1])
        XCTAssertEqual(blocks[2], .divider)
        XCTAssertEqual(blocks[3], .divider)
    }

    func testMarkdownParserPreservesNumberedLabelsAndRejectsVersionNumbers() {
        let interrupted = MarkdownBlockParser.shared.parse("""
        # 第一段
        1. 条目一
        2. 条目二
        - 穿插说明
        # 第二段
        3. 条目三
        4. 条目四
        - 另一条说明
        5. 条目五
        6. 条目六
        7. 条目七
        """)
        let groups = interrupted.compactMap { block -> [String]? in
            guard case .numberedList(let items) = block else { return nil }
            return items
        }
        XCTAssertEqual(groups, [
            ["1. 条目一", "2. 条目二"],
            ["3. 条目三", "4. 条目四"],
            ["5. 条目五", "6. 条目六", "7. 条目七"]
        ])
        XCTAssertEqual(
            MarkdownBlockParser.shared.parse("3. 非 1 起始\n4. 后续"),
            [.numberedList(["3. 非 1 起始", "4. 后续"])]
        )
        XCTAssertEqual(
            MarkdownBlockParser.shared.parse("1. 连续一\n2. 连续二\n3. 连续三"),
            [.numberedList(["1. 连续一", "2. 连续二", "3. 连续三"])]
        )
        XCTAssertEqual(
            MarkdownBlockParser.shared.parse("版本 1.2 保持正文\n1.2 也不是列表\n3. 正文保留 2.4 和 2026"),
            [
                .paragraph("版本 1.2 保持正文\n1.2 也不是列表"),
                .numberedList(["3. 正文保留 2.4 和 2026"])
            ]
        )
    }

    @MainActor
    func testStartGenerationShowsTruthfulPendingStatusBeforeBackendEvents() {
        let coordinator = TenantSessionCoordinator(hasAuthenticatedSession: { false })
        coordinator.startGeneration(text: "分析需求", quote: nil)

        let assistant = coordinator.messages.last
        XCTAssertEqual(assistant?.role, .assistant)
        XCTAssertTrue(assistant?.pending == true)
        XCTAssertTrue(assistant?.isStreaming == true)
        XCTAssertTrue(assistant?.content.isEmpty == true)
        XCTAssertTrue(assistant?.reasoningSteps.isEmpty == true)
        XCTAssertEqual(assistant?.id, coordinator.inflight?.id)
        coordinator.cancelAllTasksAndAnimations()
    }

    func testHistoryAutoLoadOnlyTriggersAtVisibleTopBoundary() {
        XCTAssertEqual(ChatMessageStreamView.historyPositionAnchor, .top)
        XCTAssertTrue(ChatMessageStreamView.shouldArmOlderHistoryPull(
            translationHeight: 13, isGenerating: false
        ))
        XCTAssertFalse(ChatMessageStreamView.shouldArmOlderHistoryPull(
            translationHeight: 12, isGenerating: false
        ))
        XCTAssertFalse(ChatMessageStreamView.shouldArmOlderHistoryPull(
            translationHeight: -40, isGenerating: false
        ))
        XCTAssertFalse(ChatMessageStreamView.shouldArmOlderHistoryPull(
            translationHeight: 40, isGenerating: true
        ))
        XCTAssertTrue(ChatMessageStreamView.isAtOlderHistoryBoundary(
            contentOffsetY: -44, topInset: 44
        ))
        XCTAssertFalse(ChatMessageStreamView.isAtOlderHistoryBoundary(
            contentOffsetY: -20, topInset: 44
        ))
        XCTAssertTrue(ChatMessageStreamView.shouldAutoLoadOlderPage(
            visibleMessageID: "first", firstMessageID: "first",
            hasOlderMessages: true, isGenerating: false, isArmed: true,
            isAtHistoryBoundary: true
        ))
        XCTAssertFalse(ChatMessageStreamView.shouldAutoLoadOlderPage(
            visibleMessageID: "middle", firstMessageID: "first",
            hasOlderMessages: true, isGenerating: false, isArmed: true,
            isAtHistoryBoundary: true
        ))
        XCTAssertFalse(ChatMessageStreamView.shouldAutoLoadOlderPage(
            visibleMessageID: "first", firstMessageID: "first",
            hasOlderMessages: true, isGenerating: true, isArmed: true,
            isAtHistoryBoundary: true
        ))
        XCTAssertFalse(ChatMessageStreamView.shouldAutoLoadOlderPage(
            visibleMessageID: "first", firstMessageID: "first",
            hasOlderMessages: true, isGenerating: false, isArmed: false,
            isAtHistoryBoundary: true
        ))
        XCTAssertFalse(ChatMessageStreamView.shouldAutoLoadOlderPage(
            visibleMessageID: "first", firstMessageID: "first",
            hasOlderMessages: true, isGenerating: false, isArmed: true,
            isAtHistoryBoundary: false
        ))

        // The same boundary becomes eligible as soon as generation settles,
        // even though the tracked top message ID itself did not change.
        XCTAssertFalse(ChatMessageStreamView.shouldAutoLoadOlderPage(
            visibleMessageID: "first", firstMessageID: "first",
            hasOlderMessages: true, isGenerating: true, isArmed: true,
            isAtHistoryBoundary: true
        ))
        XCTAssertTrue(ChatMessageStreamView.shouldAutoLoadOlderPage(
            visibleMessageID: "first", firstMessageID: "first",
            hasOlderMessages: true, isGenerating: false, isArmed: true,
            isAtHistoryBoundary: true
        ))
    }

    @MainActor
    func testChatStreamRelayoutsAfterSendingBelowExtraTallMessage() async {
        let coordinator = TenantSessionCoordinator()
        let sessionId = coordinator.sessionManager.activeSessionID()
        let longAssessment = Array(
            repeating: """
            ### 三年级英语基础水平评估测试
            1. This is ___ apple. A. a B. an C. two
            2. I ___ a student. A. am B. is C. are
            3. What's your name? My name is Tom.

            ```text
            1-B
            2-A
            3-My name is Tom.
            ```
            """,
            count: 18
        ).joined(separator: "\n\n")
        coordinator.messages = [
            ChatMessage(sessionId: sessionId, role: .assistant, content: longAssessment)
        ]

        let host = UIHostingController(rootView: ChatMessageStreamView(coordinator: coordinator))
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: 393, height: 720))
        window.rootViewController = host
        window.isHidden = false
        defer { window.isHidden = true }

        host.view.layoutIfNeeded()

        coordinator.messages.append(
            ChatMessage(sessionId: sessionId, role: .user, content: "B A C A B A B C C D A B")
        )
        coordinator.messages.append(
            ChatMessage(
                sessionId: sessionId,
                role: .assistant,
                content: "",
                isStreaming: true,
                pending: true
            )
        )

        for _ in 0..<4 {
            await Task.yield()
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
        }

        let scrollView = findScrollView(in: host.view)
        XCTAssertEqual(coordinator.messages.count, 3)
        XCTAssertGreaterThan(host.view.bounds.height, 0)
        XCTAssertNotNil(scrollView)
        XCTAssertGreaterThan(scrollView?.contentSize.height ?? 0, scrollView?.bounds.height ?? 0)

        if let scrollView {
            let maximumOffset = max(0, scrollView.contentSize.height - scrollView.bounds.height)
            for step in 1...12 {
                scrollView.setContentOffset(
                    CGPoint(x: 0, y: maximumOffset * CGFloat(step) / 12),
                    animated: false
                )
                scrollView.layoutIfNeeded()
                await Task.yield()
            }
            XCTAssertEqual(scrollView.contentOffset.y, maximumOffset, accuracy: 1)
        }
    }

    @MainActor
    func testLongAnswerDisclosureKeepsBubbleLayoutBoundedAcrossAccessibilitySizes() {
        let message = ChatMessage(
            role: .assistant,
            content: String(repeating: "## 长回答\n这是一段用于验证折叠布局的富文本。\n\n", count: 2_000)
        )
        let widths: [CGFloat] = [375, 844]

        for width in widths {
            let root = MessageBubbleView(message: message)
                .environment(\.dynamicTypeSize, .accessibility5)
                .environment(\.colorScheme, .dark)
                .frame(width: width)
            let host = UIHostingController(rootView: root)
            let fitting = host.sizeThatFits(
                in: CGSize(width: width, height: CGFloat.greatestFiniteMagnitude)
            )

            XCTAssertGreaterThan(fitting.height, 44)
            XCTAssertLessThan(fitting.height, 4_000)
        }
    }

    private func findScrollView(in view: UIView) -> UIScrollView? {
        if let scrollView = view as? UIScrollView {
            return scrollView
        }
        for subview in view.subviews {
            if let scrollView = findScrollView(in: subview) {
                return scrollView
            }
        }
        return nil
    }

    private func findScrollViews(in view: UIView) -> [UIScrollView] {
        (view as? UIScrollView).map { [$0] }
            ?? view.subviews.flatMap { findScrollViews(in: $0) }
    }

    func testCreateDraftResponseDecodesClarificationSession() throws {
        let data = Data(
            """
            {
              "workflow": {
                "id": "wf_1",
                "title": "英语提升",
                "description": "生成学习计划",
                "desired_output": "Markdown",
                "status": "clarifying",
                "active_plan_id": null,
                "clarification_session_id": "wfs_1",
                "primary_agent_id": null,
                "created_at": "2026-08-19T10:00:00Z",
                "updated_at": "2026-08-19T10:00:00Z",
                "latest_execution": null
              },
              "clarification_session": {
                "id": "wfs_1",
                "workflow_id": "wf_1",
                "phase": "clarifying",
                "round_number": 1,
                "last_event_seq": 2
              }
            }
            """.utf8
        )

        let response = try decoder().decode(WorkflowCreateResponseDTO.self, from: data)
        XCTAssertEqual(response.workflow.status, "clarifying")
        XCTAssertEqual(response.workflow.clarificationSessionId, "wfs_1")
        XCTAssertEqual(response.clarificationSession.lastEventSeq, 2)
    }

    func testAgentBuildResponseDecodesCompositionAndDelegationPolicy() throws {
        let data = Data(
            """
            {
              "workflow": {
                "id": "wf_1", "title": "任务", "description": "目标",
                "desired_output": "报告", "status": "agent_ready",
                "active_plan_id": "wfp_1", "clarification_session_id": "wfs_1",
                "primary_agent_id": "agent_1", "created_at": null,
                "updated_at": null, "latest_execution": null
              },
              "agent": {
                "id": "agent_1", "owner_user_id": "user_1",
                "origin_workflow_id": "wf_1", "custom_name": "任务专属 Agent",
                "visibility": "private", "subscribed_knowledge_packs": ["wiki"],
                "is_active": true,
                "composition_manifest": {
                  "capability_agent_ids": ["main_agent", "knowledge"],
                  "invoked_agent_ids": [],
                  "delegation": {"max_concurrent_children": 3, "max_spawn_depth": 1},
                  "knowledge_scope": ["wiki"], "plan_id": "wfp_1"
                }
              }
            }
            """.utf8
        )

        let response = try decoder().decode(WorkflowAgentBuildResponseDTO.self, from: data)
        XCTAssertEqual(response.agent.visibility, "private")
        XCTAssertEqual(response.agent.compositionManifest.capabilityAgentIds, ["main_agent", "knowledge"])
        XCTAssertEqual(response.agent.compositionManifest.delegation.maxConcurrentChildren, 3)
        XCTAssertEqual(response.workflow.primaryAgentId, "agent_1")
    }

    func testLifecycleEventIgnoresPrivateReasoningPayload() throws {
        let data = Data(
            """
            {
              "id": 7, "workflow_id": "wf_1", "session_id": "wfs_1",
              "type": "plan_compiled", "message": "工作流 DAG 已编译",
              "payload": {"internal_reasoning": "must not be rendered"},
              "created_at": "2026-08-19T10:00:01Z"
            }
            """.utf8
        )

        let event = try decoder().decode(WorkflowLifecycleEventDTO.self, from: data)
        XCTAssertEqual(event.type, "plan_compiled")
        XCTAssertEqual(event.message, "工作流 DAG 已编译")
        XCTAssertNil(event.payload.question)
    }

    func testLegacyPlanWithoutNestedPlanIdStillDecodes() throws {
        let data = Data(
            """
            {
              "id": "wfp_legacy", "workflow_id": "wf_1", "version": 1,
              "goal": "英语评估", "deliverable": "Markdown",
              "allow_network": true, "max_tokens": 24000,
              "estimated_tokens": 12000, "knowledge_scope": [],
              "validation_errors": [],
              "dsl": {"name": "英语评估", "nodes": [], "edges": [], "version": "1.0.0"},
              "frozen_at": null, "created_at": null
            }
            """.utf8
        )

        let plan = try decoder().decode(WorkflowPlanDTO.self, from: data)
        XCTAssertEqual(plan.id, "wfp_legacy")
        XCTAssertEqual(plan.dsl.planId, "")
    }

    func testNestedPlanIdDecodesWithGlobalSnakeCaseStrategy() throws {
        let data = Data(
            """
            {
              "plan_id":"wfp_nested","name":"评估","version":"1.0.0","edges":[],
              "nodes":[{
                "id":"node_01","node_type":"FILTER_PASS","name":"安全检查",
                "parameters":{
                  "agent_id":"supervision","instruction":"检查方案",
                  "output_format":"Markdown","knowledge_scope":["wiki"],
                  "allow_network":true,"requires_review":true,
                  "max_tokens":1500,"revision_note":"复核"
                }
              }]
            }
            """.utf8
        )

        let dsl = try decoder().decode(WorkflowDSLDTO.self, from: data)
        XCTAssertEqual(dsl.planId, "wfp_nested")
        XCTAssertEqual(dsl.nodes.first?.nodeType, "FILTER_PASS")
        XCTAssertEqual(dsl.nodes.first?.parameters.agentId, "supervision")
        XCTAssertEqual(dsl.nodes.first?.parameters.outputFormat, "Markdown")
        XCTAssertEqual(dsl.nodes.first?.parameters.knowledgeScope, ["wiki"])
        XCTAssertEqual(dsl.nodes.first?.parameters.allowNetwork, true)
        XCTAssertEqual(dsl.nodes.first?.parameters.requiresReview, true)
        XCTAssertEqual(dsl.nodes.first?.parameters.maxTokens, 1500)
        XCTAssertEqual(dsl.nodes.first?.parameters.revisionNote, "复核")

        let encoded = try JSONEncoder().encode(dsl)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
        let nodes = try XCTUnwrap(object["nodes"] as? [[String: Any]])
        let first = try XCTUnwrap(nodes.first)
        XCTAssertEqual(first["node_type"] as? String, "FILTER_PASS")
        let parameters = try XCTUnwrap(first["parameters"] as? [String: Any])
        XCTAssertEqual(parameters["agent_id"] as? String, "supervision")
    }

    func testActivePlanningActivityDecodesStructuredPluginStep() throws {
        let data = Data(
            """
            [{
              "workflow": {
                "id": "wf_1", "title": "英语提升", "description": "目标",
                "desired_output": "Markdown", "status": "planning",
                "active_plan_id": null, "clarification_session_id": "wfs_1",
                "primary_agent_id": null, "created_at": null, "updated_at": null,
                "latest_execution": null
              },
              "session": {
                "id": "wfs_1", "workflow_id": "wf_1", "phase": "planning",
                "round_number": 3, "last_event_seq": 8
              },
              "latest_event": {
                "id": 8, "workflow_id": "wf_1", "session_id": "wfs_1",
                "type": "planner_step", "message": "加载技能: research",
                "payload": {
                  "step_id": "bridge-8", "category": "skill_load",
                  "status": "done", "tool": "research",
                  "detail": "已加载技能", "source": "hermes_reasoning_plugin"
                },
                "created_at": "2026-08-19T10:00:01Z"
              }
            }]
            """.utf8
        )

        let activities = try decoder().decode([WorkflowActiveActivityDTO].self, from: data)
        XCTAssertEqual(activities.first?.session.phase, "planning")
        XCTAssertEqual(activities.first?.latestEvent?.payload.category, "skill_load")
        XCTAssertEqual(activities.first?.latestEvent?.payload.source, "hermes_reasoning_plugin")
    }

    func testLegacySessionRecordDefaultsToMainAgent() throws {
        let data = Data(
            """
            {
              "id":"session-legacy","title":"旧会话",
              "updatedAt":"2026-08-20T10:00:00Z","messages":[]
            }
            """.utf8
        )
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let record = try decoder.decode(SessionRecord.self, from: data)
        XCTAssertNil(record.agentId)
        XCTAssertNil(record.agentName)
    }

    func testSessionRecordPersistsSelectedAgent() throws {
        let record = SessionRecord(
            id: "session-agent", title: "英语评估", updatedAt: Date(), messages: [],
            agentId: "67d68724aefd431c967acdf0864e1949",
            agentName: "小学生英语评估 · 专属 Agent"
        )
        let data = try JSONEncoder().encode(record)
        let restored = try JSONDecoder().decode(SessionRecord.self, from: data)
        XCTAssertEqual(restored.agentId, "67d68724aefd431c967acdf0864e1949")
        XCTAssertEqual(restored.agentName, "小学生英语评估 · 专属 Agent")
    }

    func testAgentRouteSSEEventDecodesProvenance() throws {
        let event = try XCTUnwrap(APIClient.StreamEvent.parse([
            "type": "agent_route",
            "agent": [
                "id": "english-agent",
                "name": "小学生英语评估 · 专属 Agent",
                "delegated": true,
            ],
            "delegated_by": "main_agent",
        ]))
        guard case let .agentRoute(id, name, delegated, delegatedBy) = event else {
            return XCTFail("expected agentRoute event")
        }
        XCTAssertEqual(id, "english-agent")
        XCTAssertEqual(name, "小学生英语评估 · 专属 Agent")
        XCTAssertTrue(delegated)
        XCTAssertEqual(delegatedBy, "main_agent")
    }

    func testNonStreamingFeedbackReceiptDecodes() throws {
        let data = Data("""
        {
          "question": "q",
          "answer": "a",
          "session_id": "s",
          "reasoning": [],
          "feedback_receipt": {
            "feedback_id": "42",
            "signal_type": "explicit",
            "message": "已记录",
            "revocable": true
          }
        }
        """.utf8)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(ChatResponseDTO.self, from: data)
        XCTAssertEqual(response.feedbackReceipt?.feedbackId, "42")
        XCTAssertEqual(response.feedbackReceipt?.signalType, "explicit")
        XCTAssertTrue(response.feedbackReceipt?.revocable == true)
    }

    func testFeedbackReceiptSSEEventDecodes() throws {
        let event = try XCTUnwrap(APIClient.StreamEvent.parse([
            "type": "feedback_receipt",
            "feedback_id": "42",
            "signal_type": "explicit",
            "message": "已作为产品改进反馈记录",
            "revocable": true,
        ]))
        guard case let .feedbackReceipt(id, signalType, message, revocable) = event else {
            return XCTFail("expected feedbackReceipt event")
        }
        XCTAssertEqual(id, "42")
        XCTAssertEqual(signalType, "explicit")
        XCTAssertEqual(message, "已作为产品改进反馈记录")
        XCTAssertTrue(revocable)
    }

    func testNoteDraftSSEEventDecodesForConfirmation() throws {
        let event = try XCTUnwrap(APIClient.StreamEvent.parse([
            "type": "note_draft",
            "draft_id": "draft-1",
            "title": "超聚变",
            "markdown": "# 超聚变\n\n正文",
            "tags": ["企业"],
            "source_session_id": "session-1",
            "source_message_ids": ["m1"],
            "account_scope": "tenant:user",
            "merge_candidates": [[
                "id": "old-1", "title": "旧笔记", "snippet": "旧内容"
            ]],
            "merged_title": "超聚变整理",
            "merged_markdown": "# 合并内容",
            "merged_tags": ["企业"],
        ]))
        guard case let .noteDraft(id, title, markdown, _, sessionId, messageIds, accountScope, candidates, mergedTitle, mergedMarkdown, _, _, _, _, _) = event else {
            return XCTFail("expected noteDraft event")
        }
        XCTAssertEqual(id, "draft-1")
        XCTAssertEqual(title, "超聚变")
        XCTAssertTrue(markdown.contains("正文"))
        XCTAssertEqual(sessionId, "session-1")
        XCTAssertEqual(messageIds, ["m1"])
        XCTAssertEqual(accountScope, "tenant:user")
        XCTAssertEqual(candidates.map(\.id), ["old-1"])
        XCTAssertEqual(mergedTitle, "超聚变整理")
        XCTAssertEqual(mergedMarkdown, "# 合并内容")
    }

    func testKnowledgeActionSSEDecodesAndCapabilityIsNeverPersisted() throws {
        let event = try XCTUnwrap(APIClient.StreamEvent.parse([
            "type": "knowledge_action_draft",
            "action_id": "ka-1",
            "summary": "完善 TokenBox",
            "steps": [[
                "kind": "update_note", "target_note_id": "n1",
                "title": "TokenBox", "markdown": "# TokenBox\n\n新内容",
                "original_content_hash": "old-hash",
            ]],
            "action_digest": String(repeating: "a", count: 64),
            "knowledge_action_capability": "secret-short-lived-token",
            "expires_at": 4_000_000_000,
            "risk_level": "low",
            "suggested_navigation": ["destination": "note", "note_id": "n1"],
            "account_scope": ["tenant_namespace": "tenant", "user_namespace": "user"],
        ]))
        guard case let .knowledgeActionDraft(action) = event else {
            return XCTFail("expected knowledge action")
        }
        XCTAssertEqual(action.steps.first?.targetNoteId, "n1")
        XCTAssertEqual(action.transientCapability, "secret-short-lived-token")
        let message = ChatMessage(sessionId: "s1", role: .assistant, content: "", blocks: [.knowledgeAction(action)])
        let data = try JSONEncoder().encode(PersistedMessage(message))
        XCTAssertFalse(String(decoding: data, as: UTF8.self).contains("secret-short-lived-token"))
        let decoded = try JSONDecoder().decode(PersistedMessage.self, from: data)
        let restored = decoded.toChatMessage(sessionId: "s1")
        guard case let .knowledgeAction(restoredAction) = try XCTUnwrap(restored.blocks.first) else {
            return XCTFail("expected restored knowledge action")
        }
        XCTAssertNil(restoredAction.transientCapability)
        XCTAssertEqual(restoredAction.state, .stale)
    }

    func testClarifyStateSurvivesSessionPersistenceRoundTrip() throws {
        let block = ClarifyBlock(
            clarifyId: "cid-1",
            requestId: "request-1",
            sessionId: "session-1",
            agentId: "main_agent",
            expiresInSeconds: 123,
            submissionState: .submitting,
            question: "请提供具体任务",
            choices: [],
            source: "bridge",
            submittedSelection: "测试英语水平"
        )
        let message = ChatMessage(
            id: "message-1", sessionId: "session-1", role: .assistant,
            content: "", blocks: [.clarify(block)]
        )

        let data = try JSONEncoder().encode(PersistedMessage(message))
        let decoded = try JSONDecoder().decode(PersistedMessage.self, from: data)
        let restored = try XCTUnwrap(decoded.toChatMessage(sessionId: "session-1").clarifyBlock)

        XCTAssertEqual(restored.clarifyId, "cid-1")
        XCTAssertEqual(restored.requestId, "request-1")
        XCTAssertEqual(restored.submissionState, .submitting)
        XCTAssertEqual(restored.submittedSelection, "测试英语水平")
    }

    func testLegacyPersistedMessageWithoutClarifyStillDecodes() throws {
        let data = Data(
            """
            {
              "id":"m1","role":"assistant","content":"旧回答",
              "createdAt":0,"pending":false,"degraded":false,
              "isDemoSample":false,"reasoningDuration":null
            }
            """.utf8
        )
        let legacy = try JSONDecoder().decode(PersistedMessage.self, from: data)
        XCTAssertNil(legacy.clarify)
        XCTAssertEqual(legacy.toChatMessage(sessionId: "s1").content, "旧回答")
    }

    func testChatStatusDecodesRecoverableClarifyMetadata() throws {
        let data = Data(
            """
            {
              "status":"running","phase":"clarify","answer":"",
              "reasoning":[],"latest_step":"等待用户确认","consumed":false,
              "clarify":{
                "clarify_id":"cid-2","request_id":"request-2",
                "question":"选择目标","choices":["A","B"],
                "multi_select":false,"expires_in_seconds":88
              }
            }
            """.utf8
        )
        let status = try decoder().decode(ChatStatusDTO.self, from: data)
        XCTAssertEqual(status.phase, "clarify")
        XCTAssertEqual(status.clarify?.clarifyId, "cid-2")
        XCTAssertEqual(status.clarify?.requestId, "request-2")
        XCTAssertEqual(status.clarify?.expiresInSeconds, 88)
    }

    func testRunningChatStatusNeverAllowsRegenerate() {
        XCTAssertFalse(TenantSessionCoordinator.statusAllowsRegenerate("running"))
        XCTAssertFalse(TenantSessionCoordinator.statusAllowsRegenerate("completed"))
        XCTAssertTrue(TenantSessionCoordinator.statusAllowsRegenerate("failed"))
        XCTAssertTrue(TenantSessionCoordinator.statusAllowsRegenerate("timeout"))
        XCTAssertTrue(TenantSessionCoordinator.statusAllowsRegenerate("not_found"))
    }

    func testChatHistoryStorePagesOneThousandMessagesWithinBudgets() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy")
        )
        let sessionId = "large-history"
        let messages = (0..<1_000).map { index in
            ChatMessage(
                id: "message-\(index)", sessionId: sessionId,
                role: index.isMultiple(of: 2) ? .user : .assistant,
                content: "正文-\(index)-" + String(repeating: "x", count: 120)
            )
        }

        XCTAssertEqual(ChatHistoryStore.pageMessageLimit, 16)
        XCTAssertEqual(try store.upsert(messages, sessionId: sessionId), 1_000)
        let latest = try store.latest(sessionId: sessionId)
        XCTAssertLessThanOrEqual(latest.messages.count, ChatHistoryStore.pageMessageLimit)
        XCTAssertLessThanOrEqual(latest.messages.reduce(0) { $0 + $1.content.count }, ChatHistoryStore.pageCharacterLimit)
        XCTAssertEqual(latest.messages.last?.id, "message-999")
        XCTAssertTrue(latest.hasOlder)
        XCTAssertFalse(latest.hasNewer)

        let older = try store.before(sessionId: sessionId, messageId: try XCTUnwrap(latest.messages.first?.id))
        XCTAssertLessThanOrEqual(older.messages.count, ChatHistoryStore.pageMessageLimit)
        XCTAssertTrue(older.hasNewer)
        let newer = try store.after(sessionId: sessionId, messageId: try XCTUnwrap(older.messages.last?.id))
        XCTAssertEqual(newer.messages.first?.id, latest.messages.first?.id)

        let longSession = "character-budget"
        let longMessages = (0..<3).map {
            ChatMessage(id: "long-\($0)", sessionId: longSession, role: .assistant, content: String(repeating: "长", count: 40_001))
        }
        _ = try store.upsert(longMessages, sessionId: longSession)
        let characterPage = try store.latest(sessionId: longSession)
        XCTAssertEqual(characterPage.messages.count, 1)
        XCTAssertEqual(characterPage.messages.first?.content.count, 40_001)

        XCTAssertEqual(try store.previousUser(sessionId: sessionId, before: "message-51")?.id, "message-50")
        try store.truncate(sessionId: sessionId, from: "message-51")
        XCTAssertEqual(try store.count(sessionId), 51)
        try store.clear(sessionId)
        XCTAssertEqual(try store.count(sessionId), 0)
        try store.delete(longSession)
        XCTAssertNil(try store.summaries().first(where: { $0.id == longSession }))
    }

    @MainActor
    func testSessionOrganizationLifecycleAndSourceContextAreRecoverable() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let databaseURL = root.appendingPathComponent("history.sqlite")
        let legacyURL = root.appendingPathComponent("legacy")
        let store = try ChatHistoryStore(databaseURL: databaseURL, legacyDirectory: legacyURL)
        let manager = SessionManager(store: store)
        let first = manager.createSession()
        manager.setMessages([
            ChatMessage(id: "m1", sessionId: first, role: .user, content: "项目预算是两万元")
        ], for: first)
        let second = manager.createSession()
        manager.setMessages([
            ChatMessage(id: "m2", sessionId: second, role: .assistant, content: "登录页采用短信验证")
        ], for: second)
        await manager.flushPendingPersistence()
        let organizer = manager.createSession(agentId: "knowledge", agentName: "知识整理")
        let context = manager.organizationContext(
            sourceSessionIDs: [first, second], destinationSessionId: organizer
        )

        XCTAssertEqual(context.sessionId, organizer)
        XCTAssertEqual(Set(context.sourceSessions.map(\.sessionId)), Set([first, second]))
        XCTAssertEqual(context.sourceSessions.first(where: { $0.sessionId == first })?.messages.first?.id, "\(first):m1")
        XCTAssertEqual(Set(manager.organizationSources(for: organizer)), Set([first, second]))

        manager.markOrganized([first, second])
        manager.setLifecycle(.archived, for: first)
        manager.setLifecycle(.trashed, for: second)
        XCTAssertTrue(manager.sortedSessionIDs(status: .archived, query: "预算").contains(first))
        XCTAssertTrue(manager.sortedSessionIDs(status: .trashed, query: "短信").contains(second))
        manager.setLifecycle(.active, for: first)
        XCTAssertTrue(manager.sortedSessionIDs(status: .active).contains(first))

        let restored = SessionManager(
            store: try ChatHistoryStore(databaseURL: databaseURL, legacyDirectory: legacyURL)
        )
        XCTAssertNotNil(restored.sessionOrganizedAt[first])
        XCTAssertEqual(restored.sessionLifecycle[second], .trashed)
        XCTAssertEqual(Set(restored.organizationSources(for: organizer)), Set([first, second]))
    }

    func testChatHistoryStoreMigratesLegacyJSONAndKeepsBackup() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let legacy = root.appendingPathComponent("Sessions")
        try FileManager.default.createDirectory(at: legacy, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let messages = (0..<30).map {
            PersistedMessage(ChatMessage(id: "legacy-\($0)", sessionId: "legacy", role: $0.isMultiple(of: 2) ? .user : .assistant, content: "历史 \($0)"))
        }
        let record = SessionRecord(
            id: "legacy", title: "迁移会话", updatedAt: Date(timeIntervalSince1970: 1_750_000_000),
            messages: messages, agentId: "english-agent", agentName: "英语评估"
        )
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let source = legacy.appendingPathComponent("legacy.json")
        try encoder.encode(record).write(to: source)

        let store = try ChatHistoryStore(databaseURL: root.appendingPathComponent("history.sqlite"), legacyDirectory: legacy)
        XCTAssertEqual(try store.count("legacy"), 30)
        let latest = try store.latest(sessionId: "legacy")
        XCTAssertEqual(latest.messages.last?.id, "legacy-29")
        let summary = try XCTUnwrap(store.summaries().first)
        XCTAssertEqual(summary.title, "迁移会话")
        XCTAssertEqual(summary.agentId, "english-agent")
        XCTAssertFalse(FileManager.default.fileExists(atPath: source.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: legacy.appendingPathComponent("legacy.json.v1-backup").path))
    }

    func testChatHistoryStoreLeavesInvalidLegacyFileRecoverable() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let legacy = root.appendingPathComponent("Sessions")
        try FileManager.default.createDirectory(at: legacy, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let source = legacy.appendingPathComponent("broken.json")
        try Data("not-json".utf8).write(to: source)

        let store = try ChatHistoryStore(databaseURL: root.appendingPathComponent("history.sqlite"), legacyDirectory: legacy)
        XCTAssertTrue(try store.summaries().isEmpty)
        XCTAssertTrue(FileManager.default.fileExists(atPath: source.path))
    }

    func testChatHistoryStoreRollsBackFailedSessionMigration() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let legacy = root.appendingPathComponent("Sessions")
        try FileManager.default.createDirectory(at: legacy, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let duplicated = ChatMessage(id: "same-id", sessionId: "rollback", role: .assistant, content: "重复")
        let record = SessionRecord(
            id: "rollback", title: "应回滚", updatedAt: Date(),
            messages: [PersistedMessage(duplicated), PersistedMessage(duplicated)]
        )
        let encoder = JSONEncoder(); encoder.dateEncodingStrategy = .iso8601
        let source = legacy.appendingPathComponent("rollback.json")
        try encoder.encode(record).write(to: source)

        let store = try ChatHistoryStore(databaseURL: root.appendingPathComponent("history.sqlite"), legacyDirectory: legacy)
        XCTAssertNil(try store.summaries().first(where: { $0.id == "rollback" }))
        XCTAssertTrue(FileManager.default.fileExists(atPath: source.path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: legacy.appendingPathComponent("rollback.json.v1-backup").path))
    }

    @MainActor
    func testSessionManagerColdStartLoadsOnlyMetadataAndLatestPageOnDemand() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try ChatHistoryStore(databaseURL: root.appendingPathComponent("history.sqlite"), legacyDirectory: root.appendingPathComponent("legacy"))
        let sessionId = "metadata-only"
        _ = try store.upsert((0..<100).map {
            ChatMessage(id: "cold-\($0)", sessionId: sessionId, role: .assistant, content: "消息 \($0)")
        }, sessionId: sessionId)

        let manager = SessionManager(store: store)
        XCTAssertEqual(manager.messageCount(for: sessionId), 100)
        XCTAssertTrue(manager.sessions.isEmpty)
        XCTAssertLessThanOrEqual(manager.latestPage(for: sessionId).messages.count, ChatHistoryStore.pageMessageLimit)
        XCTAssertEqual(manager.sessions[sessionId]?.last?.id, "cold-99")
    }

    @MainActor
    func testCoordinatorReplacesVisibleHistoryPages() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try ChatHistoryStore(databaseURL: root.appendingPathComponent("history.sqlite"), legacyDirectory: root.appendingPathComponent("legacy"))
        let sessionId = "paging-ui"
        _ = try store.upsert((0..<60).map {
            ChatMessage(id: "page-\($0)", sessionId: sessionId, role: .assistant, content: "消息 \($0)")
        }, sessionId: sessionId)
        let manager = SessionManager(store: store)
        let coordinator = TenantSessionCoordinator(sessionManager: manager)

        XCTAssertEqual(coordinator.messages.last?.id, "page-59")
        XCTAssertLessThanOrEqual(coordinator.messages.count, ChatHistoryStore.pageMessageLimit)
        XCTAssertTrue(coordinator.hasOlderMessages)
        XCTAssertTrue(coordinator.isLatestPage)
        coordinator.loadOlderMessagePage()
        XCTAssertFalse(coordinator.isLatestPage)
        XCTAssertTrue(coordinator.hasNewerMessages)
        XCTAssertLessThanOrEqual(coordinator.messages.count, ChatHistoryStore.pageMessageLimit)
        coordinator.loadNewerMessagePage()
        XCTAssertEqual(
            coordinator.messages.first?.id,
            "page-\(60 - ChatHistoryStore.pageMessageLimit)"
        )
        coordinator.returnToLatestMessages()
        XCTAssertEqual(coordinator.messages.last?.id, "page-59")
        XCTAssertTrue(coordinator.isLatestPage)
    }

    @MainActor
    func testSessionManagerPersistsMessagesOffMainActorInOrder() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy")
        )
        let manager = SessionManager(store: store)
        let sessionId = manager.createSession()
        let first = ChatMessage(
            id: "assistant", sessionId: sessionId, role: .assistant,
            content: "第一版", blocks: [.reasoning([
                ReasoningStep(type: .thought, title: "思考", detail: "第一步")
            ])]
        )
        var second = first
        second.content = "第二版"
        second.blocks = [.reasoning([
            ReasoningStep(type: .toolCall, title: "检索 Wiki", detail: "已完成")
        ])]

        manager.setMessages([first], for: sessionId)
        manager.setMessages([second], for: sessionId)

        XCTAssertEqual(manager.messages(for: sessionId).first?.content, "第二版")
        await manager.flushPendingPersistence()
        XCTAssertEqual(try store.message(sessionId: sessionId, id: "assistant")?.content, "第二版")
    }

    @MainActor
    func testSessionManagerPersistsRunCursorOnlyChanges() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let databaseURL = root.appendingPathComponent("history.sqlite")
        let store = try ChatHistoryStore(
            databaseURL: databaseURL,
            legacyDirectory: root.appendingPathComponent("legacy")
        )
        let manager = SessionManager(store: store)
        let sessionId = manager.createSession()
        var pending = ChatMessage(
            id: "cursor-message", sessionId: sessionId, role: .assistant,
            content: "部分回答", isStreaming: true, pending: true
        )
        manager.setMessages([pending], for: sessionId)
        await manager.flushPendingPersistence()

        var lockDatabase: OpaquePointer?
        XCTAssertEqual(sqlite3_open(databaseURL.path, &lockDatabase), SQLITE_OK)
        defer { sqlite3_close(lockDatabase) }
        XCTAssertEqual(sqlite3_exec(lockDatabase, "BEGIN IMMEDIATE", nil, nil, nil), SQLITE_OK)
        pending.runId = "run-durable"
        pending.lastEventSequence = 17
        manager.setMessages([pending], for: sessionId)
        manager.cacheVisibleMessages([pending], for: sessionId, markAsPersisted: false)
        await manager.flushPendingPersistence()
        XCTAssertNil(try store.message(sessionId: sessionId, id: pending.id)?.runId)
        XCTAssertEqual(sqlite3_exec(lockDatabase, "COMMIT", nil, nil, nil), SQLITE_OK)

        // An identical projection must retry because the failed write was never marked durable.
        manager.setMessages([pending], for: sessionId)
        manager.cacheVisibleMessages([pending], for: sessionId, markAsPersisted: false)
        await manager.flushPendingPersistence()

        let restored = try XCTUnwrap(store.message(sessionId: sessionId, id: pending.id))
        XCTAssertEqual(restored.runId, "run-durable")
        XCTAssertEqual(restored.lastEventSequence, 17)
    }

    @MainActor
    func testAccountTransitionsRetainQueuedWritesUntilDurable() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let databaseURL = root.appendingPathComponent("history.sqlite")
        let store = try ChatHistoryStore(
            databaseURL: databaseURL,
            legacyDirectory: root.appendingPathComponent("legacy")
        )
        let manager = SessionManager(store: store)
        let sessionId = manager.createSession()
        var lockDatabase: OpaquePointer?
        XCTAssertEqual(sqlite3_open(databaseURL.path, &lockDatabase), SQLITE_OK)
        defer { sqlite3_close(lockDatabase) }
        XCTAssertEqual(sqlite3_exec(lockDatabase, "BEGIN IMMEDIATE", nil, nil, nil), SQLITE_OK)

        manager.setMessages([
            ChatMessage(id: "switch-write", sessionId: sessionId, role: .user, content: "切换前消息")
        ], for: sessionId)
        let tenantA = "tenant-\(UUID().uuidString)"
        let userA = "user-\(UUID().uuidString)"
        manager.activateAccount(tenantKey: tenantA, userId: userA)
        let activatedFingerprint = manager.activeAccountFingerprint
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        let activatedAccountDirectory = documents
            .appendingPathComponent("ChatHistory/accounts/\(activatedFingerprint)")
        let activatedDatabaseURL = activatedAccountDirectory.appendingPathComponent("history.sqlite")
        XCTAssertEqual(sqlite3_exec(lockDatabase, "COMMIT", nil, nil, nil), SQLITE_OK)
        await manager.flushPendingPersistence()
        XCTAssertEqual(
            try store.message(sessionId: sessionId, id: "switch-write")?.content,
            "切换前消息"
        )

        var activatedLockDatabase: OpaquePointer?
        XCTAssertEqual(sqlite3_open(activatedDatabaseURL.path, &activatedLockDatabase), SQLITE_OK)
        defer { sqlite3_close(activatedLockDatabase) }

        let revisitSessionId = manager.createSession()
        let clearAfterRevisitSessionId = manager.createSession()
        let deleteAfterRevisitSessionId = manager.createSession()
        XCTAssertEqual(
            sqlite3_exec(activatedLockDatabase, "BEGIN IMMEDIATE", nil, nil, nil),
            SQLITE_OK
        )
        let revisited = ChatMessage(
            id: "revisit-write", sessionId: revisitSessionId,
            role: .assistant, content: "旧游标", isStreaming: true, pending: true,
            runId: "run-old", lastEventSequence: 1
        )
        manager.setMessages([revisited], for: revisitSessionId)
        manager.setMessages([
            ChatMessage(
                id: "revisit-clear", sessionId: clearAfterRevisitSessionId,
                role: .user, content: "切回后清空"
            )
        ], for: clearAfterRevisitSessionId)
        manager.setMessages([
            ChatMessage(
                id: "revisit-delete", sessionId: deleteAfterRevisitSessionId,
                role: .user, content: "切回后删除"
            )
        ], for: deleteAfterRevisitSessionId)
        manager.activateAccount(
            tenantKey: "tenant-b-\(UUID().uuidString)",
            userId: "user-b-\(UUID().uuidString)"
        )
        manager.activateAccount(tenantKey: tenantA, userId: userA)
        XCTAssertTrue(manager.messages(for: revisitSessionId).isEmpty)
        manager.switchTo(revisitSessionId)
        manager.markOrganized([revisitSessionId])
        manager.clearSession(clearAfterRevisitSessionId)
        manager.deleteSession(deleteAfterRevisitSessionId)
        XCTAssertEqual(
            sqlite3_exec(activatedLockDatabase, "COMMIT", nil, nil, nil),
            SQLITE_OK
        )
        await manager.flushPendingPersistence()
        let revisitedStore = try ChatHistoryStore(
            databaseURL: activatedDatabaseURL,
            performLegacyMigration: false
        )
        let storedRevisit = try XCTUnwrap(
            revisitedStore.message(sessionId: revisitSessionId, id: revisited.id)
        )
        XCTAssertEqual(storedRevisit.content, "旧游标")
        XCTAssertEqual(storedRevisit.runId, "run-old")
        XCTAssertEqual(storedRevisit.lastEventSequence, 1)
        let refreshedRevisit = try XCTUnwrap(
            manager.messages(for: revisitSessionId).first(where: { $0.id == revisited.id })
        )
        XCTAssertEqual(refreshedRevisit.runId, "run-old")
        XCTAssertEqual(refreshedRevisit.lastEventSequence, 1)
        XCTAssertNil(manager.sessionOrganizedAt[revisitSessionId])
        XCTAssertEqual(try revisitedStore.count(clearAfterRevisitSessionId), 0)
        XCTAssertEqual(manager.sessionMessageCounts[clearAfterRevisitSessionId], 0)
        XCTAssertEqual(manager.sessionTitles[clearAfterRevisitSessionId], "新会话")
        XCTAssertNil(try revisitedStore.summary(sessionId: deleteAfterRevisitSessionId))
        XCTAssertNil(manager.sessionTitles[deleteAfterRevisitSessionId])

        let activatedSessionId = manager.createSession()
        XCTAssertEqual(
            sqlite3_exec(activatedLockDatabase, "BEGIN IMMEDIATE", nil, nil, nil),
            SQLITE_OK
        )
        manager.setMessages([
            ChatMessage(
                id: "logout-write", sessionId: activatedSessionId,
                role: .user, content: "退出前消息"
            )
        ], for: activatedSessionId)
        manager.deactivateAccount()
        XCTAssertEqual(
            sqlite3_exec(activatedLockDatabase, "COMMIT", nil, nil, nil),
            SQLITE_OK
        )
        await manager.flushPendingPersistence()
        let activatedStore = try ChatHistoryStore(
            databaseURL: activatedDatabaseURL,
            performLegacyMigration: false
        )
        XCTAssertEqual(
            try activatedStore.message(sessionId: activatedSessionId, id: "logout-write")?.content,
            "退出前消息"
        )
    }

    @MainActor
    func testAccountSwitchAfterFirstBusyTimeoutRetriesOriginalStore() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let databaseURL = root.appendingPathComponent("history.sqlite")
        let store = try ChatHistoryStore(
            databaseURL: databaseURL,
            legacyDirectory: root.appendingPathComponent("legacy")
        )
        let manager = SessionManager(store: store)
        let sessionId = manager.createSession()
        var lockDatabase: OpaquePointer?
        XCTAssertEqual(sqlite3_open(databaseURL.path, &lockDatabase), SQLITE_OK)
        defer { sqlite3_close(lockDatabase) }
        XCTAssertEqual(sqlite3_exec(lockDatabase, "BEGIN IMMEDIATE", nil, nil, nil), SQLITE_OK)

        manager.setMessages([
            ChatMessage(
                id: "busy-account-write", sessionId: sessionId,
                role: .assistant, content: "原账户最终快照"
            )
        ], for: sessionId)
        try await Task.sleep(nanoseconds: 130_000_000)
        manager.activateAccount(
            tenantKey: "tenant-\(UUID().uuidString)",
            userId: "user-\(UUID().uuidString)"
        )
        XCTAssertEqual(sqlite3_exec(lockDatabase, "COMMIT", nil, nil, nil), SQLITE_OK)
        await manager.flushPendingPersistence()

        XCTAssertEqual(
            try store.message(sessionId: sessionId, id: "busy-account-write")?.content,
            "原账户最终快照"
        )
        XCTAssertNil(
            manager.messages(for: manager.activeSessionID())
                .first(where: { $0.id == "busy-account-write" })
        )
    }

    @MainActor
    func testFailedClearAndDeleteRestoreDurableProjection() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let databaseURL = root.appendingPathComponent("history.sqlite")
        let store = try ChatHistoryStore(
            databaseURL: databaseURL,
            legacyDirectory: root.appendingPathComponent("legacy")
        )
        let manager = SessionManager(store: store)
        let cleared = manager.createSession()
        let deleted = manager.createSession()
        let survivor = manager.createSession()
        manager.setMessages([
            ChatMessage(id: "clear-message", sessionId: cleared, role: .user, content: "保留清空数据")
        ], for: cleared)
        let deletedMessages = (0..<30).map { index in
            ChatMessage(
                id: "delete-message-\(index)", sessionId: deleted,
                role: .user, content: "保留删除数据 \(index)",
                createdAt: Date(timeIntervalSince1970: TimeInterval(index + 1))
            )
        }
        manager.setMessages(deletedMessages, for: deleted)
        await manager.flushPendingPersistence()

        var lockDatabase: OpaquePointer?
        XCTAssertEqual(sqlite3_open(databaseURL.path, &lockDatabase), SQLITE_OK)
        defer { sqlite3_close(lockDatabase) }
        XCTAssertEqual(sqlite3_exec(lockDatabase, "BEGIN IMMEDIATE", nil, nil, nil), SQLITE_OK)
        manager.clearSession(cleared)
        manager.switchTo(survivor)
        manager.deleteSession(deleted)
        await manager.flushPendingPersistence()

        XCTAssertEqual(manager.messages(for: cleared).first?.content, "保留清空数据")
        XCTAssertFalse(manager.messages(for: deleted).isEmpty)
        XCTAssertEqual(manager.sessionMessageCounts[deleted], 30)
        XCTAssertNotNil(manager.sessionTitles[deleted])
        XCTAssertEqual(sqlite3_exec(lockDatabase, "COMMIT", nil, nil, nil), SQLITE_OK)
        XCTAssertEqual(try store.count(cleared), 1)
        XCTAssertEqual(try store.count(deleted), 30)
    }

    @MainActor
    func testFailedClearMergesMessagesSentWhileMutationWasBlocked() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let databaseURL = root.appendingPathComponent("history.sqlite")
        let store = try ChatHistoryStore(
            databaseURL: databaseURL,
            legacyDirectory: root.appendingPathComponent("legacy")
        )
        let manager = SessionManager(store: store)
        let sessionId = manager.createSession()
        let oldMessage = ChatMessage(
            id: "before-clear", sessionId: sessionId,
            role: .user, content: "清空前消息"
        )
        manager.setMessages([oldMessage], for: sessionId)
        await manager.flushPendingPersistence()

        var lockDatabase: OpaquePointer?
        XCTAssertEqual(sqlite3_open(databaseURL.path, &lockDatabase), SQLITE_OK)
        defer { sqlite3_close(lockDatabase) }
        XCTAssertEqual(sqlite3_exec(lockDatabase, "BEGIN IMMEDIATE", nil, nil, nil), SQLITE_OK)

        manager.clearSession(sessionId)
        let newMessage = ChatMessage(
            id: "after-clear", sessionId: sessionId,
            role: .user, content: "清空失败后的新消息"
        )
        manager.setMessages([newMessage], for: sessionId)

        // Keep the lock until the failed clear callback has merged the durable
        // message with the newer in-memory message. This avoids timing the
        // assertion against scheduler latency.
        let expectedContents = Set(["清空前消息", "清空失败后的新消息"])
        for _ in 0..<100 where Set(manager.messages(for: sessionId).map(\.content)) != expectedContents {
            try await Task.sleep(nanoseconds: 20_000_000)
        }
        XCTAssertEqual(Set(manager.messages(for: sessionId).map(\.content)), expectedContents)
        XCTAssertEqual(sqlite3_exec(lockDatabase, "COMMIT", nil, nil, nil), SQLITE_OK)
        await manager.flushPendingPersistence()

        XCTAssertEqual(Set(manager.messages(for: sessionId).map(\.id)), ["before-clear", "after-clear"])
        XCTAssertEqual(try store.count(sessionId), 2)
        XCTAssertNotNil(try store.message(sessionId: sessionId, id: oldMessage.id))
        XCTAssertNotNil(try store.message(sessionId: sessionId, id: newMessage.id))
    }

    @MainActor
    func testClearAndDeleteIgnoreOlderPersistenceCompletions() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let databaseURL = root.appendingPathComponent("history.sqlite")
        let store = try ChatHistoryStore(
            databaseURL: databaseURL,
            legacyDirectory: root.appendingPathComponent("legacy")
        )
        let manager = SessionManager(store: store)

        let cleared = manager.createSession()
        var lockDatabase: OpaquePointer?
        XCTAssertEqual(sqlite3_open(databaseURL.path, &lockDatabase), SQLITE_OK)
        defer { sqlite3_close(lockDatabase) }
        XCTAssertEqual(sqlite3_exec(lockDatabase, "BEGIN IMMEDIATE", nil, nil, nil), SQLITE_OK)
        manager.setMessages([
            ChatMessage(id: "stale-clear", sessionId: cleared, role: .user, content: "不应恢复的标题")
        ], for: cleared)
        manager.clearSession(cleared)
        XCTAssertEqual(sqlite3_exec(lockDatabase, "COMMIT", nil, nil, nil), SQLITE_OK)
        await manager.flushPendingPersistence()
        XCTAssertEqual(try store.count(cleared), 0)
        XCTAssertEqual(manager.sessionMessageCounts[cleared], 0)
        XCTAssertEqual(manager.sessionTitles[cleared], "新会话")

        let deleted = manager.createSession()
        XCTAssertEqual(sqlite3_exec(lockDatabase, "BEGIN IMMEDIATE", nil, nil, nil), SQLITE_OK)
        manager.setMessages([
            ChatMessage(id: "stale-delete", sessionId: deleted, role: .user, content: "不得复活")
        ], for: deleted)
        manager.deleteSession(deleted)
        XCTAssertEqual(sqlite3_exec(lockDatabase, "COMMIT", nil, nil, nil), SQLITE_OK)
        await manager.flushPendingPersistence()
        XCTAssertNil(try store.summary(sessionId: deleted))
        XCTAssertNil(manager.sessionTitles[deleted])
        XCTAssertNil(manager.sessionMessageCounts[deleted])
    }

    func testChatHistoryStoreSerializesConcurrentTransactionsAndStatusBackfill() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("chat-history-concurrent-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy", isDirectory: true),
            performLegacyMigration: false
        )
        let sessionId = "concurrent-session"
        let messages = (0..<40).map { index in
            ChatMessage(
                id: "m-\(index)", sessionId: sessionId, role: .assistant,
                content: "pending-\(index)", pending: true
            )
        }
        let errors = LockedErrorBox()
        let queue = DispatchQueue(label: "chat-history-concurrent", attributes: .concurrent)
        let firstBatch = DispatchGroup()
        for message in messages {
            firstBatch.enter()
            queue.async {
                defer { firstBatch.leave() }
                do { try store.upsert([message], sessionId: sessionId) }
                catch { errors.append(error) }
            }
        }
        XCTAssertEqual(firstBatch.wait(timeout: .now() + 10), .success)
        XCTAssertTrue(errors.isEmpty)
        XCTAssertEqual(try store.count(sessionId), 40)

        try store.clear(sessionId)
        try store.upsert(messages, sessionId: sessionId)

        let secondBatch = DispatchGroup()
        secondBatch.enter()
        queue.async {
            defer { secondBatch.leave() }
            do { try store.truncate(sessionId: sessionId, from: "m-20") }
            catch { errors.append(error) }
        }
        for message in messages.prefix(20) {
            secondBatch.enter()
            queue.async {
                defer { secondBatch.leave() }
                var settled = message
                settled.content = "settled-\(message.id)"
                settled.pending = false
                do { try store.upsert([settled], sessionId: sessionId) }
                catch { errors.append(error) }
            }
        }
        XCTAssertEqual(secondBatch.wait(timeout: .now() + 10), .success)
        XCTAssertTrue(errors.isEmpty)
        XCTAssertEqual(try store.count(sessionId), 20)
        for index in 0..<20 {
            let stored = try XCTUnwrap(store.message(sessionId: sessionId, id: "m-\(index)"))
            XCTAssertFalse(stored.pending)
            XCTAssertEqual(stored.content, "settled-m-\(index)")
        }
    }

    @MainActor
    func testLeavingDuringCheckpointDoesNotPollOrCancelUnsubmittedRun() async throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("chat-checkpoint-leave-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let databaseURL = root.appendingPathComponent("history.sqlite")
        let store = try ChatHistoryStore(
            databaseURL: databaseURL,
            legacyDirectory: root.appendingPathComponent("legacy", isDirectory: true),
            performLegacyMigration: false
        )
        let sessionId = "checkpoint-session"
        let user = ChatMessage(
            id: "checkpoint-user", sessionId: sessionId,
            role: .user, content: "继续执行"
        )
        try store.upsert([user], sessionId: sessionId)
        let manager = SessionManager(store: store)
        let otherSessionId = manager.createSession()
        manager.switchTo(sessionId)
        let coordinator = TenantSessionCoordinator(sessionManager: manager)

        var lockDatabase: OpaquePointer?
        XCTAssertEqual(sqlite3_open(databaseURL.path, &lockDatabase), SQLITE_OK)
        defer { sqlite3_close(lockDatabase) }
        XCTAssertEqual(sqlite3_exec(lockDatabase, "BEGIN IMMEDIATE", nil, nil, nil), SQLITE_OK)

        coordinator.startGeneration(
            text: user.content,
            quote: nil,
            userMessageId: user.id
        )
        try await Task.sleep(nanoseconds: 50_000_000)
        XCTAssertTrue(coordinator.isCheckpointingRunForTesting)
        coordinator.prepareForBackground()
        XCTAssertTrue(coordinator.isCheckpointingRunForTesting)
        XCTAssertTrue(coordinator.isGenerating)
        XCTAssertEqual(coordinator.backgroundMonitorCountForTesting, 0)
        coordinator.switchSession(to: otherSessionId)
        XCTAssertEqual(manager.activeSessionID(), otherSessionId)
        XCTAssertTrue(coordinator.isCheckpointingRunForTesting)
        XCTAssertTrue(coordinator.isGenerating)
        XCTAssertEqual(coordinator.backgroundMonitorCountForTesting, 0)
        XCTAssertTrue(TenantSessionCoordinator.shouldContinueSubmissionAfterCheckpoint(
            isCancelled: false,
            epochMatches: true,
            activeSessionMatches: false,
            detachRequested: true
        ))
        XCTAssertFalse(TenantSessionCoordinator.shouldContinueSubmissionAfterCheckpoint(
            isCancelled: false,
            epochMatches: true,
            activeSessionMatches: false,
            detachRequested: false
        ))

        coordinator.cancelAllTasksAndAnimations()
        XCTAssertEqual(sqlite3_exec(lockDatabase, "COMMIT", nil, nil, nil), SQLITE_OK)
        await manager.flushPendingPersistence()
    }

    @MainActor
    func testSessionManagerOrdersTruncateAndStatusAfterOlderSnapshots() async throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("chat-ordered-writes-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let databaseURL = root.appendingPathComponent("history.sqlite")
        let store = try ChatHistoryStore(
            databaseURL: databaseURL,
            legacyDirectory: root.appendingPathComponent("legacy", isDirectory: true),
            performLegacyMigration: false
        )
        let sessionId = "ordered-session"
        let user = ChatMessage(id: "user", sessionId: sessionId, role: .user, content: "问题")
        let pending = ChatMessage(
            id: "request", sessionId: sessionId, role: .assistant,
            content: "", isStreaming: true, pending: true
        )
        try store.upsert([user, pending], sessionId: sessionId)
        let manager = SessionManager(store: store)

        var lockDatabase: OpaquePointer?
        XCTAssertEqual(sqlite3_open(databaseURL.path, &lockDatabase), SQLITE_OK)
        defer { sqlite3_close(lockDatabase) }
        XCTAssertEqual(sqlite3_exec(lockDatabase, "BEGIN IMMEDIATE", nil, nil, nil), SQLITE_OK)
        var stale = pending
        stale.content = "stale"
        manager.setMessages([user, stale], for: sessionId)
        manager.truncateMessages(from: pending.id, sessionId: sessionId)
        XCTAssertEqual(sqlite3_exec(lockDatabase, "COMMIT", nil, nil, nil), SQLITE_OK)
        await manager.flushPendingPersistence()
        XCTAssertNil(try store.message(sessionId: sessionId, id: pending.id))

        let pendingStatus = ChatMessage(
            id: "request-2", sessionId: sessionId, role: .assistant,
            content: "", isStreaming: true, pending: true
        )
        try store.upsert([pendingStatus], sessionId: sessionId)
        manager.cacheVisibleMessages([user, pendingStatus], for: sessionId)
        XCTAssertEqual(sqlite3_exec(lockDatabase, "BEGIN IMMEDIATE", nil, nil, nil), SQLITE_OK)
        var olderSnapshot = pendingStatus
        olderSnapshot.content = "older"
        manager.setMessages([user, olderSnapshot], for: sessionId)
        manager.applyCompletedStatus(
            sessionId: sessionId,
            requestId: pendingStatus.id,
            answer: "Hermes completed"
        )
        XCTAssertEqual(sqlite3_exec(lockDatabase, "COMMIT", nil, nil, nil), SQLITE_OK)
        await manager.flushPendingPersistence()
        let completed = try XCTUnwrap(
            store.message(sessionId: sessionId, id: pendingStatus.id)
        )
        XCTAssertEqual(completed.content, "Hermes completed")
        XCTAssertFalse(completed.pending)
        XCTAssertFalse(completed.isStreaming)

        manager.clearSession(sessionId)
        manager.deactivateAccount()
        await manager.flushPendingPersistence()
        XCTAssertEqual(try store.count(sessionId), 0)
    }

    @MainActor
    func testSessionManagerDoesNotBlockMainActorWhenSQLiteWriterIsBusy() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let databaseURL = root.appendingPathComponent("history.sqlite")
        let store = try ChatHistoryStore(
            databaseURL: databaseURL,
            legacyDirectory: root.appendingPathComponent("legacy")
        )
        let manager = SessionManager(store: store)
        let sessionId = manager.createSession()

        var lockDatabase: OpaquePointer?
        XCTAssertEqual(sqlite3_open(databaseURL.path, &lockDatabase), SQLITE_OK)
        defer { sqlite3_close(lockDatabase) }
        XCTAssertEqual(sqlite3_exec(lockDatabase, "BEGIN IMMEDIATE", nil, nil, nil), SQLITE_OK)

        let startedAt = CFAbsoluteTimeGetCurrent()
        manager.setMessages([
            ChatMessage(id: "queued", sessionId: sessionId, role: .user, content: "立即发送")
        ], for: sessionId)
        let elapsed = CFAbsoluteTimeGetCurrent() - startedAt

        XCTAssertLessThan(elapsed, 0.2)
        XCTAssertEqual(manager.messages(for: sessionId).first?.content, "立即发送")
        XCTAssertEqual(sqlite3_exec(lockDatabase, "COMMIT", nil, nil, nil), SQLITE_OK)
        await manager.flushPendingPersistence()
        XCTAssertEqual(try store.message(sessionId: sessionId, id: "queued")?.content, "立即发送")
    }

    @MainActor
    func testSessionManagerCoalescesHighFrequencyStreamingPersistence() async throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("chat-coalesced-stream-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let databaseURL = root.appendingPathComponent("history.sqlite")
        let store = try ChatHistoryStore(
            databaseURL: databaseURL,
            legacyDirectory: root.appendingPathComponent("legacy")
        )
        let manager = SessionManager(store: store)
        let sessionId = manager.createSession()
        var streaming = ChatMessage(
            id: "streaming", sessionId: sessionId, role: .assistant,
            content: "chunk-0", isStreaming: true, pending: true
        )
        manager.setMessages([streaming], for: sessionId)
        await manager.flushPendingPersistence()

        var lockDatabase: OpaquePointer?
        XCTAssertEqual(sqlite3_open(databaseURL.path, &lockDatabase), SQLITE_OK)
        defer { sqlite3_close(lockDatabase) }
        XCTAssertEqual(sqlite3_exec(lockDatabase, "BEGIN IMMEDIATE", nil, nil, nil), SQLITE_OK)
        let initialGeneration = manager.persistenceTaskGenerationForTesting

        streaming.content = "chunk-1"
        manager.setMessages([streaming], for: sessionId)
        try await Task.sleep(nanoseconds: 20_000_000)
        for index in 2...1_000 {
            streaming.content = "chunk-\(index)"
            manager.setMessages([streaming], for: sessionId)
        }
        // Keep SQLite busy past one write timeout. The latest snapshot may move
        // to one replacement task, but must not allocate one task per delta.
        try await Task.sleep(nanoseconds: 150_000_000)
        XCTAssertLessThanOrEqual(manager.pendingPersistenceSnapshotCountForTesting, 1)
        XCTAssertLessThanOrEqual(manager.scheduledPersistenceWriteCountForTesting, 1)
        XCTAssertLessThanOrEqual(
            manager.persistenceTaskGenerationForTesting - initialGeneration,
            2
        )

        XCTAssertEqual(sqlite3_exec(lockDatabase, "COMMIT", nil, nil, nil), SQLITE_OK)
        try await Task.sleep(nanoseconds: 350_000_000)
        await manager.flushPendingPersistence()

        XCTAssertEqual(
            try store.message(sessionId: sessionId, id: streaming.id)?.content,
            "chunk-1000"
        )
        XCTAssertEqual(manager.pendingPersistenceSnapshotCountForTesting, 0)
        XCTAssertEqual(manager.scheduledPersistenceWriteCountForTesting, 0)
    }

    @MainActor
    func testSessionManagerAutomaticallyRetriesTheLastFailedSnapshot() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let databaseURL = root.appendingPathComponent("history.sqlite")
        let store = try ChatHistoryStore(
            databaseURL: databaseURL,
            legacyDirectory: root.appendingPathComponent("legacy")
        )
        let manager = SessionManager(store: store)
        let sessionId = manager.createSession()
        var lockDatabase: OpaquePointer?
        XCTAssertEqual(sqlite3_open(databaseURL.path, &lockDatabase), SQLITE_OK)
        defer { sqlite3_close(lockDatabase) }
        XCTAssertEqual(sqlite3_exec(lockDatabase, "BEGIN IMMEDIATE", nil, nil, nil), SQLITE_OK)

        let final = ChatMessage(
            id: "last-stream-snapshot", sessionId: sessionId, role: .assistant,
            content: "最终内容", runId: "run-final", lastEventSequence: 77
        )
        let capturedLockDatabase = lockDatabase
        let unlockTask = Task.detached { () -> Int32 in
            try? await Task.sleep(nanoseconds: 150_000_000)
            return sqlite3_exec(capturedLockDatabase, "COMMIT", nil, nil, nil)
        }
        manager.setMessages([final], for: sessionId)
        await manager.flushPendingPersistence()
        let unlockResult = await unlockTask.value
        XCTAssertEqual(unlockResult, SQLITE_OK)

        let persisted = try XCTUnwrap(store.message(sessionId: sessionId, id: final.id))
        XCTAssertEqual(persisted.content, "最终内容")
        XCTAssertEqual(persisted.runId, "run-final")
        XCTAssertEqual(persisted.lastEventSequence, 77)
    }

    @MainActor
    func testMetadataWriteFailuresDoNotPublishStaleInMemoryProjection() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("chat-metadata-failure-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let databaseURL = root.appendingPathComponent("history.sqlite")
        let store = try ChatHistoryStore(
            databaseURL: databaseURL,
            legacyDirectory: root.appendingPathComponent("legacy")
        )
        let manager = SessionManager(store: store)
        let parent = manager.createSession()
        let source = ChatMessage(
            id: "source", sessionId: parent, role: .assistant,
            content: "需要拆出的主题"
        )
        let topic = try XCTUnwrap(manager.startTopic(parentSessionId: parent, sourceMessage: source))
        let lifecycleSession = manager.createSession()

        var lockDatabase: OpaquePointer?
        XCTAssertEqual(sqlite3_open(databaseURL.path, &lockDatabase), SQLITE_OK)
        defer { sqlite3_close(lockDatabase) }
        XCTAssertEqual(sqlite3_exec(lockDatabase, "BEGIN IMMEDIATE", nil, nil, nil), SQLITE_OK)

        let sessionCountBeforeFailedTopic = manager.sessionTitles.count
        XCTAssertNil(manager.startTopic(parentSessionId: parent, sourceMessage: source))
        XCTAssertEqual(manager.sessionTitles.count, sessionCountBeforeFailedTopic)
        manager.markTopicEnding(topic.sessionId)
        manager.finishTopic(topic.sessionId)
        manager.setLifecycle(.archived, for: lifecycleSession)
        manager.markOrganized([lifecycleSession])

        XCTAssertEqual(manager.topicSessions[topic.sessionId]?.state, .active)
        XCTAssertEqual(manager.sessionLifecycle[lifecycleSession], .active)
        XCTAssertNil(manager.sessionOrganizedAt[lifecycleSession])

        XCTAssertEqual(sqlite3_exec(lockDatabase, "COMMIT", nil, nil, nil), SQLITE_OK)
        manager.markTopicEnding(topic.sessionId)
        manager.setLifecycle(.archived, for: lifecycleSession)
        manager.markOrganized([lifecycleSession])

        XCTAssertEqual(manager.topicSessions[topic.sessionId]?.state, .ending)
        XCTAssertEqual(manager.sessionLifecycle[lifecycleSession], .archived)
        XCTAssertNotNil(manager.sessionOrganizedAt[lifecycleSession])
        XCTAssertEqual(try store.summary(sessionId: topic.sessionId)?.topic?.state, .ending)
        XCTAssertEqual(try store.summary(sessionId: lifecycleSession)?.lifecycleStatus, .archived)
        XCTAssertNotNil(try store.summary(sessionId: lifecycleSession)?.organizedAt)
    }

    @MainActor
    func testTopicFinishAndPromotionRemainAtomicWhenSQLiteWriteFails() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let databaseURL = root.appendingPathComponent("history.sqlite")
        let store = try ChatHistoryStore(
            databaseURL: databaseURL,
            legacyDirectory: root.appendingPathComponent("legacy")
        )
        let manager = SessionManager(store: store)
        let parent = manager.createSession()
        let topics = try (0..<4).map { index in
            try XCTUnwrap(manager.startTopic(
                parentSessionId: parent,
                sourceMessage: ChatMessage(
                    id: "atomic-source-\(index)", sessionId: parent,
                    role: .assistant, content: "原子晋升 \(index)"
                )
            ))
        }
        var lockDatabase: OpaquePointer?
        XCTAssertEqual(sqlite3_open(databaseURL.path, &lockDatabase), SQLITE_OK)
        defer { sqlite3_close(lockDatabase) }
        XCTAssertEqual(sqlite3_exec(lockDatabase, "BEGIN IMMEDIATE", nil, nil, nil), SQLITE_OK)

        manager.finishTopic(topics[0].sessionId)

        XCTAssertEqual(manager.topicSessions[topics[0].sessionId]?.state, .active)
        XCTAssertEqual(manager.topicSessions[topics[3].sessionId]?.state, .queued)
        XCTAssertEqual(sqlite3_exec(lockDatabase, "COMMIT", nil, nil, nil), SQLITE_OK)

        manager.finishTopic(topics[0].sessionId)
        XCTAssertEqual(manager.topicSessions[topics[0].sessionId]?.state, .ended)
        XCTAssertEqual(manager.topicSessions[topics[3].sessionId]?.state, .active)
        XCTAssertEqual(try store.summary(sessionId: topics[0].sessionId)?.topic?.state, .ended)
        XCTAssertEqual(try store.summary(sessionId: topics[3].sessionId)?.topic?.state, .active)
    }

    @MainActor
    func testTopicDeleteAndPromotionRemainAtomicWhenSQLiteWriteFails() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let databaseURL = root.appendingPathComponent("history.sqlite")
        let store = try ChatHistoryStore(
            databaseURL: databaseURL,
            legacyDirectory: root.appendingPathComponent("legacy")
        )
        let manager = SessionManager(store: store)
        let parent = manager.createSession()
        let topics = try (0..<4).map { index in
            try XCTUnwrap(manager.startTopic(
                parentSessionId: parent,
                sourceMessage: ChatMessage(
                    id: "delete-source-\(index)", sessionId: parent,
                    role: .assistant, content: "删除晋升 \(index)"
                )
            ))
        }
        var lockDatabase: OpaquePointer?
        XCTAssertEqual(sqlite3_open(databaseURL.path, &lockDatabase), SQLITE_OK)
        defer { sqlite3_close(lockDatabase) }
        XCTAssertEqual(sqlite3_exec(lockDatabase, "BEGIN IMMEDIATE", nil, nil, nil), SQLITE_OK)

        manager.deleteSession(topics[0].sessionId)
        await manager.flushPendingPersistence()

        XCTAssertEqual(manager.topicSessions[topics[0].sessionId]?.state, .active)
        XCTAssertEqual(manager.topicSessions[topics[3].sessionId]?.state, .queued)
        XCTAssertEqual(sqlite3_exec(lockDatabase, "COMMIT", nil, nil, nil), SQLITE_OK)

        manager.deleteSession(topics[0].sessionId)
        await manager.flushPendingPersistence()
        XCTAssertNil(manager.topicSessions[topics[0].sessionId])
        XCTAssertEqual(manager.topicSessions[topics[3].sessionId]?.state, .active)
        XCTAssertNil(try store.summary(sessionId: topics[0].sessionId))
        XCTAssertEqual(try store.summary(sessionId: topics[3].sessionId)?.topic?.state, .active)
    }

    @MainActor
    func testInFlightDeleteReservationPreventsDuplicatePromotionAndCapacityOverflow() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let oldDatabaseURL = root.appendingPathComponent("old-history.sqlite")
        let oldStore = try ChatHistoryStore(
            databaseURL: oldDatabaseURL,
            legacyDirectory: root.appendingPathComponent("legacy")
        )
        let manager = SessionManager(store: oldStore)
        let oldSession = manager.createSession()
        var lockDatabase: OpaquePointer?
        XCTAssertEqual(sqlite3_open(oldDatabaseURL.path, &lockDatabase), SQLITE_OK)
        defer { sqlite3_close(lockDatabase) }
        XCTAssertEqual(sqlite3_exec(lockDatabase, "BEGIN IMMEDIATE", nil, nil, nil), SQLITE_OK)
        manager.setMessages([
            ChatMessage(id: "tail-blocker", sessionId: oldSession, role: .user, content: "阻塞旧账户tail")
        ], for: oldSession)
        try await Task.sleep(nanoseconds: 20_000_000)

        manager.activateAccount(
            tenantKey: "reservation-tenant-\(UUID().uuidString)",
            userId: "reservation-user-\(UUID().uuidString)"
        )
        let accountDirectory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
            .appendingPathComponent("ChatHistory/accounts/\(manager.activeAccountFingerprint)")
        defer { try? FileManager.default.removeItem(at: accountDirectory) }
        let parent = manager.createSession()
        let topics = try (0..<5).map { index in
            try XCTUnwrap(manager.startTopic(
                parentSessionId: parent,
                sourceMessage: ChatMessage(
                    id: "reserved-source-\(index)", sessionId: parent,
                    role: .assistant, content: "预留晋升 \(index)"
                )
            ))
        }
        let generationBeforeDelete = manager.persistenceTaskGenerationForTesting

        manager.deleteSession(topics[0].sessionId)
        manager.deleteSession(topics[0].sessionId)
        XCTAssertEqual(manager.persistenceTaskGenerationForTesting - generationBeforeDelete, 1)
        manager.finishTopic(topics[1].sessionId)
        manager.finishTopic(topics[3].sessionId)
        let extra = try XCTUnwrap(manager.startTopic(
            parentSessionId: parent,
            sourceMessage: ChatMessage(
                id: "reserved-source-extra", sessionId: parent,
                role: .assistant, content: "容量不得溢出"
            )
        ))

        XCTAssertEqual(manager.topicSessions[topics[3].sessionId]?.state, .queued)
        XCTAssertEqual(manager.topicSessions[topics[4].sessionId]?.state, .active)
        XCTAssertEqual(extra.state, .queued)
        XCTAssertEqual(sqlite3_exec(lockDatabase, "COMMIT", nil, nil, nil), SQLITE_OK)
        await manager.flushPendingPersistence()

        let activeCount = manager.topicSessions.values.filter {
            $0.state == .active || $0.state == .ending
        }.count
        XCTAssertEqual(activeCount, SessionManager.maximumActiveTopics)
        XCTAssertEqual(manager.topicSessions[topics[3].sessionId]?.state, .active)
        XCTAssertEqual(manager.topicSessions[topics[4].sessionId]?.state, .active)
        XCTAssertEqual(manager.topicSessions[extra.sessionId]?.state, .queued)
    }

    @MainActor
    func testTopicSessionsCapQueuePromoteAndPersistMetadata() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let databaseURL = root.appendingPathComponent("history.sqlite")
        let legacyURL = root.appendingPathComponent("legacy")
        let store = try ChatHistoryStore(databaseURL: databaseURL, legacyDirectory: legacyURL)
        let manager = SessionManager(store: store)
        let parent = manager.createSession()

        let topics = try (0..<4).map { index in
            try XCTUnwrap(manager.startTopic(
                parentSessionId: parent,
                sourceMessage: ChatMessage(
                    id: "source-\(index)", sessionId: parent,
                    role: .assistant, content: "话题来源 \(index)"
                )
            ))
        }

        XCTAssertEqual(topics.prefix(3).map(\.state), [.active, .active, .active])
        XCTAssertEqual(topics[3].state, .queued)
        manager.finishTopic(topics[0].sessionId)
        XCTAssertEqual(manager.topicSessions[topics[0].sessionId]?.state, .ended)
        XCTAssertEqual(manager.topicSessions[topics[3].sessionId]?.state, .active)

        let restored = SessionManager(
            store: try ChatHistoryStore(databaseURL: databaseURL, legacyDirectory: legacyURL)
        )
        XCTAssertEqual(restored.topicSessions[topics[0].sessionId]?.state, .ended)
        XCTAssertEqual(restored.topicSessions[topics[3].sessionId]?.sourceMessageId, "source-3")
        XCTAssertEqual(restored.visibleTopics.count, 3)
    }

    func testLoginChannelsRemainFailClosedBeforeCapabilityProbeCompletes() {
        let availability = LoginChannelAvailability()
        XCTAssertFalse(availability.phone)
        XCTAssertFalse(availability.alipay)
        XCTAssertFalse(availability.wechat)
    }

    func testLoginChannelsHonorExplicitCapabilityResponse() {
        var availability = LoginChannelAvailability()
        availability.apply(
            AuthCapabilitiesDTO(
                phone: AuthCapabilityDTO(enabled: false),
                oauth: OAuthCapabilitiesDTO(
                    wechat: AuthCapabilityDTO(enabled: true),
                    alipay: AuthCapabilityDTO(enabled: false)
                )
            )
        )
        XCTAssertFalse(availability.phone)
        XCTAssertTrue(availability.wechat)
        XCTAssertFalse(availability.alipay)
    }

    func testDeveloperCredentialsBypassUnavailableSmsChannel() {
        XCTAssertTrue(
            LoginInputPolicy.canSubmit(
                phone: "13800138000",
                code: "246810",
                phoneChannelEnabled: false,
                isLoading: false
            )
        )
        XCTAssertFalse(
            LoginInputPolicy.canSubmit(
                phone: "13800138001",
                code: "246810",
                phoneChannelEnabled: false,
                isLoading: false
            )
        )
    }

    func testLoginInputPolicyKeepsOnlyBoundedDigits() {
        XCTAssertEqual(LoginInputPolicy.digits("138 0013-8000 extra", limit: 11), "13800138000")
        XCTAssertEqual(LoginInputPolicy.digits("24681099", limit: 6), "246810")
    }

    func testAuthentication401PreservesBackendReason() {
        let body = Data(#"{"detail":"验证码无效或已过期"}"#.utf8)
        let error = APIError.authenticationFailure(body: body)
        XCTAssertEqual(error.localizedDescription, "验证码无效或已过期")
    }

    func testStreamingPreviewKeepsOnlyBoundedTail() {
        let content = String(repeating: "前", count: 1_200)
            + String(repeating: "后", count: 2_400)
        let preview = LongMessagePresentation.streamingPreview(content)

        XCTAssertTrue(preview.omittedPrefix)
        XCTAssertEqual(preview.content.count, 2_400)
        XCTAssertEqual(preview.content, String(repeating: "后", count: 2_400))
    }

    func testStreamingPreviewLeavesShortContentUnchanged() {
        let content = "短回答"
        let preview = LongMessagePresentation.streamingPreview(content)

        XCTAssertFalse(preview.omittedPrefix)
        XCTAssertEqual(preview.content, content)
    }

    func testStreamingPreviewExpandsBackwardInBoundedSteps() {
        let content = String(repeating: "前", count: 2_400)
            + String(repeating: "中", count: 2_400)
            + String(repeating: "后", count: 2_400)

        let initial = LongMessagePresentation.streamingPreview(content, limit: 2_400)
        let expanded = LongMessagePresentation.streamingPreview(content, limit: 4_800)
        let complete = LongMessagePresentation.streamingPreview(content, limit: 7_200)

        XCTAssertTrue(initial.omittedPrefix)
        XCTAssertEqual(initial.content, String(repeating: "后", count: 2_400))
        XCTAssertTrue(expanded.omittedPrefix)
        XCTAssertEqual(expanded.content, String(repeating: "中", count: 2_400) + String(repeating: "后", count: 2_400))
        XCTAssertFalse(complete.omittedPrefix)
        XCTAssertEqual(complete.content, content)
        XCTAssertEqual(LongMessagePresentation.nextStreamingLimit(current: 2_400, contentCount: 7_200), 4_800)
        XCTAssertEqual(LongMessagePresentation.nextStreamingLimit(current: 4_800, contentCount: 7_200), 7_200)
        XCTAssertEqual(LongMessagePresentation.nextStreamingLimit(current: 7_200, contentCount: 7_200), 7_200)
    }

    func testLongPreviewHandlesExtendedGraphemeClustersWithoutIndexCrash() {
        let content = String(repeating: "👨‍👩‍👧‍👦e\u{301}", count: 2_100)
        let streaming = LongMessagePresentation.streamingPreview(content)
        let collapsed = LongMessagePresentation.collapsedPreview(content)

        XCTAssertEqual(streaming.content.count, LongMessagePresentation.streamingCharacterLimit)
        XCTAssertEqual(collapsed.count, LongMessagePresentation.collapsedCharacterLimit)
        XCTAssertEqual(LongMessagePresentation.streamingPreview(content, limit: -1).content, "")
        XCTAssertEqual(LongMessagePresentation.collapsedPreview(content, limit: -1), "")
    }

    func testLongAnswerSemanticBlocksPreserveMarkdownStructure() {
        let markdown = """
        # 标题

        - [链接](https://example.com)
        - 列表项

        | 名称 | 值 |
        | --- | --- |
        | A | 1 |
        """ + String(repeating: "\n\n正文", count: 2_000)
        let blocks = MarkdownBlockParser.shared.parse(
            markdown,
            messageId: "long-semantic-\(UUID().uuidString)"
        )

        XCTAssertTrue(blocks.contains { if case .heading = $0 { return true }; return false })
        XCTAssertTrue(blocks.contains { if case .bulletList = $0 { return true }; return false })
        XCTAssertTrue(blocks.contains { if case .table = $0 { return true }; return false })
    }

    func testRecoveredRunPresentationReplacesInterruptedCard() {
        let message = ChatMessage(
            id: "recovering", sessionId: "session", role: .interrupted,
            content: "连接中断"
        )
        XCTAssertTrue(TenantSessionCoordinator.isProcessingExistingRun(
            message,
            reconcilingMessageIDs: [message.id],
            backgroundProcessingSessionIDs: []
        ))
    }

    func testRunReconciliationOwnerIsNotDuplicated() {
        let messageID = "assistant-recovery"
        XCTAssertTrue(TenantSessionCoordinator.shouldStartRunReconciliation(
            messageId: messageID,
            reconcilingMessageIDs: []
        ))
        XCTAssertFalse(TenantSessionCoordinator.shouldStartRunReconciliation(
            messageId: messageID,
            reconcilingMessageIDs: [messageID]
        ))
    }

    func testRecoveredRunMonitorRemainsPresentationOwnerAfterProbeHandoff() {
        let message = ChatMessage(
            id: "recovered-monitor", sessionId: "session", role: .assistant,
            content: "", isStreaming: true, pending: true
        )
        XCTAssertTrue(TenantSessionCoordinator.isProcessingExistingRun(
            message,
            reconcilingMessageIDs: [message.id],
            backgroundProcessingSessionIDs: []
        ))
    }

    @MainActor
    func testRunProjectionCheckpointSurvivesImmediateReopenWithoutAsyncFlush() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let databaseURL = root.appendingPathComponent("history.sqlite")
        let legacyURL = root.appendingPathComponent("legacy")
        let store = try ChatHistoryStore(databaseURL: databaseURL, legacyDirectory: legacyURL)
        let manager = SessionManager(store: store)
        let sessionId = manager.createSession()
        let projection = [
            ChatMessage(id: "user", sessionId: sessionId, role: .user, content: "长任务"),
            ChatMessage(
                id: "request", sessionId: sessionId, role: .assistant,
                content: "", isStreaming: true, pending: true
            )
        ]

        let checkpointed = await manager.checkpointRunProjection(projection, for: sessionId)
        XCTAssertTrue(checkpointed)

        let reopened = try ChatHistoryStore(
            databaseURL: databaseURL, legacyDirectory: legacyURL,
            performLegacyMigration: false
        )
        let restored = try reopened.latest(sessionId: sessionId).messages
        XCTAssertEqual(restored.map(\.id), ["user", "request"])
        XCTAssertTrue(restored.last?.pending == true)
    }

    @MainActor
    func testRetryWhileGeneratingShowsHintWithoutChangingRunState() {
        let coordinator = TenantSessionCoordinator()
        coordinator.isGenerating = true
        coordinator.retryMessage("existing-run")

        XCTAssertTrue(coordinator.isGenerating)
        XCTAssertEqual(coordinator.toastMessage, "原任务仍在 Hermes 后台处理中，无需重复执行")
    }

    func testCompletedLongAnswerUsesBoundedSemanticPreview() {
        let first = String(repeating: "甲", count: 800)
        let second = String(repeating: "乙", count: 4_000)
        let content = first + "\n\n" + second
        let preview = LongMessagePresentation.collapsedPreview(content)

        XCTAssertTrue(LongMessagePresentation.isLong(content))
        XCTAssertEqual(preview, first)
        XCTAssertLessThanOrEqual(preview.count, LongMessagePresentation.collapsedCharacterLimit)
    }

    func testLongStreamingPolicyBoundsRefreshAndTypewriterUpdates() {
        XCTAssertTrue(ChatStreamingPerformancePolicy.shouldPublishImmediately(publishedUTF8Count: 0))
        XCTAssertFalse(ChatStreamingPerformancePolicy.shouldPublishImmediately(publishedUTF8Count: 1))
        XCTAssertEqual(ChatStreamingPerformancePolicy.flushDelayNanoseconds(currentUTF8Count: 3_999), 160_000_000)
        XCTAssertEqual(ChatStreamingPerformancePolicy.flushDelayNanoseconds(currentUTF8Count: 4_000), 250_000_000)
        XCTAssertEqual(ChatStreamingPerformancePolicy.flushDelayNanoseconds(currentUTF8Count: 12_000), 400_000_000)

        let total = 100_000
        let batch = ChatStreamingPerformancePolicy.typewriterBatchSize(totalCharacterCount: total)
        XCTAssertLessThanOrEqual((total + batch - 1) / batch, 24)
    }

    func testChatDraftSubmissionConsumesTextExactlyOnce() {
        var draft = "  帮我继续调研鹿岛  "
        XCTAssertEqual(ChatDraftSubmission.consume(&draft), "帮我继续调研鹿岛")
        XCTAssertEqual(draft, "")
        XCTAssertNil(ChatDraftSubmission.consume(&draft))
    }

    func testChatDraftSubmissionKeepsWhitespaceOnlyDraftUnsent() {
        var draft = "   \n "
        XCTAssertNil(ChatDraftSubmission.consume(&draft))
        XCTAssertEqual(draft, "   \n ")
    }

    func testCloudKnowledgeSnapshotDecodesForReinstallRestore() throws {
        let data = Data("""
        {
          "items": [{
            "note_id": "note-1",
            "markdown": "---\\nid: note-1\\ntitle: 私有笔记\\n---\\n正文",
            "content_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "updated_at": "2026-09-01T12:00:00.000Z",
            "archived": false,
            "merged_into_note_id": null
          }],
          "count": 1,
          "compile_status": "private_index_ready"
        }
        """.utf8)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(CloudKnowledgeNotesResponse.self, from: data)
        XCTAssertEqual(response.count, 1)
        XCTAssertEqual(response.items.first?.noteId, "note-1")
        XCTAssertEqual(response.compileStatus, "private_index_ready")
    }

    func testDurableRunCursorPersistsAcrossColdStart() throws {
        let message = ChatMessage(
            id: "assistant-1", sessionId: "session-1", role: .assistant,
            content: "部分回答", isStreaming: true, pending: true,
            runId: "run-123", lastEventSequence: 42
        )
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let restored = try decoder.decode(
            PersistedMessage.self,
            from: encoder.encode(PersistedMessage(message))
        ).toChatMessage(sessionId: "session-1")
        XCTAssertEqual(restored.runId, "run-123")
        XCTAssertEqual(restored.lastEventSequence, 42)
    }

    func testDurableRunReplaySnapshotDecodes() throws {
        let data = Data("""
        {
          "run": {
            "run_id": "run-123",
            "status": "running",
            "event_sequence": 7,
            "partial_answer": "部分回答",
            "final_answer": "",
            "queue_position": 0,
            "attempt": 1,
            "error_code": ""
          },
          "events": [],
          "dropped_event_count": 0
        }
        """.utf8)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let replay = try decoder.decode(DurableChatReplayDTO.self, from: data)
        XCTAssertEqual(replay.run.runId, "run-123")
        XCTAssertEqual(replay.run.eventSequence, 7)
        XCTAssertEqual(replay.droppedEventCount, 0)
    }

    @MainActor
    func testDurableRunReplayDecodesKnowledgeActionEvent() throws {
        let data = Data(#"""
        {
          "run":{"run_id":"run-save","status":"running","event_sequence":4,"queue_position":0,"attempt":1,"error_code":""},
          "events":[{"type":"knowledge_action_draft","action_id":"action-save","summary":"保存复利笔记","steps":[{"kind":"create_note","title":"复利","markdown":"# 复利"}],"action_digest":"digest","knowledge_action_capability":"capability","expires_at":999}],
          "dropped_event_count":0
        }
        """#.utf8)

        let replay = try APIClient.decodeDurableChatReplay(data)
        guard case .knowledgeActionDraft(let action) = try XCTUnwrap(replay.events.first) else {
            return XCTFail("expected knowledge action draft")
        }
        XCTAssertEqual(action.id, "action-save")
        XCTAssertEqual(action.transientCapability, "capability")
    }

    @MainActor
    func testCompletedRecoveryPreservesOriginalMessageAndAnswerPageMetadata() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        )
        let manager = SessionManager(store: store)
        let sessionId = manager.createSession()
        manager.setMessages([
            ChatMessage(
                id: "original-output", sessionId: sessionId, role: .interrupted,
                content: "已收到的部分", runId: "run-original", lastEventSequence: 90
            )
        ], for: sessionId)
        let blocks = [
            AnswerBlockDTO(blockIndex: 0, kind: "markdown", content: "第一块"),
            AnswerBlockDTO(blockIndex: 1, kind: "markdown", content: "第二块")
        ]
        let page = AnswerBlockPageDTO(
            messageId: "server-message", revision: 7, status: "completed",
            blocks: blocks, bytes: 18, loadedBlockCount: 2,
            availableBlockCount: 12, hasMore: true, nextCursor: "signed-next"
        )

        manager.applyCompletedStatus(
            sessionId: sessionId,
            requestId: "original-output",
            answer: "不应覆盖分页投影",
            answerProjection: page
        )

        let recovered = try XCTUnwrap(manager.messages(for: sessionId).first)
        XCTAssertEqual(recovered.id, "original-output")
        XCTAssertEqual(recovered.runId, "run-original")
        XCTAssertEqual(recovered.lastEventSequence, 90)
        XCTAssertEqual(recovered.role, .assistant)
        XCTAssertEqual(recovered.content, "第一块第二块")
        XCTAssertEqual(recovered.answerBlocks, blocks)
        XCTAssertEqual(recovered.answerRevision, 7)
        XCTAssertEqual(recovered.answerNextCursor, "signed-next")
        XCTAssertTrue(recovered.answerHasMore)
        XCTAssertEqual(recovered.answerAvailableBlockCount, 12)
    }

    func testKnownRunAlwaysUsesDurableRecoveryIdentity() {
        let message = ChatMessage(
            sessionId: "same-session", role: .interrupted, content: "部分回答",
            runId: "existing-run", lastEventSequence: 90
        )
        XCTAssertEqual(TenantSessionCoordinator.durableRunId(for: message), "existing-run")
        XCTAssertNil(TenantSessionCoordinator.durableRunId(for: ChatMessage(
            role: .interrupted, content: "", runId: "  "
        )))
        XCTAssertNil(TenantSessionCoordinator.durableRunId(for: ChatMessage(
            role: .interrupted, content: "", runId: "  existing-run  "
        )))
    }

    @MainActor
    func testInterruptionKeepsExistingPartialContentAndRunCursor() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let sessionId = manager.createSession()
        manager.setMessages([
            ChatMessage(
                id: "partial", sessionId: sessionId, role: .assistant,
                content: "# 已收到\n\n真实正文", isStreaming: true,
                blocks: [.reasoning([ReasoningStep(
                    type: .toolCall, title: "检索", detail: "已收到结果", status: "done"
                )])],
                pending: true, runId: "run-partial", lastEventSequence: 42,
                answerRevision: 3, answerNextCursor: "partial-cursor",
                answerHasMore: true, answerAvailableBlockCount: 9,
                answerBlocks: [AnswerBlockDTO(
                    blockIndex: 0, kind: "markdown", content: "# 已收到\n\n真实正文"
                )]
            )
        ], for: sessionId)

        manager.markInterrupted(sessionId: sessionId)

        let interrupted = try XCTUnwrap(manager.messages(for: sessionId).first)
        XCTAssertEqual(interrupted.role, .interrupted)
        XCTAssertEqual(interrupted.content, "# 已收到\n\n真实正文")
        XCTAssertEqual(interrupted.runId, "run-partial")
        XCTAssertEqual(interrupted.lastEventSequence, 42)
        XCTAssertEqual(interrupted.answerRevision, 3)
        XCTAssertEqual(interrupted.answerNextCursor, "partial-cursor")
        XCTAssertEqual(interrupted.answerBlocks.count, 1)
        XCTAssertEqual(interrupted.blocks.count, 1)
        XCTAssertFalse(interrupted.pending)
        XCTAssertTrue(TenantSessionCoordinator.shouldPresentAutomaticRecovery(
            interrupted,
            activeInFlightMessageID: nil,
            reconcilingMessageIDs: [],
            backgroundProcessingSessionIDs: []
        ))
    }

    func testRecoveryBackoffAndAnswerPaginationAreBounded() {
        XCTAssertEqual(TenantSessionCoordinator.durableRecoveryDelayNanoseconds(failure: 1), 2_000_000_000)
        XCTAssertEqual(TenantSessionCoordinator.durableRecoveryDelayNanoseconds(failure: 4), 16_000_000_000)
        XCTAssertEqual(TenantSessionCoordinator.durableRecoveryDelayNanoseconds(failure: 99), 16_000_000_000)
        XCTAssertEqual(TenantSessionCoordinator.maximumAnswerPageRequests(
            availableBlockCount: 52, loadedBlockCount: 10, maxBlocks: 20
        ), 42)
        XCTAssertEqual(TenantSessionCoordinator.maximumAnswerPageRequests(
            availableBlockCount: 10, loadedBlockCount: 10, maxBlocks: 20
        ), 1)
    }

    @MainActor
    func testByteLimitedAnswerPagesCanExceedBlockLimitCeiling() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let sessionId = manager.createSession()
        let outputId = "byte-limited-output"
        manager.setMessages([
            ChatMessage(id: "user", sessionId: sessionId, role: .user, content: "导出长表格"),
            ChatMessage(
                id: outputId, sessionId: sessionId, role: .assistant, content: "0",
                runId: "run-byte-limited", answerRevision: 7, answerNextCursor: "c1",
                answerHasMore: true, answerAvailableBlockCount: 6,
                answerBlocks: [AnswerBlockDTO(blockIndex: 0, kind: "code", content: "0")]
            )
        ], for: sessionId)
        var requests = 0
        let coordinator = TenantSessionCoordinator(
            sessionManager: manager,
            fetchAnswerBlocks: { runId, cursor, maxBlocks in
                XCTAssertEqual(runId, "run-byte-limited")
                XCTAssertEqual(maxBlocks, 20)
                let index = requests + 1
                XCTAssertEqual(cursor, "c\(index)")
                requests += 1
                return AnswerBlockPageDTO(
                    messageId: outputId, revision: 7, status: "completed",
                    blocks: [AnswerBlockDTO(blockIndex: index, kind: "code", content: "\(index)")],
                    bytes: 1, loadedBlockCount: index + 1, availableBlockCount: 6,
                    hasMore: index < 5, nextCursor: index < 5 ? "c\(index + 1)" : nil
                )
            }
        )

        let fullAnswer = try await coordinator.fetchFullAnswer(messageId: outputId)
        XCTAssertEqual(fullAnswer, "012345")
        XCTAssertEqual(requests, 5)
        XCTAssertEqual(coordinator.messages.last?.content, "012345")
        XCTAssertEqual(coordinator.messages.last?.answerBlocks.map(\.blockIndex), [0, 1, 2, 3, 4, 5])
        XCTAssertFalse(coordinator.messages.last?.answerHasMore ?? true)
    }

    @MainActor
    func testFullAnswerErrorRetainsPagesAndNextActionResumesFromSavedCursor() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let sessionId = manager.createSession()
        let outputId = "resumable-full-answer"
        manager.setMessages([
            ChatMessage(
                id: outputId, sessionId: sessionId, role: .assistant, content: "0",
                runId: "run-resumable", answerRevision: 9, answerNextCursor: "c1",
                answerHasMore: true, answerAvailableBlockCount: 3,
                answerBlocks: [.init(blockIndex: 0, kind: "markdown", content: "0")]
            )
        ], for: sessionId)
        var request = 0
        let coordinator = TenantSessionCoordinator(
            sessionManager: manager,
            fetchAnswerBlocks: { _, cursor, _ in
                defer { request += 1 }
                if request == 0 {
                    XCTAssertEqual(cursor, "c1")
                    return AnswerBlockPageDTO(
                        messageId: outputId, revision: 9, status: "completed",
                        blocks: [.init(blockIndex: 1, kind: "markdown", content: "1")],
                        bytes: 1, loadedBlockCount: 2, availableBlockCount: 3,
                        hasMore: true, nextCursor: "c2"
                    )
                }
                if request == 1 {
                    XCTAssertEqual(cursor, "c2")
                    throw APIError.network("offline")
                }
                XCTAssertEqual(cursor, "c2")
                return AnswerBlockPageDTO(
                    messageId: outputId, revision: 9, status: "completed",
                    blocks: [.init(blockIndex: 2, kind: "markdown", content: "2")],
                    bytes: 1, loadedBlockCount: 3, availableBlockCount: 3,
                    hasMore: false, nextCursor: nil
                )
            }
        )

        do {
            _ = try await coordinator.fetchFullAnswer(messageId: outputId)
            XCTFail("the interrupted request must not be reported as complete")
        } catch APIError.network(_) {
        }
        XCTAssertEqual(coordinator.messages[0].content, "01")
        XCTAssertEqual(coordinator.messages[0].answerNextCursor, "c2")
        XCTAssertEqual(coordinator.messages[0].answerBlocks.map(\.blockIndex), [0, 1])
        await manager.flushPendingPersistence()
        XCTAssertEqual(manager.storedMessage(id: outputId, sessionId: sessionId)?.content, "01")

        let resumedAnswer = try await coordinator.fetchFullAnswer(messageId: outputId)
        XCTAssertEqual(resumedAnswer, "012")
        XCTAssertEqual(coordinator.messages[0].answerBlocks.map(\.blockIndex), [0, 1, 2])
        XCTAssertFalse(coordinator.messages[0].answerHasMore)
    }

    @MainActor
    func testFullAnswerRefreshesStaleStreamingCursorAfterCompletion() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let sessionId = manager.createSession()
        let outputId = "stale-cursor-output"
        manager.setMessages([
            ChatMessage(
                id: outputId, sessionId: sessionId, role: .assistant, content: "旧页",
                runId: "run-stale", answerRevision: 1, answerNextCursor: "stale",
                answerHasMore: true, answerAvailableBlockCount: 2,
                answerBlocks: [.init(blockIndex: 0, kind: "markdown", content: "旧页")]
            )
        ], for: sessionId)
        var cursors: [String?] = []
        let coordinator = TenantSessionCoordinator(
            sessionManager: manager,
            fetchAnswerBlocks: { _, cursor, _ in
                cursors.append(cursor)
                if cursor == "stale" { throw APIError.server(409, "stale_block_cursor") }
                if cursor == nil {
                    return AnswerBlockPageDTO(
                        messageId: outputId, revision: 2, status: "completed",
                        blocks: [.init(blockIndex: 0, kind: "markdown", content: "新页")],
                        bytes: 6, loadedBlockCount: 1, availableBlockCount: 2,
                        hasMore: true, nextCursor: "fresh"
                    )
                }
                return AnswerBlockPageDTO(
                    messageId: outputId, revision: 2, status: "completed",
                    blocks: [.init(blockIndex: 1, kind: "markdown", content: "全文")],
                    bytes: 6, loadedBlockCount: 2, availableBlockCount: 2,
                    hasMore: false, nextCursor: nil
                )
            }
        )

        let answer = try await coordinator.fetchFullAnswer(messageId: outputId)
        XCTAssertEqual(cursors, ["stale", nil, "fresh"])
        XCTAssertEqual(answer, "新页全文")
        XCTAssertEqual(coordinator.messages[0].answerRevision, 2)
        XCTAssertFalse(coordinator.messages[0].answerHasMore)
    }

    @MainActor
    func testFullAnswerCancellationRetainsLastCommittedPage() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let sessionId = manager.createSession()
        let outputId = "cancelled-full-answer"
        manager.setMessages([
            ChatMessage(
                id: outputId, sessionId: sessionId, role: .assistant, content: "0",
                runId: "run-cancel", answerRevision: 2, answerNextCursor: "c1",
                answerHasMore: true, answerAvailableBlockCount: 3,
                answerBlocks: [.init(blockIndex: 0, kind: "markdown", content: "0")]
            )
        ], for: sessionId)
        let secondRequestStarted = expectation(description: "second page request started")
        var request = 0
        let coordinator = TenantSessionCoordinator(
            sessionManager: manager,
            fetchAnswerBlocks: { _, _, _ in
                defer { request += 1 }
                if request == 0 {
                    return AnswerBlockPageDTO(
                        messageId: outputId, revision: 2, status: "completed",
                        blocks: [.init(blockIndex: 1, kind: "markdown", content: "1")],
                        bytes: 1, loadedBlockCount: 2, availableBlockCount: 3,
                        hasMore: true, nextCursor: "c2"
                    )
                }
                secondRequestStarted.fulfill()
                try await Task.sleep(nanoseconds: 10_000_000_000)
                throw APIError.network("unreachable")
            }
        )
        let task = Task { try await coordinator.fetchFullAnswer(messageId: outputId) }
        await fulfillment(of: [secondRequestStarted], timeout: 1)
        task.cancel()
        do {
            _ = try await task.value
            XCTFail("cancelled load must not report completion")
        } catch is CancellationError {
        }

        XCTAssertEqual(coordinator.messages[0].content, "01")
        XCTAssertEqual(coordinator.messages[0].answerNextCursor, "c2")
        XCTAssertTrue(coordinator.messages[0].answerHasMore)

    }

    @MainActor
    func testFullAnswerRejectsNoProgressAndNonAdvancingCursor() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let sessionId = manager.createSession()
        let outputId = "invalid-pagination-output"
        manager.setMessages([
            ChatMessage(
                id: outputId, sessionId: sessionId, role: .assistant, content: "partial",
                runId: "run-invalid-page", answerRevision: 1, answerNextCursor: "same",
                answerHasMore: true, answerAvailableBlockCount: 3,
                answerBlocks: [AnswerBlockDTO(blockIndex: 0, kind: "markdown", content: "partial")]
            )
        ], for: sessionId)

        for blocks in [[], [AnswerBlockDTO(blockIndex: 1, kind: "markdown", content: "more")]] {
            let coordinator = TenantSessionCoordinator(
                sessionManager: manager,
                fetchAnswerBlocks: { _, _, _ in
                    AnswerBlockPageDTO(
                        messageId: outputId, revision: 1, status: "completed",
                        blocks: blocks, bytes: blocks.isEmpty ? 0 : 4,
                        loadedBlockCount: blocks.isEmpty ? 1 : 2, availableBlockCount: 3,
                        hasMore: true, nextCursor: "same"
                    )
                }
            )
            do {
                _ = try await coordinator.fetchFullAnswer(messageId: outputId)
                XCTFail("pagination must fail instead of returning truncated content")
            } catch APIError.server(409, _) {
            } catch {
                XCTFail("unexpected error: \(error)")
            }
        }

        manager.setMessages([
            ChatMessage(
                id: outputId, sessionId: sessionId, role: .assistant, content: "partial",
                runId: "run-invalid-page", answerRevision: 1, answerNextCursor: nil,
                answerHasMore: true, answerAvailableBlockCount: 3,
                answerBlocks: [AnswerBlockDTO(blockIndex: 0, kind: "markdown", content: "partial")]
            )
        ], for: sessionId)
        let missingCursor = TenantSessionCoordinator(sessionManager: manager)
        do {
            _ = try await missingCursor.fetchFullAnswer(messageId: outputId)
            XCTFail("missing cursor must not report partial content as complete")
        } catch APIError.server(409, _) {
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    func testRaggedMarkdownTablePreservesCellsAndUsesSharedBoundedWidths() throws {
        let markdown = """
        | 名称 | URL | Note |
        | --- | --- | --- |
        | 中文项目 | https://example.com/a/very/long/path/that/must/wrap | mixed English 中文 |
        | only-one |
        | trailing-empty |  |
        | escaped | https://example.com/a\\|b | preserved |
        """
        let blocks = MarkdownBlockParser.shared.parse(markdown)
        guard case .table(let table) = try XCTUnwrap(blocks.first) else {
            return XCTFail("expected a table")
        }

        XCTAssertEqual(table.headers, ["名称", "URL", "Note"])
        XCTAssertEqual(table.rows[1], ["only-one"])
        XCTAssertEqual(table.rows[2], ["trailing-empty", ""])
        XCTAssertEqual(table.rows[3], ["escaped", "https://example.com/a\\|b", "preserved"])
        let widths = TableLayout.columnWidths(headers: table.headers, rows: table.rows)
        XCTAssertEqual(widths.count, 3)
        XCTAssertTrue(widths.allSatisfy { (96...240).contains($0) })
        XCTAssertEqual(widths, TableLayout.columnWidths(headers: table.headers, rows: table.rows))

        let segments = LongAnswerSheet.coalescedBlocks(content: "", serverBlocks: [
            .init(blockIndex: 4, kind: "table_segment", content: "| A | B |\n| --- | --- |\n"),
            .init(blockIndex: 5, kind: "table_segment", content: "| 1 | two |\n"),
            .init(blockIndex: 6, kind: "markdown", content: "after")
        ])
        XCTAssertEqual(segments.map(\.blockIndex), [4, 6])
        XCTAssertEqual(segments[0].content, "| A | B |\n| --- | --- |\n| 1 | two |\n")
    }

    @MainActor
    func testTableRenderingHasOneWholeTableHorizontalScrollForEmptyAndLargeInputs() async {
        let inputs = [
            TableBlock(title: "空表", headers: [], rows: []),
            TableBlock(
                title: "大表",
                headers: ["中文", "English", "URL"],
                rows: (0..<300).map {
                    ["第\($0)行", "value \($0)", "https://example.com/very/long/path/\($0)"]
                }
            )
        ]
        for table in inputs {
            let host = UIHostingController(rootView: TableCard(block: table).frame(width: 320))
            let window = UIWindow(frame: CGRect(x: 0, y: 0, width: 320, height: 700))
            window.rootViewController = host
            window.isHidden = false
            defer { window.isHidden = true }
            for _ in 0..<3 { await Task.yield(); host.view.layoutIfNeeded() }
            XCTAssertEqual(findScrollViews(in: host.view).count, 1)
            let image = UIGraphicsImageRenderer(size: window.bounds.size).image { context in
                window.layer.render(in: context.cgContext)
            }
            let attachment = XCTAttachment(image: image)
            attachment.name = "Synthetic-table-layout-\(table.title)"
            attachment.lifetime = .keepAlways
            add(attachment)
        }

        let structured = StableAnswerBlockView(
            messageId: "structured-table",
            block: .init(
                blockIndex: 0, kind: "table_markdown",
                content: "| A | B |\n| --- | --- |\n| 1 | https://example.com/long/path |"
            )
        )
        let host = UIHostingController(rootView: structured.frame(width: 320))
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: 320, height: 700))
        window.rootViewController = host
        window.isHidden = false
        defer { window.isHidden = true }
        for _ in 0..<3 { await Task.yield(); host.view.layoutIfNeeded() }
        XCTAssertEqual(findScrollViews(in: host.view).count, 1)
    }

    @MainActor
    func testLongAnswerSheetAppendKeepsScrollViewIdentityAndReadingOffset() async {
        let initial = (0..<80).map {
            AnswerBlockDTO(blockIndex: $0, kind: "markdown", content: "第\($0)段 stable content\n\n")
        }
        let makeSheet: ([AnswerBlockDTO]) -> LongAnswerSheet = { blocks in
            LongAnswerSheet(
                messageId: "stable-reader", content: blocks.map(\.content).joined(),
                serverBlocks: blocks, availableBlockCount: 81,
                hasMore: blocks.count < 81, isRunning: false, fetchFull: nil
            )
        }
        let host = UIHostingController(rootView: makeSheet(initial))
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: 393, height: 720))
        window.rootViewController = host
        window.isHidden = false
        defer { window.isHidden = true }
        host.view.layoutIfNeeded()
        for _ in 0..<3 { await Task.yield(); host.view.layoutIfNeeded() }

        let before = try? XCTUnwrap(findScrollViews(in: host.view).first(where: {
            $0.contentSize.height > $0.bounds.height
        }))
        XCTAssertNotNil(before)
        before?.setContentOffset(CGPoint(x: 0, y: 180), animated: false)
        for _ in 0..<2 { await Task.yield(); host.view.layoutIfNeeded() }
        let offset = before?.contentOffset.y ?? 0

        host.rootView = makeSheet(initial + [
            .init(blockIndex: 80, kind: "markdown", content: "新增末段\n\n")
        ])
        for _ in 0..<3 { await Task.yield(); host.view.layoutIfNeeded() }
        let after = findScrollViews(in: host.view).first(where: {
            $0.contentSize.height > $0.bounds.height
        })
        XCTAssertTrue(before === after)
        XCTAssertEqual(after?.contentOffset.y ?? -1, offset, accuracy: 2)

    }

    @MainActor
    func testAutomaticDurableRecoverySurvivesOutageAndCompletesSameRunWithoutRegeneration() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let sessionId = manager.createSession()
        let outputId = "same-output"
        manager.setMessages([
            ChatMessage(id: "user", sessionId: sessionId, role: .user, content: "继续原任务"),
            ChatMessage(
                id: outputId, sessionId: sessionId, role: .interrupted,
                content: "部分", runId: "run-original", lastEventSequence: 10
            )
        ], for: sessionId)
        var gets = 0
        let completed = expectation(description: "same durable run completed")
        let coordinator = TenantSessionCoordinator(
            sessionManager: manager,
            hasAuthenticatedSession: { true },
            fetchDurableChatRun: { runId, after in
                XCTAssertEqual(runId, "run-original")
                XCTAssertEqual(after, 10)
                gets += 1
                if gets == 1 { throw APIError.network("offline") }
                completed.fulfill()
                return DurableChatReplayDTO(
                    run: DurableChatRunDTO(
                        runId: runId, status: "completed", eventSequence: 11,
                        partialAnswer: nil, finalAnswer: "完整回答", queuePosition: 0,
                        attempt: 1, errorCode: "", answerProjection: nil
                    ),
                    droppedEventCount: 0
                )
            },
            recoverySleep: { _ in }
        )

        coordinator.reconcileActiveRun()
        await fulfillment(of: [completed], timeout: 1)
        for _ in 0..<20 where coordinator.messages[1].pending { await Task.yield() }

        XCTAssertEqual(gets, 2)
        XCTAssertEqual(coordinator.messages.map(\.id), ["user", outputId])
        XCTAssertEqual(coordinator.messages[1].runId, "run-original")
        XCTAssertEqual(coordinator.messages[1].content, "完整回答")
        XCTAssertEqual(coordinator.messages[1].role, .assistant)
        XCTAssertFalse(coordinator.messages[1].pending)
        XCTAssertNil(coordinator.inflight)
    }

    @MainActor
    func testLateDurableCallbackCannotCrossAccountBoundary() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        manager.activateAccount(tenantKey: "tenant-a-\(UUID())", userId: "user-a")
        let sessionId = manager.createSession()
        let outputId = "account-a-output"
        manager.setMessages([
            ChatMessage(id: "user", sessionId: sessionId, role: .user, content: "原账号问题"),
            ChatMessage(
                id: outputId, sessionId: sessionId, role: .interrupted,
                content: "账号 A 部分内容", runId: "run-account-a"
            )
        ], for: sessionId)
        var continuation: CheckedContinuation<DurableChatReplayDTO, Error>?
        let requestStarted = expectation(description: "durable GET started")
        let coordinator = TenantSessionCoordinator(
            sessionManager: manager,
            hasAuthenticatedSession: { true },
            fetchDurableChatRun: { _, _ in
                requestStarted.fulfill()
                return try await withCheckedThrowingContinuation { continuation = $0 }
            }
        )

        coordinator.reconcileActiveRun()
        await fulfillment(of: [requestStarted], timeout: 1)
        manager.activateAccount(tenantKey: "tenant-b-\(UUID())", userId: "user-b")
        continuation?.resume(returning: DurableChatReplayDTO(
            run: DurableChatRunDTO(
                runId: "run-account-a", status: "completed", eventSequence: 1,
                partialAnswer: nil, finalAnswer: "不应写入", queuePosition: 0,
                attempt: 1, errorCode: "", answerProjection: nil
            ),
            droppedEventCount: 0
        ))
        for _ in 0..<20 { await Task.yield() }

        XCTAssertEqual(coordinator.messages[1].content, "账号 A 部分内容")
        XCTAssertNotEqual(coordinator.messages[1].content, "不应写入")
    }

    @MainActor
    func testPersistedInterruptedRunRestoresVisibleToolTimelineAndAutoCompletes() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let databaseURL = root.appendingPathComponent("history.sqlite")
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: databaseURL,
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let sessionId = manager.createSession()
        let outputId = "persisted-recovery"
        let steps = [ReasoningStep(
            id: "tool-step", type: .toolCall, title: "检索资料",
            detail: "已读取 8 个来源", status: "running"
        )]
        manager.setMessages([
            ChatMessage(id: "user", sessionId: sessionId, role: .user, content: "继续调研"),
            ChatMessage(
                id: outputId, sessionId: sessionId, role: .interrupted,
                content: "已收到正文", blocks: [.reasoning(steps)],
                runId: "durable-persisted", lastEventSequence: 12,
                answerRevision: 4, answerNextCursor: "cursor-4",
                answerHasMore: true, answerAvailableBlockCount: 3,
                answerBlocks: [AnswerBlockDTO(
                    blockIndex: 0, kind: "markdown", content: "已收到正文"
                )]
            )
        ], for: sessionId)
        await manager.flushPendingPersistence()

        let restoredManager = SessionManager(store: try ChatHistoryStore(
            databaseURL: databaseURL,
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        restoredManager.switchTo(sessionId)
        let completed = expectation(description: "persisted run completed")
        let coordinator = TenantSessionCoordinator(
            sessionManager: restoredManager,
            hasAuthenticatedSession: { true },
            fetchDurableChatRun: { runId, after in
                XCTAssertEqual(runId, "durable-persisted")
                XCTAssertEqual(after, 12)
                completed.fulfill()
                return DurableChatReplayDTO(
                    run: DurableChatRunDTO(
                        runId: runId, status: "completed", eventSequence: 13,
                        partialAnswer: nil, finalAnswer: "完整正文", queuePosition: 0,
                        attempt: 1, errorCode: "", answerProjection: nil
                    ),
                    droppedEventCount: 0
                )
            }
        )

        let restored = try XCTUnwrap(coordinator.messages.last)
        XCTAssertEqual(restored.id, outputId)
        XCTAssertEqual(restored.content, "已收到正文")
        XCTAssertEqual(restored.answerRevision, 4)
        XCTAssertEqual(restored.answerNextCursor, "cursor-4")
        XCTAssertEqual(restored.blocks, [.reasoning(steps)])
        XCTAssertTrue(TenantSessionCoordinator.shouldPresentAutomaticRecovery(
            restored,
            activeInFlightMessageID: nil,
            reconcilingMessageIDs: [],
            backgroundProcessingSessionIDs: []
        ))

        coordinator.reconcileActiveRun()
        await fulfillment(of: [completed], timeout: 1)
        for _ in 0..<20 where coordinator.messages.last?.pending == true { await Task.yield() }

        XCTAssertEqual(coordinator.messages.last?.id, outputId)
        XCTAssertEqual(coordinator.messages.last?.content, "完整正文")
        guard case .reasoning(let completedSteps) = try XCTUnwrap(coordinator.messages.last?.blocks.first) else {
            XCTFail("completed recovery must preserve the visible tool timeline")
            return
        }
        XCTAssertEqual(completedSteps.map(\.id), steps.map(\.id))
        XCTAssertEqual(completedSteps.map(\.title), steps.map(\.title))
        XCTAssertEqual(completedSteps.map(\.detail), steps.map(\.detail))
        XCTAssertEqual(completedSteps.map(\.status), ["done"])
        XCTAssertEqual(coordinator.messages.last?.lastEventSequence, 13)
    }

    @MainActor
    func testSessionAwayReturnReplaysRunningRunThenCompletesWithoutDuplicateOwner() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let runSession = manager.createSession()
        let otherSession = manager.createSession()
        manager.switchTo(runSession)
        let outputId = "session-return-output"
        let step = ReasoningStep(
            id: "existing-tool", type: .toolCall, title: "搜索", detail: "进行中", status: "running"
        )
        manager.setMessages([
            ChatMessage(id: "user", sessionId: runSession, role: .user, content: "长任务"),
            ChatMessage(
                id: outputId, sessionId: runSession, role: .assistant,
                content: "部分正文", isStreaming: true, blocks: [.reasoning([step])],
                pending: true, runId: "run-session-return", lastEventSequence: 20
            )
        ], for: runSession)
        var gets = 0
        let completed = expectation(description: "same run completed after session return")
        let coordinator = TenantSessionCoordinator(
            sessionManager: manager,
            hasAuthenticatedSession: { true },
            fetchDurableChatRun: { runId, after in
                gets += 1
                XCTAssertEqual(runId, "run-session-return")
                XCTAssertEqual(after, gets == 1 ? 20 : 21)
                let done = gets == 2
                if done { completed.fulfill() }
                return DurableChatReplayDTO(
                    run: DurableChatRunDTO(
                        runId: runId, status: done ? "completed" : "running",
                        eventSequence: done ? 22 : 21,
                        partialAnswer: done ? nil : "更多正文",
                        finalAnswer: done ? "最终正文" : nil,
                        queuePosition: 0, attempt: 1, errorCode: "", answerProjection: nil
                    ),
                    droppedEventCount: 0
                )
            },
            recoverySleep: { _ in }
        )

        coordinator.switchSession(to: otherSession)
        coordinator.switchSession(to: runSession)
        coordinator.reconcileActiveRun()
        coordinator.reconcileActiveRun()
        await fulfillment(of: [completed], timeout: 1)
        for _ in 0..<20 where coordinator.messages.last?.pending == true { await Task.yield() }

        XCTAssertEqual(gets, 2)
        XCTAssertEqual(coordinator.messages.last?.id, outputId)
        XCTAssertEqual(coordinator.messages.last?.content, "最终正文")
        guard case .reasoning(let completedSteps) = try XCTUnwrap(coordinator.messages.last?.blocks.first) else {
            XCTFail("completed recovery must preserve the visible tool timeline")
            return
        }
        XCTAssertEqual(completedSteps.map(\.id), [step.id])
        XCTAssertEqual(completedSteps.map(\.title), [step.title])
        XCTAssertEqual(completedSteps.map(\.detail), [step.detail])
        XCTAssertEqual(completedSteps.map(\.status), ["done"])
        XCTAssertEqual(coordinator.messages.last?.lastEventSequence, 22)
    }

    @MainActor
    func testCompletedWhileAwayUpdatesOriginalStoredMessage() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let runSession = manager.createSession()
        let otherSession = manager.createSession()
        manager.switchTo(runSession)
        let outputId = "completed-while-away"
        manager.setMessages([
            ChatMessage(id: "user", sessionId: runSession, role: .user, content: "后台任务"),
            ChatMessage(
                id: outputId, sessionId: runSession, role: .assistant,
                content: "已有正文", isStreaming: true,
                blocks: [.reasoning([ReasoningStep(
                    id: "old-step", type: .toolCall, title: "旧进度", status: "running"
                )])],
                pending: true, runId: "run-away", lastEventSequence: 5
            )
        ], for: runSession)
        await manager.flushPendingPersistence()

        let stored = expectation(description: "completed result stored while another session is active")
        let coordinator = TenantSessionCoordinator(
            sessionManager: manager,
            hasAuthenticatedSession: { true },
            fetchChatStatus: { sessionId, consume, _ in
                XCTAssertEqual(sessionId, runSession)
                XCTAssertTrue(consume)
                stored.fulfill()
                return ChatStatusDTO(
                    status: "completed", phase: nil, answer: "离开期间完成的正文",
                    reasoning: [ChatReasoningStepDTO(
                        type: "tool_call", title: "检索完成", detail: "8 个来源", status: "done"
                    )],
                    latestStep: nil, clarify: nil, consumed: true, answerProjection: nil
                )
            }
        )
        coordinator.inflight = InFlightRequest(
            id: outputId, sessionId: runSession, text: "后台任务"
        )
        coordinator.isGenerating = true

        coordinator.switchSession(to: otherSession)
        await fulfillment(of: [stored], timeout: 1)
        for _ in 0..<100 {
            if coordinator.backgroundMonitorCountForTesting == 0 { break }
            await Task.yield()
        }
        XCTAssertEqual(coordinator.backgroundMonitorCountForTesting, 0)
        await manager.flushPendingPersistence()

        XCTAssertEqual(manager.activeSessionID(), otherSession)
        let completed = try XCTUnwrap(manager.storedMessage(id: outputId, sessionId: runSession))
        XCTAssertEqual(completed.id, outputId)
        XCTAssertEqual(completed.runId, "run-away")
        XCTAssertEqual(completed.content, "离开期间完成的正文")
        XCTAssertFalse(completed.pending)
        guard case .reasoning(let steps) = try XCTUnwrap(completed.blocks.first) else {
            XCTFail("completed status must preserve the visible tool timeline")
            return
        }
        XCTAssertEqual(steps.map(\.title), ["检索完成"])
    }

    @MainActor
    func testRepeatedForegroundReconcileStartsOneDurableGET() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let sessionId = manager.createSession()
        let outputId = "foreground-once"
        manager.setMessages([
            ChatMessage(id: "user", sessionId: sessionId, role: .user, content: "任务"),
            ChatMessage(
                id: outputId, sessionId: sessionId, role: .interrupted,
                content: "部分", runId: "run-once", lastEventSequence: 3
            )
        ], for: sessionId)
        var gets = 0
        var legacyStatusGETs = 0
        var continuation: CheckedContinuation<DurableChatReplayDTO, Error>?
        let started = expectation(description: "one durable GET")
        let coordinator = TenantSessionCoordinator(
            sessionManager: manager,
            hasAuthenticatedSession: { true },
            fetchDurableChatRun: { _, _ in
                gets += 1
                started.fulfill()
                return try await withCheckedThrowingContinuation { continuation = $0 }
            },
            fetchChatStatus: { _, _, _ in
                legacyStatusGETs += 1
                throw APIError.network("offline")
            }
        )

        coordinator.inflight = InFlightRequest(
            id: outputId, sessionId: sessionId, text: "任务"
        )
        coordinator.isGenerating = true
        coordinator.prepareForBackground()
        XCTAssertFalse(coordinator.isGenerating)
        XCTAssertNil(coordinator.inflight)
        coordinator.reconcileActiveRun()
        let messageCount = coordinator.messages.count
        coordinator.sendMessage(text: "不应创建第二个任务")
        XCTAssertEqual(coordinator.messages.count, messageCount)
        XCTAssertEqual(coordinator.toastMessage, "正在续接原任务，请稍候")
        coordinator.reconcileActiveRun()
        await fulfillment(of: [started], timeout: 1)
        XCTAssertEqual(gets, 1)
        XCTAssertLessThanOrEqual(legacyStatusGETs, 1)
        XCTAssertFalse(coordinator.confirmedRunningMessageIDs.contains(outputId))
        let completed = expectation(description: "durable replay published completed content")
        let completedObservation = coordinator.$messages
            .first(where: { messages in
                messages.last?.id == outputId
                    && messages.last?.content == "完成"
                    && messages.last?.pending == false
            })
            .sink { _ in completed.fulfill() }
        continuation?.resume(returning: DurableChatReplayDTO(
            run: DurableChatRunDTO(
                runId: "run-once", status: "completed", eventSequence: 4,
                partialAnswer: nil, finalAnswer: "完成", queuePosition: 0,
                attempt: 1, errorCode: "", answerProjection: nil
            ),
            droppedEventCount: 0
        ))
        await fulfillment(of: [completed], timeout: 1)
        withExtendedLifetime(completedObservation) {}
        XCTAssertEqual(coordinator.messages.last?.content, "完成")
        XCTAssertFalse(coordinator.confirmedRunningMessageIDs.contains(outputId))
    }

    @MainActor
    func testExplicitStopAndRealFailureAreNotAutomaticallyResumed() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let sessionId = manager.createSession()
        let stoppedId = "explicit-stop"
        manager.setMessages([
            ChatMessage(id: "user", sessionId: sessionId, role: .user, content: "停止前的问题"),
            ChatMessage(
                id: stoppedId, sessionId: sessionId, role: .assistant,
                content: "已收部分", isStreaming: true, pending: true,
                runId: "run-stopped"
            )
        ], for: sessionId)
        var replayGETs = 0
        var cancels = 0
        let coordinator = TenantSessionCoordinator(
            sessionManager: manager,
            hasAuthenticatedSession: { true },
            fetchDurableChatRun: { _, _ in
                replayGETs += 1
                return DurableChatReplayDTO(
                    run: DurableChatRunDTO(
                        runId: "run-stopped", status: "running", eventSequence: 1,
                        partialAnswer: nil, finalAnswer: nil, queuePosition: 0,
                        attempt: 1, errorCode: "", answerProjection: nil
                    ),
                    droppedEventCount: 0
                )
            },
            cancelRun: { _, _ in cancels += 1 }
        )
        coordinator.inflight = InFlightRequest(
            id: stoppedId, sessionId: sessionId, text: "停止前的问题"
        )
        coordinator.isGenerating = true
        coordinator.cancelInFlight()
        for _ in 0..<20 where cancels == 0 { await Task.yield() }
        coordinator.reconcileActiveRun()
        XCTAssertEqual(cancels, 1)
        XCTAssertEqual(replayGETs, 0)
        XCTAssertFalse(coordinator.messages.last?.pending ?? true)

        let failedId = "real-failure"
        coordinator.messages.append(ChatMessage(
            id: failedId, sessionId: sessionId, role: .interrupted,
            content: "失败前部分", runId: "run-failed"
        ))
        coordinator.commitSession()
        var failureGETs = 0
        let failed = expectation(description: "real failure returned")
        let failureCoordinator = TenantSessionCoordinator(
            sessionManager: manager,
            hasAuthenticatedSession: { true },
            fetchDurableChatRun: { _, _ in
                failureGETs += 1
                failed.fulfill()
                return DurableChatReplayDTO(
                    run: DurableChatRunDTO(
                        runId: "run-failed", status: "failed", eventSequence: 2,
                        partialAnswer: nil, finalAnswer: nil, queuePosition: 0,
                        attempt: 1, errorCode: "server_error", answerProjection: nil
                    ),
                    droppedEventCount: 0
                )
            }
        )
        failureCoordinator.reconcileActiveRun()
        await fulfillment(of: [failed], timeout: 1)
        for _ in 0..<20 where failureCoordinator.messages.last?.pending == true { await Task.yield() }
        failureCoordinator.reconcileActiveRun()
        XCTAssertEqual(failureGETs, 1)
        XCTAssertTrue(failureCoordinator.messages.last?.degraded == true)
        XCTAssertTrue(failureCoordinator.messages.last?.content.contains("任务执行失败") == true)
    }

    @MainActor
    func testLateDurableCallbackCannotCrossSessionBoundary() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let firstSession = manager.createSession()
        let secondSession = manager.createSession()
        manager.switchTo(firstSession)
        let outputId = "session-a-output"
        manager.setMessages([
            ChatMessage(id: "user", sessionId: firstSession, role: .user, content: "原问题"),
            ChatMessage(
                id: outputId, sessionId: firstSession, role: .interrupted,
                content: "原会话部分", runId: "run-session-a"
            )
        ], for: firstSession)
        await manager.flushPendingPersistence()
        var continuation: CheckedContinuation<DurableChatReplayDTO, Error>?
        let started = expectation(description: "session A GET started")
        let coordinator = TenantSessionCoordinator(
            sessionManager: manager,
            hasAuthenticatedSession: { true },
            fetchDurableChatRun: { _, _ in
                started.fulfill()
                return try await withCheckedThrowingContinuation { continuation = $0 }
            }
        )
        coordinator.reconcileActiveRun()
        await fulfillment(of: [started], timeout: 1)
        coordinator.switchSession(to: secondSession)
        continuation?.resume(returning: DurableChatReplayDTO(
            run: DurableChatRunDTO(
                runId: "run-session-a", status: "completed", eventSequence: 1,
                partialAnswer: nil, finalAnswer: "不应跨会话写入", queuePosition: 0,
                attempt: 1, errorCode: "", answerProjection: nil
            ),
            droppedEventCount: 0
        ))
        for _ in 0..<20 { await Task.yield() }

        XCTAssertEqual(manager.activeSessionID(), secondSession)
        XCTAssertFalse(coordinator.messages.contains { $0.content == "不应跨会话写入" })
        XCTAssertEqual(manager.storedMessage(id: outputId, sessionId: firstSession)?.content, "原会话部分")
    }
}

@MainActor
final class ClarifyAnswerPaginationRegressionTests: XCTestCase {
    private func submittedClarify(sessionId: String) -> ClarifyBlock {
        ClarifyBlock(
            requestId: "request-1", sessionId: sessionId,
            submissionState: .accepted, question: "选择路线", choices: ["省钱"],
            source: "bridge", isSubmitted: true, submittedSelection: "省钱"
        )
    }

    func testLegacyClarifyContinuationRecoversMissingRunId() {
        let sessionId = "session-1"
        var messages = [
            ChatMessage(
                id: "clarify", sessionId: sessionId, role: .assistant,
                content: "", blocks: [.clarify(submittedClarify(sessionId: sessionId))],
                runId: "durable-run", lastEventSequence: 4
            ),
            ChatMessage(
                id: "answer", sessionId: sessionId, role: .assistant,
                content: "首批正文", answerRevision: 2,
                answerNextCursor: "signed-cursor", answerHasMore: true,
                answerAvailableBlockCount: 40,
                answerBlocks: [AnswerBlockDTO(
                    blockIndex: 0, kind: "markdown", content: "首批正文"
                )]
            )
        ]

        let repaired = TenantSessionCoordinator.repairClarifyContinuationRunLinks(
            in: &messages
        )

        XCTAssertEqual(repaired, 1)
        XCTAssertEqual(messages[1].runId, "durable-run")
        XCTAssertEqual(messages[1].lastEventSequence, 4)
    }

    func testRunRepairNeverLinksUnrelatedAnswer() {
        let sessionId = "session-1"
        var messages = [
            ChatMessage(
                sessionId: sessionId, role: .assistant, content: "",
                blocks: [.clarify(submittedClarify(sessionId: sessionId))],
                runId: "durable-run"
            ),
            ChatMessage(sessionId: sessionId, role: .user, content: "新问题"),
            ChatMessage(
                sessionId: sessionId, role: .assistant, content: "独立回答",
                answerNextCursor: "cursor", answerHasMore: true
            )
        ]

        XCTAssertEqual(
            TenantSessionCoordinator.repairClarifyContinuationRunLinks(in: &messages),
            0
        )
        XCTAssertNil(messages[2].runId)
    }

    func testLegacyClarifyContinuationCanFetchRemainingAnswer() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let sessionId = manager.createSession()
        manager.setMessages([
            ChatMessage(
                id: "clarify", sessionId: sessionId, role: .assistant,
                content: "", blocks: [.clarify(submittedClarify(sessionId: sessionId))],
                runId: "durable-run"
            ),
            ChatMessage(
                id: "answer", sessionId: sessionId, role: .assistant,
                content: "第1页", answerRevision: 2,
                answerNextCursor: "page-2", answerHasMore: true,
                answerAvailableBlockCount: 2,
                answerBlocks: [AnswerBlockDTO(
                    blockIndex: 0, kind: "markdown", content: "第1页"
                )]
            )
        ], for: sessionId)
        let fetched = expectation(description: "remaining page fetched with inherited run")
        let coordinator = TenantSessionCoordinator(
            sessionManager: manager,
            hasAuthenticatedSession: { true },
            fetchAnswerBlocks: { runID, cursor, maxBlocks in
                XCTAssertEqual(runID, "durable-run")
                XCTAssertEqual(cursor, "page-2")
                XCTAssertEqual(maxBlocks, 20)
                fetched.fulfill()
                return AnswerBlockPageDTO(
                    messageId: "server-answer", revision: 2, status: "completed",
                    blocks: [AnswerBlockDTO(
                        blockIndex: 1, kind: "markdown", content: "第2页"
                    )], bytes: 7, loadedBlockCount: 2,
                    availableBlockCount: 2, hasMore: false, nextCursor: nil
                )
            }
        )

        let fullAnswer = try await coordinator.fetchFullAnswer(messageId: "answer")
        await fulfillment(of: [fetched], timeout: 1)

        XCTAssertEqual(fullAnswer, "第1页第2页")
        XCTAssertEqual(coordinator.messages[1].runId, "durable-run")
        XCTAssertFalse(coordinator.messages[1].answerHasMore)
        XCTAssertNil(coordinator.messages[1].answerNextCursor)
    }
}
