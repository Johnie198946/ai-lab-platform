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

    public var id: String { category }
}

/// GET /api/v1/catalog 响应
public struct CatalogResponse: Codable {
    public let catalog: [CatalogCategory]
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

/// GET /api/knowledge/search 单条结果
public struct SearchDoc: Codable, Identifiable, Hashable {
    public let path: String
    public let title: String
    public let score: Double
    public let snippet: String

    public var id: String { path }

    /// 该文档所属类目（首段路径前缀；行业知识取 knowledge/行业知识/<domain> 两段）
    public var category: String {
        let parts = path.split(separator: "/", omittingEmptySubsequences: false)
        if parts.count >= 3 && parts[0] == "knowledge" && parts[1] == "行业知识" {
            return "knowledge/行业知识/\(parts[2])"
        }
        return String(parts.first ?? "")
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

// MARK: - API 错误

public enum APIError: Error, LocalizedError {
    case invalidURL
    case unauthorized
    case server(Int, String)
    case network(String)
    case decoding(String)

    public var errorDescription: String? {
        switch self {
        case .invalidURL: return "无效的请求地址"
        case .unauthorized: return "登录态失效，请重新登录"
        case .server(let code, let msg): return "服务端错误 \(code): \(msg)"
        case .network(let msg): return "网络不可用: \(msg)"
        case .decoding(let msg): return "数据解析失败: \(msg)"
        }
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
    private let decoder: JSONDecoder

    public init(baseURL: URL = URL(string: "http://127.0.0.1:8000")!) {
        self.baseURL = baseURL
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 8
        config.timeoutIntervalForResource = 15
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        self.session = URLSession(configuration: config)
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

        do {
            let (data, response) = try await session.data(for: request)
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
                throw APIError.server(
                    http.statusCode,
                    String(data: data, encoding: .utf8) ?? ""
                )
            }
            isOfflineMode = false
            do {
                return try decoder.decode(T.self, from: data)
            } catch {
                throw APIError.decoding(error.localizedDescription)
            }
        } catch let urlError as URLError where urlError.code == .cancelled {
            throw urlError  // 请求取消，原样上抛，不误标离线
        } catch let urlError as URLError {
            isOfflineMode = true
            throw APIError.network(urlError.localizedDescription)
        }
    }

    // MARK: - 业务接口

    public func fetchCatalog() async throws -> [CatalogCategory] {
        let resp: CatalogResponse = try await request(
            CatalogResponse.self, path: "catalog"
        )
        return resp.catalog
    }

    public func fetchSubscriptions() async throws -> [String] {
        let resp: SubscriptionsResponse = try await request(
            SubscriptionsResponse.self, path: "me/subscriptions"
        )
        return resp.categories
    }

    public func subscribe(category: String) async throws -> [String] {
        struct Body: Encodable { let category: String }
        let resp: SubscriptionsResponse = try await request(
            SubscriptionsResponse.self,
            path: "me/subscriptions",
            method: "POST",
            body: Body(category: category)
        )
        return resp.categories
    }

    public func unsubscribe(category: String) async throws -> [String] {
        let resp: SubscriptionsResponse = try await request(
            SubscriptionsResponse.self,
            path: "me/subscriptions/\(encodedPath(category))",
            method: "DELETE"
        )
        return resp.categories
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
        do {
            let (data, response) = try await session.data(for: request)
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
                throw APIError.server(
                    http.statusCode, String(data: data, encoding: .utf8) ?? ""
                )
            }
            isOfflineMode = false
            return try decoder.decode(SearchResponse.self, from: data).docs
        } catch let urlError as URLError where urlError.code == .cancelled {
            throw urlError
        } catch let urlError as URLError {
            isOfflineMode = true
            throw APIError.network(urlError.localizedDescription)
        }
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
}
