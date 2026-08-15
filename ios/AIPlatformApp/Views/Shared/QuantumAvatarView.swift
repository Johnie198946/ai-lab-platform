//
//  QuantumAvatarView.swift
//  AIPlatformApp
//
//  Quantum 品牌头像组件（Logo 保真 + 暗色自适应托盘）
//  规格：Circle().fill(avatarBackplate) + Image("quantum_logo_icon").renderingMode(.original).clipShape(Circle())
//        + 暗色微光描边 quantumBlue.opacity(0.12)
//  层级：底板 #121316 < 托盘 #16171D < 卡片 #1A1C22（暗色三级亮度递增，杜绝突兀白斑）
//

import SwiftUI

public struct QuantumAvatarView: View {
    /// 头像外接圆直径（默认 32pt，与助手气泡头像对齐）
    public var size: CGFloat = 32

    public init(size: CGFloat = 32) {
        self.size = size
    }

    public var body: some View {
        ZStack {
            // 自适应托盘底板（亮 #FFFFFF / 暗 #16171D）
            Circle()
                .fill(AppTheme.Colors.avatarBackplate)

            // 官方 Logo 球体图标（原色渲染，严禁模板化着色破坏官方原色）
            Image("quantum_logo_icon")
                .resizable()
                .renderingMode(.original)
                .scaledToFit()
                .clipShape(Circle())
                .padding(size * 0.06)
        }
        .frame(width: size, height: size)
        .overlay(
            Circle()
                .stroke(AppTheme.Colors.quantumBlue.opacity(0.12), lineWidth: 1)
        )
    }
}

// MARK: - Xcode #Preview

#Preview("QuantumAvatarView - Light") {
    HStack(spacing: 16) {
        QuantumAvatarView(size: 32)
        QuantumAvatarView(size: 48)
        QuantumAvatarView(size: 64)
    }
    .padding()
    .background(AppTheme.Colors.groupedBackground)
}

#Preview("QuantumAvatarView - Dark") {
    HStack(spacing: 16) {
        QuantumAvatarView(size: 32)
        QuantumAvatarView(size: 48)
        QuantumAvatarView(size: 64)
    }
    .padding()
    .background(AppTheme.Colors.groupedBackground)
    .preferredColorScheme(.dark)
}
