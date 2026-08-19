import SwiftUI

// MARK: - 工作流主页

public struct WorkflowDashboardView: View {
    @StateObject private var model = WorkflowDashboardModel()
    @State private var showingCreate = false
    @State private var showingTopology = false
    @State private var clarificationWorkflow: WorkflowDTO?

    public init() {}

    public var body: some View {
        NavigationStack {
            ZStack {
                QuantumWorkflowBackground()

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
            }
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
                    clarificationWorkflow = created.workflow
                    await model.load()
                }
            }
            .fullScreenCover(item: $clarificationWorkflow) { workflow in
                NavigationStack {
                    WorkflowClarificationView(workflow: workflow) {
                        clarificationWorkflow = nil
                        await model.load()
                    }
                }
            }
            .sheet(isPresented: $showingTopology) {
                NavigationStack { TopologyCanvasView() }
            }
            .task { await model.load() }
        }
    }

    private var emptyState: some View {
        VStack(spacing: AppTheme.Spacing.xl) {
            Image(systemName: "sparkles.rectangle.stack.fill")
                .font(.system(size: 28, weight: .semibold))
                .foregroundStyle(AppTheme.Colors.quantumGradient)
                .frame(width: 64, height: 64)
                .background(AppTheme.Colors.selectionTint, in: RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))

            VStack(spacing: AppTheme.Spacing.sm) {
                Text("把想法变成工作流")
                    .font(AppTheme.Typography.screenTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Text("描述你想获得的结果。Quantum 会先澄清需求并生成可编辑方案，确认后构建专属 Agent，由你再次点击启动。")
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .multilineTextAlignment(.center)
            }

            Button("创建第一个工作流", systemImage: "plus") { showingCreate = true }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
        }
        .padding(AppTheme.Spacing.xxl)
        .frame(maxWidth: 340)
        .background(.ultraThinMaterial)
        .background(AppTheme.Colors.cardBackground.opacity(0.82))
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous)
                .stroke(AppTheme.Colors.border.opacity(0.9), lineWidth: 0.75)
        }
        .padding(AppTheme.Metrics.contentGutter)
    }
}

private struct QuantumWorkflowBackground: View {
    var body: some View {
        ZStack {
            AppTheme.Colors.background
            Circle()
                .fill(AppTheme.Colors.quantumBlue.opacity(0.11))
                .frame(width: 330, height: 330)
                .blur(radius: 70)
                .offset(x: 150, y: -280)
            Circle()
                .fill(AppTheme.Colors.primary.opacity(0.10))
                .frame(width: 300, height: 300)
                .blur(radius: 80)
                .offset(x: -150, y: 250)
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
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

            if let agent = workflow.agent {
                HStack(spacing: AppTheme.Spacing.md) {
                    Image(systemName: "person.crop.circle.badge.checkmark")
                        .foregroundStyle(AppTheme.Colors.quantumBlue)
                        .frame(width: 36, height: 36)
                        .background(AppTheme.Colors.surfaceTint, in: Circle())
                    VStack(alignment: .leading, spacing: 2) {
                        Text(agent.customName ?? "任务专用 Agent")
                            .font(AppTheme.Typography.cardTitle)
                        Text(agent.compositionManifest.capabilityAgentIds.map(\.workflowCapabilityLabel).joined(separator: " · "))
                            .font(AppTheme.Typography.micro)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                            .lineLimit(2)
                    }
                    Spacer(minLength: 0)
                }
                .padding(AppTheme.Spacing.md)
                .background(AppTheme.Colors.surfaceTint)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
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

    private var planningProgress: Int {
        switch workflow.status {
        case "clarifying": return 5
        case "planning", "needs_attention": return 10
        case "awaiting_approval": return 15
        case "building_agent": return 18
        case "agent_ready", "ready": return 20
        default: return 0
        }
    }
    private var planningState: String {
        switch workflow.status {
        case "clarifying": return "澄清中"
        case "planning": return "生成中"
        case "needs_attention": return "需处理"
        case "awaiting_approval": return "待确认"
        case "building_agent": return "构建中"
        case "agent_ready", "ready": return "已确认"
        default: return "未开始"
        }
    }
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
                    Label("创建后先通过独立会话澄清需求；确认方案前不会执行任务。", systemImage: "lock.shield")
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
                    Button(isSubmitting ? "建档中…" : "开始澄清") { submit() }
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
            if ["clarifying", "planning"].contains(current.status) && execution == nil {
                WorkflowClarificationView(workflow: current) {
                    await refresh()
                    await onChanged()
                }
            } else if current.status == "awaiting_approval" && execution == nil {
                WorkflowPlanReviewView(workflow: current) { buildResult in
                    current = buildResult.workflow
                    Task { await onChanged() }
                }
            } else if current.status == "agent_ready", let agent = current.agent, execution == nil {
                WorkflowAgentReadyView(workflow: current, agent: agent) { started in
                    execution = started
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

// MARK: - 任务内需求澄清

@MainActor
private final class WorkflowClarificationModel: ObservableObject {
    let workflowId: String
    @Published var snapshot: WorkflowClarificationSnapshotDTO?
    @Published var events: [WorkflowLifecycleEventDTO] = []
    @Published var isLoading = false
    @Published var isSubmitting = false
    @Published var errorMessage: String?
    private var streamActive = false

    init(workflowId: String) { self.workflowId = workflowId }

    var phase: String { snapshot?.session.phase ?? "clarifying" }
    var lastEventId: Int { events.map(\.id).max() ?? 0 }

    func start() async {
        guard !streamActive else { return }
        streamActive = true
        defer { streamActive = false }
        await refresh()
        guard !Task.isCancelled,
              !["awaiting_approval", "agent_ready", "needs_attention"].contains(phase) else { return }
        var retries = 0
        while !Task.isCancelled {
            do {
                for try await event in APIClient.shared.workflowLifecycleEventStream(
                    workflowId: workflowId, after: lastEventId
                ) {
                    retries = 0
                    if !events.contains(where: { $0.id == event.id }) { events.append(event) }
                    if ["plan_ready", "agent_built", "planning_failed"].contains(event.type) {
                        await refresh()
                    }
                }
                return
            } catch is CancellationError {
                return
            } catch {
                retries += 1
                errorMessage = "进度连接已中断，正在恢复同一任务…"
                let delay = UInt64(min(retries, 8)) * 1_000_000_000
                try? await Task.sleep(nanoseconds: delay)
                await refresh()
            }
        }
    }

    func refresh() async {
        isLoading = snapshot == nil
        defer { isLoading = false }
        do {
            let loaded = try await APIClient.shared.fetchWorkflowClarification(workflowId: workflowId)
            snapshot = loaded
            events = loaded.events
            errorMessage = nil
        } catch {
            errorMessage = "无法恢复任务会话：\(error.localizedDescription)"
        }
    }

    func respond(_ response: String) async {
        guard !response.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        isSubmitting = true
        defer { isSubmitting = false }
        do {
            _ = try await APIClient.shared.respondToWorkflowClarification(
                workflowId: workflowId, response: response
            )
            await refresh()
            if phase == "planning" {
                Task { await self.start() }
            }
        } catch {
            errorMessage = "提交失败，需求进度已保留：\(error.localizedDescription)"
        }
    }

    func retryPlanning() async {
        isSubmitting = true
        defer { isSubmitting = false }
        do {
            _ = try await APIClient.shared.retryWorkflowPlanning(workflowId: workflowId)
            await refresh()
            await start()
        } catch {
            errorMessage = "规划重试失败，已有内容不会丢失：\(error.localizedDescription)"
        }
    }

    func reopenClarification() async {
        isSubmitting = true
        defer { isSubmitting = false }
        do {
            _ = try await APIClient.shared.reopenWorkflowClarification(workflowId: workflowId)
            await refresh()
        } catch {
            errorMessage = "无法继续澄清：\(error.localizedDescription)"
        }
    }

    var reasoningSteps: [ReasoningStep] {
        events.filter {
            ["planning_retry_scheduled", "planning_started", "planner_context_loaded", "capabilities_selecting", "plan_compiled", "policy_validated", "plan_ready", "planning_failed", "agent_built"].contains($0.type)
        }.map { event in
            let type: ReasoningStepType
            switch event.type {
            case "planner_context_loaded": type = .skillLoad
            case "capabilities_selecting", "agent_built": type = .agentSpawn
            case "plan_compiled", "policy_validated": type = .toolCall
            default: type = .thought
            }
            let running = event.id == lastEventId && ["planning", "building_agent"].contains(phase)
            return ReasoningStep(
                id: "workflow-event-\(event.id)", type: type,
                title: event.message,
                detail: event.payload.detail ?? event.payload.tool ?? "",
                status: event.type == "planning_failed" ? "failed" : (running ? "running" : "done")
            )
        }
    }
}

private struct WorkflowClarificationView: View {
    let workflow: WorkflowDTO
    let onFinished: () async -> Void
    @StateObject private var model: WorkflowClarificationModel

    init(workflow: WorkflowDTO, onFinished: @escaping () async -> Void) {
        self.workflow = workflow
        self.onFinished = onFinished
        _model = StateObject(wrappedValue: WorkflowClarificationModel(workflowId: workflow.id))
    }

    var body: some View {
        VStack(spacing: 0) {
            WorkflowTaskStageHeader(phase: model.phase)
                .padding(.horizontal, AppTheme.Metrics.contentGutter)
                .padding(.vertical, AppTheme.Spacing.md)

            Divider()

            if model.isLoading {
                Spacer()
                ProgressView("正在恢复需求会话…")
                Spacer()
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                        if !model.reasoningSteps.isEmpty {
                            ReasoningCard(
                                steps: model.reasoningSteps,
                                isStreaming: ["planning", "building_agent"].contains(model.phase)
                            )
                        }
                        ForEach(model.snapshot?.messages ?? []) { message in
                            workflowMessage(message)
                        }
                        if let error = model.errorMessage {
                            WorkflowErrorBanner(message: error)
                            if model.phase != "needs_attention" {
                                Button("重新连接", systemImage: "arrow.clockwise") {
                                    Task { await model.refresh() }
                                }
                                .buttonStyle(.bordered)
                                .frame(minHeight: 44)
                            }
                        }
                        if model.phase == "needs_attention" {
                            if model.errorMessage == nil {
                                WorkflowErrorBanner(message: "方案生成未完成，已保留需求与过程记录。")
                            }
                            HStack(spacing: AppTheme.Spacing.md) {
                                Button("继续澄清", systemImage: "bubble.left.and.text.bubble.right") {
                                    Task { await model.reopenClarification() }
                                }
                                .buttonStyle(.bordered)
                                Button("重试规划", systemImage: "arrow.clockwise") {
                                    Task { await model.retryPlanning() }
                                }
                                .buttonStyle(.borderedProminent)
                            }
                            .frame(minHeight: 44)
                            .disabled(model.isSubmitting)
                        }
                    }
                    .padding(AppTheme.Metrics.contentGutter)
                }
            }
        }
        .background(AppTheme.Colors.background)
        .navigationTitle(workflow.title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                Button("返回任务") { Task { await onFinished() } }
            }
        }
        .safeAreaInset(edge: .bottom) {
            if ["awaiting_approval", "agent_ready"].contains(model.phase) {
                Button(model.phase == "agent_ready" ? "查看专属 Agent" : "查看并确认方案") {
                    Task { await onFinished() }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .frame(maxWidth: .infinity, minHeight: 44)
                .padding(AppTheme.Metrics.contentGutter)
                .background(.ultraThinMaterial)
            }
        }
        .task { await model.start() }
    }

    @ViewBuilder
    private func workflowMessage(_ message: WorkflowSessionMessageDTO) -> some View {
        let isLast = message.id == model.snapshot?.messages.last?.id
        if message.role == "assistant",
           isLast,
           ["clarify", "requirement_confirmation"].contains(message.messageType),
           let question = message.payload.question {
            ClarifyCard(
                block: ClarifyBlock(
                    question: question,
                    choices: message.payload.choices ?? [],
                    multiSelect: message.payload.multiSelect ?? false,
                    submitLabel: message.payload.submitLabel ?? "确认并继续",
                    source: "workflow"
                ),
                onSubmit: { selection in Task { await model.respond(selection) } }
            )
            .disabled(model.isSubmitting)
        } else {
            HStack {
                if message.role == "user" { Spacer(minLength: 44) }
                Text(message.content)
                    .font(AppTheme.Typography.body)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                    .padding(AppTheme.Spacing.md)
                    .background(
                        message.role == "user"
                        ? AppTheme.Colors.quantumBlue.opacity(0.16)
                        : AppTheme.Colors.cardBackground
                    )
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
                if message.role != "user" { Spacer(minLength: 44) }
            }
        }
    }
}

private struct WorkflowTaskStageHeader: View {
    let phase: String
    private let stages = [
        ("需求", "clarifying"), ("方案", "planning"), ("确认", "awaiting_approval"),
        ("构建", "building_agent"), ("待启动", "agent_ready")
    ]

    private var currentIndex: Int {
        switch phase {
        case "planning", "needs_attention": return 1
        case "awaiting_approval": return 2
        case "building_agent": return 3
        case "agent_ready": return 4
        default: return 0
        }
    }

    var body: some View {
        HStack(spacing: AppTheme.Spacing.xs) {
            ForEach(Array(stages.enumerated()), id: \.offset) { index, stage in
                VStack(spacing: 4) {
                    Image(systemName: index < currentIndex ? "checkmark.circle.fill" : (index == currentIndex ? "circle.inset.filled" : "circle"))
                        .foregroundStyle(index <= currentIndex ? AppTheme.Colors.quantumBlue : AppTheme.Colors.textTertiary)
                    Text(stage.0)
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(index <= currentIndex ? AppTheme.Colors.textPrimary : AppTheme.Colors.textTertiary)
                }
                .frame(maxWidth: .infinity, minHeight: 44)
                if index < stages.count - 1 {
                    Rectangle()
                        .fill(index < currentIndex ? AppTheme.Colors.quantumBlue : AppTheme.Colors.border)
                        .frame(height: 1)
                }
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("任务阶段：\(phase.workflowStatusLabel)")
    }
}

private struct WorkflowAgentReadyView: View {
    let workflow: WorkflowDTO
    let agent: WorkflowTaskAgentDTO
    let onStarted: (WorkflowExecutionDTO) -> Void
    @State private var isStarting = false
    @State private var errorMessage: String?
    @State private var requestId = UUID().uuidString

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xl) {
                WorkflowTaskStageHeader(phase: "agent_ready")
                VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                    Label("任务专用 Agent", systemImage: "person.crop.circle.badge.checkmark")
                        .font(AppTheme.Typography.label)
                        .foregroundStyle(AppTheme.Colors.quantumBlue)
                    Text(agent.customName ?? "专属 Agent")
                        .font(AppTheme.Typography.screenTitle)
                    Text("创建者：\(agent.ownerUserId ?? "当前用户") · 仅创建者可见 · 已绑定批准方案")
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                    capabilitySection
                    Label(
                        "临时子 Agent：最多并发 \(agent.compositionManifest.delegation.maxConcurrentChildren) 个 · 深度 \(agent.compositionManifest.delegation.maxSpawnDepth) 层",
                        systemImage: "person.3.sequence"
                    )
                    .font(AppTheme.Typography.supporting)
                    if !agent.compositionManifest.knowledgeScope.isEmpty {
                        Text("知识范围：\(agent.compositionManifest.knowledgeScope.joined(separator: "、"))")
                            .font(AppTheme.Typography.supporting)
                    }
                }
                .padding(AppTheme.Spacing.xl)
                .quantumCard()
                if let errorMessage { WorkflowErrorBanner(message: errorMessage) }
            }
            .padding(AppTheme.Metrics.contentGutter)
        }
        .safeAreaInset(edge: .bottom) {
            Button(isStarting ? "正在启动…" : "启动任务", systemImage: "play.fill") { start() }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(isStarting)
                .frame(maxWidth: .infinity, minHeight: 44)
                .padding(AppTheme.Metrics.contentGutter)
                .background(.ultraThinMaterial)
        }
    }

    private var capabilitySection: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 108), spacing: AppTheme.Spacing.sm)], spacing: AppTheme.Spacing.sm) {
            ForEach(agent.compositionManifest.capabilityAgentIds, id: \.self) { capability in
                Text(capability.workflowCapabilityLabel)
                    .font(AppTheme.Typography.micro)
                    .padding(.horizontal, AppTheme.Spacing.sm)
                    .padding(.vertical, 6)
                    .background(AppTheme.Colors.surfaceTint, in: Capsule())
            }
        }
    }

    private func start() {
        isStarting = true
        Task {
            do {
                let execution = try await APIClient.shared.startWorkflow(
                    workflowId: workflow.id, requestId: requestId
                )
                onStarted(execution)
            } catch {
                errorMessage = error.localizedDescription
                isStarting = false
            }
        }
    }
}

private struct WorkflowPlanReviewView: View {
    let workflow: WorkflowDTO
    let onApproved: (WorkflowAgentBuildResponseDTO) -> Void
    @State private var plan: WorkflowPlanDTO?
    @State private var tenantAgents: [TenantAgentDTO] = []
    @State private var availableKnowledgeScopes: [String] = []
    @State private var isSaving = false
    @State private var errorMessage: String?
    @State private var replanInstruction = ""
    @State private var approvalRequestId = UUID().uuidString
    @State private var replanEvents: [WorkflowLifecycleEventDTO] = []

    var body: some View {
        Group {
            if let draft = plan {
                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.xl) {
                        WorkflowTaskStageHeader(phase: "awaiting_approval")
                        planHeader(draft)
                        if !draft.validationErrors.isEmpty {
                            WorkflowErrorBanner(message: draft.validationErrors.joined(separator: "\n"))
                        }
                        configuration(plan: planBinding)
                        nodeTimeline(plan: planBinding)
                        if !replanReasoningSteps.isEmpty {
                            ReasoningCard(steps: replanReasoningSteps, isStreaming: isSaving)
                        }
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
                        Button(isSaving ? "正在处理…" : "确认并构建 Agent") { approve() }
                            .buttonStyle(.borderedProminent)
                            .frame(maxWidth: .infinity)
                            .disabled(!draft.validationErrors.isEmpty)
                    }
                    .controlSize(.large)
                    .padding(AppTheme.Metrics.contentGutter)
                    .background(.ultraThinMaterial)
                }
                .disabled(isSaving)
            } else {
                VStack(spacing: AppTheme.Spacing.lg) {
                    if let errorMessage {
                        WorkflowErrorBanner(message: errorMessage)
                        Button("重新读取", systemImage: "arrow.clockwise") {
                            Task { await load() }
                        }
                        .buttonStyle(.borderedProminent)
                        .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                    } else {
                        ProgressView("正在读取执行计划…")
                    }
                }
                .padding(AppTheme.Metrics.contentGutter)
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
            async let loadedAccess = APIClient.shared.fetchKnowledgeAccess()
            plan = try await loadedPlan
            tenantAgents = (try? await loadedAgents) ?? []
            availableKnowledgeScopes = (try? await loadedAccess)?.effectiveCategories ?? plan?.knowledgeScope ?? []
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
                let buildResult = try await APIClient.shared.approveWorkflowPlan(
                    workflowId: workflow.id,
                    requestId: approvalRequestId
                )
                onApproved(buildResult)
            } catch {
                errorMessage = error.localizedDescription
                isSaving = false
            }
        }
    }

    private func replan() {
        isSaving = true
        errorMessage = nil
        Task {
            do {
                _ = try await APIClient.shared.replanWorkflow(
                    workflowId: workflow.id, instruction: replanInstruction
                )
                replanInstruction = ""
                var finished = false
                var reconnectAttempt = 0
                while !finished && !Task.isCancelled {
                    do {
                        let cursor = replanEvents.map(\.id).max() ?? 0
                        for try await event in APIClient.shared.workflowLifecycleEventStream(
                            workflowId: workflow.id, after: cursor
                        ) {
                            reconnectAttempt = 0
                            if !replanEvents.contains(where: { $0.id == event.id }) {
                                replanEvents.append(event)
                            }
                            if event.type == "planning_failed" {
                                errorMessage = "方案生成失败，需求与过程记录已保留，请返回任务页重试或继续澄清。"
                                finished = true
                                break
                            }
                            if event.type == "plan_ready" {
                                plan = try await APIClient.shared.fetchWorkflowPlan(workflowId: workflow.id)
                                finished = true
                                break
                            }
                        }
                    } catch is CancellationError {
                        return
                    } catch {
                        reconnectAttempt += 1
                        errorMessage = "进度连接中断，正在恢复同一规划任务…"
                        let delay = UInt64(min(reconnectAttempt, 8)) * 1_000_000_000
                        try? await Task.sleep(nanoseconds: delay)
                    }
                }
            } catch { errorMessage = error.localizedDescription }
            isSaving = false
        }
    }

    private var replanReasoningSteps: [ReasoningStep] {
        replanEvents.filter {
            ["replan_requested", "planning_started", "planner_context_loaded", "capabilities_selecting", "plan_compiled", "policy_validated", "plan_ready", "planning_failed"].contains($0.type)
        }.map { event in
            let type: ReasoningStepType
            switch event.type {
            case "planner_context_loaded": type = .skillLoad
            case "capabilities_selecting": type = .agentSpawn
            case "plan_compiled", "policy_validated": type = .toolCall
            default: type = .thought
            }
            return ReasoningStep(
                id: "replan-event-\(event.id)", type: type,
                title: event.message,
                detail: event.payload.detail ?? event.payload.tool ?? "",
                status: event.type == "planning_failed" ? "failed" : "done"
            )
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
    var workflowCapabilityLabel: String {
        switch self {
        case "main_agent": return "Main · 智能编排"
        case "knowledge": return "Knowledge · 知识"
        case "coder": return "Coder · 开发"
        case "supervision": return "Supervision · 审查"
        default: return self
        }
    }
    var workflowStatusLabel: String {
        switch self {
        case "clarifying": return "需求澄清中"
        case "planning": return "生成计划中"
        case "needs_attention": return "规划需处理"
        case "awaiting_approval": return "待确认计划"
        case "building_agent": return "构建 Agent 中"
        case "agent_ready": return "Agent 待启动"
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
        case "running", "planning", "building_agent": return "waveform"
        case "needs_attention": return "exclamationmark.arrow.triangle.2.circlepath"
        case "clarifying": return "bubble.left.and.text.bubble.right"
        case "agent_ready": return "person.crop.circle.badge.checkmark"
        case "awaiting_approval", "awaiting_review": return "person.badge.clock"
        case "completed", "succeeded": return "checkmark.circle.fill"
        case "failed": return "exclamationmark.triangle.fill"
        case "cancelled": return "xmark.circle.fill"
        default: return "clock"
        }
    }
    var workflowStatusColor: Color {
        switch self {
        case "running", "planning", "building_agent", "clarifying", "queued": return AppTheme.Colors.statusRunning
        case "awaiting_approval", "awaiting_review": return AppTheme.Colors.securityYellow
        case "completed", "succeeded", "ready", "agent_ready": return AppTheme.Colors.statusCompleted
        case "failed", "needs_attention": return AppTheme.Colors.statusError
        default: return AppTheme.Colors.statusIdle
        }
    }
}
