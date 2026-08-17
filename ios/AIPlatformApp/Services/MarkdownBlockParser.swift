//
//  MarkdownBlockParser.swift
//  AIPlatformApp
//
//  纯 Swift 原生 Markdown 分块解析器（零第三方依赖）。
//  将助手正文解析为卡片化块：heading / callout / paragraph / bulletList /
//  numberedList / codeBlock / quote / divider / table / chart / sourceCitations。
//
//  核心排版规则（2026-08-17 视觉增强）：
//  1. 结构化标题提升：支持 # ~ ### 及中文序号标题（一、二、三、）提升为 Section Heading；
//  2. 知识库溯源条目提升：识别「来源条目 / 知识库来源」并将路径列表提升为 SourceCitations 专属卡片；
//  3. 重点高亮提取：Code Span 优先，加粗重点强化视觉对比；
//  4. Fenced 状态机：代码块、表格、图表独立卡片化。
//

import Foundation

// MARK: - Markdown 块类型（11 类）

public enum MarkdownBlock: Identifiable, Hashable {
    case heading(level: Int, text: String)
    case callout(label: String, text: String)
    case paragraph(String)
    case bulletList([String])
    case numberedList([String])
    case codeBlock(language: String?, code: String)
    case quote(String)
    case divider
    case table(TableBlock)
    case chart(ChartBlock)
    case sourceCitations([String])

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
        case .table(let t): return "tbl_\(t.id)"
        case .chart(let c): return "chr_\(c.id)"
        case .sourceCitations(let items): return "src_\(items.hashValue)"
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

    private final class BlocksBox: NSObject {
        let blocks: [MarkdownBlock]
        init(_ blocks: [MarkdownBlock]) { self.blocks = blocks }
    }

    private let cache = NSCache<NSString, BlocksBox>()

    public init() {
        cache.countLimit = 100
    }

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
                    let code = codeLines.joined(separator: "\n")
                    if let chartBlock = Self.tryParseChartBlock(language: codeLanguage, code: code) {
                        blocks.append(.chart(chartBlock))
                    } else {
                        blocks.append(.codeBlock(language: codeLanguage, code: code))
                    }
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

            // 3) 表格解析：以 | 开头且下一行为分隔行 |---|
            if let (tableBlock, nextIdx) = Self.tryParseMarkdownTable(lines: lines, startIndex: index) {
                flushAll()
                blocks.append(.table(tableBlock))
                index = nextIdx
                continue
            }

            // 4) 来源引用条目识别（「来源条目：」/「知识库来源：」及后随路径列表）
            if Self.isSourceCitationHeader(trimmed) {
                flushAll()
                var citations: [String] = []
                var next = index + 1
                while next < lines.count {
                    let nextTrimmed = lines[next].trimmingCharacters(in: .whitespaces)
                    if nextTrimmed.isEmpty {
                        next += 1
                        continue
                    }
                    if let item = Self.parseBulletItem(nextTrimmed) {
                        citations.append(item)
                        next += 1
                    } else if Self.looksLikePath(nextTrimmed) {
                        citations.append(nextTrimmed)
                        next += 1
                    } else {
                        break
                    }
                }
                if !citations.isEmpty {
                    blocks.append(.sourceCitations(citations))
                    index = next
                    continue
                }
            }

            // 5) 分隔线 --- / *** / ___
            if Self.isDivider(trimmed) {
                flushAll()
                blocks.append(.divider)
                index += 1
                continue
            }

            // 6) 标题 # ~ ######
            if let heading = Self.parseHeading(trimmed) {
                flushAll()
                blocks.append(heading)
                index += 1
                continue
            }

            // 7) 中文序号大标题（如「一、核心定位」「三、知识库里的最新动态」）
            if let cnHeading = Self.parseChineseNumeralHeading(trimmed) {
                flushAll()
                blocks.append(cnHeading)
                index += 1
                continue
            }

            // 8) 语义 Callout 【结论】…（提升为高亮结论卡）
            if let callout = Self.parseCallout(trimmed) {
                flushAll()
                blocks.append(callout)
                index += 1
                continue
            }

            // 9) 引用 >
            if trimmed.hasPrefix(">") {
                flushAll()
                let quoteText = String(trimmed.dropFirst()).trimmingCharacters(in: .whitespaces)
                blocks.append(.quote(quoteText))
                index += 1
                continue
            }

            // 10) 无序列表 - / * / +
            if let item = Self.parseBulletItem(trimmed) {
                flushParagraph(); flushNumbered()
                bulletBuffer.append(item)
                index += 1
                continue
            }

            // 11) 有序列表 1. / 2) 等
            if let item = Self.parseNumberedItem(trimmed) {
                flushParagraph(); flushBullet()
                numberedBuffer.append(item)
                index += 1
                continue
            }

            // 12) 空行 → 冲刷缓冲
            if trimmed.isEmpty {
                flushAll()
                index += 1
                continue
            }

            // 13) 普通段落行
            flushBullet(); flushNumbered()
            paragraphBuffer.append(line)
            index += 1
        }

        if inCodeBlock {
            let code = codeLines.joined(separator: "\n")
            blocks.append(.codeBlock(language: codeLanguage, code: code))
        }
        flushAll()

        return blocks
    }

    // MARK: - 来源引用检测

    private static func isSourceCitationHeader(_ line: String) -> Bool {
        let clean = line.trimmingCharacters(in: CharacterSet(charactersIn: "*_` "))
        let headers = [
            "来源条目：", "来源条目:", "知识库来源：", "知识库来源:",
            "参考条目：", "参考条目:", "引用条目：", "引用条目:",
            "相关条目：", "相关条目:", "来源：", "来源:",
            "Sources:", "References:", "数据源："
        ]
        return headers.contains(where: { clean == $0 || clean.hasPrefix($0) })
    }

    private static func looksLikePath(_ text: String) -> Bool {
        let clean = text.trimmingCharacters(in: CharacterSet(charactersIn: "`*- "))
        return clean.hasPrefix("wiki/") || clean.hasPrefix("knowledge/") || clean.hasPrefix("raw/") || clean.hasPrefix("data/")
    }

    // MARK: - 中文序号标题检测（一、二、三、）

    private static func parseChineseNumeralHeading(_ line: String) -> MarkdownBlock? {
        let clean = line.trimmingCharacters(in: CharacterSet(charactersIn: "#* "))
        let prefixes = ["一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、", "九、", "十、", "十一、", "十二、"]
        for p in prefixes {
            if clean.hasPrefix(p) {
                return .heading(level: 2, text: clean)
            }
        }
        return nil
    }

    // MARK: - 表格与图表解析支持

    private static func tryParseMarkdownTable(lines: [String], startIndex: Int) -> (TableBlock, Int)? {
        guard startIndex + 1 < lines.count else { return nil }
        let headerLine = lines[startIndex].trimmingCharacters(in: .whitespaces)
        let separatorLine = lines[startIndex + 1].trimmingCharacters(in: .whitespaces)

        guard headerLine.hasPrefix("|") && headerLine.hasSuffix("|") else { return nil }
        guard separatorLine.hasPrefix("|") && separatorLine.hasSuffix("|") && separatorLine.contains("-") else { return nil }

        let headers = splitTableRow(headerLine)
        guard headers.count >= 2 else { return nil }

        var rows: [[String]] = []
        var curr = startIndex + 2
        while curr < lines.count {
            let rowLine = lines[curr].trimmingCharacters(in: .whitespaces)
            guard rowLine.hasPrefix("|") && rowLine.hasSuffix("|") else { break }
            let cells = splitTableRow(rowLine)
            guard cells.count == headers.count else { break }
            rows.append(cells)
            curr += 1
        }

        guard !rows.isEmpty else { return nil }
        return (TableBlock(title: "数据统计表格", headers: headers, rows: rows), curr)
    }

    private static func splitTableRow(_ line: String) -> [String] {
        let trimmed = line.trimmingCharacters(in: CharacterSet(charactersIn: "|"))
        return trimmed.components(separatedBy: "|").map { $0.trimmingCharacters(in: .whitespaces) }
    }

    private static func tryParseChartBlock(language: String?, code: String) -> ChartBlock? {
        guard let lang = language?.lowercased(), (lang == "chart" || lang == "json-chart" || lang == "chart-json") else {
            return nil
        }
        guard let data = code.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }

        let title = json["title"] as? String ?? "数据趋势图"
        let summary = json["summary"] as? String ?? ""
        let typeStr = (json["type"] as? String ?? "line").lowercased()
        let chartType: ChartType = (typeStr == "bar") ? .bar : .line

        var points: [ChartPoint] = []
        if let rawPoints = json["points"] as? [[String: Any]] {
            for p in rawPoints {
                let label = p["label"] as? String ?? ""
                let val = (p["value"] as? Double) ?? Double(p["value"] as? Int ?? 0)
                points.append(ChartPoint(label: label, value: val))
            }
        }
        guard !points.isEmpty else { return nil }

        let series = [ChartSeries(name: "默认序列", points: points)]
        return ChartBlock(title: title, chartType: chartType, series: series, summary: summary)
    }

    // MARK: - 行内解析（Code Span 优先 + 粗体提亮）

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
                segments.append(contentsOf: parseEmphasis(String(before) + "`" + String(afterOpen)))
                remaining = ""
            }
        }

        if !remaining.isEmpty {
            segments.append(contentsOf: parseEmphasis(String(remaining)))
        }
        return segments
    }

    private static func parseEmphasis(_ text: String) -> [InlineSegment] {
        var segments: [InlineSegment] = []
        var remaining = Substring(text)

        while let openRange = remaining.range(of: "**") {
            let before = remaining[..<openRange.lowerBound]
            let afterOpen = remaining[openRange.upperBound...]
            if let closeRange = afterOpen.range(of: "**") {
                let boldText = afterOpen[..<closeRange.lowerBound]
                segments.append(contentsOf: parseItalic(String(before)))
                if !boldText.isEmpty { segments.append(.bold(String(boldText))) }
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

    private static func parseItalic(_ text: String) -> [InlineSegment] {
        var segments: [InlineSegment] = []
        var remaining = Substring(text)

        while let openRange = remaining.range(of: "*") {
            let before = remaining[..<openRange.lowerBound]
            let afterOpen = remaining[openRange.upperBound...]
            if let closeRange = afterOpen.range(of: "*") {
                let italicText = afterOpen[..<closeRange.lowerBound]
                if !before.isEmpty { segments.append(.text(String(before))) }
                if !italicText.isEmpty { segments.append(.italic(String(italicText))) }
                remaining = afterOpen[closeRange.upperBound...]
            } else {
                segments.append(.text(String(before) + "*" + String(afterOpen)))
                remaining = ""
            }
        }

        if !remaining.isEmpty {
            segments.append(contentsOf: parseItalic(String(remaining)))
        }
        return segments
    }

    // MARK: - 模式匹配辅助

    private static func extractCodeLanguage(_ line: String) -> String? {
        let afterTicks = line.drop(while: { $0 == "`" }).trimmingCharacters(in: .whitespaces)
        return afterTicks.isEmpty ? nil : afterTicks
    }

    private static func isDivider(_ line: String) -> Bool {
        guard line.count >= 3 else { return false }
        let set = CharacterSet(charactersIn: "-*_ ")
        return line.unicodeScalars.allSatisfy { set.contains($0) }
            && (line.contains("---") || line.contains("***") || line.contains("___"))
    }

    private static func parseHeading(_ line: String) -> MarkdownBlock? {
        var level = 0
        for ch in line {
            if ch == "#" { level += 1 } else { break }
        }
        guard level >= 1 && level <= 6 else { return nil }
        let after = line.dropFirst(level)
        guard after.hasPrefix(" ") || after.isEmpty else { return nil }
        let text = after.trimmingCharacters(in: .whitespaces)
        return .heading(level: level, text: text)
    }

    private static func parseCallout(_ line: String) -> MarkdownBlock? {
        guard line.hasPrefix("【") else { return nil }
        guard let closeIdx = line.firstIndex(of: "】") else { return nil }
        let label = String(line[line.index(after: line.startIndex)..<closeIdx])
        let text = String(line[line.index(after: closeIdx)...]).trimmingCharacters(in: .whitespaces)
        let validLabels = ["一句话结论", "核心发现", "关键结论", "建议", "注意", "风险", "核心结论", "总结", "结论", "战略判断"]
        guard validLabels.contains(label) || label.hasSuffix("结论") || label.hasSuffix("建议") || label.hasSuffix("判断") else {
            return nil
        }
        return .callout(label: label, text: text)
    }

    private static func parseBulletItem(_ line: String) -> String? {
        if line.hasPrefix("- ") || line.hasPrefix("* ") || line.hasPrefix("+ ") {
            return String(line.dropFirst(2)).trimmingCharacters(in: .whitespaces)
        }
        return nil
    }

    private static func parseNumberedItem(_ line: String) -> String? {
        var digits = ""
        var idx = line.startIndex
        while idx < line.endIndex && line[idx].isNumber {
            digits.append(line[idx])
            idx = line.index(after: idx)
        }
        guard !digits.isEmpty && idx < line.endIndex else { return nil }
        if line[idx] == "." || line[idx] == ")" || line[idx] == "、" {
            let after = line[line.index(after: idx)...]
            guard after.hasPrefix(" ") || after.isEmpty else { return nil }
            return "\(digits). \(after.trimmingCharacters(in: .whitespaces))"
        }
        return nil
    }
}
