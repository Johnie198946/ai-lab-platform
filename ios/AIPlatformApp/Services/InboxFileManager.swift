//
//  InboxFileManager.swift
//  AIPlatformApp
//
//  微信「OpenIn」文件接收目录管理与长图降采样：
//  - cleanupStaleInboxFiles(): 单一 mtime 判据（mtime > 24h 删除），
//    写入中文件 mtime 新 → 天然保护；无锁机制、无孤儿锁；lastCleanup 24h 节流。
//  - downsampleImage(): 最长边 2048px 等比缩放 + JPEG 0.85 压缩。
//  - fileSizeBytes(at:): 读取 Data 前的前置文件体积预检。
//

import Foundation
import UIKit

public final class InboxFileManager {

    public static let shared = InboxFileManager()

    /// 50MB 前置预检阈值（读取 Data 前拦截）
    public static let maxFileSizeBytes: Int64 = 50 * 1024 * 1024

    /// mtime 过期判定阈值（> 24h 删除）
    private let staleThreshold: TimeInterval = 24 * 60 * 60

    /// 清理节流间隔（距上次 < 24h 跳过）
    private let cleanupThrottleInterval: TimeInterval = 24 * 60 * 60

    private var lastCleanup: Date?

    private init() {}

    // MARK: - 微信「OpenIn」接收目录

    /// 系统「OpenIn」标准通道投递的文件目录（Documents/Inbox）
    public var inboxDirectory: URL {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        return docs.appendingPathComponent("Inbox", isDirectory: true)
    }

    // MARK: - 过期文件清理（单一 mtime 判据 + 节流）

    /// 触发点：scenePhase 变 active 或进入 + 号面板；内置 24h 节流防高频遍历。
    public func cleanupStaleInboxFiles() {
        let now = Date()
        if let last = lastCleanup, now.timeIntervalSince(last) < cleanupThrottleInterval {
            return // 距上次不足 24h，节流跳过
        }
        lastCleanup = now

        let fm = FileManager.default
        let dir = inboxDirectory
        guard let entries = try? fm.contentsOfDirectory(
            at: dir,
            includingPropertiesForKeys: [.contentModificationDateKey],
            options: [.skipsHiddenFiles]
        ) else {
            return
        }

        for url in entries {
            guard let values = try? url.resourceValues(forKeys: [.contentModificationDateKey]),
                  let mtime = values.contentModificationDate else { continue }
            if now.timeIntervalSince(mtime) > staleThreshold {
                try? fm.removeItem(at: url)
            }
        }
    }

    // MARK: - 前置体积预检

    /// 读取 Data 前通过 resourceValues(.fileSizeKey) 预检文件体积
    public func fileSizeBytes(at url: URL) -> Int64? {
        guard let values = try? url.resourceValues(forKeys: [.fileSizeKey]),
              let size = values.fileSize else { return nil }
        return Int64(size)
    }

    // MARK: - 长图降采样（2048px 等比 + JPEG 0.85）

    /// 最长边 2048px 等比缩放降采样，输出 JPEG 数据（0.85 压缩）
    @discardableResult
    public func downsampleImage(
        data: Data,
        maxDimension: CGFloat = 2048,
        compressionQuality: CGFloat = 0.85
    ) -> Data? {
        guard let image = UIImage(data: data) else { return nil }

        let originalSize = image.size
        let longest = max(originalSize.width, originalSize.height)

        guard longest > maxDimension else {
            return image.jpegData(compressionQuality: compressionQuality)
        }

        let scale = maxDimension / longest
        let newSize = CGSize(
            width: max(1, originalSize.width * scale),
            height: max(1, originalSize.height * scale)
        )

        let renderer = UIGraphicsImageRenderer(size: newSize)
        let resized = renderer.image { _ in
            image.draw(in: CGRect(origin: .zero, size: newSize))
        }
        return resized.jpegData(compressionQuality: compressionQuality)
    }
}
