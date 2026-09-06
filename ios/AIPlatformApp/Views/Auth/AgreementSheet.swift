import SwiftUI

struct AgreementSheet: View {
    let agreement: AgreementDTO?
    let isLoading: Bool
    let isAccepting: Bool
    let errorMessage: String?
    let onRetry: () -> Void
    let onAccept: () -> Void

    @Environment(\.dismiss) private var dismiss
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass

    var body: some View {
        Group {
            if let agreement {
                agreementContent(agreement)
            } else if isLoading {
                ProgressView("正在加载服务协议…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ContentUnavailableView {
                    Label("无法加载服务协议", systemImage: "wifi.exclamationmark")
                } description: {
                    Text(errorMessage ?? "当前协议版本未知，暂时无法确认。")
                } actions: {
                    Button("重试", action: onRetry)
                        .buttonStyle(.borderedProminent)
                        .disabled(isLoading)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AppTheme.Colors.cardBackground)
        .overlay(alignment: .topTrailing) {
            if agreement == nil {
                closeButton
                    .padding(.top, AppTheme.Spacing.sm)
                    .padding(.trailing, AppTheme.Spacing.xl)
            }
        }
    }

    private func agreementContent(_ agreement: AgreementDTO) -> some View {
        VStack(spacing: 0) {
            VStack(spacing: AppTheme.Spacing.sm) {
                ZStack {
                    Text(agreement.title)
                        .font(.title2.bold())
                        .foregroundColor(AppTheme.Colors.textPrimary)
                        .accessibilityAddTraits(.isHeader)
                        .accessibilitySortPriority(7)
                        .accessibilityIdentifier("agreement.title")

                    HStack {
                        Spacer()
                        closeButton
                    }
                }

                Text("版本：\(agreement.version) · 更新日期：\(displayDate(agreement.updatedAt))")
                    .font(.subheadline)
                    .foregroundColor(AppTheme.Colors.textSecondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilitySortPriority(6)
                    .accessibilityIdentifier("agreement.version")
            }
            .frame(maxWidth: AppTheme.Metrics.readableContentWidth)
            .padding(.horizontal, horizontalPadding)
            .padding(.top, AppTheme.Spacing.sm)
            .padding(.bottom, AppTheme.Spacing.lg)
            .frame(maxWidth: .infinity)

            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xxl) {
                    ForEach(Array(agreement.sections.enumerated()), id: \.element.id) { index, section in
                        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                            Text("\(chineseNumber(index + 1))、\(section.title)")
                                .font(.headline)
                                .foregroundColor(AppTheme.Colors.textPrimary)
                                .accessibilityAddTraits(.isHeader)
                            ForEach(Array(section.clauses.enumerated()), id: \.offset) { clauseIndex, clause in
                                HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                                    Text("\(clauseIndex + 1).")
                                    Text(clause)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                }
                                .font(.body)
                                .foregroundColor(AppTheme.Colors.textPrimary)
                                .lineSpacing(6)
                                .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                        .accessibilityElement(children: .combine)
                        .accessibilitySortPriority(Double(5 - index))
                        .accessibilityIdentifier("agreement.chapter.\(index + 1)")
                    }
                }
                .frame(maxWidth: AppTheme.Metrics.readableContentWidth)
                .padding(.horizontal, horizontalPadding)
                .padding(.top, AppTheme.Spacing.xxl)
                .padding(.bottom, AppTheme.Spacing.xl)
                .frame(maxWidth: .infinity)
            }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            VStack(spacing: 0) {
                Divider()
                Button(action: onAccept) {
                    HStack {
                        if isAccepting { ProgressView().tint(AppTheme.Colors.onPrimary) }
                        Text("我已阅读并同意全部协议")
                    }
                    .font(.headline)
                    .foregroundColor(AppTheme.Colors.onPrimary)
                    .frame(maxWidth: AppTheme.Metrics.readableContentWidth)
                    .frame(minHeight: 52)
                    .background(AppTheme.Colors.actionGradient)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                }
                .buttonStyle(.plain)
                .disabled(isAccepting)
                .minimumTouchTarget()
                .accessibilitySortPriority(1)
                .accessibilityIdentifier("agreement.cta")
                .padding(.horizontal, horizontalPadding)
                .padding(.vertical, AppTheme.Spacing.md)
            }
            .background(AppTheme.Colors.cardBackground)
        }
        .accessibilityElement(children: .contain)
    }

    private var horizontalPadding: CGFloat {
        horizontalSizeClass == .regular ? AppTheme.Spacing.xxxl : AppTheme.Spacing.xl
    }

    private var closeButton: some View {
        Button { dismiss() } label: {
            Image(systemName: "xmark")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(AppTheme.Colors.textSecondary)
                .frame(width: 36, height: 36)
                .background(AppTheme.Colors.surfaceTint, in: Circle())
        }
        .buttonStyle(.plain)
        .frame(width: 44, height: 44)
        .contentShape(Rectangle())
        .accessibilityLabel("关闭服务协议")
        .accessibilitySortPriority(0)
        .accessibilityIdentifier("agreement.close")
    }

    private func displayDate(_ value: String) -> String {
        guard let date = ISO8601DateFormatter().date(from: value) else { return value }
        return date.formatted(.dateTime.year().month().day().locale(Locale(identifier: "zh_CN")))
    }

    private func chineseNumber(_ value: Int) -> String {
        ["一", "二", "三"][value - 1]
    }
}
