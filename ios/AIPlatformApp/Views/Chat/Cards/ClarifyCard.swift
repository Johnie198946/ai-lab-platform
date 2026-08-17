//
//  ClarifyCard.swift
//  AIPlatformApp
//
//  澄清选项卡片（对齐 Hermes clarify 协议：question / choices / multi_select）。
//  - 单选（Radio）：轻触即选，点「确认选择」提交；
//  - 多选（Checkbox）：可多选，点「确认选择」批量提交；
//  - 自定义输入：choices 为空时提供自由文本输入框；
//  - 提交后 isSubmitted=true，展示已选结果并禁用重复提交。
//  视觉严格对齐 Quantum 品牌光谱（Cyan #56C8EB / Blue #5B7CEE / Violet #9E6EE8）。
//

import SwiftUI

public struct ClarifyCard: View {
    public let block: ClarifyBlock
    /// 提交回调（nil 时仅展示态：消息流中的非交互预览）
    public var onSubmit: ((String) -> Void)?

    @State private var selectedIDs: Set<String> = []
    @State private var customText: String = ""

    public init(block: ClarifyBlock, onSubmit: ((String) -> Void)? = nil) {
        self.block = block
        self.onSubmit = onSubmit
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            // 头部：图标 + 提问
            HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                Image(systemName: "questionmark.circle.fill")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.quantumBlue)
                Text(block.question)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
            }

            // 已提交态：显示选择结果，替代选项列表
            if block.isSubmitted {
                submittedView
            } else {
                optionsView
                if block.choices.isEmpty {
                    customInputView
                }
                submitButton
            }
        }
        .padding(AppTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                .stroke(
                    LinearGradient(
                        colors: [
                            AppTheme.Colors.quantumCyan.opacity(0.45),
                            AppTheme.Colors.quantumBlue.opacity(0.45),
                            AppTheme.Colors.quantumViolet.opacity(0.45),
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    ),
                    lineWidth: 1
                )
        )
    }

    // MARK: - 选项列表（单选/多选统一胶囊行）

    private var optionsView: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            ForEach(block.choices) { option in
                optionRow(option)
            }
        }
    }

    private func optionRow(_ option: ClarifyOption) -> some View {
        let isSelected = selectedIDs.contains(option.id)
        return Button(action: {
            withAnimation(.easeInOut(duration: 0.18)) {
                if block.multiSelect {
                    if isSelected {
                        selectedIDs.remove(option.id)
                    } else {
                        selectedIDs.insert(option.id)
                    }
                } else {
                    selectedIDs = [option.id]
                }
            }
        }) {
            HStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: block.multiSelect
                      ? (isSelected ? "checkmark.square.fill" : "square")
                      : (isSelected ? "largecircle.fill.circle" : "circle"))
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(isSelected
                                     ? AppTheme.Colors.quantumBlue
                                     : AppTheme.Colors.textTertiary)

                Text(option.label)
                    .font(.system(size: 14, weight: isSelected ? .semibold : .regular))
                    .foregroundColor(isSelected
                                     ? AppTheme.Colors.textPrimary
                                     : AppTheme.Colors.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)

                Spacer(minLength: 0)
            }
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.sm)
            .background(
                RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                    .fill(isSelected
                          ? AppTheme.Colors.quantumBlue.opacity(0.08)
                          : AppTheme.Colors.secondaryBackground)
            )
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                    .stroke(isSelected
                            ? AppTheme.Colors.quantumBlue.opacity(0.5)
                            : AppTheme.Colors.border.opacity(0.4),
                            lineWidth: isSelected ? 1 : 0.5)
            )
        }
        .buttonStyle(SoftButtonStyle())
    }

    // MARK: - 自定义输入（choices 为空时）

    private var customInputView: some View {
        TextField("请输入您的需求…", text: $customText, axis: .vertical)
            .font(.system(size: 14))
            .lineLimit(1...4)
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.sm)
            .background(AppTheme.Colors.secondaryBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                    .stroke(AppTheme.Colors.border.opacity(0.5), lineWidth: 0.5)
            )
    }

    // MARK: - 提交按钮

    private var submitButton: some View {
        let hasSelection = !selectedIDs.isEmpty || !customText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        return Button(action: submit) {
            HStack(spacing: 6) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 14, weight: .semibold))
                Text(block.submitLabel)
                    .font(.system(size: 14, weight: .semibold))
            }
            .foregroundColor(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .background(
                LinearGradient(
                    colors: [
                        AppTheme.Colors.quantumCyan,
                        AppTheme.Colors.quantumBlue,
                        AppTheme.Colors.quantumViolet,
                    ],
                    startPoint: .leading,
                    endPoint: .trailing
                )
                .opacity(hasSelection ? 1 : 0.45)
            )
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        }
        .buttonStyle(SoftButtonStyle())
        .disabled(!hasSelection)
    }

    private func submit() {
        guard !block.isSubmitted else { return }
        let selection: String
        if block.multiSelect {
            selection = selectedIDs
                .compactMap { id in block.choices.first { $0.id == id }?.label }
                .joined(separator: "、")
        } else if let onlyID = selectedIDs.first,
                  let option = block.choices.first(where: { $0.id == onlyID }) {
            selection = option.label
        } else {
            selection = customText.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        guard !selection.isEmpty else { return }
        onSubmit?(selection)
    }

    // MARK: - 已提交态

    private var submittedView: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            HStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.securityGreen)
                Text("已确认：\\(block.submittedSelection)")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
            }
            // 执行中状态：明确告知用户 Agent 正在继续工作（顶设铁律：下一步在干嘛不允许空着）
            HStack(spacing: 8) {
                ProgressView()
                    .controlSize(.small)
                    .tint(AppTheme.Colors.quantumCyan)
                Text("已收到，Agent 继续执行中…")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(AppTheme.Colors.quantumBlue)
            }
            .padding(.top, 2)
        }
        .padding(AppTheme.Spacing.sm)
        .background(AppTheme.Colors.securityGreen.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }
}
