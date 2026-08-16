//
//  LocalArtifactStore.swift
//  AIPlatformApp
//
//  设置页「我创建的智能体 / 我制作的技能」本地 JSON 持久化。
//  健壮性要求（按 Supervision 批复）：
//    - 原子写：先写 .tmp 再 rename 覆盖主文件
//    - 损坏恢复：主文件解析失败时从 .bak 备份恢复；备份亦损坏则安全重建为空集合
//    - 版本与租户：schema_version = 1、tenant_key = "demo"
//  语义：本地演示（与云端 CRUD 双轨并行，云端 CRUD = P2），UI 显式标注「本地演示」。
//

import Foundation
import Combine

public final class LocalArtifactStore: ObservableObject {
    public static let shared = LocalArtifactStore()
    @Published public private(set) var agents: [CreatedAgent] = []
    @Published public private(set) var skills: [CreatedSkill] = []

    private static let schemaVersion = 1
    private static let tenantKey = "demo"

    private struct Envelope: Codable {
        var schemaVersion: Int
        var tenantKey: String
        var agents: [CreatedAgent]
        var skills: [CreatedSkill]
    }

    private var directory: URL {
        let base = FileManager.default.urls(
            for: .applicationSupportDirectory, in: .userDomainMask
        ).first ?? FileManager.default.temporaryDirectory
        return base.appendingPathComponent("AIPlatformApp", isDirectory: true)
    }

    private var mainURL: URL { directory.appendingPathComponent("artifacts.json") }
    private var tmpURL: URL { directory.appendingPathComponent("artifacts.json.tmp") }
    private var backupURL: URL { directory.appendingPathComponent("artifacts.json.bak") }

    public init() {
        load()
    }

    // MARK: - 读（含损坏恢复）

    private func load() {
        let env = Self.readEnvelope(from: mainURL)
            ?? Self.readEnvelope(from: backupURL)
            ?? Envelope(
                schemaVersion: Self.schemaVersion,
                tenantKey: Self.tenantKey,
                agents: [],
                skills: []
            )
        agents = env.agents
        skills = env.skills
    }

    /// 主文件 → 备份逐级降级读取；解析失败或 schema 不匹配视为损坏（返回 nil 触发下一级恢复）。
    private static func readEnvelope(from url: URL) -> Envelope? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        guard let env = try? JSONDecoder().decode(Envelope.self, from: data),
              env.schemaVersion == schemaVersion else { return nil }
        return env
    }

    // MARK: - 写（原子写 .tmp → rename；成功后刷新 .bak）

    private func persist() {
        try? FileManager.default.createDirectory(
            at: directory, withIntermediateDirectories: true
        )
        let env = Envelope(
            schemaVersion: Self.schemaVersion,
            tenantKey: Self.tenantKey,
            agents: agents,
            skills: skills
        )
        guard let data = try? JSONEncoder().encode(env) else { return }
        Self.atomicWrite(data, to: mainURL, tmpURL: tmpURL)
        // 每次成功保存后刷新最近一次有效备份（.bak 供损坏恢复）
        try? data.write(to: backupURL, options: .atomic)
    }

    private static func atomicWrite(_ data: Data, to url: URL, tmpURL: URL) {
        // 1) 原子写临时文件（完整 flush）
        try? data.write(to: tmpURL, options: .atomic)
        // 2) 原子 rename/替换主文件
        if FileManager.default.fileExists(atPath: url.path) {
            _ = try? FileManager.default.replaceItemAt(url, withItemAt: tmpURL)
        } else {
            try? FileManager.default.moveItem(at: tmpURL, to: url)
        }
    }

    // MARK: - 增删

    public func addAgent(_ agent: CreatedAgent) {
        agents.append(agent)
        persist()
    }

    public func addSkill(_ skill: CreatedSkill) {
        skills.append(skill)
        persist()
    }

    public func removeAgent(id: String) {
        agents.removeAll { $0.id == id }
        persist()
    }

    public func removeSkill(id: String) {
        skills.removeAll { $0.id == id }
        persist()
    }
}
