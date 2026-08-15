//
//  WeChatLinkValidator.swift
//  AIPlatformApp
//
//  微信文章链接前端校验器（合规路径）：
//  仅接受官方 mp.weixin.qq.com 域名白名单，异常链接直接拒绝并回传原因，
//  供 UI 层 Toast 降级提示。后端抓取引擎复用由后续轮次承接。
//

import Foundation

/// 微信文章链接校验结果
public struct WeChatLinkValidation: Sendable, Hashable {
    public let isValid: Bool
    public let reason: String

    public init(isValid: Bool, reason: String) {
        self.isValid = isValid
        self.reason = reason
    }
}

/// 微信文章链接域名白名单校验器
public enum WeChatLinkValidator {

    /// 官方文章域名白名单（严格主域名）
    public static let allowedHost = "mp.weixin.qq.com"

    /// 校验入口：解析 scheme/host，逐层拒绝非法输入
    public static func validate(_ raw: String) -> WeChatLinkValidation {
        var urlString = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !urlString.isEmpty else {
            return WeChatLinkValidation(isValid: false, reason: "链接为空")
        }

        // 无 scheme 粘贴（如 "mp.weixin.qq.com/s/xxx"）自动补 https://
        let lower = urlString.lowercased()
        if !lower.hasPrefix("http://") && !lower.hasPrefix("https://") {
            urlString = "https://" + urlString
        }

        guard let url = URL(string: urlString),
              let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let host = components.host else {
            return WeChatLinkValidation(isValid: false, reason: "无法解析的链接")
        }

        guard let scheme = components.scheme?.lowercased(),
              scheme == "http" || scheme == "https" else {
            return WeChatLinkValidation(isValid: false, reason: "仅支持 http/https 协议")
        }

        let hostLower = host.lowercased()
        guard hostLower == allowedHost || hostLower.hasSuffix("." + allowedHost) else {
            return WeChatLinkValidation(isValid: false, reason: "非法链接：仅支持 mp.weixin.qq.com")
        }

        return WeChatLinkValidation(isValid: true, reason: "校验通过：微信文章链接")
    }
}
