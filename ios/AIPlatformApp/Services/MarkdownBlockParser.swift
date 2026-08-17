//
//  MarkdownBlockParser.swift
//  AIPlatformApp
//
//  极简单遍 Markdown 分块解析器（零冗余计算·极速纯原生）。
//  按行切分：heading / callout / paragraph / bulletList / numberedList /
//  codeBlock / quote / divider / table / chart / sourceCitations。
//  行内样式（粗体/斜体/代码）交由 SwiftUI 原生 LocalizedStringKey 零开销渲染。
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

// MARK: - 单遍解析器（~100 行极简状态机）

public final class MarkdownBlockParser {

    public static let shared = MarkdownBlockParser()

    public func parse(_ content: String, messageId: String = "") -> [MarkdownBlock] {
        guard !content.isEmpty else { return [] }
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

            // 1. 代码块开闭
            if inCodeBlock {
                if trimmed.hasPrefix("```") {
                    let code = codeLines.joined(separator: "\n")
                    if let chart = Self.tryChart(codeLanguage, code) {
                        blocks.append(.chart(chart))
                    } else {
                        blocks.append(.codeBlock(language: codeLanguage, code: code))
                    }
                    codeLines.removeAll(); codeLanguage = nil; inCodeBlock = false
                } else {
                    codeLines.append(line)
                }
                index += 1
                continue
            }
            if trimmed.hasPrefix("```") {
                flushAll()
                codeLanguage = trimmed.drop(while: { $0 == "`" }).trimmingCharacters(in: .whitespaces)
                if codeLanguage?.isEmpty == true { codeLanguage = nil }
                codeLines = []
                inCodeBlock = true
                index += 1
                continue
            }

            // 2. 表格
            if let (table, nextIdx) = Self.tryTable(lines: lines, start: index) {
                flushAll()
                blocks.append(.table(table))
                index = nextIdx
                continue
            }

            // 3. 来源条目
            if Self.isSourceHeader(trimmed) {
                flushAll()
                var citations: [String] = []
                var next = index + 1
                while next < lines.count {
                    let nTrim = lines[next].trimmingCharacters(in: .whitespaces)
                    if nTrim.isEmpty { next += 1; continue }
                    if let item = Self.parseBullet(nTrim) {
                        citations.append(item); next += 1
                    } else if nTrim.hasPrefix("wiki/") || nTrim.hasPrefix("knowledge/") || nTrim.hasPrefix("raw/") || nTrim.hasPrefix("`") {
                        citations.append(nTrim); next += 1
                    } else { break }
                }
                if !citations.isEmpty {
                    blocks.append(.sourceCitations(citations))
                    index = next
                    continue
                }
            }

            // 4. 分隔线
            if trimmed == "---" || trimmed == "***" || trimmed == "___" {
                flushAll(); blocks.append(.divider); index += 1; continue
            }

            // 5. 标题（# ~ ### 或 中文序号 一、二、三、）
            if let heading = Self.parseHeading(trimmed) {
                flushAll(); blocks.append(heading); index += 1; continue
            }

            // 6. Callout 【结论/战略判断】
            if let callout = Self.parseCallout(trimmed) {
                flushAll(); blocks.append(callout); index += 1; continue
            }

            // 7. 引用 >
            if trimmed.hasPrefix(">") {
                flushAll()
                blocks.append(.quote(String(trimmed.dropFirst()).trimmingCharacters(in: .whitespaces)))
                index += 1
                continue
            }

            // 8. 无序列表 - / *
            if let item = Self.parseBullet(trimmed) {
                flushParagraph(); flushNumbered()
                bulletBuffer.append(item)
                index += 1
                continue
            }

            // 9. 有序列表 1.
            if let item = Self.parseNumbered(trimmed) {
                flushParagraph(); flushBullet()
                numberedBuffer.append(item)
                index += 1
                continue
            }

            // 10. 空行
            if trimmed.isEmpty {
                flushAll(); index += 1; continue
            }

            // 11. 普通段落
            flushBullet(); flushNumbered()
            paragraphBuffer.append(line)
            index += 1
        }

        if inCodeBlock {
            blocks.append(.codeBlock(language: codeLanguage, code: codeLines.joined(separator: "\n")))
        }
        flushAll()
        return blocks
    }

    // MARK: - 模式匹配辅助（纯静态·零内存开销）

    private static func isSourceHeader(_ s: String) -> Bool {
        let clean = s.trimmingCharacters(in: CharacterSet(charactersIn: "*_` "))
        return clean.hasPrefix("来源条目") || clean.hasPrefix("知识库来源") || clean.hasPrefix("参考条目") ||
               clean.hasPrefix("引用条目") || clean.hasPrefix("相关条目") || clean.hasPrefix("来源：") ||
               clean.hasPrefix("Sources:") || clean.hasPrefix("References:")
    }

    private static func parseHeading(_ s: String) -> MarkdownBlock? {
        if s.hasPrefix("#") {
            let level = s.prefix(while: { $0 == "#" }).count
            let text = s.dropFirst(level).trimmingCharacters(in: .whitespaces)
            return .heading(level: min(max(level, 1), 6), text: text)
        }
        let cnPrefixes = ["一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、", "九、", "十、"]
        if cnPrefixes.contains(where: { s.hasPrefix($0) }) {
            return .heading(level: 2, text: s)
        }
        return nil
    }

    private static func parseCallout(_ s: String) -> MarkdownBlock? {
        guard s.hasPrefix("【"), let close = s.firstIndex(of: "】") else { return nil }
        let label = String(s[s.index(after: s.startIndex)..<close])
        let text = String(s[s.index(after: close)...]).trimmingCharacters(in: .whitespaces)
        return .callout(label: label, text: text)
    }

    private static func parseBullet(_ s: String) -> String? {
        if s.hasPrefix("- ") || s.hasPrefix("* ") || s.hasPrefix("+ ") {
            return String(s.dropFirst(2)).trimmingCharacters(in: .whitespaces)
        }
        return nil
    }

    private static func parseNumbered(_ s: String) -> String? {
        guard let dotIdx = s.firstIndex(where: { $0 == "." || $0 == "、" }) else { return nil }
        let prefix = s[..<dotIdx]
        guard Int(prefix) != nil else { return nil }
        let after = s[s.index(after: dotIdx)...].trimmingCharacters(in: .whitespaces)
        return "\(prefix). \(after)"
    }

    private static func tryTable(lines: [String], start: Int) -> (TableBlock, Int)? {
        guard start + 1 < lines.count else { return nil }
        let hLine = lines[start].trimmingCharacters(in: .whitespaces)
        let sLine = lines[start + 1].trimmingCharacters(in: .whitespaces)
        guard hLine.hasPrefix("|") && sLine.hasPrefix("|") && sLine.contains("-") else { return nil }
        let headers = hLine.trimmingCharacters(in: CharacterSet(charactersIn: "|")).components(separatedBy: "|").map { $0.trimmingCharacters(in: .whitespaces) }
        guard headers.count >= 2 else { return nil }
        var rows: [[String]] = []
        var curr = start + 2
        while curr < lines.count {
            let rLine = lines[curr].trimmingCharacters(in: .whitespaces)
            guard rLine.hasPrefix("|") else { break }
            let cells = rLine.trimmingCharacters(in: CharacterSet(charactersIn: "|")).components(separatedBy: "|").map { $0.trimmingCharacters(in: .whitespaces) }
            guard cells.count == headers.count else { break }
            rows.append(cells); curr += 1
        }
        guard !rows.isEmpty else { return nil }
        return (TableBlock(title: "数据统计表格", headers: headers, rows: rows), curr)
    }

    private static func tryChart(_ lang: String?, _ code: String) -> ChartBlock? {
        guard let l = lang?.lowercased(), l.contains("chart"),
              let data = code.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        let title = json["title"] as? String ?? "数据趋势图"
        let summary = json["summary"] as? String ?? ""
        let isBar = (json["type"] as? String ?? "") == "bar"
        var pts: [ChartPoint] = []
        if let raw = json["points"] as? [[String: Any]] {
            for p in raw {
                let lbl = p["label"] as? String ?? ""
                let val = (p["value"] as? Double) ?? Double(p["value"] as? Int ?? 0)
                pts.append(ChartPoint(label: lbl, value: val))
            }
        }
        guard !pts.isEmpty else { return nil }
        return ChartBlock(title: title, chartType: isBar ? .bar : .line, series: [ChartSeries(name: "默认", points: pts)], summary: summary)
    }
}
