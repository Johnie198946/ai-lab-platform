//
//  MarkdownBlockParser.swift
//  AIPlatformApp
//
//  纯 Swift 原生 Markdown 分块解析器（零第三方依赖）。
//  将助手正文解析为卡片化块：heading / callout / paragraph / bulletList /
//  numberedList / codeBlock / quote / divider。
//
//  核心契约（对齐 Supervision 批复）：
//  - Fenced 状态机：``` 开闭代码块，块内完全豁免行内与块级解析；
//  - 行内 Code Span 优先：反引号 `code` 内不解析 ** 粗体与特殊符号；
//  - 语义 Callout 识别：行首 【一句话结论/核心发现/关键结论/建议/注意/风险/核心结论】；
//  - 优雅间距：--- 分隔线解析为 DividerCard，彻底告别字符堆砌；
//  - NSCache 缓存：Key = messageId + "_" + contentHash，countLimit = 100。
//

import Foundation

// MARK: - Markdown 块类型（8 类）

public enum MarkdownBlock: Identifiable, Hashable {
    case heading(level: Int, text: String)
    case callout(label: String, text: String)
    case paragraph(String)
    case bulletList([String])
    case numberedList([String])
    case codeBlock(language: String?, code: String)
    case quote(String)
    case divider

    public var id: String {
        switch self {
        case .heading(let level, let text): return "h\(level)_\(text.hashValue)"
        case .callout(let label, let text): return "c_\(label)_\(text.hashValue)"
        case .paragraph(let text): return "p_\(text.hashValue)"
        case .bulletList(let items): return "ul_\(items.hashValue)"
        case .numberedList(let items): return "ol_\(items.hashValue)"
        case .codeBlock(let lang, let code): return "code_\(lang ?? "")_\(code.hashValue)"
        case .quote(let text): return "q_\(text.hashValue)"
        case .divider: return "divider"
        }
    }
}

// MARK: - 行内段（Code Span 优先后的富文本段）

public enum InlineSegment: Hashable {
    case text(String)
    case code(String)
    case bold(String)
    case italic(String)
}

// MARK: - 解析器

public final class MarkdownBlockParser {

    public static let shared = MarkdownBlockParser()

    /// NSCache 内存缓存：已解析的 [MarkdownBlock] 装箱（Swift enum 无法直接桥接 NSArray）。
    private final class BlocksBox: NSObject {
        let blocks: [MarkdownBlock]
        init(_ blocks: [MarkdownBlock]) { self.blocks = blocks }
    }

    private let cache = NSCache<NSString, BlocksBox>()

    public init() {
        // 长列表滚动 60fps + 无内存膨胀风险
        cache.countLimit = 100
    }

    /// 解析入口（带缓存）：Key = messageId + "_" + contentHash。
    public func parse(_ content: String, messageId: String = "") -> [MarkdownBlock] {
        guard !content.isEmpty else { return [] }
        let key = "\(messageId)_\(content.hashValue)" as NSString
        if let box = cache.object(forKey: key) {
            return box.blocks
        }
        let blocks = parseUncached(content)
        cache.setObject(BlocksBox(blocks), forKey: key)
        return blocks
    }

    // MARK: - 块级解析（Fenced 状态机）

    private func parseUncached(_ content: String) -> [MarkdownBlock] {
        let lines = content.components(separatedBy: "\n")
        var blocks: [MarkdownBlock] = []
        var index = 0

        var inCodeBlock = false
        var codeLanguage: String?
        var codeLines: [String] = []

        var paragraphBuffer: [String] = []
        var bulletBuffer: [String] = []
        var numberedBuffer: [String] = []

        func flushParagraph() {
            guard !paragraphBuffer.isEmpty else { return }
            blocks.append(.paragraph(paragraphBuffer.joined(separator: "\n")))
            paragraphBuffer.removeAll()
        }
        func flushBullet() {
            guard !bulletBuffer.isEmpty else { return }
            blocks.append(.bulletList(bulletBuffer))
            bulletBuffer.removeAll()
        }
        func flushNumbered() {
            guard !numberedBuffer.isEmpty else { return }
            blocks.append(.numberedList(numberedBuffer))
            numberedBuffer.removeAll()
        }
        func flushAll() {
            flushParagraph(); flushBullet(); flushNumbered()
        }

        while index < lines.count {
            let line = lines[index]
            let trimmed = line.trimmingCharacters(in: .whitespaces)

            // 1) 代码块内：完全豁免，原样收集，``` 闭合
            if inCodeBlock {
                if trimmed.hasPrefix("```") {
                    blocks.append(.codeBlock(language: codeLanguage, code: codeLines.joined(separator: "\n")))
                    codeLines.removeAll()
                    codeLanguage = nil
                    inCodeBlock = false
                } else {
                    codeLines.append(line)
                }
                index += 1
                continue
            }

            // 2) 打开代码块 ```lang
            if trimmed.hasPrefix("```") {
                flushAll()
                codeLanguage = Self.extractCodeLanguage(trimmed)
                codeLines = []
                inCodeBlock = true
                index += 1
                continue
            }

            // 3) 分隔线 --- / *** / ___
            if Self.isDivider(trimmed) {
                flushAll()
                blocks.append(.divider)
                index += 1
                continue
            }

            // 4) 标题 # ~ ######
            if let heading = Self.parseHeading(trimmed) {
                flushAll()
                blocks.append(heading)
                index += 1
                continue
            }

            // 5) 语义 Callout 【结论】…（提升为高亮结论卡）
            if let callout = Self.parseCallout(trimmed) {
                flushAll()
                blocks.append(callout)
                index += 1
                continue
            }

            // 6) 引用 >
            if trimmed.hasPrefix(">") {
                flushAll()
                let quoteText = String(trimmed.dropFirst()).trimmingCharacters(in: .whitespaces)
                blocks.append(.quote(quoteText))
                index += 1
                continue
            }

            // 7) 无序列表 - / * / +
            if let item = Self.parseBulletItem(trimmed) {
                flushParagraph(); flushNumbered()
                bulletBuffer.append(item)
                index += 1
                continue
            }

            // 8) 有序列表 1. / 2) 等
            if let item = Self.parseNumberedItem(trimmed) {
                flushParagraph(); flushBullet()
                numberedBuffer.append(item)
                index += 1
                continue
            }

            // 9) 空行 → 冲刷缓冲
            if trimmed.isEmpty {
                flushAll()
                index += 1
                continue
            }

            // 10) 普通段落行
            flushBullet(); flushNumbered()
            paragraphBuffer.append(line)
            index += 1
        }

        // 收尾：未闭合代码块也按块落盘（诚实渲染）
        if inCodeBlock {
            blocks.append(.codeBlock(language: codeLanguage, code: codeLines.joined(separator: "\n")))
        }
        flushAll()

        return blocks
    }

    // MARK: - 行内解析（Code Span 优先）

    /// 行内富文本分段：反引号 `code` 优先保护，非代码段再解析 **bold** 与 *italic*。
    public static func parseInline(_ text: String) -> [InlineSegment] {
        var segments: [InlineSegment] = []
        var remaining = Substring(text)

        while let openRange = remaining.range(of: "`") {
            let before = remaining[..<openRange.lowerBound]
            let afterOpen = remaining[openRange.upperBound...]
            if let closeRange = afterOpen.range(of: "`") {
                let code = afterOpen[..<closeRange.lowerBound]
                segments.append(contentsOf: parseEmphasis(String(before)))
                if !code.isEmpty { segments.append(.code(String(code))) }
                remaining = afterOpen[closeRange.upperBound...]
            } else {
                // 无闭合反引号 → 整段按普通文本处理（不误吞）
                segments.append(contentsOf: parseEmphasis(String(before) + "`" + String(afterOpen)))
                remaining = ""
            }
        }

        if !remaining.isEmpty {
            segments.append(contentsOf: parseEmphasis(String(remaining)))
        }
        return segments
    }

    /// 解析 **bold** 与 *italic*（不触碰已被 Code Span 剥离的代码段）。
    private static func parseEmphasis(_ text: String) -> [InlineSegment] {
        var segments: [InlineSegment] = []
        var remaining = Substring(text)

        while let openRange = remaining.range(of: "**") {
            let before = remaining[..<openRange.lowerBound]
            let afterOpen = remaining[openRange.upperBound...]
            if let closeRange = afterOpen.range(of: "**") {
                let bold = afterOpen[..<closeRange.lowerBound]
                segments.append(contentsOf: parseItalic(String(before)))
                if !bold.isEmpty { segments.append(.bold(String(bold))) }
                remaining = afterOpen[closeRange.upperBound...]
            } else {
                segments.append(contentsOf: parseItalic(String(before) + "**" + String(afterOpen)))
                remaining = ""
            }
        }

        if !remaining.isEmpty {
            segments.append(contentsOf: parseItalic(String(remaining)))
        }
        return segments
    }

    /// 解析 *italic*（单星号）。
    private static func parseItalic(_ text: String) -> [InlineSegment] {
        var segments: [InlineSegment] = []
        var remaining = Substring(text)

        while let openRange = remaining.range(of: "*") {
            let before = remaining[..<openRange.lowerBound]
            let afterOpen = remaining[openRange.upperBound...]
            if let closeRange = afterOpen.range(of: "*") {
                let italic = afterOpen[..<closeRange.lowerBound]
                appendText(&segments, String(before))
                if !italic.isEmpty { segments.append(.italic(String(italic))) }
                remaining = afterOpen[closeRange.upperBound...]
            } else {
                appendText(&segments, String(before) + "*" + String(afterOpen))
                remaining = ""
            }
        }

        if !remaining.isEmpty {
            appendText(&segments, String(remaining))
        }
        return segments
    }

    private static func appendText(_ segments: inout [InlineSegment], _ text: String) {
        guard !text.isEmpty else { return }
        segments.append(.text(text))
    }

    // MARK: - 块级辅助识别

    private static func isDivider(_ trimmed: String) -> Bool {
        guard trimmed.count >= 3 else { return false }
        let chars = Set(trimmed)
        guard chars.count == 1, let c = chars.first, c == "-" || c == "*" || c == "_" else {
            return false
        }
        return true
    }

    private static func parseHeading(_ trimmed: String) -> MarkdownBlock? {
        // 匹配 "# " 至 "###### "
        let parts = trimmed.split(separator: " ", maxSplits: 1, omittingEmptySubsequences: false)
        guard parts.count == 2, let hashes = parts.first else { return nil }
        let hashCount = hashes.count
        guard hashCount >= 1 && hashCount <= 6, hashes.allSatisfy({ $0 == "#" }) else { return nil }
        let text = String(parts[1]).trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return nil }
        return .heading(level: hashCount, text: text)
    }

    /// 语义 Callout：行首匹配 【(一句话结论|核心发现|关键结论|建议|注意|风险|核心结论)】。
    private static let calloutRegex: NSRegularExpression = {
        // swiftlint:disable:next force_try
        try! NSRegularExpression(
            pattern: "^【(一句话结论|核心发现|关键结论|建议|注意|风险|核心结论)】(.*)$"
        )
    }()

    private static func parseCallout(_ trimmed: String) -> MarkdownBlock? {
        let range = NSRange(trimmed.startIndex..., in: trimmed)
        guard let match = calloutRegex.firstMatch(in: trimmed, options: [], range: range),
              match.numberOfRanges >= 3 else { return nil }
        let label = (trimmed as NSString).substring(with: match.range(at: 1))
        let text = (trimmed as NSString).substring(with: match.range(at: 2))
            .trimmingCharacters(in: .whitespaces)
        return .callout(label: label, text: text)
    }

    private static func parseBulletItem(_ trimmed: String) -> String? {
        guard trimmed.count >= 2 else { return nil }
        let first = trimmed.first
        guard first == "-" || first == "*" || first == "+" else { return nil }
        let after = trimmed.dropFirst()
        guard after.first == " " || after.first == "\t" else { return nil }
        let text = after.dropFirst().trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return nil }
        return text
    }

    private static func parseNumberedItem(_ trimmed: String) -> String? {
        // 形如 "1." "2)" "3、" 开头
        guard let firstNonDigit = trimmed.firstIndex(where: { !$0.isNumber }) else { return nil }
        let prefix = trimmed[..<firstNonDigit]
        guard !prefix.isEmpty, prefix.allSatisfy({ $0.isNumber }) else { return nil }
        let separator = trimmed[firstNonDigit]
        guard separator == "." || separator == ")" || separator == "、" else { return nil }
        let after = trimmed[trimmed.index(after: firstNonDigit)...]
        let text = after.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return nil }
        return text
    }

    private static func extractCodeLanguage(_ trimmed: String) -> String? {
        let lang = trimmed.dropFirst(3).trimmingCharacters(in: .whitespaces)
        return lang.isEmpty ? nil : lang
    }
}
