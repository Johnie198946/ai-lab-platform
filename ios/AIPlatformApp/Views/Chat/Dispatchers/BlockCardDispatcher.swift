//
//  BlockCardDispatcher.swift
//  AIPlatformApp
//
//  Zero-AnyView Static Card Dispatcher for Message Blocks
//  Strictly adheres to DeepSeek Harness / Cordis plugin dispatch principles.
//  Preserves SwiftUI Structural Identity to prevent list drop-frame and state loss.
//

import SwiftUI

public struct BlockCardDispatcher: View {
    public let block: MessageBlock
    public var isStreaming: Bool = false
    public var onClarifySubmit: ((String) -> Void)? = nil

    public init(
        block: MessageBlock,
        isStreaming: Bool = false,
        onClarifySubmit: ((String) -> Void)? = nil
    ) {
        self.block = block
        self.isStreaming = isStreaming
        self.onClarifySubmit = onClarifySubmit
    }

    public var body: some View {
        dispatchView(for: block)
    }

    @ViewBuilder
    private func dispatchView(for block: MessageBlock) -> some View {
        switch block {
        case .code(let snippet):
            CodeBlockCard(snippet: snippet)

        case .formula(let formula):
            FormulaCard(formula: formula)

        case .chart(let chartBlock):
            ChartCard(block: chartBlock)

        case .image(let imageBlock):
            ImageCard(block: imageBlock)

        case .table(let tableBlock):
            TableCard(block: tableBlock)

        case .attachment(let attachmentBlock):
            AttachmentCard(block: attachmentBlock)

        case .reasoning(let steps):
            ReasoningCard(steps: steps, isStreaming: isStreaming)

        case .clarify(let clarifyBlock):
            ClarifyCard(block: clarifyBlock, onSubmit: onClarifySubmit)
        }
    }
}
