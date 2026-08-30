//
//  Theme.swift
//  AIPlatformApp
//
//  Design System Tokens & Styling Definitions
//  Compliant with Apple Human Interface Guidelines (HIG) & iOS 17+ Dark/Light Mode
//  Quantum Pearl 全域设计令牌（冷白珠光、青蓝紫品牌光谱）
//

import SwiftUI

#if os(iOS)
import UIKit
#endif

public enum AppTheme {
    
    // MARK: - Color Palette
    public enum Colors {
        // Logo 原色只用于品牌标记和数据序列；界面交互使用下方 Aurora 语义色。
        public static let quantumCyan = Color(hex: "56C8EB")
        public static let quantumBlue = Color(hex: "5B7CEE")
        public static let quantumViolet = Color(hex: "9E6EE8")
        public static let auroraViolet = Color(hex: "7468EE")
        public static let auroraBlue = Color(hex: "526CFF")
        public static let auroraCyan = Color(hex: "4CCFE0")
        public static let auroraPink = Color(hex: "FF9BC3")
        public static let emberOrange = Color(hex: "E97942")
        public static let emberAmber = Color(hex: "F2A15F")
        public static let emberCream = Color(hex: "FFF7EC")
        public static let emberInk = Color(hex: "2B1811")
        /// 历史命名兼容：交互入口已映射到 Ember，不再代表视觉上的蓝/紫。
        public static let interactiveBlue = Color(hex: "8057E8")
        public static let interactiveViolet = Color(hex: "6845D6")

        // 语义别名（收敛到 Quantum 真值，杜绝双源漂移）
        public static let brandPrimary = quantumBlue
        public static let brandSecondary = quantumViolet
        public static let brandTertiary = quantumCyan

        // Quantum 光谱只用于品牌标识；结构性操作使用暖色 Ember 渐变。
        public static let quantumGradient = LinearGradient(
            colors: [auroraViolet, auroraBlue, auroraCyan, auroraPink],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        public static let actionGradient = LinearGradient(
            colors: [Color(hex: "328CE4"), Color(hex: "8057E8")],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        public static let userBubbleGradient = LinearGradient(
            colors: [Color(hex: "8057E8"), Color(hex: "6845D6")],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )

        // primary / accent 统一为 Quantum Blue（主 CTA / 链接 / TabBar 选中高亮）
        public static let primary = interactiveBlue
        public static let accent = interactiveViolet
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
        public static var statusIdle: Color { adaptive("7B849E", "9EA7C4") }
        public static var statusRunning: Color { adaptive("C9572D", "F08A4B") }
        public static var statusCompleted: Color { adaptive("199B75", "4DD5A8") }
        public static var statusError: Color { adaptive("D94A67", "FF7690") }
        public static var statusWarning: Color { adaptive("C98214", "F3B64F") }
        
        // Third-Party Brand Colors (收敛进 Token 域)
        public static let thirdPartyWeChat = Color(hex: "07C160")
        public static let thirdPartyAlipay = Color(hex: "1677FF")
        
        // Code Window & Syntax Colors (功能性例外 · 豁免低饱和)
        public static let codeWindowRed = Color(hex: "FF5F56")
        public static let codeWindowYellow = Color(hex: "FFBD2E")
        public static let codeWindowGreen = Color(hex: "27C93F")
        public static let codeSyntaxForeground = Color(hex: "E6EDF3")
        
        // Ember Glass 三层深色画布：charcoal → smoked cocoa → raised glass。
        public static var background: Color { adaptive("F8F7FC", "17141F") }
        public static var secondaryBackground: Color { adaptive("F1EEFA", "211D2B") }
        public static var tertiaryBackground: Color { adaptive("E8E3F3", "2B2637") }
        public static var cardBackground: Color { adaptive("FFFFFF", "24202E") }
        public static var surfaceElevated: Color { adaptive("FFFFFF", "302A3B") }
        public static var groupedBackground: Color { background }
        public static var surfaceTint: Color { adaptive("F4F0FC", "352E42") }
        public static var selectionTint: Color { adaptive("ECE5FB", "403652") }
        public static var successSurface: Color { adaptive("E7F8F2", "17342D") }
        public static var warningSurface: Color { adaptive("FFF4DF", "462B1B") }
        public static var dangerSurface: Color { adaptive("FDECEF", "3D1D22") }
        public static var focusRing: Color { interactiveBlue.opacity(0.28) }
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
        public static var textPrimary: Color { adaptive("191521", "F8F4FF") }
        public static var textSecondary: Color { adaptive("746E7F", "D1C9DC") }
        public static var textTertiary: Color { adaptive("9690A2", "A69BB2") }
        
        // Border & Divider — Quantum 冷调发丝线
        public static var border: Color { adaptive("EAE6F2", "51475E") }

        // Soft Intelligence Bento accent fills（彩色卡片始终搭配指定前景色）
        public static let bentoLavender = Color(hex: "E9E0FB")
        public static let bentoSky = Color(hex: "DDF3FB")
        public static let bentoRose = Color(hex: "F8E4F1")
        public static let bentoAmber = Color(hex: "FFF1D9")
        
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

    // MARK: - Semantic Icon Palette
    /// SF Symbols 只引用语义角色，不直接选择品牌原色。
    /// 品牌色只保留给数据可视化与第三方品牌；导航、操作、智能、状态各用一个稳定入口。
    public enum Icons {
        public static var primary: Color { Colors.textPrimary }
        public static var secondary: Color { Colors.textSecondary }
        public static var tertiary: Color { Colors.textTertiary }
        public static let interactive = Colors.interactiveBlue
        public static let intelligence = Colors.quantumViolet
        public static let live = Colors.quantumCyan
        public static var success: Color { Colors.statusCompleted }
        public static var warning: Color { Colors.securityYellow }
        public static var destructive: Color { Colors.statusError }
        public static let onAccent = Colors.onPrimary
        public static var navigationInactive: Color { Colors.textTertiary }
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
        public static let hero = Font.system(.largeTitle, design: .rounded, weight: .bold)
        public static let screenTitle = Font.system(.title, design: .rounded, weight: .bold)
        public static let sectionTitle = Font.system(.title2, design: .rounded, weight: .semibold)
        public static let cardTitle = Font.system(.headline, design: .rounded, weight: .semibold)
        public static let body = Font.body
        public static let supporting = Font.subheadline
        public static let label = Font.caption.weight(.semibold)
        public static let micro = Font.caption2.weight(.medium)
    }

    public enum Metrics {
        public static let minimumTouchTarget: CGFloat = 44
        public static let inputHeight: CGFloat = 52
        public static let contentGutter: CGFloat = 20
        public static let readableContentWidth: CGFloat = 720
        public static let floatingTabBarHeight: CGFloat = 64
        public static let panelRadius: CGFloat = 22
    }

    public enum Motion {
        public static let quick = Animation.easeOut(duration: 0.18)
        public static let standard = Animation.easeOut(duration: 0.24)
        public static let spring = Animation.spring(response: 0.32, dampingFraction: 0.86)
    }
    
    // MARK: - Corner Radius Tokens
    public enum Radius {
        public static let xs: CGFloat = 10
        public static let sm: CGFloat = 14
        public static let md: CGFloat = 18
        public static let lg: CGFloat = 24
        public static let xl: CGFloat = 30
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
                color: colorScheme == .dark ? Color.black.opacity(0.18) : Color(hex: "6B5A8A").opacity(0.10),
                radius: 20,
                x: 0,
                y: 4
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
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init() {}
    
    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.97 : 1.0)
            .opacity(configuration.isPressed ? 0.86 : 1.0)
            .animation(reduceMotion ? nil : AppTheme.Motion.quick, value: configuration.isPressed)
    }
}

public struct QuantumCardModifier: ViewModifier {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    public func body(content: Content) -> some View {
        content
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(AppTheme.Colors.border.opacity(0.92), lineWidth: 0.75)
            }
            .contentShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .shadow(
                color: colorScheme == .dark ? Color.black.opacity(0.24) : Color(hex: "6B5A8A").opacity(0.10),
                radius: 20,
                x: 0,
                y: 4
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

    /// 保留调用兼容性，但全局关闭发光反馈。
    func pressBorderGlow(cornerRadius: CGFloat = AppTheme.Radius.md) -> some View {
        self
    }
}

/// Aurora Workbench 主操作按钮。仅用于每个区域唯一的主动作。
public struct QuantumPrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init() {}

    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline.weight(.semibold))
            .foregroundStyle(AppTheme.Colors.onPrimary)
            .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.inputHeight)
            .padding(.horizontal, AppTheme.Spacing.xl)
            .background(AppTheme.Colors.actionGradient.opacity(isEnabled ? 1 : 0.46))
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .opacity(configuration.isPressed ? 0.92 : 1)
            .animation(reduceMotion ? nil : AppTheme.Motion.quick, value: configuration.isPressed)
    }
}

/// 冷白珠光环境底景。光晕保持静态，避免持续动画和额外解码成本。
public struct QuantumMistBackground: View {
    @Environment(\.colorScheme) private var colorScheme

    public init() {}

    public var body: some View {
        ZStack {
            AppTheme.Colors.background
            LinearGradient(
                colors: [Color(hex: "EEF8FF"), Color(hex: "F8F7FC"), Color(hex: "F5EEFF")],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            Circle()
                .fill(AppTheme.Colors.quantumViolet.opacity(0.15))
                .frame(width: 360, height: 360)
                .blur(radius: 100)
                .offset(x: 190, y: -260)
            Circle()
                .fill(AppTheme.Colors.quantumCyan.opacity(0.12))
                .frame(width: 340, height: 340)
                .blur(radius: 96)
                .offset(x: -210, y: -40)
            Circle()
                .fill(AppTheme.Colors.auroraPink.opacity(0.12))
                .frame(width: 300, height: 500)
                .blur(radius: 105)
                .offset(x: 230, y: 390)
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
    }
}
