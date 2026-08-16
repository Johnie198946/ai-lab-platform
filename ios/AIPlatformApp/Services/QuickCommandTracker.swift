//
//  QuickCommandTracker.swift
//  AIPlatformApp
//
//  本地快捷指令使用频次追踪（需求1：本地滑动窗口频次 Top3）。
//  - 仅本地计算：数据存于 UserDefaults，绝不上传，UI 标注「仅本地计算，保护隐私」。
//  - 滑动窗口：7 天内使用记录计入频次，写入时自动剪除窗口外旧记录。
//  - 冷启动兜底：无历史记录时由调用方回退到默认预设指令。
//

import Foundation

public final class QuickCommandTracker {
    public static let shared = QuickCommandTracker()

    private let defaults: UserDefaults
    private let storageKey = "quick_command_usage_v1"
    /// 滑动窗口：7 天（秒）
    private let window: TimeInterval = 7 * 24 * 60 * 60

    private struct Record: Codable {
        var command: String
        var timestamp: TimeInterval
    }

    private init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    /// 记录一次指令使用（点击快捷指令时触发）。
    public func record(_ command: String) {
        let key = normalized(command)
        guard !key.isEmpty else { return }
        let now = Date().timeIntervalSince1970
        // 写入时剪除窗口外旧记录，防止无限增长
        var records = load().filter { $0.timestamp >= now - window }
        records.append(Record(command: key, timestamp: now))
        save(records)
    }

    /// 窗口内按频次降序返回 [(指令, 频次)]。
    public func rankedCommands() -> [(command: String, count: Int)] {
        let now = Date().timeIntervalSince1970
        let cutoff = now - window
        var counts: [String: Int] = [:]
        for r in load() where r.timestamp >= cutoff {
            counts[r.command, default: 0] += 1
        }
        return counts
            .map { (command: $0.key, count: $0.value) }
            .sorted { lhs, rhs in
                if lhs.count != rhs.count { return lhs.count > rhs.count }
                return lhs.command < rhs.command
            }
    }

    /// 清空本地统计（调试/测试用）。
    public func reset() {
        defaults.removeObject(forKey: storageKey)
    }

    private func normalized(_ command: String) -> String {
        command.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func load() -> [Record] {
        guard let data = defaults.data(forKey: storageKey),
              let records = try? JSONDecoder().decode([Record].self, from: data) else {
            return []
        }
        return records
    }

    private func save(_ records: [Record]) {
        if let data = try? JSONEncoder().encode(records) {
            defaults.set(data, forKey: storageKey)
        }
    }
}
