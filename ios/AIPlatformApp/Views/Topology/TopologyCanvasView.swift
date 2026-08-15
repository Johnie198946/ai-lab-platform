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
    
    @State private var graph: TopologyGraph = MockData.topologyGraph
    @State private var selectedNode: AgentNode? = nil
    
    // Zoom and Pan Gestures
    @State private var offset: CGSize = .zero
    @State private var lastOffset: CGSize = .zero
    @State private var scale: CGFloat = 1.0
    @State private var lastScale: CGFloat = 1.0
    
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
                
                // MARK: - 2. Read-Only Security Notice & Chat Redirection Banner
                VStack {
                    Spacer()
                    conversationalGuidanceBanner
                }
            }
            .navigationTitle("协同拓扑 (只读)")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: resetCanvasView) {
                        Image(systemName: "arrow.counterclockwise")
                            .font(.system(size: 14))
                            .foregroundColor(AppTheme.Colors.textSecondary)
                    }
                }
            }
            .sheet(item: $selectedNode) { node in
                AgentNodeDetailSheet(node: node) { prompt in
                    selectedNode = nil
                    appState.navigateToChatWithPrompt(prompt)
                }
            }
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
        ForEach(graph.nodes) { node in
            NodeCardView(node: node, isSelected: selectedNode?.id == node.id)
                .position(x: node.x + 80, y: node.y + 20)
                .onTapGesture {
                    #if os(iOS)
                    UIImpactFeedbackGenerator(style: .light).impactOccurred()
                    #endif
                    self.selectedNode = node
                }
        }
    }
    
    // MARK: - Guidance Banner
    private var conversationalGuidanceBanner: some View {
        VStack(spacing: AppTheme.Spacing.xs) {
            HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                Image(systemName: "lock.shield.fill")
                    .font(.system(size: 16))
                    .foregroundColor(AppTheme.Colors.accent)
                
                VStack(alignment: .leading, spacing: 4) {
                    Text("只读拓扑安全硬锁 · 声明式后端驱动")
                        .font(.system(size: 13, weight: .bold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                    
                    Text("💡 拓扑结构由后端编排引擎驱动。如需调整节点或流向，请前往对话中下发指令（如：“帮我将质检节点串联至审计节点之后”）。")
                        .font(.system(size: 11))
                        .foregroundColor(AppTheme.Colors.textSecondary)
                        .lineSpacing(2)
                }
                
                Spacer()
                
                Button(action: {
                    #if os(iOS)
                    UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                    #endif
                    appState.navigateToChatWithPrompt("帮我根据当前制造业务流程，自动优化 DAG 拓扑编排结构。")
                }) {
                    Text("对话调整")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(AppTheme.Colors.onPrimary)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(AppTheme.Colors.accent)
                        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                }
                .buttonStyle(SoftButtonStyle())
            }
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.bottom, AppTheme.Spacing.md)
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
            
            HStack(spacing: 4) {
                Text(node.roleCategory)
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.primary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(AppTheme.Colors.primary.opacity(0.12))
                    .clipShape(Capsule())
                
                Text(node.status.labelText)
                    .font(.system(size: 10))
                    .foregroundColor(AppTheme.Colors.textTertiary)
            }
        }
        .padding(10)
        .frame(width: 160)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: AppTheme.Radius.md)
                .stroke(
                    isSelected ? AppTheme.Colors.primary : AppTheme.Colors.border,
                    lineWidth: isSelected ? 2 : 1
                )
        )
    }
}

// MARK: - Agent Node Detail Drawer Sheet
public struct AgentNodeDetailSheet: View {
    public let node: AgentNode
    public var onAdjustViaChat: (String) -> Void
    
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
                    
                    // System Prompt Summary
                    VStack(alignment: .leading, spacing: 6) {
                        Text("System Prompt 策略摘要")
                            .font(.system(size: 13, weight: .bold))
                            .foregroundColor(AppTheme.Colors.textSecondary)
                        
                        Text(node.systemPromptSummary)
                            .font(.system(size: 14))
                            .foregroundColor(AppTheme.Colors.textPrimary)
                            .padding(AppTheme.Spacing.md)
                            .background(AppTheme.Colors.secondaryBackground)
                            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                    }
                    
                    // Subscribed Knowledge Packs
                    VStack(alignment: .leading, spacing: 6) {
                        Text("已挂载知识包")
                            .font(.system(size: 13, weight: .bold))
                            .foregroundColor(AppTheme.Colors.textSecondary)
                        
                        if node.subscribedKnowledge.isEmpty {
                            Text("暂无挂载知识库")
                                .font(.system(size: 13))
                                .foregroundColor(AppTheme.Colors.textTertiary)
                        } else {
                            WrappingHStack(items: node.subscribedKnowledge)
                        }
                    }
                    
                    // Dependencies
                    VStack(alignment: .leading, spacing: 6) {
                        Text("DAG 依赖链路")
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
                    
                    // Chat Adjustment Action Button
                    Button(action: {
                        onAdjustViaChat("请帮我调整节点 [\(node.name)] 的执行策略与上下游连接...")
                    }) {
                        HStack {
                            Image(systemName: "bubble.left.and.bubble.right.fill")
                            Text("在对话中调整该节点配置")
                                .font(.system(size: 15, weight: .bold))
                        }
                        .frame(maxWidth: .infinity)
                        .frame(height: 48)
                        .foregroundColor(AppTheme.Colors.onPrimary)
                        .background(AppTheme.Colors.primary)
                        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                    }
                    .buttonStyle(SoftButtonStyle())
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
