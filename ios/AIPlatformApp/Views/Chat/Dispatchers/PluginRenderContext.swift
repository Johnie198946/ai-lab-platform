//
//  PluginRenderContext.swift
//  AIPlatformApp
//
//  Live Interactive Rendering Context for Cordis / Block Plugin Cards
//  Connects Block Cards to Coordinator Action Dispatchers (HITL Option Submit, Quote, Retry).
//

import Foundation

public struct PluginRenderContext {
    public let messageId: String
    public let isStreaming: Bool
    public var onClarifySubmit: ((String) -> Void)? = nil
    public var onQuoteFollowUp: ((QuotedContext) -> Void)? = nil
    public var onRegenerate: ((String) -> Void)? = nil
    public var onNoteDraftAction: ((String, String) -> Void)? = nil
    public var onKnowledgeAction: ((String, String) -> Void)? = nil

    public init(
        messageId: String,
        isStreaming: Bool = false,
        onClarifySubmit: ((String) -> Void)? = nil,
        onQuoteFollowUp: ((QuotedContext) -> Void)? = nil,
        onRegenerate: ((String) -> Void)? = nil,
        onNoteDraftAction: ((String, String) -> Void)? = nil,
        onKnowledgeAction: ((String, String) -> Void)? = nil
    ) {
        self.messageId = messageId
        self.isStreaming = isStreaming
        self.onClarifySubmit = onClarifySubmit
        self.onQuoteFollowUp = onQuoteFollowUp
        self.onRegenerate = onRegenerate
        self.onNoteDraftAction = onNoteDraftAction
        self.onKnowledgeAction = onKnowledgeAction
    }

    /// 静态预览上下文（无交互事件回调）
    public static let preview = PluginRenderContext(messageId: "preview")
}
