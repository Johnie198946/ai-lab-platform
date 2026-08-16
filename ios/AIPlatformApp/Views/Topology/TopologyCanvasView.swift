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
                AppTheme.Colors.groupedBackground
                    .ignoresSafeArea()
                
                // MARK: - 1. Interactive DAG Canvas Area
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
                
                // MARK: - 2. （底部长说明横幅已移除 → 精简为角落微型 Chip，见 guidanceChip）
            }
            .navigationTitle(isEditMode ? "协同拓扑 (布局编辑)" : "协同拓扑")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button(action: toggleEditMode) {
                        Image(systemName: isEditMode ? "checkmark.circle.fill" : "square.and.pencil")
                            .font(.system(size: 14))
                            .foregroundColor(isEditMode ? AppTheme.Colors.primary : AppTheme.Colors.textSecondary)
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: resetCanvasView) {
                        Image(systemName: "arrow.counterclockwise")
                            .font(.system(size: 14))
                            .foregroundColor(AppTheme.Colors.textSecondary)
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
            .overlay(alignment: .bottomLeading) { guidanceChip }
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
        } catch {
            loadFailed = true
        }
        // 本租户切片叠加渲染（同源 /api/v1/tenant-agents，多租户隔离由后端保证）
        if let list = try? await APIClient.shared.fetchTenantAgents() {
            mergeTenantAgents(list)
        }
        isLoading = false
    }

    /// 将本租户 Agent 切片叠加为拓扑节点（第三列布局，仅切片可删除）。
    private func mergeTenantAgents(_ list: [TenantAgentDTO]) {
        var ids = Set<String>()
        var nodes = graph.nodes
        for (i, ta) in list.enumerated() {
            ids.insert(ta.id)
            nodes.append(
                AgentNode(
                    id: ta.id,
                    name: ta.customName ?? ta.baseAgentId,
                    roleCategory: "租户切片 · \(ta.baseAgentId)",
                    systemPromptSummary: ta.privatePromptDelta.isEmpty ? "基于基线 \(ta.baseAgentId) 的租户私有切片" : ta.privatePromptDelta,
                    status: ta.isActive ? .idle : .error,
                    position: tenantLayout(index: i)
                )
            )
        }
        graph.nodes = nodes
        tenantAgentIds = ids
    }

    private func tenantLayout(index: Int) -> CGPoint {
        CGPoint(x: 380, y: 140 + CGFloat(index) * 100)
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
        .foregroundColor(AppTheme.Colors.textSecondary)
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
                        .foregroundColor(AppTheme.Colors.onPrimary)
                        .background(AppTheme.Colors.primary)
                        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                    }
                    .buttonStyle(SoftButtonStyle())

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
                            .foregroundColor(AppTheme.Colors.securityRed)
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
