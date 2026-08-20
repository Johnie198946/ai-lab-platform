//
//  TopologyCanvasView.swift
//  AIPlatformApp
//
//  Read-Only DAG Agent Orchestration Topology Canvas
//  Strict Security Lock: Zero In-Place Canvas Editing / Conversational Topology Modification
//

import SwiftUI

public struct TopologyCanvasView: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.colorScheme) private var colorScheme
    
    @State private var graph: TopologyGraph = TopologyGraph()
    @State private var selectedNode: AgentNode? = nil
    @State private var isLoading: Bool = false
    @State private var loadFailed: Bool = false
    /// 本租户切片节点 id 集合（仅切片可删除，基线只读）
    @State private var tenantAgentIds: Set<String> = []
    /// 切片删除失败提示（云端失败本地回滚）
    @State private var deleteError: String? = nil
    
    // Zoom and Pan Gestures
    @State private var offset: CGSize = .zero
    @State private var lastOffset: CGSize = .zero
    @State private var scale: CGFloat = 1.0
    @State private var lastScale: CGFloat = 1.0

    // Edit/Layout Mode（需求5：编辑模式开关 + 节点长按拖动）
    @State private var isEditMode: Bool = false
    @State private var dragOrigin: CGPoint = .zero

    public init() {}
    
    public var body: some View {
        NavigationStack {
            ZStack {
                // Canvas Background Grid
                QuantumMistBackground()
                
                // MARK: - 1. Interactive DAG Canvas Area
                if graph.nodes.isEmpty && !isLoading && !loadFailed {
                    tenantEmptyView
                } else {
                    GeometryReader { geometry in
                        ZStack {
                            // Background Grid Lines
                            gridPatternBackground(geometry: geometry)
                            
                            // DAG Connections & Nodes Container
                            ZStack {
                                // Edge Layer (Bezier Curves with Arrows)
                                edgesLayer
                                
                                // Nodes Layer
                                nodesLayer
                            }
                            .scaleEffect(scale)
                            .offset(offset)
                            .gesture(
                                SimultaneousGesture(
                                    DragGesture()
                                        .onChanged { value in
                                            offset = CGSize(
                                                width: lastOffset.width + value.translation.width,
                                                height: lastOffset.height + value.translation.height
                                            )
                                        }
                                        .onEnded { _ in
                                            lastOffset = offset
                                        },
                                    MagnificationGesture()
                                        .onChanged { value in
                                            let delta = value / lastScale
                                            lastScale = value
                                            let newScale = scale * delta
                                            scale = min(max(newScale, 0.5), 2.5)
                                        }
                                        .onEnded { _ in
                                            lastScale = 1.0
                                        }
                                )
                            )
                        }
                    }
                }
                
                // MARK: - 2. 状态提示与操作引导
                VStack {
                    guidanceChip
                    Spacer()
                    demonstrationBadge
                }
                .padding(AppTheme.Spacing.md)
            }
            .navigationTitle(isEditMode ? "协同拓扑 (布局编辑)" : "协同拓扑")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button(action: toggleEditMode) {
                        Image(systemName: isEditMode ? "checkmark.circle.fill" : "square.and.pencil")
                            .font(.system(size: 14))
                            .foregroundColor(isEditMode ? AppTheme.Icons.interactive : AppTheme.Icons.secondary)
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: resetCanvasView) {
                        Image(systemName: "arrow.counterclockwise")
                            .font(.system(size: 14))
                            .foregroundColor(AppTheme.Icons.secondary)
                    }
                }
            }
            .sheet(item: $selectedNode) { node in
                AgentNodeDetailSheet(
                    node: node,
                    onChatWithAgent: { agentId in
                        selectedNode = nil
                        appState.selectedAgentId = agentId
                        appState.navigateToChatWithPrompt("以「\(node.name)」角色发起协作对话")
                    },
                    isDeletable: tenantAgentIds.contains(node.id),
                    onDelete: {
                        selectedNode = nil
                        deleteTenantSlice(node)
                    }
                )
            }
            .task { await loadTopology() }
            .onReceive(NotificationCenter.default.publisher(for: .tenantAgentsDidUpdate)) { _ in
                // 对话式创建 Agent 成功后静默刷新切片叠加（拓扑页与云端同源）
                Task { await loadTopology() }
            }
            .overlay(alignment: .top) { loadStatusBadge }
        }
    }

    // MARK: - 拓扑加载状态标注（诚实展示，不静默失败）
    @ViewBuilder
    private var loadStatusBadge: some View {
        if let err = deleteError {
            Text(err)
                .font(.system(size: 12))
                .foregroundColor(AppTheme.Colors.onPrimary)
                .padding(.horizontal, 12).padding(.vertical, 6)
                .background(AppTheme.Colors.securityRed.opacity(0.9))
                .clipShape(Capsule())
                .padding(.top, AppTheme.Spacing.sm)
        } else if isLoading {
            Text("正在加载协同拓扑…")
                .font(.system(size: 12))
                .foregroundColor(AppTheme.Colors.textSecondary)
                .padding(.horizontal, 12).padding(.vertical, 6)
                .background(AppTheme.Colors.cardBackground)
                .clipShape(Capsule())
                .padding(.top, AppTheme.Spacing.sm)
        } else if loadFailed {
            Text("拓扑加载失败，请检查网络后重试")
                .font(.system(size: 12))
                .foregroundColor(AppTheme.Colors.securityRed)
                .padding(.horizontal, 12).padding(.vertical, 6)
                .background(AppTheme.Colors.cardBackground)
                .clipShape(Capsule())
                .padding(.top, AppTheme.Spacing.sm)
        }
    }

    private func loadTopology() async {
        isLoading = true
        loadFailed = false
        do {
            let dto = try await APIClient.shared.fetchTopology()
            graph = dto.toTopologyGraph()
            tenantAgentIds = Set(graph.nodes.map(\.id))
        } catch {
            loadFailed = true
        }
        isLoading = false
    }

    // MARK: - 3. 空态引导与诚实标注（Supervision 批复）

    private var tenantEmptyView: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            HStack {
                VStack(alignment: .leading, spacing: 6) {
                    Text("ORCHESTRATION · LIVE MAP")
                        .font(AppTheme.Typography.micro)
                        .tracking(0.8)
                        .foregroundColor(AppTheme.Icons.interactive)
                    Text("构建你的协同编队")
                        .font(AppTheme.Typography.sectionTitle)
                        .foregroundColor(AppTheme.Colors.textPrimary)
                }
                Spacer()
                Image(systemName: "point.3.connected.trianglepath.dotted")
                    .font(.system(size: 30, weight: .medium))
                    .foregroundColor(AppTheme.Icons.intelligence)
                    .frame(width: 60, height: 60)
                    .background(AppTheme.Colors.selectionTint)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            }

            Text("尚未创建租户专属 Agent")
                .font(.system(size: 16, weight: .bold))
                .foregroundColor(AppTheme.Colors.textPrimary)

            Text("在对话中提出「创建一个…的agent」，或在个人与设置中一键创建专属智能体编队")
                .font(.system(size: 13))
                .foregroundColor(AppTheme.Colors.textSecondary)
                .multilineTextAlignment(.leading)

            Button(action: {
                appState.activeTab = 3 // 切换到「个人与设置」Tab
            }) {
                Label("前往创建智能体", systemImage: "plus.circle.fill")
            }
            .buttonStyle(QuantumPrimaryButtonStyle())
            .padding(.top, AppTheme.Spacing.xs)
        }
        .padding(AppTheme.Spacing.xl)
        .frame(maxWidth: 440)
        .quantumCard()
        .padding(.horizontal, AppTheme.Metrics.contentGutter)
    }

    private var demonstrationBadge: some View {
        HStack(spacing: 4) {
            Image(systemName: "info.circle")
                .font(.system(size: 10))
            Text("架构装配示意 · 演示态")
                .font(.system(size: 10, weight: .medium))
        }
        .foregroundColor(AppTheme.Icons.tertiary)
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(AppTheme.Colors.cardBackground.opacity(0.8))
        .clipShape(Capsule())
    }

    /// 删除切片：乐观更新（先本地移除）→ 云端删除失败则本地回滚恢复 + 错误提示。
    private func deleteTenantSlice(_ node: AgentNode) {
        let removed = node
        graph.nodes.removeAll { $0.id == node.id }
        tenantAgentIds.remove(node.id)
        Task { @MainActor in
            do {
                try await APIClient.shared.deleteTenantAgent(id: node.id)
            } catch {
                // 云端删除失败：本地回滚恢复切片节点
                if !graph.nodes.contains(where: { $0.id == removed.id }) {
                    graph.nodes.append(removed)
                }
                tenantAgentIds.insert(removed.id)
                showDeleteError("删除失败，已恢复：\(error.localizedDescription)")
            }
        }
    }

    private func showDeleteError(_ text: String) {
        deleteError = text
        DispatchQueue.main.asyncAfter(deadline: .now() + 3.0) {
            if deleteError == text { deleteError = nil }
        }
    }
    
    // MARK: - Canvas Layers
    
    private func gridPatternBackground(geometry: GeometryProxy) -> some View {
        Canvas { context, size in
            let gridSize: CGFloat = 30 * scale
            let offsetX = offset.width.truncatingRemainder(dividingBy: gridSize)
            let offsetY = offset.height.truncatingRemainder(dividingBy: gridSize)
            
            var path = Path()
            var x = offsetX
            while x < size.width {
                path.move(to: CGPoint(x: x, y: 0))
                path.addLine(to: CGPoint(x: x, y: size.height))
                x += gridSize
            }
            
            var y = offsetY
            while y < size.height {
                path.move(to: CGPoint(x: 0, y: y))
                path.addLine(to: CGPoint(x: size.width, y: y))
                y += gridSize
            }
            
            context.stroke(
                path,
                with: .color(colorScheme == .dark ? Color.white.opacity(0.04) : Color.black.opacity(0.04)),
                lineWidth: 1
            )
        }
    }
    
    private var edgesLayer: some View {
        Canvas { context, _ in
            for edge in graph.edges {
                guard let src = graph.nodes.first(where: { $0.id == edge.sourceNodeId }),
                      let dst = graph.nodes.first(where: { $0.id == edge.targetNodeId }) else {
                    continue
                }
                
                let startPoint = CGPoint(x: src.x + 80, y: src.y + 40)
                let endPoint = CGPoint(x: dst.x + 80, y: dst.y)
                
                var path = Path()
                path.move(to: startPoint)
                
                let control1 = CGPoint(x: startPoint.x, y: (startPoint.y + endPoint.y) / 2)
                let control2 = CGPoint(x: endPoint.x, y: (startPoint.y + endPoint.y) / 2)
                path.addCurve(to: endPoint, control1: control1, control2: control2)
                
                context.stroke(
                    path,
                    with: .color(AppTheme.Colors.accent.opacity(0.6)),
                    style: StrokeStyle(lineWidth: 2, lineCap: .round, dash: [4, 4])
                )
            }
        }
    }
    
    private var nodesLayer: some View {
        ForEach(Array(graph.nodes.enumerated()), id: \.element.id) { index, node in
            nodeView(node, index: index)
        }
    }

    @ViewBuilder
    private func nodeView(_ node: AgentNode, index: Int) -> some View {
        let card = NodeCardView(
            node: node,
            isSelected: selectedNode?.id == node.id,
            isEditing: isEditMode
        )
        .position(x: node.x + 80, y: node.y + 20)
        .onTapGesture {
            #if os(iOS)
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            #endif
            self.selectedNode = node
        }
        if isEditMode {
            card.gesture(dragGesture(for: index))
        } else {
            card
        }
    }

    // MARK: - 编辑模式：节点长按拖动（需求5）
    private func dragGesture(for index: Int) -> some Gesture {
        LongPressGesture(minimumDuration: 0.25)
            .sequenced(before: DragGesture(minimumDistance: 0))
            .onChanged { value in
                switch value {
                case .first(true):
                    // 长按识别：记录拖拽起点（缩放补偿在 onChanged 内换算）
                    dragOrigin = CGPoint(x: graph.nodes[index].x, y: graph.nodes[index].y)
                case .second(true, let drag?):
                    var updated = graph.nodes[index]
                    updated.x = dragOrigin.x + drag.translation.width / scale
                    updated.y = dragOrigin.y + drag.translation.height / scale
                    graph.nodes[index] = updated
                default:
                    break
                }
            }
    }

    private func toggleEditMode() {
        withAnimation(.spring()) {
            isEditMode.toggle()
            selectedNode = nil
        }
    }

    /// 精简后的轻量级角落 Chip（替代原底部长说明横幅，释放画布可视空间）
    private var guidanceChip: some View {
        HStack(spacing: 4) {
            Image(systemName: isEditMode ? "arrow.up.and.down.and.arrow.left.and.right" : "lock.shield.fill")
                .font(.system(size: 10))
            Text(isEditMode ? "布局编辑 · 长按拖动节点" : "只读拓扑 · 后端驱动")
                .font(.system(size: 11, weight: .semibold))
        }
        .foregroundColor(AppTheme.Icons.secondary)
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(Capsule())
        .padding(AppTheme.Spacing.md)
    }
    
    private func resetCanvasView() {
        withAnimation(.spring()) {
            offset = .zero
            lastOffset = .zero
            scale = 1.0
            lastScale = 1.0
        }
    }
}

// MARK: - Node Card View
public struct NodeCardView: View {
    public let node: AgentNode
    public let isSelected: Bool
    public var isEditing: Bool = false
    @Environment(\.colorScheme) private var colorScheme
    
    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Circle()
                    .fill(node.status.indicatorColor)
                    .frame(width: 8, height: 8)
                
                Text(node.name)
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(AppTheme.Colors.textPrimary)
                    .lineLimit(1)
            }
            
            // 节点去长说明：role_desc 不再平铺展示，仅详情 sheet 呈现（需求5）
            Text(node.status.labelText)
                .font(.system(size: 10))
                .foregroundColor(AppTheme.Colors.textTertiary)
        }
        .padding(10)
        .frame(width: 160)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: AppTheme.Radius.md)
                .stroke(
                    isSelected ? AppTheme.Colors.primary
                               : (isEditing ? AppTheme.Colors.accent.opacity(0.7) : AppTheme.Colors.border),
                    lineWidth: isSelected ? 2 : 1
                )
        )
    }
}

// MARK: - Agent Node Detail Drawer Sheet
public struct AgentNodeDetailSheet: View {
    public let node: AgentNode
    public var onChatWithAgent: (String) -> Void
    public var isDeletable: Bool = false
    public var onDelete: (() -> Void)? = nil
    
    @Environment(\.dismiss) private var dismiss
    @State private var showEvaluation = false
    
    public var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                    
                    // Status & Role Header
                    HStack(spacing: AppTheme.Spacing.md) {
                        ZStack {
                            Circle()
                                .fill(node.status.indicatorColor.opacity(0.2))
                                .frame(width: 48, height: 48)
                            
                            Image(systemName: "cpu.fill")
                                .font(.system(size: 24))
                                .foregroundColor(node.status.indicatorColor)
                        }
                        
                        VStack(alignment: .leading, spacing: 4) {
                            Text(node.name)
                                .font(.system(size: 18, weight: .bold))
                            
                            HStack(spacing: 6) {
                                Text(node.roleCategory)
                                    .font(.system(size: 12, weight: .semibold))
                                    .foregroundColor(AppTheme.Colors.primary)
                                
                                Text("•")
                                    .foregroundColor(AppTheme.Colors.textTertiary)
                                
                                Text(node.status.labelText)
                                    .font(.system(size: 12))
                                    .foregroundColor(AppTheme.Colors.textSecondary)
                            }
                        }
                    }
                    .padding(.top, AppTheme.Spacing.sm)
                    
                    Divider()
                    
                    // Role Responsibility
                    VStack(alignment: .leading, spacing: 6) {
                        Text("角色职责")
                            .font(.system(size: 13, weight: .bold))
                            .foregroundColor(AppTheme.Colors.textSecondary)
                        
                        Text(node.systemPromptSummary)
                            .font(.system(size: 14))
                            .foregroundColor(AppTheme.Colors.textPrimary)
                            .padding(AppTheme.Spacing.md)
                            .background(AppTheme.Colors.secondaryBackground)
                            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                    }
                    
                    // Mounted Tools
                    VStack(alignment: .leading, spacing: 6) {
                        Text("已挂载工具")
                            .font(.system(size: 13, weight: .bold))
                            .foregroundColor(AppTheme.Colors.textSecondary)
                        
                        if node.tools.isEmpty {
                            Text("暂无挂载工具")
                                .font(.system(size: 13))
                                .foregroundColor(AppTheme.Colors.textTertiary)
                        } else {
                            WrappingHStack(items: node.tools)
                        }
                    }
                    
                    // Collaboration Links
                    VStack(alignment: .leading, spacing: 6) {
                        Text("协同链路")
                            .font(.system(size: 13, weight: .bold))
                            .foregroundColor(AppTheme.Colors.textSecondary)
                        
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("上游输入依赖: \(node.inputDeps.isEmpty ? "根节点 (None)" : node.inputDeps.joined(separator: ", "))")
                                Text("下游输出分发: \(node.outputDeps.isEmpty ? "终端叶节点 (Leaf)" : node.outputDeps.joined(separator: ", "))")
                            }
                            .font(.system(size: 13))
                            .foregroundColor(AppTheme.Colors.textSecondary)
                        }
                        .padding(AppTheme.Spacing.md)
                        .background(AppTheme.Colors.secondaryBackground)
                        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                    }
                    
                    Spacer(minLength: 20)
                    
                    // Chat Collaboration Action Button
                    Button(action: {
                        onChatWithAgent(node.id)
                    }) {
                        HStack {
                            Image(systemName: "bubble.left.and.bubble.right.fill")
                            Text("在对话中与该角色协作")
                                .font(.system(size: 15, weight: .bold))
                        }
                        .frame(maxWidth: .infinity)
                        .frame(height: 48)
            .foregroundColor(AppTheme.Icons.onAccent)
                        .background(AppTheme.Colors.primary)
                        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                    }
                    .buttonStyle(SoftButtonStyle())

                    Button {
                        showEvaluation = true
                    } label: {
                        Label("正式评估", systemImage: "checkmark.shield")
                            .font(.system(size: 15, weight: .bold))
                            .frame(maxWidth: .infinity)
                            .frame(minHeight: 48)
                    }
                    .buttonStyle(.bordered)

                    // 切片删除（仅租户切片可删除；乐观更新 + 失败回滚）
                    if isDeletable {
                        Button(action: {
                            onDelete?()
                            dismiss()
                        }) {
                            HStack {
                                Image(systemName: "trash")
                                Text("删除此切片")
                                    .font(.system(size: 15, weight: .semibold))
                            }
                            .frame(maxWidth: .infinity)
                            .frame(height: 48)
            .foregroundColor(AppTheme.Icons.destructive)
                            .background(AppTheme.Colors.securityRed.opacity(0.1))
                            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                        }
                        .buttonStyle(SoftButtonStyle())
                    }
                }
                .padding(AppTheme.Spacing.lg)
            }
            .navigationTitle("智能体节点详情")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("完成") {
                        dismiss()
                    }
                }
            }
        }
        .sheet(isPresented: $showEvaluation) {
            AgentEvaluationView(agentId: node.id, agentName: node.name)
        }
    }
}

private struct AgentEvaluationView: View {
    let agentId: String
    let agentName: String
    @Environment(\.dismiss) private var dismiss
    @State private var run: AgentEvaluationRunDTO?
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                    if let run {
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("综合得分").font(AppTheme.Typography.supporting)
                                Text("\(Int(run.score))").font(.system(size: 40, weight: .bold, design: .rounded))
                            }
                            Spacer()
                            Text(evaluationStatusLabel(run.status))
                                .font(AppTheme.Typography.micro.weight(.semibold))
                                .padding(.horizontal, 12)
                                .frame(minHeight: 32)
                                .background(AppTheme.Colors.primary.opacity(0.1))
                                .foregroundStyle(AppTheme.Colors.primary)
                                .clipShape(Capsule())
                        }
                        .padding(AppTheme.Spacing.lg)
                        .background(AppTheme.Colors.surfaceTint)
                        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xl))

                        ReasoningCard(
                            steps: reasoningSteps(run.events),
                            isStreaming: ["queued", "running"].contains(run.status),
                            initiallyExpanded: true
                        )

                        ForEach(run.results) { result in
                            HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                                Image(systemName: result.status == "passed" ? "checkmark.circle.fill" : "exclamationmark.circle.fill")
                                    .foregroundStyle(result.status == "passed" ? AppTheme.Colors.statusCompleted : AppTheme.Colors.statusWarning)
                                VStack(alignment: .leading, spacing: 4) {
                                    HStack { Text(result.name).font(AppTheme.Typography.cardTitle); Spacer(); Text("\(Int(result.score))") }
                                    Text(result.detail).font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary)
                                }
                            }
                            .padding(AppTheme.Spacing.md)
                            .background(AppTheme.Colors.cardBackground)
                            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                        }
                        if let usage = run.usage, let total = usage.totalTokens {
                            Label("本次评估精确用量：\(total) tokens", systemImage: "gauge.with.dots.needle.50percent")
                                .font(AppTheme.Typography.supporting)
                        } else if ["queued", "running"].contains(run.status) {
                            Label("本次调用计量中", systemImage: "clock.arrow.circlepath")
                                .font(AppTheme.Typography.supporting)
                        }
                    } else if let errorMessage {
                        Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                            .font(AppTheme.Typography.supporting)
                            .foregroundStyle(AppTheme.Colors.statusError)
                            .padding(AppTheme.Spacing.md)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(AppTheme.Colors.statusError.opacity(0.1))
                            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                        Button("重试") { Task { await startAndMonitor() } }.buttonStyle(.borderedProminent)
                    } else {
                        ProgressView("正在创建可恢复的正式评估…")
                            .frame(maxWidth: .infinity, minHeight: 220)
                    }
                }
                .padding(AppTheme.Metrics.contentGutter)
            }
            .navigationTitle("评估 · \(agentName)")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("完成") { dismiss() } } }
            .task { await startAndMonitor() }
        }
    }

    private func reasoningSteps(_ events: [AgentEvaluationEventDTO]) -> [ReasoningStep] {
        events.map { event in
            let category = event.payload?.category ?? event.type
            let type: ReasoningStepType = category == "skill_load" ? .skillLoad : (category == "agent_spawn" ? .agentSpawn : (category.hasPrefix("tool") ? .toolCall : .thought))
            return ReasoningStep(
                id: String(event.seq), type: type, title: event.message,
                detail: [event.payload?.tool, event.payload?.detail].compactMap { $0 }.joined(separator: " · "),
                status: event.payload?.status ?? (event.type.hasSuffix("started") ? "running" : "done")
            )
        }
    }

    private func evaluationStatusLabel(_ status: String) -> String {
        switch status {
        case "queued": return "排队中"
        case "running": return "评估中"
        case "completed": return "已完成"
        case "failed": return "失败"
        default: return status
        }
    }

    @MainActor
    private func startAndMonitor() async {
        errorMessage = nil
        do {
            let storageKey = "agent.evaluation.active.\(agentId)"
            var current: AgentEvaluationRunDTO
            if let saved = UserDefaults.standard.string(forKey: storageKey), !saved.isEmpty {
                do {
                    current = try await APIClient.shared.fetchAgentEvaluation(id: saved)
                } catch {
                    UserDefaults.standard.removeObject(forKey: storageKey)
                    current = try await APIClient.shared.startAgentEvaluation(
                        agentId: agentId, requestId: "ios-eval-\(UUID().uuidString)"
                    )
                }
            } else {
                current = try await APIClient.shared.startAgentEvaluation(
                    agentId: agentId, requestId: "ios-eval-\(UUID().uuidString)"
                )
            }
            UserDefaults.standard.set(current.id, forKey: storageKey)
            run = current
            while !Task.isCancelled && ["queued", "running"].contains(current.status) {
                try await Task.sleep(for: .seconds(2))
                current = try await APIClient.shared.fetchAgentEvaluation(id: current.id)
                run = current
            }
        } catch is CancellationError {
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

// Simple Wrapping Tag Flow
private struct WrappingHStack: View {
    let items: [String]
    
    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(items, id: \.self) { item in
                    HStack(spacing: 4) {
                        Image(systemName: "book.closed.fill")
                            .font(.system(size: 10))
                        Text(item)
                            .font(.system(size: 12))
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .foregroundColor(AppTheme.Colors.primary)
                    .background(AppTheme.Colors.primary.opacity(0.1))
                    .clipShape(Capsule())
                }
            }
        }
    }
}

// MARK: - Xcode #Preview

#Preview("TopologyCanvasView - Light") {
    TopologyCanvasView()
        .environmentObject(AppState())
}

#Preview("TopologyCanvasView - Dark") {
    TopologyCanvasView()
        .environmentObject(AppState())
        .preferredColorScheme(.dark)
}
