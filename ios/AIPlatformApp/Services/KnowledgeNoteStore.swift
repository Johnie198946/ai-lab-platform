//
//  KnowledgeNoteStore.swift
//  AIPlatformApp
//
//  Local-first Markdown vault used by the Knowledge tab.
//  Markdown files remain readable by Obsidian and any plain-text editor.
//

import Combine
import Foundation

public struct KnowledgeNote: Identifiable, Hashable, Sendable {
    public let id: String
    public var title: String
    public var body: String
    public var tags: [String]
    public var aliases: [String]
    public var createdAt: Date
    public var updatedAt: Date
    public var isPinned: Bool
    public var fileURL: URL
    public var outgoingLinks: [String]

    public var preview: String {
        var text = body
            .replacingOccurrences(of: #"!\[\[[^\]]+\]\]"#, with: "附件", options: .regularExpression)
        if let expression = try? NSRegularExpression(pattern: #"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]"#) {
            let matches = expression.matches(in: text, range: NSRange(text.startIndex..., in: text))
            for match in matches.reversed() {
                guard let fullRange = Range(match.range(at: 0), in: text),
                      let titleRange = Range(match.range(at: 1), in: text) else { continue }
                let aliasRange = Range(match.range(at: 2), in: text)
                let replacement = aliasRange.map { String(text[$0]) } ?? String(text[titleRange])
                text.replaceSubrange(fullRange, with: replacement)
            }
        }
        return text
            .replacingOccurrences(of: #"[#>*_`=\-\[\]]"#, with: "", options: .regularExpression)
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
            .prefix(3)
            .joined(separator: " ")
    }

    public var isDailyNote: Bool {
        tags.contains(where: { $0.caseInsensitiveCompare("daily") == .orderedSame })
    }
}

@MainActor
public final class KnowledgeNoteStore: ObservableObject {
    public static let shared = KnowledgeNoteStore()

    @Published public private(set) var notes: [KnowledgeNote] = []
    @Published public private(set) var isLoading = false
    @Published public private(set) var lastError: String?

    private let fileManager = FileManager.default
    private let isoFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    public var vaultDirectory: URL {
        let documents = fileManager.urls(for: .documentDirectory, in: .userDomainMask).first
            ?? fileManager.temporaryDirectory
        return documents.appendingPathComponent("KnowledgeVault", isDirectory: true)
    }

    public var allTags: [String] {
        Array(Set(notes.flatMap(\.tags))).sorted { $0.localizedStandardCompare($1) == .orderedAscending }
    }

    private init() {
        reload()
    }

    public func reload() {
        isLoading = true
        defer { isLoading = false }

        do {
            try fileManager.createDirectory(at: vaultDirectory, withIntermediateDirectories: true)
            var loaded: [KnowledgeNote] = []
            if let enumerator = fileManager.enumerator(
                at: vaultDirectory,
                includingPropertiesForKeys: [.isRegularFileKey, .contentModificationDateKey],
                options: [.skipsHiddenFiles]
            ) {
                for case let url as URL in enumerator where url.pathExtension.lowercased() == "md" {
                    guard !url.path.contains("/.trash/") else { continue }
                    if let note = try parseNote(at: url) {
                        loaded.append(note)
                    }
                }
            }

            if loaded.isEmpty {
                try seedStarterNotes()
                reload()
                return
            }

            notes = sorted(loaded)
            lastError = nil
        } catch {
            lastError = "无法读取本地笔记：\(error.localizedDescription)"
        }
    }

    public func clearError() {
        lastError = nil
    }

    public func markdown(for note: KnowledgeNote) -> String {
        encode(note)
    }

    @discardableResult
    public func createNote(title: String = "无标题", body: String = "", tags: [String] = []) -> KnowledgeNote? {
        let now = Date()
        let note = KnowledgeNote(
            id: UUID().uuidString.lowercased(),
            title: title,
            body: body,
            tags: normalized(tags + extractInlineTags(from: body)),
            aliases: [],
            createdAt: now,
            updatedAt: now,
            isPinned: false,
            fileURL: uniqueURL(for: title),
            outgoingLinks: extractWikiLinks(from: body)
        )
        do {
            try write(note)
            notes.insert(note, at: 0)
            notes = sorted(notes)
            lastError = nil
            return note
        } catch {
            lastError = "无法创建笔记：\(error.localizedDescription)"
            return nil
        }
    }

    @discardableResult
    public func dailyNote(for date: Date = Date()) -> KnowledgeNote? {
        let calendar = Calendar.current
        if let existing = notes.first(where: { $0.isDailyNote && calendar.isDate($0.createdAt, inSameDayAs: date) }) {
            return existing
        }

        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_Hans_CN")
        formatter.dateFormat = "yyyy-MM-dd"
        let title = formatter.string(from: date)
        let body = """
        ## 今日重点

        - [ ] 

        ## 记录

        
        """
        return createNote(title: title, body: body, tags: ["daily"])
    }

    @discardableResult
    public func save(
        id: String,
        title: String,
        body: String,
        tags: [String],
        isPinned: Bool
    ) -> KnowledgeNote? {
        guard let index = notes.firstIndex(where: { $0.id == id }) else { return nil }
        let oldTitle = notes[index].title
        var note = notes[index]
        let cleanedTitle = title.trimmingCharacters(in: .whitespacesAndNewlines)
        note.title = cleanedTitle.isEmpty ? "无标题" : cleanedTitle
        note.body = body
        note.tags = normalized(tags + extractInlineTags(from: body))
        note.isPinned = isPinned
        note.updatedAt = Date()
        note.outgoingLinks = extractWikiLinks(from: body)

        if oldTitle != note.title {
            note.fileURL = uniqueURL(for: note.title, excluding: note.fileURL)
        }

        do {
            try write(note)
            if notes[index].fileURL != note.fileURL, fileManager.fileExists(atPath: notes[index].fileURL.path) {
                try fileManager.removeItem(at: notes[index].fileURL)
            }
            notes[index] = note
            if oldTitle != note.title {
                try updateIncomingLinks(from: oldTitle, to: note.title, excluding: note.id)
            }
            notes = sorted(notes)
            lastError = nil
            return notes.first(where: { $0.id == id })
        } catch {
            lastError = "自动保存失败：\(error.localizedDescription)"
            return nil
        }
    }

    public func togglePin(id: String) {
        guard let note = note(id: id) else { return }
        _ = save(id: id, title: note.title, body: note.body, tags: note.tags, isPinned: !note.isPinned)
    }

    /// Recoverable deletion: notes are moved into KnowledgeVault/.trash.
    public func moveToTrash(id: String) {
        guard let note = note(id: id) else { return }
        do {
            let trash = vaultDirectory.appendingPathComponent(".trash", isDirectory: true)
            try fileManager.createDirectory(at: trash, withIntermediateDirectories: true)
            var destination = trash.appendingPathComponent(note.fileURL.lastPathComponent)
            if fileManager.fileExists(atPath: destination.path) {
                destination = trash.appendingPathComponent("\(UUID().uuidString)-\(note.fileURL.lastPathComponent)")
            }
            try fileManager.moveItem(at: note.fileURL, to: destination)
            notes.removeAll { $0.id == id }
            lastError = nil
        } catch {
            lastError = "无法移到废纸篓：\(error.localizedDescription)"
        }
    }

    public func note(id: String) -> KnowledgeNote? {
        notes.first { $0.id == id }
    }

    public func note(matchingLink link: String) -> KnowledgeNote? {
        let target = link.trimmingCharacters(in: .whitespacesAndNewlines)
        return notes.first { note in
            note.title.caseInsensitiveCompare(target) == .orderedSame
                || note.fileURL.deletingPathExtension().lastPathComponent.caseInsensitiveCompare(target) == .orderedSame
                || note.aliases.contains(where: { $0.caseInsensitiveCompare(target) == .orderedSame })
        }
    }

    public func backlinks(to note: KnowledgeNote) -> [KnowledgeNote] {
        notes.filter { candidate in
            candidate.id != note.id && candidate.outgoingLinks.contains { link in
                link.caseInsensitiveCompare(note.title) == .orderedSame
                    || note.aliases.contains(where: { $0.caseInsensitiveCompare(link) == .orderedSame })
            }
        }
    }

    public func unresolvedLinks(in note: KnowledgeNote) -> [String] {
        note.outgoingLinks.filter { self.note(matchingLink: $0) == nil }
    }

    public func search(_ query: String, tag: String? = nil) -> [KnowledgeNote] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        return notes.filter { note in
            let tagMatches = tag == nil || note.tags.contains(where: { $0.caseInsensitiveCompare(tag!) == .orderedSame })
            let queryMatches = trimmed.isEmpty
                || note.title.localizedCaseInsensitiveContains(trimmed)
                || note.body.localizedCaseInsensitiveContains(trimmed)
                || note.tags.contains(where: { $0.localizedCaseInsensitiveContains(trimmed) })
            return tagMatches && queryMatches
        }
    }

    private func parseNote(at url: URL) throws -> KnowledgeNote? {
        let content = try String(contentsOf: url, encoding: .utf8)
        let lines = content.components(separatedBy: .newlines)
        var metadata: [String: String] = [:]
        var listValues: [String: [String]] = [:]
        var bodyStart = 0

        if lines.first?.trimmingCharacters(in: .whitespaces) == "---",
           let closing = lines.dropFirst().firstIndex(where: { $0.trimmingCharacters(in: .whitespaces) == "---" }) {
            var activeListKey: String?
            for line in lines[1..<closing] {
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                if trimmed.hasPrefix("- "), let key = activeListKey {
                    listValues[key, default: []].append(unquote(String(trimmed.dropFirst(2))))
                } else if let separator = trimmed.firstIndex(of: ":") {
                    let key = String(trimmed[..<separator]).trimmingCharacters(in: .whitespaces)
                    let value = String(trimmed[trimmed.index(after: separator)...]).trimmingCharacters(in: .whitespaces)
                    metadata[key] = unquote(value)
                    activeListKey = value.isEmpty ? key : nil
                    if value.hasPrefix("[") && value.hasSuffix("]") {
                        listValues[key] = value.dropFirst().dropLast().split(separator: ",").map {
                            unquote(String($0).trimmingCharacters(in: .whitespaces))
                        }
                    }
                }
            }
            bodyStart = closing + 1
        }

        let body = lines.dropFirst(bodyStart).joined(separator: "\n").trimmingCharacters(in: .newlines)
        let attributes = try? url.resourceValues(forKeys: [.contentModificationDateKey, .creationDateKey])
        let fallbackDate = attributes?.contentModificationDate ?? Date()
        let title = metadata["title"].flatMap { $0.isEmpty ? nil : $0 }
            ?? url.deletingPathExtension().lastPathComponent
        let frontmatterTags = listValues["tags"] ?? metadata["tags"].map { [$0] } ?? []
        let created = metadata["created"].flatMap(isoFormatter.date(from:))
            ?? attributes?.creationDate
            ?? fallbackDate
        let updated = metadata["updated"].flatMap(isoFormatter.date(from:)) ?? fallbackDate

        return KnowledgeNote(
            id: metadata["id"].flatMap { $0.isEmpty ? nil : $0 } ?? UUID().uuidString.lowercased(),
            title: title,
            body: body,
            tags: normalized(frontmatterTags + extractInlineTags(from: body)),
            aliases: normalized(listValues["aliases"] ?? []),
            createdAt: created,
            updatedAt: updated,
            isPinned: metadata["pinned"] == "true",
            fileURL: url,
            outgoingLinks: extractWikiLinks(from: body)
        )
    }

    private func write(_ note: KnowledgeNote) throws {
        try fileManager.createDirectory(
            at: note.fileURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        let content = encode(note)
        try content.write(to: note.fileURL, atomically: true, encoding: .utf8)
    }

    private func encode(_ note: KnowledgeNote) -> String {
        var lines = [
            "---",
            "id: \(yamlString(note.id))",
            "title: \(yamlString(note.title))",
            "created: \(isoFormatter.string(from: note.createdAt))",
            "updated: \(isoFormatter.string(from: note.updatedAt))",
            "pinned: \(note.isPinned ? "true" : "false")",
            note.tags.isEmpty ? "tags: []" : "tags:",
        ]
        lines.append(contentsOf: note.tags.map { "  - \(yamlString($0))" })
        lines.append(note.aliases.isEmpty ? "aliases: []" : "aliases:")
        lines.append(contentsOf: note.aliases.map { "  - \(yamlString($0))" })
        lines.append("---")
        lines.append("")
        lines.append(note.body)
        lines.append("")
        return lines.joined(separator: "\n")
    }

    private func updateIncomingLinks(from oldTitle: String, to newTitle: String, excluding id: String) throws {
        guard !oldTitle.isEmpty, oldTitle != newTitle else { return }
        let escaped = NSRegularExpression.escapedPattern(for: oldTitle)
        let pattern = #"\[\[("# + escaped + #")((?:#[^\]|]+)?(?:\|[^\]]+)?)\]\]"#
        let regex = try NSRegularExpression(pattern: pattern, options: [.caseInsensitive])

        for index in notes.indices where notes[index].id != id {
            let body = notes[index].body
            let range = NSRange(body.startIndex..., in: body)
            let replaced = regex.stringByReplacingMatches(in: body, range: range, withTemplate: "[[\(newTitle)$2]]")
            guard replaced != body else { continue }
            notes[index].body = replaced
            notes[index].outgoingLinks = extractWikiLinks(from: replaced)
            notes[index].updatedAt = Date()
            try write(notes[index])
        }
    }

    private func extractWikiLinks(from text: String) -> [String] {
        guard let regex = try? NSRegularExpression(pattern: #"!?\[\[([^\]|#]+)"#) else { return [] }
        let range = NSRange(text.startIndex..., in: text)
        return normalized(regex.matches(in: text, range: range).compactMap { match in
            guard let swiftRange = Range(match.range(at: 1), in: text) else { return nil }
            return String(text[swiftRange]).trimmingCharacters(in: .whitespacesAndNewlines)
        })
    }

    private func extractInlineTags(from text: String) -> [String] {
        guard let regex = try? NSRegularExpression(pattern: #"#([\p{L}_][\p{L}\p{N}_/-]*)"#) else { return [] }
        let range = NSRange(text.startIndex..., in: text)
        return normalized(regex.matches(in: text, range: range).compactMap { match in
            guard let swiftRange = Range(match.range(at: 1), in: text) else { return nil }
            return String(text[swiftRange])
        })
    }

    private func uniqueURL(for title: String, excluding currentURL: URL? = nil) -> URL {
        let base = safeFilename(title)
        var candidate = vaultDirectory.appendingPathComponent(base).appendingPathExtension("md")
        var suffix = 2
        while fileManager.fileExists(atPath: candidate.path) && candidate != currentURL {
            candidate = vaultDirectory.appendingPathComponent("\(base)-\(suffix)").appendingPathExtension("md")
            suffix += 1
        }
        return candidate
    }

    private func safeFilename(_ title: String) -> String {
        let invalid = CharacterSet(charactersIn: "/\\:*?\"<>|#[]")
        let cleaned = title
            .components(separatedBy: invalid)
            .joined(separator: "-")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return String((cleaned.isEmpty ? "无标题" : cleaned).prefix(80))
    }

    private func sorted(_ values: [KnowledgeNote]) -> [KnowledgeNote] {
        values.sorted {
            if $0.isPinned != $1.isPinned { return $0.isPinned }
            if $0.updatedAt != $1.updatedAt { return $0.updatedAt > $1.updatedAt }
            return $0.title.localizedStandardCompare($1.title) == .orderedAscending
        }
    }

    private func normalized(_ values: [String]) -> [String] {
        var seen = Set<String>()
        return values.compactMap { raw in
            let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !value.isEmpty else { return nil }
            let key = value.lowercased()
            guard seen.insert(key).inserted else { return nil }
            return value
        }
    }

    private func yamlString(_ value: String) -> String {
        "\"\(value.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "\"", with: "\\\""))\""
    }

    private func unquote(_ value: String) -> String {
        guard value.count >= 2,
              (value.hasPrefix("\"") && value.hasSuffix("\"") || value.hasPrefix("'") && value.hasSuffix("'"))
        else { return value }
        return String(value.dropFirst().dropLast())
            .replacingOccurrences(of: "\\\"", with: "\"")
            .replacingOccurrences(of: "\\\\", with: "\\")
    }

    private func seedStarterNotes() throws {
        let welcome = KnowledgeNote(
            id: UUID().uuidString.lowercased(),
            title: "欢迎使用知识笔记",
            body: """
            这里是你的本地 Markdown 笔记空间。每篇笔记都是普通的 `.md` 文件，可以使用 Obsidian 或其他文本编辑器打开。

            ## 从这里开始

            - 创建一篇新笔记
            - 输入 `[[灵感收集]]` 建立双向链接
            - 使用 `#项目/示例` 添加层级标签
            - 打开每日笔记记录今天

            > [!tip] 本地优先
            > 笔记默认保存在设备的 `KnowledgeVault` 文件夹中。

            继续阅读 [[灵感收集]]。
            """,
            tags: ["入门"],
            aliases: ["开始"],
            createdAt: Date(),
            updatedAt: Date(),
            isPinned: true,
            fileURL: uniqueURL(for: "欢迎使用知识笔记"),
            outgoingLinks: ["灵感收集"]
        )
        let ideas = KnowledgeNote(
            id: UUID().uuidString.lowercased(),
            title: "灵感收集",
            body: """
            随手记下想法，再把它们连接到相关页面。

            ## Inbox

            - [ ] 尝试创建第一篇项目笔记
            - [ ] 在正文里输入 `[[欢迎使用知识笔记]]`

            返回 [[欢迎使用知识笔记]]。
            """,
            tags: ["inbox"],
            aliases: [],
            createdAt: Date(),
            updatedAt: Date(),
            isPinned: false,
            fileURL: uniqueURL(for: "灵感收集"),
            outgoingLinks: ["欢迎使用知识笔记"]
        )
        try write(welcome)
        try write(ideas)
    }
}
