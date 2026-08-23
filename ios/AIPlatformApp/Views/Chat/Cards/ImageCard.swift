//
//  ImageCard.swift
//  AIPlatformApp
//
//  图片卡片：仅支持本地 assetName，UIImage(named:) 严格判空，
//  资源缺失时渲染灰底占位框（图标 + 文件名），杜绝运行时崩溃。
//

import SwiftUI

public struct ImageCard: View {
    public let block: ImageBlock

    public init(block: ImageBlock) {
        self.block = block
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            // 图片主体（优先运行时数据，其次本地资源；均判空降级）
            if let data = block.imageData, let uiImage = UIImage(data: data) {
                Image(uiImage: uiImage)
                    .resizable()
                    .scaledToFit()
                    .frame(maxWidth: .infinity)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
            } else if let uiImage = UIImage(named: block.assetName) {
                Image(uiImage: uiImage)
                    .resizable()
                    .scaledToFit()
                    .frame(maxWidth: .infinity)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
            } else {
                placeholderView
            }

            // 图注
            if !block.caption.isEmpty {
                Text(block.caption)
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textSecondary)
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
        .pressBorderGlow(cornerRadius: AppTheme.Radius.md)
    }

    /// 资源缺失优雅占位框（灰底 + 占位图标 + 文件名）
    private var placeholderView: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: "photo")
                .font(.system(size: 32))
                    .foregroundColor(AppTheme.Icons.tertiary)
            Text(block.assetName)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(AppTheme.Colors.textSecondary)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity)
        .frame(height: 120)
        .background(AppTheme.Colors.tertiaryBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
    }
}

// MARK: - Xcode #Preview

#Preview("ImageCard - Missing Asset Fallback") {
    ImageCard(block: ImageBlock(assetName: "nonexistent_asset", caption: "缺失资源占位示例"))
        .padding()
        .background(AppTheme.Colors.groupedBackground)
}
