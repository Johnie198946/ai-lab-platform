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

public enum WikiLinkAnchor: Hashable, Sendable {
    case heading(String)
    case block(String)

    public var rawValue: String {
        switch self {
        case .heading(let value): return value
        case .block(let value): return "^\(value)"
        }
    }
}

public struct WikiLinkReference: Identifiable, Hashable, Sendable {
    public let target: String
    public let displayText: String?
    public let anchor: WikiLinkAnchor?
    public let isEmbed: Bool
    public let location: Int
    public let length: Int
    public let rawText: String

    public var id: String { "\(location):\(length):\(rawText)" }
    public var range: NSRange { NSRange(location: location, length: length) }
    public var visibleText: String {
        if let displayText, !displayText.isEmpty { return displayText }
        if !target.isEmpty { return target }
        return anchor?.rawValue ?? rawText
    }
}

public enum WikiLinkParser {
    public static func hasMalformedTripleBrackets(_ source: String) -> Bool {
        source.range(of: #"\[\[\[[^\n]*\]\]\]"#, options: .regularExpression) != nil
    }

    /// Parse Obsidian-style wikilinks while ignoring frontmatter, fenced/inline
    /// code and Obsidian comments. Malformed triple brackets are deliberately
    /// ignored so the editor can surface them as syntax errors instead.
    public static func parse(_ source: String) -> [WikiLinkReference] {
        let string = source as NSString
        let fullRange = NSRange(location: 0, length: string.length)
        var excluded: [NSRange] = excludedLineRanges(in: source)
        for pattern in [#"`+[^`\n]*`+"#, #"(?s)%%.*?%%"#] {
            guard let regex = try? NSRegularExpression(pattern: pattern) else { continue }
            excluded.append(contentsOf: regex.matches(in: source, range: fullRange).map(\.range))
        }

        guard let regex = try? NSRegularExpression(pattern: #"(!)?\[\[([^\]\r\n]+)\]\]"#) else {
            return []
        }
        return regex.matches(in: source, range: fullRange).compactMap { match in
            let matchRange = match.range
            guard !excluded.contains(where: { NSIntersectionRange($0, matchRange).length > 0 }) else { return nil }
            if matchRange.location > 0, string.substring(with: NSRange(location: matchRange.location - 1, length: 1)) == "[" {
                return nil
            }
            if NSMaxRange(matchRange) < string.length,
               string.substring(with: NSRange(location: NSMaxRange(matchRange), length: 1)) == "]" {
                return nil
            }
            guard match.numberOfRanges >= 3,
                  let innerRange = Range(match.range(at: 2), in: source) else { return nil }
            let inner = String(source[innerRange])
            let pipeParts = inner.split(separator: "|", maxSplits: 1, omittingEmptySubsequences: false)
            let destination = String(pipeParts[0]).trimmingCharacters(in: .whitespacesAndNewlines)
            let display = pipeParts.count == 2
                ? String(pipeParts[1]).trimmingCharacters(in: .whitespacesAndNewlines)
                : nil
            let hashParts = destination.split(separator: "#", maxSplits: 1, omittingEmptySubsequences: false)
            let target = String(hashParts[0]).trimmingCharacters(in: .whitespacesAndNewlines)
            let anchor: WikiLinkAnchor?
            if hashParts.count == 2 {
                let value = String(hashParts[1]).trimmingCharacters(in: .whitespacesAndNewlines)
                if value.hasPrefix("^") {
                    anchor = .block(String(value.dropFirst()))
                } else if !value.isEmpty {
                    anchor = .heading(value)
                } else {
                    anchor = nil
                }
            } else {
                anchor = nil
            }
            guard !target.isEmpty || anchor != nil else { return nil }
            return WikiLinkReference(
                target: target,
                displayText: display?.isEmpty == false ? display : nil,
                anchor: anchor,
                isEmbed: match.range(at: 1).location != NSNotFound,
                location: matchRange.location,
                length: matchRange.length,
                rawText: string.substring(with: matchRange)
            )
        }
    }

    private static func excludedLineRanges(in source: String) -> [NSRange] {
        let lines = source.components(separatedBy: "\n")
        var offset = 0
        var inFrontmatter = lines.first?.trimmingCharacters(in: .whitespacesAndNewlines) == "---"
        var frontmatterClosed = !inFrontmatter
        var fenceMarker: String?
        var ranges: [NSRange] = []

        for (index, line) in lines.enumerated() {
            let lineLength = (line as NSString).length + (index < lines.count - 1 ? 1 : 0)
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            var exclude = false
            if inFrontmatter {
                exclude = true
                if index > 0, trimmed == "---" {
                    inFrontmatter = false
                    frontmatterClosed = true
                }
            } else if frontmatterClosed {
                if let marker = fenceMarker {
                    exclude = true
                    if trimmed.hasPrefix(marker) { fenceMarker = nil }
                } else if trimmed.hasPrefix("```") {
                    fenceMarker = "```"
                    exclude = true
                } else if trimmed.hasPrefix("~~~") {
                    fenceMarker = "~~~"
                    exclude = true
                }
            }
            if exclude { ranges.append(NSRange(location: offset, length: lineLength)) }
            offset += lineLength
        }
        return ranges
    }
}

public struct WikiLinkBacklink: Identifiable, Hashable {
    public let sourceNote: KnowledgeNote
    public let reference: WikiLinkReference
    public let context: String

    public var id: String { "\(sourceNote.id):\(reference.id)" }
}

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
        for link in WikiLinkParser.parse(text).reversed() {
            text = (text as NSString).replacingCharacters(in: link.range, with: link.isEmbed ? "附件" : link.visibleText)
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
    @Published public private(set) var archivedNotes: [KnowledgeNote] = []
    @Published public private(set) var isLoading = false
    @Published public private(set) var lastError: String?
    @Published public private(set) var pendingSyncNoteIDs: Set<String> = []

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

    public var allTags: [String] {
        Array(Set(notes.flatMap(\.tags))).sorted { $0.localizedStandardCompare($1) == .orderedAscending }
    }

    public var archiveDirectory: URL {
        vaultDirectory.appendingPathComponent(".archive", isDirectory: true)
    }

    private init() {}

    public func activate(tenantKey: String, userId: String) {
        let tenant = Self.namespace(tenantKey)
        let user = Self.namespace(userId)
        guard tenant != tenantNamespace || user != userNamespace else { return }
        notes.removeAll()
        archivedNotes.removeAll()
        pendingSyncNoteIDs.removeAll()
        tenantNamespace = tenant
        userNamespace = user
        accountFingerprint = "\(tenant):\(user)"
        reload()
    }

    public func deactivate() {
        notes.removeAll()
        archivedNotes.removeAll()
        pendingSyncNoteIDs.removeAll()
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
            pendingSyncNoteIDs.insert(note.id)
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
            pendingSyncNoteIDs.insert(note.id)
            if oldTitle != note.title {
                pendingSyncNoteIDs.formUnion(
                    try updateIncomingLinks(from: oldTitle, to: note.title, excluding: note.id)
                )
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

    public func note(matchingLink link: String) -> KnowledgeNote? {
        var target = link.trimmingCharacters(in: .whitespacesAndNewlines)
        if target.lowercased().hasSuffix(".md") { target = String(target.dropLast(3)) }
        return notes.first { note in
            note.title.caseInsensitiveCompare(target) == .orderedSame
                || note.fileURL.deletingPathExtension().lastPathComponent.caseInsensitiveCompare(target) == .orderedSame
                || note.aliases.contains(where: { $0.caseInsensitiveCompare(target) == .orderedSame })
        }
    }

    public func backlinks(to note: KnowledgeNote) -> [KnowledgeNote] {
        Array(Set(backlinkReferences(to: note).map(\.sourceNote))).sorted {
            $0.updatedAt > $1.updatedAt
        }
    }

    public func backlinkReferences(to note: KnowledgeNote) -> [WikiLinkBacklink] {
        notes.flatMap { candidate -> [WikiLinkBacklink] in
            guard candidate.id != note.id else { return [] }
            return WikiLinkParser.parse(candidate.body).compactMap { reference in
                guard reference.target.caseInsensitiveCompare(note.title) == .orderedSame
                        || note.aliases.contains(where: { $0.caseInsensitiveCompare(reference.target) == .orderedSame })
                else { return nil }
                return WikiLinkBacklink(
                    sourceNote: candidate,
                    reference: reference,
                    context: linkContext(in: candidate.body, around: reference.range)
                )
            }
        }.sorted { $0.sourceNote.updatedAt > $1.sourceNote.updatedAt }
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

    public func wikiLinkSuggestions(_ query: String, excluding noteID: String? = nil, limit: Int = 8) -> [KnowledgeNote] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        return notes
            .filter { $0.id != noteID }
            .filter { note in
                trimmed.isEmpty
                    || note.title.localizedCaseInsensitiveContains(trimmed)
                    || note.aliases.contains(where: { $0.localizedCaseInsensitiveContains(trimmed) })
            }
            .sorted { lhs, rhs in
                let lhsExact = lhs.title.caseInsensitiveCompare(trimmed) == .orderedSame
                let rhsExact = rhs.title.caseInsensitiveCompare(trimmed) == .orderedSame
                if lhsExact != rhsExact { return lhsExact }
                return lhs.updatedAt > rhs.updatedAt
            }
            .prefix(max(1, limit))
            .map { $0 }
    }

    public func pendingSyncNotes() -> [KnowledgeNote] {
        notes.filter { pendingSyncNoteIDs.contains($0.id) }
    }

    public func markSynced(noteID: String) {
        pendingSyncNoteIDs.remove(noteID)
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

    private func updateIncomingLinks(from oldTitle: String, to newTitle: String, excluding id: String) throws -> [String] {
        guard !oldTitle.isEmpty, oldTitle != newTitle else { return [] }
        var updatedIDs: [String] = []
        for index in notes.indices where notes[index].id != id {
            var replaced = notes[index].body
            let matches = WikiLinkParser.parse(replaced).filter {
                $0.target.caseInsensitiveCompare(oldTitle) == .orderedSame
            }
            for link in matches.reversed() {
                var destination = newTitle
                if let anchor = link.anchor { destination += "#\(anchor.rawValue)" }
                if let displayText = link.displayText { destination += "|\(displayText)" }
                let replacement = "\(link.isEmbed ? "!" : "")[[\(destination)]]"
                replaced = (replaced as NSString).replacingCharacters(in: link.range, with: replacement)
            }
            let body = notes[index].body
            guard replaced != body else { continue }
            notes[index].body = replaced
            notes[index].outgoingLinks = extractWikiLinks(from: replaced)
            notes[index].updatedAt = Date()
            try write(notes[index])
            updatedIDs.append(notes[index].id)
        }
        return updatedIDs
    }

    private func extractWikiLinks(from text: String) -> [String] {
        normalized(WikiLinkParser.parse(text).map(\.target).filter { !$0.isEmpty })
    }

    private func linkContext(in text: String, around range: NSRange) -> String {
        let source = text as NSString
        let start = max(0, range.location - 70)
        let end = min(source.length, NSMaxRange(range) + 70)
        return source.substring(with: NSRange(location: start, length: end - start))
            .replacingOccurrences(of: "\n", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
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
