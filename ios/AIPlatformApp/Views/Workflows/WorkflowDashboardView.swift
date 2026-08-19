import SwiftUI

// MARK: - 工作流主页

public struct WorkflowDashboardView: View {
    @StateObject private var model = WorkflowDashboardModel()
    @State private var showingCreate = false
    @State private var showingTopology = false

    public init() {}

    public var body: some View {
        NavigationStack {
            Group {
                if model.isLoading && model.workflows.isEmpty {
                    ProgressView("正在读取工作流…")
                } else if model.workflows.isEmpty {
                    emptyState
                } else {
                    ScrollView {
                        LazyVStack(spacing: AppTheme.Spacing.lg) {
                            ForEach(model.workflows) { workflow in
                                NavigationLink(value: workflow) {
                                    WorkflowSummaryCard(workflow: workflow)
                                }
                                .buttonStyle(SoftButtonStyle())
                            }
                        }
                        .padding(AppTheme.Metrics.contentGutter)
                    }
                    .refreshable { await model.load() }
                }
            }
            .background(AppTheme.Colors.background.ignoresSafeArea())
            .navigationTitle("任务")
            .navigationDestination(for: WorkflowDTO.self) { workflow in
                WorkflowDetailView(workflow: workflow) {
                    await model.load()
                }
            }
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button("协同拓扑", systemImage: "point.3.connected.trianglepath.dotted") {
                        showingTopology = true
                    }
                    .accessibilityHint("查看 Agent、工具与知识依赖")
                    Button("创建工作流", systemImage: "plus") {
                        showingCreate = true
                    }
                }
            }
            .overlay(alignment: .top) {
                if let error = model.errorMessage {
                    WorkflowErrorBanner(message: error)
                        .padding(.top, AppTheme.Spacing.sm)
                }
            }
            .sheet(isPresented: $showingCreate) {
                WorkflowCreateSheet { created in
                    showingCreate = false
                    await model.load()
                }
            }
            .sheet(isPresented: $showingTopology) {
                NavigationStack { TopologyCanvasView() }
            }
            .task { await model.load() }
        }
    }

    private var emptyState: some View {
        ContentUnavailableView {
            Label("还没有工作流", systemImage: "square.stack.3d.up")
        } description: {
            Text("描述你想获得的结果。Quantum 会先生成可编辑计划，确认后才开始执行。")
        } actions: {
            Button("创建第一个工作流") { showingCreate = true }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
        }
    }
}

@MainActor
private final class WorkflowDashboardModel: ObservableObject {
    @Published var workflows: [WorkflowDTO] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            workflows = try await APIClient.shared.fetchWorkflows()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct WorkflowSummaryCard: View {
    let workflow: WorkflowDTO
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                    Text(workflow.title)
                        .font(AppTheme.Typography.screenTitle)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .multilineTextAlignment(.leading)
                    Text(workflow.description)
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)
                }
                Spacer(minLength: AppTheme.Spacing.sm)
                WorkflowStatusBadge(status: workflow.latestExecution?.status ?? workflow.status)
            }

            ProgressView(value: Double(workflow.latestExecution?.progress ?? planningProgress))
                .tint(AppTheme.Colors.quantumBlue)

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: AppTheme.Spacing.sm) {
                WorkflowStageChip(icon: "list.clipboard", title: "需求与计划", state: planningState)
                WorkflowStageChip(icon: "doc.text.magnifyingglass", title: "知识与证据", state: executionState(0))
                WorkflowStageChip(icon: "person.3.sequence", title: "Agent 协作", state: executionState(1))
                WorkflowStageChip(icon: "checkmark.shield", title: "复核与归档", state: reviewState)
            }

            HStack {
                Label(workflow.desiredOutput, systemImage: "doc.richtext")
                    .lineLimit(1)
                Spacer()
                Image(systemName: "chevron.right")
            }
            .font(AppTheme.Typography.label)
            .foregroundStyle(AppTheme.Colors.textSecondary)
        }
        .padding(AppTheme.Spacing.xl)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.xl)
                .stroke(AppTheme.Colors.border, lineWidth: 1)
        }
        .cardShadow(colorScheme: colorScheme)
        .accessibilityElement(children: .combine)
    }

    private var planningProgress: Int { workflow.status == "awaiting_approval" ? 15 : 0 }
    private var planningState: String { workflow.status == "awaiting_approval" ? "待确认" : "已确认" }
    private func executionState(_ offset: Int) -> String {
        guard let execution = workflow.latestExecution else { return "未开始" }
        if execution.status == "failed" { return "需处理" }
        if execution.progress > (offset == 0 ? 15 : 45) { return "进行中" }
        return "等待中"
    }
    private var reviewState: String {
        switch workflow.latestExecution?.status {
        case "awaiting_review": return "待复核"
        case "completed": return "已归档"
        default: return "未开始"
        }
    }
}

private struct WorkflowStageChip: View {
    let icon: String
    let title: String
    let state: String

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Image(systemName: icon)
                .font(.body.weight(.semibold))
                .foregroundStyle(AppTheme.Colors.quantumBlue)
                .frame(width: 32, height: 32)
                .background(AppTheme.Colors.quantumBlue.opacity(0.12), in: Circle())
            Text(title).font(AppTheme.Typography.cardTitle)
            Text(state)
                .font(AppTheme.Typography.micro)
                .foregroundStyle(AppTheme.Colors.textSecondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.secondaryBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
    }
}

// MARK: - 创建

private struct WorkflowCreateSheet: View {
    let onCreated: (WorkflowCreateResponseDTO) async -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var title = ""
    @State private var description = ""
    @State private var output = "研究报告（Markdown）"
    @State private var isSubmitting = false
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("工作流") {
                    TextField("名称，例如：拜仁洞察", text: $title)
                        .textInputAutocapitalization(.never)
                    TextField("详细描述目标、范围和你希望看到的结果", text: $description, axis: .vertical)
                        .lineLimit(5...10)
                }
                Section("交付物") {
                    TextField("例如：带引用的 Markdown 研究报告", text: $output)
                }
                Section {
                    Label("创建后只生成执行计划；确认计划前不会联网或消耗执行 Token。", systemImage: "lock.shield")
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                }
                if let errorMessage {
                    Section { Text(errorMessage).foregroundStyle(AppTheme.Colors.statusError) }
                }
            }
            .navigationTitle("创建工作流")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                        .disabled(isSubmitting)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(isSubmitting ? "生成中…" : "生成计划") { submit() }
                        .disabled(title.trimmingCharacters(in: .whitespaces).isEmpty || description.count < 3 || isSubmitting)
                }
            }
            .interactiveDismissDisabled(isSubmitting)
        }
    }

    private func submit() {
        isSubmitting = true
        errorMessage = nil
        Task {
            do {
                let created = try await APIClient.shared.createWorkflow(
                    title: title, description: description, desiredOutput: output
                )
                await onCreated(created)
            } catch {
                errorMessage = error.localizedDescription
                isSubmitting = false
            }
        }
    }
}

// MARK: - 详情与计划确认

private struct WorkflowDetailView: View {
    let workflow: WorkflowDTO
    let onChanged: () async -> Void
    @State private var current: WorkflowDTO
    @State private var execution: WorkflowExecutionDTO?

    init(workflow: WorkflowDTO, onChanged: @escaping () async -> Void) {
        self.workflow = workflow
        self.onChanged = onChanged
        _current = State(initialValue: workflow)
        _execution = State(initialValue: workflow.latestExecution)
    }

    var body: some View {
        Group {
            if current.status == "awaiting_approval" && execution == nil {
                WorkflowPlanReviewView(workflow: current) { createdExecution in
                    execution = createdExecution
                    Task { await onChanged() }
                }
            } else if let execution {
                WorkflowExecutionView(workflow: current, initialExecution: execution)
            } else {
                ProgressView("正在恢复工作流状态…")
            }
        }
        .navigationTitle(current.title)
        .navigationBarTitleDisplayMode(.inline)
        .task { await refresh() }
    }

    private func refresh() async {
        do {
            current = try await APIClient.shared.fetchWorkflow(id: workflow.id)
            execution = current.latestExecution
        } catch { }
    }
}

private struct WorkflowPlanReviewView: View {
    let workflow: WorkflowDTO
    let onApproved: (WorkflowExecutionDTO) -> Void
    @State private var plan: WorkflowPlanDTO?
    @State private var tenantAgents: [TenantAgentDTO] = []
    @State private var availableKnowledgeScopes: [String] = []
    @State private var isSaving = false
    @State private var errorMessage: String?
    @State private var replanInstruction = ""
    @State private var approvalRequestId = UUID().uuidString

    var body: some View {
        Group {
            if let draft = plan {
                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.xl) {
                        planHeader(draft)
                        configuration(plan: planBinding)
                        nodeTimeline(plan: planBinding)
                        replanSection
                        if let errorMessage { WorkflowErrorBanner(message: errorMessage) }
                    }
                    .padding(AppTheme.Metrics.contentGutter)
                    .padding(.bottom, 96)
                }
                .safeAreaInset(edge: .bottom) {
                    HStack(spacing: AppTheme.Spacing.md) {
                        Button("保存修改") { save() }
                            .buttonStyle(.bordered)
                            .frame(maxWidth: .infinity)
                        Button("确认并执行") { approve() }
                            .buttonStyle(.borderedProminent)
                            .frame(maxWidth: .infinity)
                    }
                    .controlSize(.large)
                    .padding(AppTheme.Metrics.contentGutter)
                    .background(.ultraThinMaterial)
                }
                .disabled(isSaving)
            } else {
                ProgressView("正在读取执行计划…")
            }
        }
        .task { await load() }
    }

    private var planBinding: Binding<WorkflowPlanDTO> {
        Binding(
            get: { plan! },
            set: { plan = $0 }
        )
    }

    private func planHeader(_ plan: WorkflowPlanDTO) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            Label("计划 v\(plan.version) · 等待确认", systemImage: "checklist.checked")
                .font(AppTheme.Typography.label)
                .foregroundStyle(AppTheme.Colors.quantumBlue)
            Text(plan.goal)
                .font(AppTheme.Typography.screenTitle)
            HStack {
                Label("预计 \(plan.estimatedTokens) tokens", systemImage: "gauge.with.dots.needle.50percent")
                Label(plan.allowNetwork ? "允许证据缺口联网" : "仅知识库", systemImage: plan.allowNetwork ? "network" : "internaldrive")
            }
            .font(AppTheme.Typography.micro)
            .foregroundStyle(AppTheme.Colors.textSecondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(AppTheme.Spacing.xl)
        .background(AppTheme.Colors.surfaceTint)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xl))
    }

    private func configuration(plan: Binding<WorkflowPlanDTO>) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            Text("执行边界").font(AppTheme.Typography.sectionTitle)
            TextField("最终交付物", text: plan.deliverable)
                .textFieldStyle(.roundedBorder)
            Toggle(
                "知识库无证据时允许联网补充",
                isOn: Binding(
                    get: { plan.wrappedValue.allowNetwork },
                    set: { enabled in
                        plan.wrappedValue.allowNetwork = enabled
                        for index in plan.wrappedValue.dsl.nodes.indices {
                            plan.wrappedValue.dsl.nodes[index].parameters.allowNetwork = enabled
                        }
                    }
                )
            )
            Stepper("Token 上限：\(plan.wrappedValue.maxTokens)", value: plan.maxTokens, in: 4000...128000, step: 2000)
            if !availableKnowledgeScopes.isEmpty {
                Text("知识范围").font(AppTheme.Typography.label)
                ForEach(availableKnowledgeScopes, id: \.self) { scope in
                    Toggle(
                        scope,
                        isOn: Binding(
                            get: { plan.wrappedValue.knowledgeScope.contains(scope) },
                            set: { enabled in
                                if enabled {
                                    if !plan.wrappedValue.knowledgeScope.contains(scope) {
                                        plan.wrappedValue.knowledgeScope.append(scope)
                                    }
                                } else {
                                    plan.wrappedValue.knowledgeScope.removeAll { $0 == scope }
                                }
                                for index in plan.wrappedValue.dsl.nodes.indices {
                                    plan.wrappedValue.dsl.nodes[index].parameters.knowledgeScope = plan.wrappedValue.knowledgeScope
                                }
                            }
                        )
                    )
                }
            }
        }
        .padding(AppTheme.Spacing.lg)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg))
    }

    private func nodeTimeline(plan: Binding<WorkflowPlanDTO>) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack {
                Text("执行步骤").font(AppTheme.Typography.sectionTitle)
                Spacer()
                Button("添加", systemImage: "plus") { addNode() }
            }
            ForEach(plan.wrappedValue.dsl.nodes.indices, id: \.self) { index in
                WorkflowPlanNodeEditor(
                    index: index,
                    node: plan.dsl.nodes[index],
                    agents: tenantAgents,
                    isLast: index == plan.wrappedValue.dsl.nodes.count - 1,
                    onDelete: { deleteNode(at: index) },
                    onMoveUp: { moveNode(from: index, to: index - 1) },
                    onMoveDown: { moveNode(from: index, to: index + 1) }
                )
            }
        }
    }

    private var replanSection: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Text("让 Quantum 重新规划").font(AppTheme.Typography.sectionTitle)
            TextField("例如：增加竞品对比和近三个月新闻", text: $replanInstruction, axis: .vertical)
                .textFieldStyle(.roundedBorder)
            Button("按意见重新生成", systemImage: "arrow.triangle.2.circlepath") { replan() }
                .disabled(replanInstruction.trimmingCharacters(in: .whitespaces).isEmpty)
        }
    }

    private func load() async {
        do {
            async let loadedPlan = APIClient.shared.fetchWorkflowPlan(workflowId: workflow.id)
            async let loadedAgents = APIClient.shared.fetchTenantAgents()
            async let loadedScopes = APIClient.shared.fetchSubscriptions()
            plan = try await loadedPlan
            tenantAgents = (try? await loadedAgents) ?? []
            availableKnowledgeScopes = (try? await loadedScopes) ?? plan?.knowledgeScope ?? []
        } catch { errorMessage = error.localizedDescription }
    }

    private func save() {
        guard let plan else { return }
        isSaving = true
        Task {
            do {
                self.plan = try await APIClient.shared.updateWorkflowPlan(workflowId: workflow.id, plan: plan)
                errorMessage = nil
            } catch { errorMessage = error.localizedDescription }
            isSaving = false
        }
    }

    private func approve() {
        guard let plan else { return }
        isSaving = true
        Task {
            do {
                _ = try await APIClient.shared.updateWorkflowPlan(workflowId: workflow.id, plan: plan)
                let execution = try await APIClient.shared.approveWorkflowPlan(
                    workflowId: workflow.id,
                    requestId: approvalRequestId
                )
                onApproved(execution)
            } catch {
                errorMessage = error.localizedDescription
                isSaving = false
            }
        }
    }

    private func replan() {
        isSaving = true
        Task {
            do {
                plan = try await APIClient.shared.replanWorkflow(workflowId: workflow.id, instruction: replanInstruction)
                replanInstruction = ""
            } catch { errorMessage = error.localizedDescription }
            isSaving = false
        }
    }

    private func addNode() {
        guard var plan else { return }
        let id = "custom_\(UUID().uuidString.lowercased().replacingOccurrences(of: "-", with: ""))"
        plan.dsl.nodes.append(
            WorkflowPlanNodeDTO(
                id: id,
                nodeType: "PROMPT_TRANSFORM",
                name: "新增处理步骤",
                parameters: WorkflowNodeParametersDTO(
                    agentId: "main_agent", query: nil, instruction: "",
                    outputFormat: nil, knowledgeScope: plan.knowledgeScope,
                    allowNetwork: plan.allowNetwork, requiresReview: false,
                    maxTokens: 3000, revisionNote: nil
                )
            )
        )
        self.plan = rebuiltEdges(plan)
    }

    private func deleteNode(at index: Int) {
        guard var plan, plan.dsl.nodes.count > 1 else { return }
        plan.dsl.nodes.remove(at: index)
        self.plan = rebuiltEdges(plan)
    }

    private func moveNode(from: Int, to: Int) {
        guard var plan, plan.dsl.nodes.indices.contains(from), plan.dsl.nodes.indices.contains(to) else { return }
        let node = plan.dsl.nodes.remove(at: from)
        plan.dsl.nodes.insert(node, at: to)
        self.plan = rebuiltEdges(plan)
    }

    private func rebuiltEdges(_ value: WorkflowPlanDTO) -> WorkflowPlanDTO {
        var copy = value
        copy.dsl.edges = zip(copy.dsl.nodes, copy.dsl.nodes.dropFirst()).map {
            WorkflowPlanEdgeDTO(source: $0.id, target: $1.id, condition: nil)
        }
        return copy
    }
}

private struct WorkflowPlanNodeEditor: View {
    let index: Int
    @Binding var node: WorkflowPlanNodeDTO
    let agents: [TenantAgentDTO]
    let isLast: Bool
    let onDelete: () -> Void
    let onMoveUp: () -> Void
    let onMoveDown: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
            VStack(spacing: 0) {
                Text("\(index + 1)")
                    .font(AppTheme.Typography.label)
                    .foregroundStyle(.white)
                    .frame(width: 28, height: 28)
                    .background(AppTheme.Colors.quantumBlue, in: Circle())
                Rectangle().fill(AppTheme.Colors.border).frame(width: 1, height: 92)
            }
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                TextField("步骤名称", text: Binding(get: { node.name ?? "" }, set: { node.name = $0 }))
                    .font(AppTheme.Typography.cardTitle)
                Text(node.nodeType.replacingOccurrences(of: "_", with: " "))
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.textTertiary)
                Menu {
                    ForEach(["main_agent", "knowledge", "coder", "supervision"], id: \.self) { id in
                        Button(id) { node.parameters.agentId = id }
                    }
                    ForEach(agents) { agent in
                        Button(agent.customName ?? agent.id) { node.parameters.agentId = agent.id }
                    }
                } label: {
                    Label(node.parameters.agentId ?? "main_agent", systemImage: "person.crop.circle.badge.checkmark")
                }
                TextField(
                    "节点执行要求",
                    text: Binding(
                        get: { node.parameters.instruction ?? node.parameters.query ?? "" },
                        set: { node.parameters.instruction = $0; node.parameters.query = nil }
                    ),
                    axis: .vertical
                )
                .font(AppTheme.Typography.supporting)
                HStack {
                    Button("上移", systemImage: "arrow.up", action: onMoveUp).disabled(index == 0)
                    Button("下移", systemImage: "arrow.down", action: onMoveDown).disabled(isLast)
                    Spacer()
                    Button("删除", systemImage: "trash", role: .destructive, action: onDelete)
                }
                .labelStyle(.iconOnly)
                .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                Stepper(
                    "节点预算：\(node.parameters.maxTokens ?? 3000)",
                    value: Binding(
                        get: { node.parameters.maxTokens ?? 3000 },
                        set: { node.parameters.maxTokens = $0 }
                    ),
                    in: 1000...32000,
                    step: 1000
                )
                .font(AppTheme.Typography.micro)
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg))
        }
    }
}

// MARK: - 执行与成果复核

private struct WorkflowExecutionView: View {
    let workflow: WorkflowDTO
    @State private var execution: WorkflowExecutionDTO
    @State private var artifacts: [WorkflowArtifactDTO] = []
    @State private var selectedArtifacts: Set<String> = []
    @State private var selectedArtifact: WorkflowArtifactDTO?
    @State private var errorMessage: String?
    @State private var isWorking = false

    init(workflow: WorkflowDTO, initialExecution: WorkflowExecutionDTO) {
        self.workflow = workflow
        _execution = State(initialValue: initialExecution)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xl) {
                executionHeader
                nodeProgress
                if execution.status == "awaiting_review" || execution.status == "completed" {
                    artifactReview
                }
                if let errorMessage { WorkflowErrorBanner(message: errorMessage) }
            }
            .padding(AppTheme.Metrics.contentGutter)
            .padding(.bottom, 88)
        }
        .safeAreaInset(edge: .bottom) { actionBar }
        .task { await monitor() }
        .sheet(item: $selectedArtifact) { artifact in
            WorkflowArtifactPreview(executionId: execution.id, artifact: artifact)
        }
    }

    private var executionHeader: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack {
                WorkflowStatusBadge(status: execution.status)
                Spacer()
                Text("\(execution.progress)%").font(AppTheme.Typography.screenTitle)
            }
            ProgressView(value: Double(execution.progress), total: 100)
                .tint(AppTheme.Colors.quantumBlue)
            HStack {
                Label("\(execution.tokenUsed) / \(execution.tokenBudget) tokens", systemImage: "gauge.with.dots.needle.50percent")
                Spacer()
                Label("\(execution.artifactCount) 个产物", systemImage: "doc.on.doc")
            }
            .font(AppTheme.Typography.micro)
            .foregroundStyle(AppTheme.Colors.textSecondary)
            if let model = execution.modelUsed, !model.isEmpty {
                Label(
                    "\(model) · \(execution.providerUsed ?? "自动路由")",
                    systemImage: "point.3.connected.trianglepath.dotted"
                )
                .font(AppTheme.Typography.supporting)
                .foregroundStyle(AppTheme.Colors.textSecondary)
            }
            if let reason = execution.routeReason, !reason.isEmpty {
                Text(reason)
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.textTertiary)
            }
            usageBreakdown
        }
        .padding(AppTheme.Spacing.xl)
        .background(AppTheme.Colors.surfaceTint)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xl))
    }

    private var usageBreakdown: some View {
        let input = execution.inputTokens ?? 0
        let output = execution.outputTokens ?? 0
        let reasoning = execution.reasoningTokens ?? 0
        let cached = execution.cacheReadTokens ?? 0
        return VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
            HStack(spacing: AppTheme.Spacing.md) {
                Text("输入 \(input)")
                Text("输出 \(output)")
                if reasoning > 0 { Text("推理 \(reasoning)") }
            }
            HStack(spacing: AppTheme.Spacing.md) {
                Label("缓存命中 \(cached)", systemImage: "bolt.horizontal.circle")
                Text("\(execution.apiCalls ?? 0) 次调用")
                if let cost = execution.estimatedCostUsd, cost > 0 {
                    Text(cost, format: .currency(code: "USD"))
                }
            }
        }
        .font(AppTheme.Typography.micro)
        .foregroundStyle(AppTheme.Colors.textSecondary)
        .accessibilityElement(children: .combine)
    }

    private var nodeProgress: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            Text("实时执行").font(AppTheme.Typography.sectionTitle)
            ForEach(execution.nodes) { node in
                HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                    Image(systemName: nodeIcon(node.status))
                        .foregroundStyle(nodeColor(node.status))
                        .frame(width: 28, height: 28)
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                        Text(node.name).font(AppTheme.Typography.cardTitle)
                        Text("\(node.agentId) · \(node.tokenUsed) tokens")
                            .font(AppTheme.Typography.micro)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                        if let model = node.modelUsed, !model.isEmpty {
                            Text("\(model) · \(node.providerUsed ?? "自动路由") · 缓存 \(node.cacheReadTokens ?? 0)")
                                .font(AppTheme.Typography.micro)
                                .foregroundStyle(AppTheme.Colors.textTertiary)
                        }
                        if let error = node.errorMessage {
                            Text(error).font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.statusError)
                        }
                    }
                    Spacer()
                    Text(node.status.workflowStatusLabel)
                        .font(AppTheme.Typography.micro)
                }
                .padding(AppTheme.Spacing.md)
                .background(AppTheme.Colors.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
            }
        }
    }

    private var artifactReview: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            Text("成果与入库素材").font(AppTheme.Typography.sectionTitle)
            Text("所有内容已保存到工作流档案。勾选后批准，才会进入正式知识库。")
                .font(AppTheme.Typography.supporting)
                .foregroundStyle(AppTheme.Colors.textSecondary)
            ForEach(artifacts) { artifact in
                HStack(spacing: AppTheme.Spacing.md) {
                    Button {
                        if selectedArtifacts.contains(artifact.id) { selectedArtifacts.remove(artifact.id) }
                        else { selectedArtifacts.insert(artifact.id) }
                    } label: {
                        Image(systemName: selectedArtifacts.contains(artifact.id) ? "checkmark.square.fill" : "square")
                            .foregroundStyle(AppTheme.Colors.quantumBlue)
                            .frame(width: 44, height: 44)
                    }
                    Button {
                        selectedArtifact = artifact
                    } label: {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(artifact.title).font(AppTheme.Typography.cardTitle).lineLimit(2)
                            Text(artifact.kind).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .buttonStyle(.plain)
                    Image(systemName: "chevron.right").foregroundStyle(AppTheme.Colors.textTertiary)
                }
                .padding(AppTheme.Spacing.sm)
                .background(AppTheme.Colors.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
            }
        }
    }

    @ViewBuilder
    private var actionBar: some View {
        HStack(spacing: AppTheme.Spacing.md) {
            if execution.status == "queued" || execution.status == "running" {
                Button("取消执行", role: .destructive) { cancel() }
                    .buttonStyle(.bordered)
            } else if execution.status == "failed" || execution.status == "cancelled" {
                Button("从失败处重试", systemImage: "arrow.clockwise") { retry() }
                    .buttonStyle(.borderedProminent)
            } else if execution.status == "awaiting_review" {
                Button("退回修改") { requestRevision() }
                    .buttonStyle(.bordered)
                Button("批准并入库", systemImage: "checkmark.shield") { approveOutput() }
                    .buttonStyle(.borderedProminent)
                    .disabled(selectedArtifacts.isEmpty)
            } else {
                Label("已完成并归档", systemImage: "checkmark.seal.fill")
                    .foregroundStyle(AppTheme.Colors.statusCompleted)
            }
        }
        .controlSize(.large)
        .frame(maxWidth: .infinity)
        .padding(AppTheme.Metrics.contentGutter)
        .background(.ultraThinMaterial)
        .disabled(isWorking)
    }

    private func monitor() async {
        do {
            execution = try await APIClient.shared.fetchWorkflowExecution(id: execution.id)
            if !["awaiting_review", "completed", "failed", "cancelled"].contains(execution.status) {
                for try await _ in APIClient.shared.workflowEventStream(executionId: execution.id) {
                    execution = try await APIClient.shared.fetchWorkflowExecution(id: execution.id)
                }
            }
        } catch {
            // SSE 在代理或弱网下不可用时，下面的持久状态轮询接管恢复。
        }
        while !Task.isCancelled {
            do {
                execution = try await APIClient.shared.fetchWorkflowExecution(id: execution.id)
                if ["awaiting_review", "completed"].contains(execution.status) {
                    artifacts = try await APIClient.shared.fetchWorkflowArtifacts(executionId: execution.id)
                    if selectedArtifacts.isEmpty {
                        selectedArtifacts = Set(artifacts.filter(\.selectedForPublish).map(\.id))
                    }
                    return
                }
                if ["failed", "cancelled"].contains(execution.status) { return }
            } catch {
                errorMessage = error.localizedDescription
            }
            try? await Task.sleep(for: .seconds(2))
        }
    }

    private func cancel() { perform { execution = try await APIClient.shared.cancelWorkflowExecution(id: execution.id) } }
    private func retry() { perform { execution = try await APIClient.shared.retryWorkflowExecution(id: execution.id); await monitor() } }
    private func requestRevision() {
        let nodeId = execution.nodes.first(where: { $0.nodeType == "FILTER_PASS" })?.nodeId ?? execution.nodes.last?.nodeId ?? "review_output"
        perform {
            execution = try await APIClient.shared.requestWorkflowRevision(
                executionId: execution.id, nodeId: nodeId, comment: "请根据复核意见重新检查并完善成果"
            )
            await monitor()
        }
    }
    private func approveOutput() {
        perform {
            try await APIClient.shared.approveWorkflowOutput(
                executionId: execution.id, artifactIds: Array(selectedArtifacts)
            )
            execution = try await APIClient.shared.fetchWorkflowExecution(id: execution.id)
        }
    }
    private func perform(_ operation: @escaping () async throws -> Void) {
        isWorking = true
        Task {
            do { try await operation(); errorMessage = nil }
            catch { errorMessage = error.localizedDescription }
            isWorking = false
        }
    }
    private func nodeIcon(_ status: String) -> String {
        switch status {
        case "running": return "waveform.circle.fill"
        case "succeeded": return "checkmark.circle.fill"
        case "failed": return "exclamationmark.triangle.fill"
        default: return "circle.dotted"
        }
    }
    private func nodeColor(_ status: String) -> Color {
        switch status {
        case "running": return AppTheme.Colors.statusRunning
        case "succeeded": return AppTheme.Colors.statusCompleted
        case "failed": return AppTheme.Colors.statusError
        default: return AppTheme.Colors.statusIdle
        }
    }
}

private struct WorkflowArtifactPreview: View {
    let executionId: String
    let artifact: WorkflowArtifactDTO
    @State private var content: String?
    @State private var errorMessage: String?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                if let content {
                    Text(content)
                        .font(.body)
                        .textSelection(.enabled)
                        .frame(maxWidth: AppTheme.Metrics.readableContentWidth, alignment: .leading)
                        .padding(AppTheme.Metrics.contentGutter)
                } else if let errorMessage {
                    WorkflowErrorBanner(message: errorMessage).padding()
                } else {
                    ProgressView("正在读取落盘内容…").padding()
                }
            }
            .navigationTitle(artifact.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { Button("完成") { dismiss() } }
            .task {
                do {
                    content = try await APIClient.shared.fetchWorkflowArtifactContent(
                        executionId: executionId, artifactId: artifact.id
                    ).content
                } catch { errorMessage = error.localizedDescription }
            }
        }
    }
}

private struct WorkflowStatusBadge: View {
    let status: String
    var body: some View {
        Label(status.workflowStatusLabel, systemImage: status.workflowStatusIcon)
            .font(AppTheme.Typography.micro)
            .foregroundStyle(status.workflowStatusColor)
            .padding(.horizontal, AppTheme.Spacing.sm)
            .frame(minHeight: 28)
            .background(status.workflowStatusColor.opacity(0.12), in: Capsule())
    }
}

private struct WorkflowErrorBanner: View {
    let message: String
    var body: some View {
        Label(message, systemImage: "exclamationmark.triangle.fill")
            .font(AppTheme.Typography.supporting)
            .foregroundStyle(AppTheme.Colors.statusError)
            .padding(AppTheme.Spacing.md)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(AppTheme.Colors.statusError.opacity(0.12))
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
    }
}

private extension String {
    var workflowStatusLabel: String {
        switch self {
        case "planning": return "生成计划中"
        case "awaiting_approval": return "待确认计划"
        case "ready": return "已就绪"
        case "queued": return "排队中"
        case "running": return "执行中"
        case "awaiting_review": return "待成果复核"
        case "completed", "succeeded": return "已完成"
        case "failed": return "执行失败"
        case "cancelled": return "已取消"
        case "pending": return "等待中"
        case "skipped": return "已跳过"
        default: return self
        }
    }
    var workflowStatusIcon: String {
        switch self {
        case "running", "planning": return "waveform"
        case "awaiting_approval", "awaiting_review": return "person.badge.clock"
        case "completed", "succeeded": return "checkmark.circle.fill"
        case "failed": return "exclamationmark.triangle.fill"
        case "cancelled": return "xmark.circle.fill"
        default: return "clock"
        }
    }
    var workflowStatusColor: Color {
        switch self {
        case "running", "planning", "queued": return AppTheme.Colors.statusRunning
        case "awaiting_approval", "awaiting_review": return AppTheme.Colors.securityYellow
        case "completed", "succeeded", "ready": return AppTheme.Colors.statusCompleted
        case "failed": return AppTheme.Colors.statusError
        default: return AppTheme.Colors.statusIdle
        }
    }
}
