//
//  MarkdownBlockParser.swift
//  AIPlatformApp
//
//  极简单遍 Markdown 分块解析器（零冗余计算·极速纯原生）。
//

import Foundation

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
        case .heading(let l, let t): return "h\(l)_\(t.hashValue)"
        case .callout(let l, let t): return "c_\(l)_\(t.hashValue)"
        case .paragraph(let t): return "p_\(t.hashValue)"
        case .bulletList(let i): return "ul_\(i.hashValue)"
        case .numberedList(let i): return "ol_\(i.hashValue)"
        case .codeBlock(let l, let c): return "code_\(l ?? "")_\(c.hashValue)"
        case .quote(let t): return "q_\(t.hashValue)"
        case .divider: return "divider"
        case .table(let t): return "tbl_\(t.id)"
        case .chart(let c): return "chr_\(c.id)"
        case .sourceCitations(let i): return "src_\(i.hashValue)"
        }
    }
}

public final class MarkdownBlockParser {
    public static let shared = MarkdownBlockParser()

    public func parse(_ content: String, messageId: String = "") -> [MarkdownBlock] {
        guard !content.isEmpty else { return [] }
        let lines = content.components(separatedBy: "\n")
        var blocks: [MarkdownBlock] = []
        var index = 0
        var inCode = false, codeLang: String?, codeLines: [String] = []
        var pBuf: [String] = [], bBuf: [String] = [], nBuf: [String] = []

        func flushP() { if !pBuf.isEmpty { blocks.append(.paragraph(pBuf.joined(separator: "\n"))); pBuf.removeAll() } }
        func flushB() { if !bBuf.isEmpty { blocks.append(.bulletList(bBuf)); bBuf.removeAll() } }
        func flushN() { if !nBuf.isEmpty { blocks.append(.numberedList(nBuf)); nBuf.removeAll() } }
        func flushAll() { flushP(); flushB(); flushN() }

        while index < lines.count {
            let line = lines[index], trimmed = line.trimmingCharacters(in: .whitespaces)
            if inCode {
                if trimmed.hasPrefix("```") {
                    let code = codeLines.joined(separator: "\n")
                    blocks.append(Self.tryChart(codeLang, code) ?? .codeBlock(language: codeLang, code: code))
                    codeLines.removeAll(); codeLang = nil; inCode = false
                } else { codeLines.append(line) }
                index += 1; continue
            }
            if trimmed.hasPrefix("```") {
                flushAll(); codeLang = trimmed.drop(while: { $0 == "`" }).trimmingCharacters(in: .whitespaces)
                if codeLang?.isEmpty == true { codeLang = nil }
                codeLines = []; inCode = true; index += 1; continue
            }
            if let (table, nextIdx) = Self.tryTable(lines: lines, start: index) {
                flushAll(); blocks.append(.table(table)); index = nextIdx; continue
            }
            if Self.isSource(trimmed) {
                flushAll(); var c: [String] = [], next = index + 1
                while next < lines.count {
                    let nt = lines[next].trimmingCharacters(in: .whitespaces)
                    if nt.isEmpty { next += 1; continue }
                    if let item = Self.parseBullet(nt) { c.append(item); next += 1 }
                    else if nt.hasPrefix("wiki/") || nt.hasPrefix("knowledge/") || nt.hasPrefix("raw/") || nt.hasPrefix("`") { c.append(nt); next += 1 }
                    else { break }
                }
                if !c.isEmpty { blocks.append(.sourceCitations(c)); index = next; continue }
            }
            if trimmed == "---" || trimmed == "***" || trimmed == "___" {
                flushAll(); blocks.append(.divider); index += 1; continue
            }
            if let heading = Self.parseHeading(trimmed) {
                flushAll(); blocks.append(heading); index += 1; continue
            }
            if let callout = Self.parseCallout(trimmed) {
                flushAll(); blocks.append(callout); index += 1; continue
            }
            if trimmed.hasPrefix(">") {
                flushAll(); blocks.append(.quote(String(trimmed.dropFirst()).trimmingCharacters(in: .whitespaces))); index += 1; continue
            }
            if let item = Self.parseBullet(trimmed) {
                flushP(); flushN(); bBuf.append(item); index += 1; continue
            }
            if let item = Self.parseNumbered(trimmed) {
                flushP(); flushB(); nBuf.append(item); index += 1; continue
            }
            if trimmed.isEmpty { flushAll(); index += 1; continue }
            flushB(); flushN(); pBuf.append(line); index += 1
        }
        if inCode { blocks.append(.codeBlock(language: codeLang, code: codeLines.joined(separator: "\n"))) }
        flushAll()
        return blocks
    }

    private static func isSource(_ s: String) -> Bool {
        let c = s.trimmingCharacters(in: CharacterSet(charactersIn: "*_` "))
        return c.hasPrefix("来源条目") || c.hasPrefix("知识库来源") || c.hasPrefix("参考条目") || c.hasPrefix("引用条目") || c.hasPrefix("来源：") || c.hasPrefix("Sources:")
    }
    private static func parseHeading(_ s: String) -> MarkdownBlock? {
        if s.hasPrefix("#") {
            let l = s.prefix(while: { $0 == "#" }).count
            return .heading(level: min(max(l, 1), 6), text: s.dropFirst(l).trimmingCharacters(in: .whitespaces))
        }
        let cn = ["一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、", "九、", "十、"]
        return cn.contains(where: { s.hasPrefix($0) }) ? .heading(level: 2, text: s) : nil
    }
    private static func parseCallout(_ s: String) -> MarkdownBlock? {
        guard s.hasPrefix("【"), let close = s.firstIndex(of: "】") else { return nil }
        return .callout(label: String(s[s.index(after: s.startIndex)..<close]), text: String(s[s.index(after: close)...]).trimmingCharacters(in: .whitespaces))
    }
    private static func parseBullet(_ s: String) -> String? {
        (s.hasPrefix("- ") || s.hasPrefix("* ") || s.hasPrefix("+ ")) ? String(s.dropFirst(2)).trimmingCharacters(in: .whitespaces) : nil
    }
    private static func parseNumbered(_ s: String) -> String? {
        guard let dot = s.firstIndex(where: { $0 == "." || $0 == "、" }), Int(s[..<dot]) != nil else { return nil }
        return "\(s[..<dot]). \(s[s.index(after: dot)...].trimmingCharacters(in: .whitespaces))"
    }
    private static func tryTable(lines: [String], start: Int) -> (TableBlock, Int)? {
        guard start + 1 < lines.count else { return nil }
        let hLine = lines[start].trimmingCharacters(in: .whitespaces), sLine = lines[start + 1].trimmingCharacters(in: .whitespaces)
        guard hLine.hasPrefix("|") && sLine.hasPrefix("|") && sLine.contains("-") else { return nil }
        let headers = hLine.trimmingCharacters(in: CharacterSet(charactersIn: "|")).components(separatedBy: "|").map { $0.trimmingCharacters(in: .whitespaces) }
        guard headers.count >= 2 else { return nil }
        var rows: [[String]] = [], curr = start + 2
        while curr < lines.count {
            let rLine = lines[curr].trimmingCharacters(in: .whitespaces)
            guard rLine.hasPrefix("|") else { break }
            let cells = rLine.trimmingCharacters(in: CharacterSet(charactersIn: "|")).components(separatedBy: "|").map { $0.trimmingCharacters(in: .whitespaces) }
            guard cells.count == headers.count else { break }
            rows.append(cells); curr += 1
        }
        return rows.isEmpty ? nil : (TableBlock(title: "数据统计表格", headers: headers, rows: rows), curr)
    }
    private static func tryChart(_ lang: String?, _ code: String) -> MarkdownBlock? {
        guard let l = lang?.lowercased(), l.contains("chart"), let d = code.data(using: .utf8),
              let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return nil }
        let title = j["title"] as? String ?? "数据趋势图", summary = j["summary"] as? String ?? "", isBar = (j["type"] as? String ?? "") == "bar"
        var pts: [ChartPoint] = []
        if let raw = j["points"] as? [[String: Any]] {
            for p in raw { pts.append(ChartPoint(label: p["label"] as? String ?? "", value: (p["value"] as? Double) ?? Double(p["value"] as? Int ?? 0))) }
        }
        return pts.isEmpty ? nil : .chart(ChartBlock(title: title, chartType: isBar ? .bar : .line, series: [ChartSeries(name: "默认", points: pts)], summary: summary))
    }
}
