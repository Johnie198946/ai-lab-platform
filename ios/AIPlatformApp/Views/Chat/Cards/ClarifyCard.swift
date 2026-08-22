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
    public var onRecover: (() -> Void)? = nil

    @State private var selectedIDs: Set<String> = []
    @State private var customText: String = ""

    public init(
        block: ClarifyBlock,
        onSubmit: ((String) -> Void)? = nil,
        onRecover: (() -> Void)? = nil
    ) {
        self.block = block
        self.onSubmit = onSubmit
        self.onRecover = onRecover
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            headerView
            if block.submissionState == .expired {
                expiredRecoveryView
            } else if [.submitting, .reconciling].contains(block.submissionState) {
                submittingView
            } else if block.isSubmitted {
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

    private var submittingView: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            ProgressView()
            Text(block.submissionState == .reconciling ? "正在核对服务端状态…" : "正在提交确认…")
                .font(AppTheme.Typography.supporting.weight(.medium))
                .foregroundColor(AppTheme.Colors.textSecondary)
            Spacer()
        }
        .frame(minHeight: AppTheme.Metrics.inputHeight)
        .padding(.horizontal, AppTheme.Spacing.md)
        .background(AppTheme.Colors.surfaceTint)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    private var expiredRecoveryView: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Label("本次确认已超时，系统不会自动重复执行", systemImage: "clock.badge.exclamationmark")
                .font(AppTheme.Typography.supporting.weight(.semibold))
                .foregroundColor(AppTheme.Colors.textSecondary)
            Button(action: { onRecover?() }) {
                Label("确认后恢复任务", systemImage: "arrow.clockwise")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(QuantumPrimaryButtonStyle())
        }
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
            if let seconds = block.expiresInSeconds, seconds > 0, !block.isSubmitted {
                Text("等待确认剩余约 \(seconds) 秒")
                    .font(AppTheme.Typography.micro)
                    .foregroundColor(AppTheme.Colors.textSecondary)
            }
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
        guard !block.isSubmitted, block.submissionState != .submitting else { return }
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
                .joined(separator: ", ")
        } else {
            selection = customText.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        guard !selection.isEmpty else { return }
        onSubmit?(selection)
    }
}

// MARK: - Workflow Requirement Confirmation

/// Final requirement checkpoint used by workflow clarification.
/// It turns the server's summary text into a scan-friendly decision document while
/// preserving the exact choice labels expected by the workflow state machine.
public struct RequirementConfirmationCard: View {
    public let block: ClarifyBlock
    public var onSubmit: ((String) -> Void)? = nil

    @State private var selectedID: String?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init(block: ClarifyBlock, onSubmit: ((String) -> Void)? = nil) {
        self.block = block
        self.onSubmit = onSubmit
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xl) {
            confirmationHeader
            requirementSummary
            decisionSection
        }
        .padding(AppTheme.Spacing.xl)
        .quantumCard()
        .accessibilityElement(children: .contain)
    }

    private var confirmationHeader: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack(spacing: AppTheme.Spacing.md) {
                Image(systemName: "checkmark.seal.fill")
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(AppTheme.Icons.onAccent)
                    .frame(width: 44, height: 44)
                    .background(AppTheme.Colors.actionGradient, in: Circle())
                    .accessibilityHidden(true)

                VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                    Text("需求收敛确认单")
                        .font(AppTheme.Typography.cardTitle)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    Text("确认后将据此生成可审阅方案")
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                }

                Spacer(minLength: 0)
            }

            HStack(spacing: AppTheme.Spacing.sm) {
                Label("已完成澄清", systemImage: "checkmark.circle.fill")
                Text("·")
                Text("\(summaryItems.count) 项边界已收敛")
            }
            .font(AppTheme.Typography.micro)
            .foregroundStyle(AppTheme.Colors.textSecondary)
            .padding(.horizontal, AppTheme.Spacing.md)
            .frame(minHeight: 32)
            .background(AppTheme.Colors.statusCompleted.opacity(0.10), in: Capsule())
        }
    }

    @ViewBuilder
    private var requirementSummary: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            Text("任务边界")
                .font(AppTheme.Typography.label)
                .foregroundStyle(AppTheme.Colors.textSecondary)
                .textCase(.uppercase)

            if let goal = summaryItems.first(where: { $0.kind == .goal }) {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    Label(goal.title, systemImage: goal.icon)
                        .font(AppTheme.Typography.label)
                        .foregroundStyle(AppTheme.Icons.intelligence)
                    Text(goal.value)
                        .font(AppTheme.Typography.body)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(AppTheme.Spacing.lg)
                .background(AppTheme.Colors.surfaceTint)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            }

            VStack(spacing: 0) {
                ForEach(Array(summaryItems.filter { $0.kind != .goal }.enumerated()), id: \.element.id) { index, item in
                    summaryRow(item)
                    if index < summaryItems.filter({ $0.kind != .goal }).count - 1 {
                        Divider().padding(.leading, 52)
                    }
                }
            }
            .padding(.horizontal, AppTheme.Spacing.lg)
            .background(AppTheme.Colors.secondaryBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        }
    }

    private func summaryRow(_ item: RequirementSummaryItem) -> some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
            Image(systemName: item.icon)
                .font(.body.weight(.semibold))
                .foregroundStyle(AppTheme.Icons.interactive)
                .frame(width: 36, height: 36)
                .background(AppTheme.Colors.quantumBlue.opacity(0.10), in: Circle())
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                Text(item.title)
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                Text(item.value)
                    .font(AppTheme.Typography.supporting.weight(.medium))
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.vertical, AppTheme.Spacing.md)
        .accessibilityElement(children: .combine)
    }

    private var decisionSection: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                Text("下一步")
                    .font(AppTheme.Typography.label)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Text("请确认内容是否准确，你的选择会立即保存")
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            }

            VStack(spacing: AppTheme.Spacing.sm) {
                ForEach(block.choices) { option in
                    decisionButton(option)
                }
            }

            Button(action: submitSelection) {
                Label(primaryActionTitle, systemImage: primaryActionIcon)
            }
            .disabled(selectedID == nil)
            .buttonStyle(QuantumPrimaryButtonStyle())
            .accessibilityHint("提交当前选择并进入下一阶段")
        }
    }

    private func decisionButton(_ option: ClarifyOption) -> some View {
        let selected = selectedID == option.id
        let affirmative = option.label.hasPrefix("确认") || option.label.contains("进入方案")
        return Button {
            #if os(iOS)
            UISelectionFeedbackGenerator().selectionChanged()
            #endif
            withAnimation(reduceMotion ? nil : AppTheme.Motion.quick) {
                selectedID = option.id
            }
        } label: {
            HStack(spacing: AppTheme.Spacing.md) {
                Image(systemName: affirmative ? "checkmark.circle" : "pencil.circle")
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(selected ? AppTheme.Icons.onAccent : AppTheme.Icons.secondary)
                    .frame(width: 40, height: 40)
                    .background(
                        selected ? AppTheme.Colors.actionGradient : LinearGradient(
                            colors: [AppTheme.Colors.secondaryBackground, AppTheme.Colors.secondaryBackground],
                            startPoint: .leading,
                            endPoint: .trailing
                        ),
                        in: Circle()
                    )

                VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                    Text(affirmative ? "内容准确" : "需要调整")
                        .font(AppTheme.Typography.cardTitle)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    Text(affirmative ? "锁定需求，进入方案设计" : "继续补充或修改任务边界")
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                }
                .multilineTextAlignment(.leading)

                Spacer(minLength: 0)

                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                    .font(.title3)
                    .foregroundStyle(selected ? AppTheme.Icons.interactive : AppTheme.Icons.tertiary)
                    .accessibilityHidden(true)
            }
            .frame(maxWidth: .infinity, minHeight: 68, alignment: .leading)
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.sm)
            .background(selected ? AppTheme.Colors.quantumViolet.opacity(0.10) : AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                    .stroke(selected ? AppTheme.Colors.interactiveViolet : AppTheme.Colors.border, lineWidth: selected ? 1.5 : 0.75)
            }
        }
        .buttonStyle(SoftButtonStyle())
        .accessibilityLabel("\(selected ? "已选择" : "未选择")，\(affirmative ? "内容准确" : "需要调整")")
        .accessibilityHint(affirmative ? "锁定需求并进入方案设计" : "返回需求澄清继续修改")
    }

    private var selectedOption: ClarifyOption? {
        guard let selectedID else { return nil }
        return block.choices.first { $0.id == selectedID }
    }

    private var primaryActionTitle: String {
        guard let option = selectedOption else { return "请选择下一步" }
        return option.label.hasPrefix("确认") || option.label.contains("进入方案")
            ? "确认并生成方案"
            : "返回继续澄清"
    }

    private var primaryActionIcon: String {
        guard let option = selectedOption else { return "arrow.right" }
        return option.label.hasPrefix("确认") || option.label.contains("进入方案")
            ? "wand.and.stars"
            : "arrow.uturn.backward"
    }

    private func submitSelection() {
        guard let option = selectedOption else { return }
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        #endif
        onSubmit?(option.label)
    }

    private var summaryItems: [RequirementSummaryItem] {
        let parsed = RequirementSummaryItem.parse(block.question)
        if !parsed.isEmpty { return parsed }
        return [
            RequirementSummaryItem(
                kind: .goal,
                title: "需求说明",
                value: block.question,
                icon: "scope"
            )
        ]
    }
}

private struct RequirementSummaryItem: Identifiable {
    enum Kind { case goal, deliverable, audience, scope, acceptance, other }

    let id = UUID()
    let kind: Kind
    let title: String
    let value: String
    let icon: String

    static func parse(_ question: String) -> [RequirementSummaryItem] {
        let definitions: [(prefix: String, kind: Kind, title: String, icon: String)] = [
            ("目标：", .goal, "任务目标", "scope"),
            ("交付物：", .deliverable, "交付成果", "doc.richtext"),
            ("目标用户与场景：", .audience, "使用对象", "person.crop.circle"),
            ("MVP 范围：", .scope, "首期范围", "square.dashed.inset.filled"),
            ("约束与验收：", .acceptance, "验收标准", "checkmark.shield")
        ]
        return question
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .compactMap { line in
                guard !line.isEmpty, !line.hasPrefix("请确认需求单") else { return nil }
                guard let definition = definitions.first(where: { line.hasPrefix($0.prefix) }) else {
                    return RequirementSummaryItem(kind: .other, title: "补充说明", value: line, icon: "text.alignleft")
                }
                let value = String(line.dropFirst(definition.prefix.count)).trimmingCharacters(in: .whitespaces)
                guard !value.isEmpty else { return nil }
                return RequirementSummaryItem(
                    kind: definition.kind,
                    title: definition.title,
                    value: value,
                    icon: definition.icon
                )
            }
    }
}
