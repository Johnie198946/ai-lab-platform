//
//  ClarifyCard.swift
//  AIPlatformApp
//
//  Clean Native Option Selection Card (Ground-up Rewrite)
//  - Single-select: Tap option -> immediate haptic -> submit -> stream
//  - Multi-select: Checkboxes -> submit button
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
                if block.multiSelect || block.choices.isEmpty {
                    submitButtonView
                }
            }
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                .stroke(AppTheme.Colors.assistantBubbleBorder.opacity(0.3), lineWidth: 0.5)
        )
        .shadow(color: Color.black.opacity(0.04), radius: 6, x: 0, y: 2)
    }

    // MARK: - Header
    private var headerView: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            Image(systemName: "questionmark.circle.fill")
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(AppTheme.Colors.quantumCyan)
                .padding(.top, 1)

            Text(block.question)
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(AppTheme.Colors.textPrimary)
                .fixedSize(horizontal: false, vertical: true)

            Spacer(minLength: 0)
        }
    }

    // MARK: - Submitted Badge
    private var submittedBadgeView: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(AppTheme.Colors.securityGreen)

            Text("已确认：\(block.submittedSelection.isEmpty ? "已提交" : block.submittedSelection)")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(AppTheme.Colors.textSecondary)

            Spacer()
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, 8)
        .background(AppTheme.Colors.securityGreen.opacity(0.08))
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
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(isSelected ? AppTheme.Colors.quantumBlue : AppTheme.Colors.textTertiary)

                Text(option.label)
                    .font(.system(size: 14, weight: isSelected ? .semibold : .regular))
                    .foregroundColor(isSelected ? AppTheme.Colors.textPrimary : AppTheme.Colors.textSecondary)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)

                Spacer(minLength: 0)
            }
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.sm)
            .background(
                RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                    .fill(isSelected ? AppTheme.Colors.quantumBlue.opacity(0.08) : AppTheme.Colors.secondaryBackground)
            )
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                    .stroke(isSelected ? AppTheme.Colors.quantumBlue.opacity(0.5) : AppTheme.Colors.border.opacity(0.4),
                            lineWidth: isSelected ? 1 : 0.5)
            )
        }
        .buttonStyle(SoftButtonStyle())
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
            // 单选：点击直接触发提交
            selectedIDs = [option.id]
            onSubmit?(option.label)
        }
    }

    // MARK: - Custom Input (if no choices)
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

    // MARK: - Multi-select Submit Button
    private var submitButtonView: some View {
        let hasSelection = !selectedIDs.isEmpty || !customText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        return Button(action: submitMultiSelect) {
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
                    colors: [AppTheme.Colors.quantumCyan, AppTheme.Colors.quantumBlue, AppTheme.Colors.quantumViolet],
                    startPoint: .leading,
                    endPoint: .trailing
                )
                .opacity(hasSelection ? 1 : 0.45)
            )
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        }
        .disabled(!hasSelection)
        .buttonStyle(SoftButtonStyle())
    }

    private func submitMultiSelect() {
        guard !block.isSubmitted else { return }
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        #endif

        let selection: String
        if block.multiSelect {
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
