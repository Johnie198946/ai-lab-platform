//
//  QuantumAvatarView.swift
//  AIPlatformApp
//
//  Quantum 官方标志组件。Logo 自带透明留白，不额外套圆形托盘或描边。
//

import SwiftUI

public struct QuantumAvatarView: View {
    /// 头像外接圆直径（默认 32pt，与助手气泡头像对齐）
    public var size: CGFloat = 32

    public init(size: CGFloat = 32) {
        self.size = size
    }

    public var body: some View {
        Image("quantum_logo_icon")
            .resizable()
            .renderingMode(.original)
            .scaledToFit()
        .frame(width: size, height: size)
        .accessibilityLabel("Quantum")
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
