//
//  AttachmentCard.swift
//  AIPlatformApp
//
//  附件卡片：类型图标（word/pdf/ppt/excel）+ 文件名 + 大小 + 打开提示。
//  点击触觉反馈并提示「演示环境暂不支持打开附件」。
//

import SwiftUI

public struct AttachmentCard: View {
    public let block: AttachmentBlock
    @State private var showUnavailableTip: Bool = false

    public init(block: AttachmentBlock) {
        self.block = block
    }

    public var body: some View {
        Button(action: {
            #if os(iOS)
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            #endif
            showUnavailableTip = true
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.6) {
                showUnavailableTip = false
            }
        }) {
            HStack(spacing: AppTheme.Spacing.md) {
                // 文档类型图标
                Image(systemName: block.fileType.iconName)
                    .font(.system(size: 22))
                    .foregroundColor(AppTheme.Colors.primary)
                    .frame(width: 40, height: 40)
                    .background(AppTheme.Colors.primary.opacity(0.08))
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))

                // 文件名 + 大小
                VStack(alignment: .leading, spacing: 2) {
                    Text(block.fileName)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                        .lineLimit(1)
                    Text(block.fileSize)
                        .font(.system(size: 11))
                        .foregroundColor(AppTheme.Colors.textTertiary)
                }

                Spacer()

                // 打开提示（触觉反馈后短暂显示）
                if showUnavailableTip {
                    Text("演示环境暂不支持打开附件")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(AppTheme.Colors.textSecondary)
                } else {
                    Image(systemName: "arrow.down.circle")
                        .font(.system(size: 16))
                        .foregroundColor(AppTheme.Colors.textTertiary)
                }
            }
            .padding(AppTheme.Spacing.md)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                    .stroke(AppTheme.Colors.border, lineWidth: 0.5)
            )
        }
        .buttonStyle(SoftButtonStyle())
    }
}

public extension AttachmentFileType {
    /// 文档类型 → SF Symbol 图标映射
    var iconName: String {
        switch self {
        case .word: return "doc.text.fill"
        case .pdf: return "doc.richtext.fill"
        case .ppt: return "chart.bar.doc.horizontal.fill"
        case .excel: return "tablecells.fill"
        case .generic: return "doc.fill"
        }
    }
}

// MARK: - Xcode #Preview

#Preview("AttachmentCard - Light") {
    AttachmentCard(block: AttachmentBlock(fileName: "AI竞品周报_2026W33.pdf", fileType: .pdf, fileSize: "2.4 MB"))
        .padding()
        .background(AppTheme.Colors.groupedBackground)
}
