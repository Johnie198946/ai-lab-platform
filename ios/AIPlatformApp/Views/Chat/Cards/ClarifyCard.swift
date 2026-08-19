//
//  ClarifyCard.swift
//  AIPlatformApp
//
//  Clean Native Option Selection Card (Ground-up Rewrite)
//  - Single-select: Tap option -> local selection -> explicit confirm -> stream
//  - Multi-select: Checkboxes -> explicit confirm
//  - Submitted state: Compact green badge with confirmed label
//

import SwiftUI

public struct ClarifyCard: View {
    public let block: ClarifyBlock
    public var onSubmit: ((String) -> Void)? = nil

    @State private var selectedIDs: Set<String> = []
    @State private var customText: String = ""

    public init(block: ClarifyBlock, onSubmit: ((String) -> Void)? = nil) {
        self.block = block
        self.onSubmit = onSubmit
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            headerView
            if block.isSubmitted {
                submittedBadgeView
            } else {
                optionsListView
                if block.choices.isEmpty {
                    customInputView
                }
                submitButtonView
            }
        }
        .padding(AppTheme.Spacing.xl)
        .quantumCard()
    }

    // MARK: - Header
    private var headerView: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            HStack(spacing: AppTheme.Spacing.sm) {
                Label("需求确认", systemImage: "sparkles")
                    .font(AppTheme.Typography.label)
                    .foregroundColor(AppTheme.Icons.intelligence)
                Spacer(minLength: 0)
                Text("逐项收敛")
                    .font(AppTheme.Typography.micro)
                    .foregroundColor(AppTheme.Colors.textSecondary)
                    .padding(.horizontal, AppTheme.Spacing.sm)
                    .padding(.vertical, 5)
                    .background(AppTheme.Colors.surfaceTint)
                    .clipShape(Capsule())
            }

            Text(block.question)
                .font(AppTheme.Typography.sectionTitle)
                .foregroundColor(AppTheme.Colors.textPrimary)
                .fixedSize(horizontal: false, vertical: true)

            Text(helperText)
                .font(AppTheme.Typography.supporting)
                .foregroundColor(AppTheme.Colors.textSecondary)
        }
    }

    private var helperText: String {
        if block.source == "workflow" {
            return block.multiSelect ? "可选择多项，提交后保存到任务需求" : "选择一项并明确确认，任务进度会自动保存"
        }
        return block.multiSelect ? "可选择多项，确认后继续下一个问题" : "选择最符合的一项，确认后继续下一个问题"
    }

    // MARK: - Submitted Badge
    private var submittedBadgeView: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: "checkmark.circle.fill")
                .font(.body.weight(.semibold))
                .foregroundColor(AppTheme.Icons.success)

            Text("已确认：\(block.submittedSelection.isEmpty ? "已提交" : block.submittedSelection)")
                .font(AppTheme.Typography.supporting.weight(.medium))
                .foregroundColor(AppTheme.Colors.textSecondary)

            Spacer()
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.statusCompleted.opacity(0.10))
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    // MARK: - Options List
    private var optionsListView: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            ForEach(block.choices) { option in
                optionRow(option)
            }
        }
    }

    private func optionRow(_ option: ClarifyOption) -> some View {
        let isSelected = selectedIDs.contains(option.id)
        return Button(action: {
            handleOptionTap(option)
        }) {
            HStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: block.multiSelect
                      ? (isSelected ? "checkmark.square.fill" : "square")
                      : (isSelected ? "largecircle.fill.circle" : "circle"))
                    .font(.body.weight(.semibold))
            .foregroundColor(isSelected ? AppTheme.Icons.interactive : AppTheme.Icons.tertiary)

                Text(option.label)
                    .font(AppTheme.Typography.body.weight(isSelected ? .semibold : .regular))
                    .foregroundColor(isSelected ? AppTheme.Colors.textPrimary : AppTheme.Colors.textSecondary)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)

                Spacer(minLength: 0)
            }
            .frame(minHeight: AppTheme.Metrics.inputHeight)
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.xs)
            .background(
                RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                    .fill(isSelected ? AppTheme.Colors.quantumViolet.opacity(0.14) : AppTheme.Colors.secondaryBackground)
            )
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                    .stroke(isSelected ? AppTheme.Colors.interactiveViolet : AppTheme.Colors.border.opacity(0.72),
                            lineWidth: isSelected ? 2 : 0.75)
            )
        }
        .buttonStyle(SoftButtonStyle())
        .accessibilityLabel("\(isSelected ? "已选择" : "未选择")，\(option.label)")
        .accessibilityHint(block.multiSelect ? "轻点切换选择" : "轻点选择，再使用确认并继续按钮提交")
    }

    private func handleOptionTap(_ option: ClarifyOption) {
        guard !block.isSubmitted else { return }
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        #endif

        if block.multiSelect {
            withAnimation(.easeInOut(duration: 0.15)) {
                if selectedIDs.contains(option.id) {
                    selectedIDs.remove(option.id)
                } else {
                    selectedIDs.insert(option.id)
                }
            }
        } else {
            withAnimation(AppTheme.Motion.quick) {
                selectedIDs = [option.id]
            }
        }
    }

    // MARK: - Custom Input (if no choices)
    private var customInputView: some View {
        TextField("请输入您的需求…", text: $customText, axis: .vertical)
            .font(AppTheme.Typography.body)
            .lineLimit(1...4)
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.sm)
            .frame(minHeight: AppTheme.Metrics.inputHeight)
            .background(AppTheme.Colors.secondaryBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                    .stroke(AppTheme.Colors.border.opacity(0.5), lineWidth: 0.5)
            )
            .accessibilityLabel("需求补充内容")
    }

    // MARK: - Multi-select Submit Button
    private var submitButtonView: some View {
        let hasSelection = !selectedIDs.isEmpty || !customText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        return Button(action: submitMultiSelect) {
            Label(block.submitLabel, systemImage: "arrow.right")
        }
        .disabled(!hasSelection)
        .buttonStyle(QuantumPrimaryButtonStyle())
    }

    private func submitMultiSelect() {
        guard !block.isSubmitted else { return }
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        #endif

        let selection: String
        if !block.choices.isEmpty {
            selection = selectedIDs
                .compactMap { id in block.choices.first { $0.id == id }?.label }
                .joined(separator: "、")
        } else {
            selection = customText.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        guard !selection.isEmpty else { return }
        onSubmit?(selection)
    }
}
