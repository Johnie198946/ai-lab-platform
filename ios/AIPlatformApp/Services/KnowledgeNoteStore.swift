//
//  KnowledgeNoteStore.swift
//  AIPlatformApp
//
//  Local-first Markdown vault used by the Knowledge tab.
//  Markdown files remain readable by Obsidian and any plain-text editor.
//

import Combine
import CryptoKit
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
    public var archivedAt: Date?
    public var mergedIntoNoteId: String?

    public init(
        id: String, title: String, body: String, tags: [String], aliases: [String],
        createdAt: Date, updatedAt: Date, isPinned: Bool, fileURL: URL,
        outgoingLinks: [String], archivedAt: Date? = nil,
        mergedIntoNoteId: String? = nil
    ) {
        self.id = id
        self.title = title
        self.body = body
        self.tags = tags
        self.aliases = aliases
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.isPinned = isPinned
        self.fileURL = fileURL
        self.outgoingLinks = outgoingLinks
        self.archivedAt = archivedAt
        self.mergedIntoNoteId = mergedIntoNoteId
    }

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

public struct KnowledgeNoteIndex: Sendable {
    public var tags: [String] = []
    public var previewsByNoteID: [String: String] = [:]
    public var backlinkCountsByNoteID: [String: Int] = [:]
}

@MainActor
public final class KnowledgeNoteStore: ObservableObject {
    public static let shared = KnowledgeNoteStore()

    @Published public private(set) var notes: [KnowledgeNote] = []
    @Published public private(set) var archivedNotes: [KnowledgeNote] = []
    @Published public private(set) var index = KnowledgeNoteIndex()
    @Published public private(set) var isLoading = false
    @Published public private(set) var lastError: String?

    private let fileManager = FileManager.default
    private var tenantNamespace = "unconfigured"
    private var userNamespace = "unconfigured"
    @Published public private(set) var accountFingerprint = "unconfigured"
    private let isoFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    public var vaultDirectory: URL {
        let documents = fileManager.urls(for: .documentDirectory, in: .userDomainMask).first
            ?? fileManager.temporaryDirectory
        return documents
            .appendingPathComponent("KnowledgeVault/accounts", isDirectory: true)
            .appendingPathComponent(tenantNamespace, isDirectory: true)
            .appendingPathComponent(userNamespace, isDirectory: true)
    }

    public var allTags: [String] { index.tags }

    public var archiveDirectory: URL {
        vaultDirectory.appendingPathComponent(".archive", isDirectory: true)
    }

    public var actionDirectory: URL {
        vaultDirectory.appendingPathComponent(".actions", isDirectory: true)
    }

    public var authorizationScope: String {
        "\(tenantNamespace.prefix(16)):\(userNamespace.prefix(16))"
    }

    private init() {}

    public func activate(tenantKey: String, userId: String) {
        let tenant = Self.namespace(tenantKey)
        let user = Self.namespace(userId)
        guard tenant != tenantNamespace || user != userNamespace else { return }
        notes.removeAll()
        archivedNotes.removeAll()
        index = KnowledgeNoteIndex()
        tenantNamespace = tenant
        userNamespace = user
        accountFingerprint = "\(tenant):\(user)"
        reload()
    }

    public func deactivate() {
        notes.removeAll()
        archivedNotes.removeAll()
        index = KnowledgeNoteIndex()
        tenantNamespace = "unconfigured"
        userNamespace = "unconfigured"
        accountFingerprint = "unconfigured"
        lastError = nil
    }

    private static func namespace(_ value: String) -> String {
        SHA256.hash(data: Data(value.utf8)).prefix(10)
            .map { String(format: "%02x", $0) }.joined()
    }

    public func reload() {
        isLoading = true
        defer { isLoading = false }

        do {
            try fileManager.createDirectory(at: vaultDirectory, withIntermediateDirectories: true)
            var loaded: [KnowledgeNote] = []
            var archived: [KnowledgeNote] = []
            if let enumerator = fileManager.enumerator(
                at: vaultDirectory,
                includingPropertiesForKeys: [.isRegularFileKey, .contentModificationDateKey],
                options: [.skipsHiddenFiles]
            ) {
                for case let url as URL in enumerator where url.pathExtension.lowercased() == "md" {
                    guard !url.path.contains("/.trash/") else { continue }
                    if let note = try parseNote(at: url) {
                        if url.path.contains("/.archive/") {
                            archived.append(note)
                        } else {
                            loaded.append(note)
                        }
                    }
                }
            }

            notes = sorted(loaded)
            archivedNotes = sorted(archived)
            rebuildIndex()
            lastError = nil
        } catch {
            lastError = "无法读取本地笔记：\(error.localizedDescription)"
        }
    }

    public func clearError() {
        lastError = nil
    }

    /// Restore the authenticated account's durable server snapshot after login or reinstall.
    /// Existing local edits only yield to a strictly newer cloud copy.
    public func restoreFromCloud() async {
        guard accountFingerprint != "unconfigured" else { return }
        let expectedFingerprint = accountFingerprint
        do {
            let response = try await APIClient.shared.fetchKnowledgeNotes()
            guard accountFingerprint == expectedFingerprint else { return }
            try restoreFromCloudSnapshot(response)
            lastError = nil
        } catch {
            guard accountFingerprint == expectedFingerprint else { return }
            lastError = "云端笔记暂未同步：\(error.localizedDescription)"
        }
    }

    /// Materialize a server-authenticated snapshot in the local vault so a
    /// server-proposed action can reference notes absent from this device.
    public func restoreFromCloudSnapshot(_ response: CloudKnowledgeNotesResponse) throws {
        for snapshot in response.items {
            try applyCloudSnapshot(snapshot)
        }
        reload()
    }

    private func applyCloudSnapshot(_ snapshot: CloudKnowledgeNoteDTO) throws {
        if let existing = anyNote(id: snapshot.noteId) {
            let localHash = SHA256.hash(data: Data(markdown(for: existing).utf8))
                .map { String(format: "%02x", $0) }.joined()
            if localHash == snapshot.contentHash { return }
            let remoteUpdatedAt = snapshot.updatedAt.flatMap(Self.parseServerDate)
            if remoteUpdatedAt == nil || remoteUpdatedAt! <= existing.updatedAt { return }
            try? fileManager.removeItem(at: existing.fileURL)
        }

        let directory = snapshot.archived ? archiveDirectory : vaultDirectory
        try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
        let destination = directory.appendingPathComponent("\(snapshot.noteId).md")
        try snapshot.markdown.write(to: destination, atomically: true, encoding: .utf8)
    }

    private static func parseServerDate(_ value: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractional.date(from: value) { return date }
        return ISO8601DateFormatter().date(from: value)
    }

    public func markdown(for note: KnowledgeNote) -> String {
        encode(note)
    }

    public func contentHash(for note: KnowledgeNote) -> String {
        SHA256.hash(data: Data(encode(note).utf8))
            .map { String(format: "%02x", $0) }
            .joined()
    }

    @discardableResult
    public func createNote(id: String = UUID().uuidString.lowercased(), title: String = "无标题", body: String = "", tags: [String] = []) -> KnowledgeNote? {
        if let existing = note(id: id) { return existing }
        let now = Date()
        let note = KnowledgeNote(
            id: id,
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
            rebuildIndex()
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
            rebuildIndex()
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
            rebuildIndex()
            lastError = nil
        } catch {
            lastError = "无法移到废纸篓：\(error.localizedDescription)"
        }
    }

    /// Merged source notes remain recoverable but are excluded from active search and sync.
    @discardableResult
    public func archive(id: String, mergedInto: String) -> KnowledgeNote? {
        guard let index = notes.firstIndex(where: { $0.id == id }) else {
            return archivedNotes.first { $0.id == id }
        }
        var note = notes[index]
        do {
            try fileManager.createDirectory(at: archiveDirectory, withIntermediateDirectories: true)
            var destination = archiveDirectory.appendingPathComponent(note.fileURL.lastPathComponent)
            if fileManager.fileExists(atPath: destination.path) {
                destination = archiveDirectory.appendingPathComponent("\(note.id)-\(note.fileURL.lastPathComponent)")
            }
            try fileManager.moveItem(at: note.fileURL, to: destination)
            note.fileURL = destination
            note.archivedAt = Date()
            note.mergedIntoNoteId = mergedInto
            try write(note)
            notes.remove(at: index)
            archivedNotes = sorted(archivedNotes + [note])
            rebuildIndex()
            lastError = nil
            return note
        } catch {
            lastError = "无法归档笔记：\(error.localizedDescription)"
            return nil
        }
    }

    @discardableResult
    public func restoreArchivedNote(id: String) -> KnowledgeNote? {
        guard let index = archivedNotes.firstIndex(where: { $0.id == id }) else { return nil }
        var note = archivedNotes[index]
        do {
            let destination = uniqueURL(for: note.title)
            try fileManager.moveItem(at: note.fileURL, to: destination)
            note.fileURL = destination
            note.archivedAt = nil
            note.mergedIntoNoteId = nil
            try write(note)
            archivedNotes.remove(at: index)
            notes = sorted(notes + [note])
            rebuildIndex()
            lastError = nil
            return note
        } catch {
            lastError = "无法恢复归档笔记：\(error.localizedDescription)"
            return nil
        }
    }

    public func note(id: String) -> KnowledgeNote? {
        notes.first { $0.id == id }
    }

    public func archivedNote(id: String) -> KnowledgeNote? {
        archivedNotes.first { $0.id == id }
    }

    public func anyNote(id: String) -> KnowledgeNote? {
        note(id: id) ?? archivedNote(id: id)
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
        search(query, tags: tag.map { Set([$0]) } ?? [])
    }

    /// Every selected tag must be present (logical AND), matching the knowledge
    /// workspace's multi-tag filtering contract.
    public func search(_ query: String, tags: Set<String>) -> [KnowledgeNote] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        return notes.filter { note in
            let noteTags = Set(note.tags.map { $0.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: .current) })
            let requestedTags = Set(tags.map { $0.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: .current) })
            let tagMatches = requestedTags.isSubset(of: noteTags)
            let queryMatches = trimmed.isEmpty
                || note.title.localizedCaseInsensitiveContains(trimmed)
                || note.body.localizedCaseInsensitiveContains(trimmed)
                || note.tags.contains(where: { $0.localizedCaseInsensitiveContains(trimmed) })
            return tagMatches && queryMatches
        }
    }

    private func rebuildIndex() {
        var previews: [String: String] = [:]
        var titleOwners: [String: String] = [:]
        var backlinks = Dictionary(uniqueKeysWithValues: notes.map { ($0.id, 0) })

        for note in notes {
            previews[note.id] = note.preview
            for title in [note.title] + note.aliases {
                titleOwners[normalizedLinkKey(title)] = note.id
            }
        }
        for source in notes {
            for link in source.outgoingLinks {
                guard let targetID = titleOwners[normalizedLinkKey(link)], targetID != source.id else { continue }
                backlinks[targetID, default: 0] += 1
            }
        }

        index = KnowledgeNoteIndex(
            tags: Array(Set(notes.flatMap(\.tags))).sorted {
                $0.localizedStandardCompare($1) == .orderedAscending
            },
            previewsByNoteID: previews,
            backlinkCountsByNoteID: backlinks
        )
    }

    private func normalizedLinkKey(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines)
            .folding(options: [.caseInsensitive, .diacriticInsensitive], locale: .current)
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
            outgoingLinks: extractWikiLinks(from: body),
            archivedAt: metadata["archived_at"].flatMap(isoFormatter.date(from:)),
            mergedIntoNoteId: metadata["merged_into"].flatMap { $0.isEmpty ? nil : $0 }
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
            note.archivedAt.map { "archived_at: \(isoFormatter.string(from: $0))" } ?? "archived_at:",
            note.mergedIntoNoteId.map { "merged_into: \(yamlString($0))" } ?? "merged_into:",
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

public struct KnowledgeActionExecutionResult: Sendable {
    public let state: KnowledgeActionState
    public let noteIds: [String]
    public let message: String?
}

private struct KnowledgeActionReceipt: Codable {
    let actionId: String
    let actionDigest: String
    let accountFingerprint: String
    var status: KnowledgeActionState
    var resultNoteIds: [String]
    var updatedAt: Date
}

/// The only client component allowed to mutate the personal knowledge vault.
/// Hermes proposes typed steps; this executor validates, journals and applies them locally.
@MainActor
public final class KnowledgeActionExecutor {
    public static let shared = KnowledgeActionExecutor()
    private let store = KnowledgeNoteStore.shared
    private let fileManager = FileManager.default

    private init() {}

    public func execute(_ action: KnowledgeActionBlock) async -> KnowledgeActionExecutionResult {
        guard action.accountScope == nil || action.accountScope == store.authorizationScope else {
            return .init(state: .stale, noteIds: [], message: "账号已切换，请重新生成操作")
        }
        let expectedFingerprint = store.accountFingerprint
        if let receipt = loadReceipt(action.id), receipt.actionDigest == action.actionDigest,
           [.localApplied, .syncPending, .synced].contains(receipt.status) {
            if receipt.status != .synced {
                return await synchronize(
                    action,
                    capability: validCapability(for: action),
                    noteIds: receipt.resultNoteIds,
                    expectedFingerprint: expectedFingerprint
                )
            }
            return .init(state: .synced, noteIds: receipt.resultNoteIds, message: nil)
        }
        guard let capability = validCapability(for: action) else {
            return .init(state: .stale, noteIds: [], message: "确认凭证已失效，请重新生成操作")
        }
        guard validateTargets(action.steps) else {
            return .init(state: .stale, noteIds: [], message: "笔记已变化，请重新生成修改方案")
        }

        let backup = backupDirectory(action.id)
        do {
            try prepareBackup(at: backup)
            saveReceipt(.init(
                actionId: action.id, actionDigest: action.actionDigest,
                accountFingerprint: store.accountFingerprint, status: .applying,
                resultNoteIds: [], updatedAt: Date()
            ))
            let ids = try applySteps(action.steps, actionId: action.id)
            saveReceipt(.init(
                actionId: action.id, actionDigest: action.actionDigest,
                accountFingerprint: store.accountFingerprint, status: .localApplied,
                resultNoteIds: ids, updatedAt: Date()
            ))
            try? fileManager.removeItem(at: backup)
            return await synchronize(action, capability: capability, noteIds: ids, expectedFingerprint: expectedFingerprint)
        } catch {
            try? restoreBackup(from: backup)
            store.reload()
            saveReceipt(.init(
                actionId: action.id, actionDigest: action.actionDigest,
                accountFingerprint: store.accountFingerprint, status: .failed,
                resultNoteIds: [], updatedAt: Date()
            ))
            return .init(state: .failed, noteIds: [], message: error.localizedDescription)
        }
    }

    public func discard(_ action: KnowledgeActionBlock) async -> KnowledgeActionExecutionResult {
        guard let capability = action.transientCapability else {
            return .init(state: .stale, noteIds: [], message: "确认凭证已失效")
        }
        do {
            try await APIClient.shared.discardKnowledgeAction(
                id: action.id, capability: capability, actionDigest: action.actionDigest
            )
            saveReceipt(.init(
                actionId: action.id, actionDigest: action.actionDigest,
                accountFingerprint: store.accountFingerprint, status: .discarded,
                resultNoteIds: [], updatedAt: Date()
            ))
            return .init(state: .discarded, noteIds: [], message: nil)
        } catch {
            return .init(state: .failed, noteIds: [], message: error.localizedDescription)
        }
    }

    private func validateTargets(_ steps: [KnowledgeActionStep]) -> Bool {
        for step in steps {
            let ids = ([step.targetNoteId].compactMap { $0 } + step.sourceNoteIds)
            for id in ids {
                guard let note = store.anyNote(id: id) else { return false }
                if id == step.targetNoteId, let expected = step.originalContentHash,
                   !expected.isEmpty, store.contentHash(for: note) != expected { return false }
                if let expected = step.sourceContentHashes?[id] ?? nil,
                   !expected.isEmpty, store.contentHash(for: note) != expected { return false }
            }
        }
        return true
    }

    private func applySteps(_ steps: [KnowledgeActionStep], actionId: String) throws -> [String] {
        var changed: [String] = []
        for (index, step) in steps.enumerated() {
            let stableID = Self.stableNoteID(actionId: actionId, index: index)
            switch step.kind {
            case "create_note", "create_daily_note":
                let body = markdownBody(step.markdown ?? "")
                let tags = step.kind == "create_daily_note" ? step.tags + ["daily"] : step.tags
                guard let note = store.createNote(id: stableID, title: step.title ?? inferredTitle(step.markdown), body: body, tags: tags) else { throw ActionError.writeFailed }
                changed.append(note.id)
            case "update_note", "rename_note", "set_tags", "set_pinned", "add_wikilink", "remove_wikilink":
                guard let id = step.targetNoteId, let note = store.note(id: id) else { throw ActionError.targetMissing }
                var body = step.markdown.map(markdownBody) ?? note.body
                if step.kind == "add_wikilink", let link = step.linkTitle, !body.contains("[[\(link)]]") {
                    body += "\n\n[[\(link)]]"
                } else if step.kind == "remove_wikilink", let link = step.linkTitle {
                    body = body.replacingOccurrences(of: "[[\(link)]]", with: link)
                }
                guard store.save(
                    id: id, title: step.title ?? note.title, body: body,
                    tags: step.kind == "set_tags" ? step.tags : (step.tags.isEmpty ? note.tags : step.tags),
                    isPinned: step.pinned ?? note.isPinned
                ) != nil else { throw ActionError.writeFailed }
                changed.append(id)
            case "merge_notes":
                let body = markdownBody(step.markdown ?? "")
                let primaryID = Self.mergePrimaryNoteID(
                    step: step, actionId: actionId, stepIndex: index
                )
                let merged: KnowledgeNote?
                if let note = store.note(id: primaryID) {
                    merged = store.save(
                        id: primaryID,
                        title: step.title ?? note.title,
                        body: body,
                        tags: step.tags.isEmpty ? note.tags : step.tags,
                        isPinned: note.isPinned
                    )
                } else {
                    merged = store.createNote(
                        id: primaryID,
                        title: step.title ?? inferredTitle(step.markdown),
                        body: body,
                        tags: step.tags
                    )
                }
                guard let merged else { throw ActionError.writeFailed }
                // Sources stay active until the primary has passed server CAS and
                // read-back verification. A retry can therefore resume safely.
                changed.append(merged.id)
                changed.append(contentsOf: Self.mergeArchiveSourceIDs(step: step, primaryID: merged.id))
            case "archive_note":
                guard let id = step.targetNoteId, store.archive(id: id, mergedInto: id) != nil else { throw ActionError.writeFailed }
                changed.append(id)
            case "restore_note":
                guard let id = step.targetNoteId, store.restoreArchivedNote(id: id) != nil else { throw ActionError.writeFailed }
                changed.append(id)
            case "move_to_trash":
                guard let id = step.targetNoteId, store.note(id: id) != nil else { throw ActionError.targetMissing }
                store.moveToTrash(id: id)
                changed.append(id)
            default:
                throw ActionError.unsupported
            }
        }
        var seen = Set<String>()
        return changed.filter { seen.insert($0).inserted }
    }

    private func validCapability(for action: KnowledgeActionBlock) -> String? {
        guard action.expiresAt > Int(Date().timeIntervalSince1970),
              let capability = action.transientCapability,
              !capability.isEmpty else { return nil }
        return capability
    }

    private func synchronize(_ action: KnowledgeActionBlock, capability: String?, noteIds: [String], expectedFingerprint: String) async -> KnowledgeActionExecutionResult {
        do {
            var mergeHandledIDs = Set<String>()
            for (index, step) in action.steps.enumerated() {
                guard store.accountFingerprint == expectedFingerprint else { throw ActionError.accountChanged }
                if step.kind == "move_to_trash", let id = step.targetNoteId {
                    try await APIClient.shared.trashKnowledgeNote(id: id)
                } else if step.kind == "archive_note", let id = step.targetNoteId {
                    if let archived = store.archivedNote(id: id) {
                        try await APIClient.shared.syncKnowledgeNote(id: id, markdown: store.markdown(for: archived), updatedAt: archived.updatedAt)
                    }
                    try await APIClient.shared.archiveKnowledgeNote(id: id, mergedIntoNoteId: id)
                } else if step.kind == "restore_note", let id = step.targetNoteId {
                    try await APIClient.shared.restoreKnowledgeNote(id: id)
                } else if step.kind == "merge_notes" {
                    let primaryID = Self.mergePrimaryNoteID(
                        step: step, actionId: action.id, stepIndex: index
                    )
                    try await synchronizeMerge(
                        step, primaryID: primaryID, expectedFingerprint: expectedFingerprint
                    )
                    mergeHandledIDs.insert(primaryID)
                    mergeHandledIDs.formUnion(
                        Self.mergeArchiveSourceIDs(step: step, primaryID: primaryID)
                    )
                }
            }
            for id in noteIds where !mergeHandledIDs.contains(id) {
                guard store.accountFingerprint == expectedFingerprint else { throw ActionError.accountChanged }
                if let note = store.note(id: id) {
                    try await APIClient.shared.syncKnowledgeNote(id: id, markdown: store.markdown(for: note), updatedAt: note.updatedAt)
                }
            }
            try await finalizeLedger(
                action, capability: capability, status: "synced", noteIds: noteIds
            )
            updateReceipt(action, state: .synced, ids: noteIds)
            return .init(state: .synced, noteIds: noteIds, message: nil)
        } catch {
            guard store.accountFingerprint == expectedFingerprint else {
                return .init(state: .stale, noteIds: noteIds, message: "账号已切换，旧账号同步已取消")
            }
            try? await finalizeLedger(
                action, capability: capability, status: "sync_pending",
                noteIds: noteIds, errorCode: "sync_failed"
            )
            updateReceipt(action, state: .syncPending, ids: noteIds)
            return .init(state: .syncPending, noteIds: noteIds, message: "已保存合并进度，可重试完成同步与归档")
        }
    }

    /// Server order is deliberate: verify the primary content first, then archive
    /// each non-primary source. Every check is idempotent so a partial failure can resume.
    private func synchronizeMerge(
        _ step: KnowledgeActionStep,
        primaryID: String,
        expectedFingerprint: String
    ) async throws {
        guard let primary = store.note(id: primaryID) else { throw ActionError.targetMissing }
        let primaryMarkdown = store.markdown(for: primary)
        let desiredHash = store.contentHash(for: primary)
        let expectedBaseHash = step.originalContentHash
            ?? step.sourceContentHashes?[primaryID]
            ?? nil

        var cloud = try await APIClient.shared.fetchKnowledgeNotes(includeArchived: true)
        if !cloud.items.contains(where: {
            $0.noteId == primaryID && !$0.archived && $0.contentHash == desiredHash
        }) {
            if cloud.items.contains(where: { $0.noteId == primaryID && $0.archived }) {
                throw ActionError.primaryArchived
            }
            let activePrimary = cloud.items.first(where: {
                $0.noteId == primaryID && !$0.archived
            })
            if activePrimary != nil, expectedBaseHash == nil {
                throw ActionError.targetChanged
            }
            try await APIClient.shared.syncKnowledgeNote(
                id: primaryID,
                markdown: primaryMarkdown,
                updatedAt: primary.updatedAt,
                // An unsynced local primary is created with no base. Existing
                // server notes always use the proposal's original hash as CAS.
                baseHash: activePrimary == nil ? nil : expectedBaseHash
            )
            cloud = try await APIClient.shared.fetchKnowledgeNotes(includeArchived: true)
        }
        guard cloud.items.contains(where: {
            $0.noteId == primaryID && !$0.archived && $0.contentHash == desiredHash
        }) else { throw ActionError.readBackFailed }

        for sourceID in Self.mergeArchiveSourceIDs(step: step, primaryID: primaryID) {
            guard store.accountFingerprint == expectedFingerprint else { throw ActionError.accountChanged }
            cloud = try await APIClient.shared.fetchKnowledgeNotes(includeArchived: true)
            if let archived = cloud.items.first(where: { $0.noteId == sourceID && $0.archived }) {
                guard archived.mergedIntoNoteId == primaryID else { throw ActionError.archiveConflict }
            } else {
                guard let source = store.note(id: sourceID) else { throw ActionError.targetMissing }
                let sourceHash = store.contentHash(for: source)
                guard let expectedSourceHash = step.sourceContentHashes?[sourceID] ?? nil,
                      expectedSourceHash == sourceHash
                else { throw ActionError.targetChanged }
                if let active = cloud.items.first(where: { $0.noteId == sourceID && !$0.archived }) {
                    guard active.contentHash == expectedSourceHash else {
                        throw ActionError.targetChanged
                    }
                } else {
                    try await APIClient.shared.syncKnowledgeNote(
                        id: sourceID,
                        markdown: store.markdown(for: source),
                        updatedAt: source.updatedAt
                    )
                }
                try await APIClient.shared.archiveKnowledgeNote(
                    id: sourceID,
                    mergedIntoNoteId: primaryID,
                    expectedContentHash: expectedSourceHash
                )
                cloud = try await APIClient.shared.fetchKnowledgeNotes(includeArchived: true)
                guard cloud.items.contains(where: {
                    $0.noteId == sourceID && $0.archived && $0.mergedIntoNoteId == primaryID
                }) else { throw ActionError.readBackFailed }
            }
            guard store.archive(id: sourceID, mergedInto: primaryID) != nil,
                  store.note(id: sourceID) == nil,
                  store.archivedNote(id: sourceID)?.mergedIntoNoteId == primaryID
            else { throw ActionError.readBackFailed }
        }
        guard store.note(id: primaryID) != nil,
              store.archivedNote(id: primaryID) == nil
        else { throw ActionError.primaryArchived }
    }

    private func finalizeLedger(
        _ action: KnowledgeActionBlock,
        capability: String?,
        status: String,
        noteIds: [String],
        errorCode: String? = nil
    ) async throws {
        if let capability {
            do {
                _ = try await APIClient.shared.commitKnowledgeAction(
                    id: action.id, capability: capability, actionDigest: action.actionDigest,
                    status: status, resultNoteIds: noteIds, errorCode: errorCode
                )
                return
            } catch {
                // The local transaction is already durable. A token may expire while
                // the app is syncing, so fall through to the JWT-owned ledger resume.
            }
        }
        _ = try await APIClient.shared.resumeKnowledgeActionSync(
            id: action.id, actionDigest: action.actionDigest,
            status: status, resultNoteIds: noteIds, errorCode: errorCode
        )
    }

    static func mergePrimaryNoteID(
        step: KnowledgeActionStep,
        actionId: String,
        stepIndex: Int
    ) -> String {
        if let target = step.targetNoteId?.trimmingCharacters(in: .whitespacesAndNewlines),
           !target.isEmpty {
            return target
        }
        if let stableSource = Set(step.sourceNoteIds).sorted().first {
            return stableSource
        }
        return stableNoteID(actionId: actionId, index: stepIndex)
    }

    static func mergeArchiveSourceIDs(
        step: KnowledgeActionStep,
        primaryID: String
    ) -> [String] {
        Array(Set(step.sourceNoteIds.filter { !$0.isEmpty && $0 != primaryID })).sorted()
    }

    private static func stableNoteID(actionId: String, index: Int) -> String {
        let digest = SHA256.hash(data: Data("\(actionId):\(index)".utf8)).map { String(format: "%02x", $0) }.joined()
        return "ka-\(digest.prefix(32))"
    }

    private func inferredTitle(_ markdown: String?) -> String {
        markdown?.split(separator: "\n").first.map { String($0).replacingOccurrences(of: #"^#{1,6}\s*"#, with: "", options: .regularExpression) } ?? "无标题"
    }

    private func markdownBody(_ markdown: String) -> String {
        var lines = markdown.components(separatedBy: .newlines)
        if lines.first?.trimmingCharacters(in: .whitespaces) == "---",
           let closing = lines.dropFirst().firstIndex(where: { $0.trimmingCharacters(in: .whitespaces) == "---" }) {
            lines.removeSubrange(0...closing)
        }
        return lines.joined(separator: "\n").trimmingCharacters(in: .newlines)
    }

    private func receiptURL(_ actionId: String) -> URL {
        store.actionDirectory.appendingPathComponent("\(actionId).json")
    }

    private func loadReceipt(_ actionId: String) -> KnowledgeActionReceipt? {
        guard let data = try? Data(contentsOf: receiptURL(actionId)) else { return nil }
        return try? JSONDecoder().decode(KnowledgeActionReceipt.self, from: data)
    }

    private func saveReceipt(_ receipt: KnowledgeActionReceipt) {
        try? fileManager.createDirectory(at: store.actionDirectory, withIntermediateDirectories: true)
        if let data = try? JSONEncoder().encode(receipt) {
            try? data.write(to: receiptURL(receipt.actionId), options: .atomic)
        }
    }

    private func updateReceipt(_ action: KnowledgeActionBlock, state: KnowledgeActionState, ids: [String]) {
        saveReceipt(.init(actionId: action.id, actionDigest: action.actionDigest, accountFingerprint: store.accountFingerprint, status: state, resultNoteIds: ids, updatedAt: Date()))
    }

    private func backupDirectory(_ actionId: String) -> URL {
        store.actionDirectory.appendingPathComponent("rollback-\(actionId)", isDirectory: true)
    }

    private func markdownFiles(at root: URL, excludingActions: Bool = false) -> [URL] {
        guard let enumerator = fileManager.enumerator(at: root, includingPropertiesForKeys: [.isRegularFileKey], options: []) else { return [] }
        return enumerator.compactMap { $0 as? URL }.filter {
            $0.pathExtension == "md" && (!excludingActions || !$0.path.contains("/.actions/"))
        }
    }

    private func prepareBackup(at backup: URL) throws {
        try? fileManager.removeItem(at: backup)
        try fileManager.createDirectory(at: backup, withIntermediateDirectories: true)
        for source in markdownFiles(at: store.vaultDirectory, excludingActions: true) {
            let relative = source.path.replacingOccurrences(of: store.vaultDirectory.path + "/", with: "")
            let destination = backup.appendingPathComponent(relative)
            try fileManager.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
            try fileManager.copyItem(at: source, to: destination)
        }
    }

    private func restoreBackup(from backup: URL) throws {
        for current in markdownFiles(at: store.vaultDirectory, excludingActions: true) { try fileManager.removeItem(at: current) }
        for source in markdownFiles(at: backup) {
            let relative = source.path.replacingOccurrences(of: backup.path + "/", with: "")
            let destination = store.vaultDirectory.appendingPathComponent(relative)
            try fileManager.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
            try fileManager.copyItem(at: source, to: destination)
        }
        try? fileManager.removeItem(at: backup)
    }

    private enum ActionError: LocalizedError {
        case targetMissing, targetChanged, writeFailed, unsupported, accountChanged
        case readBackFailed, archiveConflict, primaryArchived
        var errorDescription: String? {
            switch self {
            case .targetMissing: return "目标笔记不存在"
            case .targetChanged: return "来源笔记已变化，请重新生成合并方案"
            case .writeFailed: return "本地笔记写入失败"
            case .unsupported: return "暂不支持该知识操作"
            case .accountChanged: return "账号已切换，旧账号同步已取消"
            case .readBackFailed: return "服务端读回校验失败，可重试继续"
            case .archiveConflict: return "来源笔记已归档到其他主笔记"
            case .primaryArchived: return "主笔记不能被归档"
            }
        }
    }
}
