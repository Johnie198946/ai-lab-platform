//
//  Theme.swift
//  AIPlatformApp
//
//  Design System Tokens & Styling Definitions
//  Compliant with Apple Human Interface Guidelines (HIG) & iOS 17+ Dark/Light Mode
//  Quantum 全域色彩系统（2026-08-16 拍板：基于 Logo 官方原色 Cyan/Blue/Violet 冷调重塑）
//

import SwiftUI

#if os(iOS)
import UIKit
#endif

public enum AppTheme {
    
    // MARK: - Color Palette
    public enum Colors {
        // Core Brand Colors — Quantum 官方三色真值（唯一真值源，严格锚定 Logo 原色谱，不做偏移）
        // quantumCyan   = #56C8EB 青蓝：高光态 / 活跃指示 / 技能步 / 图表首序列
        // quantumBlue   = #5B7CEE 量子蓝：主品牌色 / 主 CTA / TabBar 高亮 / 通信状态
        // quantumViolet = #9E6EE8 量子紫：智能体专属 / 思考步 / 算力矩阵
        public static let quantumCyan = Color(hex: "56C8EB")
        public static let quantumBlue = Color(hex: "5B7CEE")
        public static let quantumViolet = Color(hex: "9E6EE8")

        // 语义别名（收敛到 Quantum 真值，杜绝双源漂移）
        public static let brandPrimary = quantumBlue
        public static let brandSecondary = quantumViolet
        public static let brandTertiary = quantumCyan

        // Quantum 主品牌流光渐变：Cyan ➔ Blue ➔ Violet（135° topLeading ➔ bottomTrailing）
        public static let quantumGradient = LinearGradient(
            colors: [quantumCyan, quantumBlue, quantumViolet],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        // 用户气泡三色量子流光渐变（白字），告别死板单色纯蓝
        public static let userBubbleGradient = quantumGradient

        // primary / accent 统一为 Quantum Blue（主 CTA / 链接 / TabBar 选中高亮）
        public static let primary = brandPrimary
        public static let accent = brandPrimary
        // onPrimary：primary（饱和蓝）之上的文字与图标——亮暗恒为白字，保证 WCAG AA 对比
        public static let onPrimary = Color(hex: "FFFFFF")
        // onSemantic：语义色（黄/绿）按钮上的深色文字——亮暗通用（浅色底必须深字才达 AA）
        public static let onSemantic = Color(hex: "1F1F1F")

        // 对话气泡系统：用户气泡三色流光渐变（白字），助手卡片冷岩/深曜石底 + 量子青/蓝微光细边框
        public static let userBubbleBackground = Color(hex: "5B7CEE")
        public static let assistantBubbleBorder = adaptive("5B7CEE", "56C8EB")
        
        // Security Classification Three-Color Tokens (红黄绿三色安全徽章) → System Semantic Colors
        public static var securityRed: Color {
            #if os(iOS)
            Color(uiColor: .systemRed)
            #else
            Color.red
            #endif
        }
        public static var securityYellow: Color {
            #if os(iOS)
            Color(uiColor: .systemYellow)
            #else
            Color.yellow
            #endif
        }
        public static var securityGreen: Color {
            #if os(iOS)
            Color(uiColor: .systemGreen)
            #else
            Color.green
            #endif
        }
        
        // Semantic Status Colors → System Semantic Colors
        public static var statusIdle: Color {
            #if os(iOS)
            Color(uiColor: .systemGray)
            #else
            Color.gray
            #endif
        }
        public static var statusRunning: Color {
            #if os(iOS)
            Color(uiColor: .systemBlue)
            #else
            Color.blue
            #endif
        }
        public static var statusCompleted: Color {
            #if os(iOS)
            Color(uiColor: .systemGreen)
            #else
            Color.green
            #endif
        }
        public static var statusError: Color {
            #if os(iOS)
            Color(uiColor: .systemRed)
            #else
            Color.red
            #endif
        }
        
        // Third-Party Brand Colors (收敛进 Token 域)
        public static let thirdPartyWeChat = Color(hex: "07C160")
        public static let thirdPartyAlipay = Color(hex: "1677FF")
        
        // Code Window & Syntax Colors (功能性例外 · 豁免低饱和)
        public static let codeWindowRed = Color(hex: "FF5F56")
        public static let codeWindowYellow = Color(hex: "FFBD2E")
        public static let codeWindowGreen = Color(hex: "27C93F")
        public static let codeSyntaxForeground = Color(hex: "E6EDF3")
        
        // Layered surfaces — calm in light mode, cinematic rather than pure black in dark mode.
        public static var background: Color { adaptive("F6F7FB", "0D0F14") }
        public static var secondaryBackground: Color { adaptive("EEF1F7", "171A22") }
        public static var tertiaryBackground: Color { adaptive("E4E8F1", "222631") }
        public static var cardBackground: Color { adaptive("FFFFFF", "151821") }
        public static var surfaceElevated: Color { adaptive("FFFFFF", "1C202A") }
        public static var groupedBackground: Color { background }
        public static var surfaceTint: Color { adaptive("EEF2FF", "20243A") }
        public static var focusRing: Color { quantumBlue.opacity(0.28) }
        public static var scrim: Color { Color.black.opacity(0.52) }

        // 头像自适应托盘：暗色下底板 #121316 < 托盘 #16171D < 卡片 #1A1C22（三级亮度递增，杜绝暗色白斑）
        public static let avatarBackplate = adaptive("FFFFFF", "16171D")
        
        // Code Block and Monospace Surfaces
        public static let codeBlockBackground = Color(hex: "1C1C1E")
        public static let codeBlockHeader = Color(hex: "2C2C2E")
        public static let codeSyntaxKeyword = Color(hex: "FF7AB2")
        public static let codeSyntaxString = Color(hex: "FF8170")
        public static let codeSyntaxComment = Color(hex: "7F8C8D")
        public static let codeSyntaxType = Color(hex: "6BDFFF")
        
        // Dynamic Label Colors — Quantum 同源文字（亮 #333333 · 暗 #F5F5F7）
        public static var textPrimary: Color { adaptive("172033", "F4F6FC") }
        public static var textSecondary: Color { adaptive("526079", "B4BECE") }
        public static var textTertiary: Color { adaptive("738098", "8F9AAD") }
        
        // Border & Divider — Quantum 冷调发丝线
        public static var border: Color { adaptive("DDE3EE", "303541") }
        
        // MARK: - 双模式自适应色辅助
        private static func adaptive(_ light: String, _ dark: String) -> Color {
            #if os(iOS)
            return Color(uiColor: UIColor { trait in
                trait.userInterfaceStyle == .dark ? UIColor(hex: dark) : UIColor(hex: light)
            })
            #else
            return Color(hex: light)
            #endif
        }
    }
    
    // MARK: - Spacing Tokens
    public enum Spacing {
        public static let xxs: CGFloat = 2
        public static let xs: CGFloat = 4
        public static let sm: CGFloat = 8
        public static let md: CGFloat = 12
        public static let lg: CGFloat = 16
        public static let xl: CGFloat = 20
        public static let xxl: CGFloat = 24
        public static let xxxl: CGFloat = 32
        public static let section: CGFloat = 40
    }

    // MARK: - Semantic Type (Dynamic Type by default)
    public enum Typography {
        public static let screenTitle = Font.title2.weight(.bold)
        public static let sectionTitle = Font.headline.weight(.semibold)
        public static let cardTitle = Font.subheadline.weight(.semibold)
        public static let body = Font.body
        public static let supporting = Font.subheadline
        public static let label = Font.caption.weight(.semibold)
        public static let micro = Font.caption2.weight(.medium)
    }

    public enum Metrics {
        public static let minimumTouchTarget: CGFloat = 44
        public static let inputHeight: CGFloat = 48
        public static let contentGutter: CGFloat = 16
        public static let readableContentWidth: CGFloat = 720
    }

    public enum Motion {
        public static let quick = Animation.easeOut(duration: 0.18)
        public static let standard = Animation.easeOut(duration: 0.24)
        public static let spring = Animation.spring(response: 0.32, dampingFraction: 0.86)
    }
    
    // MARK: - Corner Radius Tokens
    public enum Radius {
        public static let xs: CGFloat = 4
        public static let sm: CGFloat = 8
        public static let md: CGFloat = 12
        public static let lg: CGFloat = 16
        public static let xl: CGFloat = 20
        public static let full: CGFloat = 999
    }
    
    // MARK: - Shadows
    public enum Shadows {
        public static func card(colorScheme: ColorScheme) -> some ViewModifier {
            CardShadowModifier(colorScheme: colorScheme)
        }
    }
}

// MARK: - Color Hex Initializer
public extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 3: // RGB (12-bit)
            (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6: // RGB (24-bit)
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8: // ARGB (32-bit)
            (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (255, 0, 0, 0)
        }
        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue:  Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
}

// MARK: - UIColor Hex Initializer (for dynamicProvider)
#if os(iOS)
public extension UIColor {
    convenience init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 6: // RGB (24-bit)
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (255, 0, 0, 0)
        }
        self.init(
            red: CGFloat(r) / 255,
            green: CGFloat(g) / 255,
            blue: CGFloat(b) / 255,
            alpha: CGFloat(a) / 255
        )
    }
}
#endif

// MARK: - Helper Modifiers
private struct CardShadowModifier: ViewModifier {
    let colorScheme: ColorScheme
    
    func body(content: Content) -> some View {
        content
            .shadow(
                color: colorScheme == .dark ? Color.black.opacity(0.18) : Color.black.opacity(0.06),
                radius: 24,
                x: 0,
                y: 12
            )
    }
}

public extension View {
    func cardShadow(colorScheme: ColorScheme) -> some View {
        modifier(AppTheme.Shadows.card(colorScheme: colorScheme))
    }
}

// MARK: - Press Feedback Button Style (Taste-skill :active 规则移植 SwiftUI ButtonStyle)
public struct SoftButtonStyle: ButtonStyle {
    public init() {}
    
    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.97 : 1.0)
            .opacity(configuration.isPressed ? 0.86 : 1.0)
            .animation(AppTheme.Motion.quick, value: configuration.isPressed)
    }
}

public struct QuantumCardModifier: ViewModifier {
    @Environment(\.colorScheme) private var colorScheme

    public func body(content: Content) -> some View {
        content
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(AppTheme.Colors.border.opacity(colorScheme == .dark ? 0.9 : 0.7), lineWidth: 0.75)
            }
            .shadow(
                color: Color.black.opacity(colorScheme == .dark ? 0.18 : 0.045),
                radius: 12,
                x: 0,
                y: 5
            )
    }
}

public extension View {
    func quantumCard() -> some View {
        modifier(QuantumCardModifier())
    }

    func minimumTouchTarget() -> some View {
        frame(minWidth: AppTheme.Metrics.minimumTouchTarget, minHeight: AppTheme.Metrics.minimumTouchTarget)
            .contentShape(Rectangle())
    }
}
