//
//  TenantScopedCache.swift
//  AIPlatformApp
//
//  Three-Segment Scoped Cache for Multi-Tenant Isolation
//  Key format: "\(tenantId):\(namespace):\(key)"
//  Ensures AST, parsed markdown, and charts are completely isolated across tenants.
//

import Foundation

/// 租户作用域缓存（三段式键强制隔离）
public final class TenantScopedCache<Value: AnyObject>: @unchecked Sendable {
    private let cache = NSCache<NSString, Value>()
    private let lock = NSLock()

    public var countLimit: Int {
        get { cache.countLimit }
        set { cache.countLimit = newValue }
    }

    public var totalCostLimit: Int {
        get { cache.totalCostLimit }
        set { cache.totalCostLimit = newValue }
    }

    public init(countLimit: Int = 200, totalCostLimit: Int = 0) {
        cache.countLimit = countLimit
        cache.totalCostLimit = totalCostLimit
    }

    /// 生成三段式隔离 Key: tenantId:namespace:key
    public static func makeKey(tenantId: String, namespace: String, key: String) -> NSString {
        return "\(tenantId):\(namespace):\(key)" as NSString
    }

    /// 存储缓存
    public func set(tenantId: String, namespace: String, key: String, value: Value, cost: Int = 0) {
        let scopedKey = Self.makeKey(tenantId: tenantId, namespace: namespace, key: key)
        lock.lock()
        defer { lock.unlock() }
        if cost > 0 {
            cache.setObject(value, forKey: scopedKey, cost: cost)
        } else {
            cache.setObject(value, forKey: scopedKey)
        }
    }

    /// 获取缓存
    public func get(tenantId: String, namespace: String, key: String) -> Value? {
        let scopedKey = Self.makeKey(tenantId: tenantId, namespace: namespace, key: key)
        lock.lock()
        defer { lock.unlock() }
        return cache.object(forKey: scopedKey)
    }

    /// 删除指定缓存
    public func remove(tenantId: String, namespace: String, key: String) {
        let scopedKey = Self.makeKey(tenantId: tenantId, namespace: namespace, key: key)
        lock.lock()
        defer { lock.unlock() }
        cache.removeObject(forKey: scopedKey)
    }

    /// 清空所有缓存
    public func removeAll() {
        lock.lock()
        defer { lock.unlock() }
        cache.removeAllObjects()
    }
}
