//
//  KnowledgeView.swift
//  AIPlatformApp
//
//  知识库 Tab 两层重构：
//   上层 = 类目订阅卡（GET /catalog，订阅/退订，已订置顶）
//   下层 = 已订内容按类目分组浏览（复用 /search + _rel_visible 前缀匹配）
//  双轨：联网真实 API，离线/失败自动切本地 Mock 并标注「演示数据」。
//

import SwiftUI

public struct KnowledgeView: View {
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var api: APIClient
    @Environment(\.colorScheme) private var colorScheme

    @State private var catalog: [CatalogCategory] = []
    @State private var subscriptions: Set<String> = []
    @State private var searchText: String = ""
    @State private var searchDocs: [SearchDoc] = []
    @State private var isLoadingCatalog: Bool = false
    @State private var isSearching: Bool = false
    @State private var loadTask: Task<Void, Never>? = nil

    public init() {}

    // 已订类目置顶
    private var orderedCatalog: [CatalogCategory] {
        catalog.sorted {
            let lhsSub = subscriptions.contains($0.category)
            let rhsSub = subscriptions.contains($1.category)
            if lhsSub != rhsSub { return lhsSub }
            return $0.category < $1.category
        }
    }

    // 搜索结果按类目分组
    private var groupedDocs: [(category: String, docs: [SearchDoc])] {
        let groups = Dictionary(grouping: searchDocs, by: { $0.category })
        return groups
            .map { (category: $0.key, docs: $0.value) }
            .sorted { $0.category < $1.category }
    }

    public var body: some View {
        NavigationStack {
            ZStack {
                AppTheme.Colors.groupedBackground
                    .ignoresSafeArea()

                ScrollView {
                    VStack(spacing: AppTheme.Spacing.md) {
                        if api.isOfflineMode {
                            demoModeBanner
                        }

                        categorySubscriptionSection
                        subscribedContentSection
                    }
                    .padding(.horizontal, AppTheme.Spacing.md)
                    .padding(.top, AppTheme.Spacing.sm)
                    .padding(.bottom, AppTheme.Spacing.xl)
                }
            }
            .navigationTitle("知识")
            .searchable(text: $searchText, prompt: "搜索已订阅知识...")
            .onSubmit(of: .search) {
                Task { await runSearch() }
            }
            .task {
                await initialLoad()
            }
            .onDisappear {
                loadTask?.cancel()
            }
            .refreshable {
                await initialLoad()
            }
        }
    }

    // MARK: - 离线标注

    private var demoModeBanner: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: "wifi.slash")
                .font(.system(size: 12, weight: .semibold))
            Text("演示数据 · 离线降级（联网后自动切回真实 API）")
                .font(.system(size: 12, weight: .semibold))
            Spacer()
        }
        .foregroundColor(AppTheme.Colors.onSemantic)
        .padding(AppTheme.Spacing.sm)
        .background(AppTheme.Colors.securityYellow)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
    }

    // MARK: - 上层：类目订阅卡

    private var categorySubscriptionSection: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            sectionHeader(icon: "square.grid.2x2.fill", title: "类目订阅")

            if isLoadingCatalog && catalog.isEmpty {
                ProgressView()
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, AppTheme.Spacing.xl)
            } else {
                LazyVStack(spacing: AppTheme.Spacing.sm) {
                    ForEach(orderedCatalog) { cat in
                        CategorySubscriptionCard(
                            category: cat,
                            isSubscribed: subscriptions.contains(cat.category),
                            onToggle: { toggleSubscription(cat) }
                        )
                    }
                }
            }
        }
    }

    // MARK: - 下层：已订内容分组浏览

    private var subscribedContentSection: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            sectionHeader(icon: "text.book.closed.fill", title: "已订内容（按类目分组）")

            if subscriptions.isEmpty {
                emptySubscriptionsHint
            } else if searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                subscribedCategoryOverview
            } else if isSearching {
                ProgressView()
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, AppTheme.Spacing.xl)
            } else if groupedDocs.isEmpty {
                emptySearchResult
            } else {
                ForEach(groupedDocs, id: \.category) { group in
                    SearchGroupCard(category: group.category, docs: group.docs)
                }
            }
        }
    }

    private var emptySubscriptionsHint: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: "plus.magnifyingglass")
                .font(.system(size: 34))
                .foregroundColor(AppTheme.Colors.textTertiary)
            Text("尚未订阅任何类目")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(AppTheme.Colors.textSecondary)
            Text("在上方类目订阅卡中点击「订阅」，即可在此按类目浏览内容。")
                .font(.system(size: 12))
                .foregroundColor(AppTheme.Colors.textTertiary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, AppTheme.Spacing.xl)
    }

    private var subscribedCategoryOverview: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            ForEach(orderedCatalog.filter { subscriptions.contains($0.category) }) { cat in
                HStack(spacing: AppTheme.Spacing.sm) {
                    Image(systemName: "folder.fill")
                        .font(.system(size: 13))
                        .foregroundColor(AppTheme.Colors.accent)
                    Text(cat.title)
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                    Spacer()
                    Text("\(cat.docCount) 篇")
                        .font(.system(size: 12))
                        .foregroundColor(AppTheme.Colors.textTertiary)
                }
                .padding(AppTheme.Spacing.md)
                .background(AppTheme.Colors.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            }
            Text("输入关键词搜索，结果将按已订类目分组展示。")
                .font(.system(size: 12))
                .foregroundColor(AppTheme.Colors.textTertiary)
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.top, AppTheme.Spacing.xs)
        }
    }

    private var emptySearchResult: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: "doc.text.magnifyingglass")
                .font(.system(size: 32))
                .foregroundColor(AppTheme.Colors.textTertiary)
            Text("未找到相关已订阅内容")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(AppTheme.Colors.textSecondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, AppTheme.Spacing.xl)
    }

    private func sectionHeader(icon: String, title: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 13))
                .foregroundColor(AppTheme.Colors.accent)
            Text(title)
                .font(.system(size: 15, weight: .bold))
                .foregroundColor(AppTheme.Colors.textPrimary)
            Spacer()
        }
    }

    // MARK: - Actions

    private func initialLoad() async {
        loadTask = Task {
            isLoadingCatalog = true
            // 类目（联网，失败回退 Mock）
            if let cats = try? await api.fetchCatalog(), !cats.isEmpty {
                catalog = cats
            } else if catalog.isEmpty {
                catalog = Self.mockCatalog
            }
            // 我的订阅（联网，失败回退 Mock）
            if let subs = try? await api.fetchSubscriptions() {
                subscriptions = Set(subs)
            } else if subscriptions.isEmpty {
                subscriptions = Set(Self.mockSubscriptions)
            }
            isLoadingCatalog = false
        }
        await loadTask?.value
    }

    private func toggleSubscription(_ cat: CatalogCategory) {
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        #endif
        if api.isOfflineMode {
            // 离线：本地 Mock 切换
            if subscriptions.contains(cat.category) {
                subscriptions.remove(cat.category)
            } else {
                subscriptions.insert(cat.category)
            }
            return
        }
        loadTask = Task {
            do {
                if subscriptions.contains(cat.category) {
                    let subs = try await api.unsubscribe(category: cat.category)
                    subscriptions = Set(subs)
                } else {
                    let subs = try await api.subscribe(category: cat.category)
                    subscriptions = Set(subs)
                }
            } catch {
                // 失败回退本地 Mock（保持演示可用）
                if subscriptions.contains(cat.category) {
                    subscriptions.remove(cat.category)
                } else {
                    subscriptions.insert(cat.category)
                }
            }
        }
    }

    private func runSearch() async {
        let q = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty else {
            searchDocs = []
            return
        }
        isSearching = true
        defer { isSearching = false }
        if api.isOfflineMode {
            // 离线 Mock：按类目过滤演示结果
            searchDocs = Self.mockDocs.filter {
                $0.title.localizedCaseInsensitiveContains(q)
                    || $0.snippet.localizedCaseInsensitiveContains(q)
            }
            return
        }
        if let docs = try? await api.search(query: q) {
            searchDocs = docs
        } else {
            searchDocs = Self.mockDocs.filter {
                $0.title.localizedCaseInsensitiveContains(q)
                    || $0.snippet.localizedCaseInsensitiveContains(q)
            }
        }
    }
}

// MARK: - 类目订阅卡

public struct CategorySubscriptionCard: View {
    public let category: CatalogCategory
    public let isSubscribed: Bool
    public var onToggle: () -> Void

    public var body: some View {
        HStack(spacing: AppTheme.Spacing.md) {
            Image(systemName: isSubscribed ? "folder.fill" : "folder")
                .font(.system(size: 20))
                .foregroundColor(isSubscribed ? AppTheme.Colors.accent : AppTheme.Colors.textTertiary)
                .frame(width: 30)

            VStack(alignment: .leading, spacing: 3) {
                Text(category.title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.textPrimary)
                    .lineLimit(1)
                Text("\(category.docCount) 篇 · \(category.category)")
                    .font(.system(size: 11))
                    .foregroundColor(AppTheme.Colors.textTertiary)
                    .lineLimit(1)
            }

            Spacer()

            Button(action: onToggle) {
                HStack(spacing: 4) {
                    Image(systemName: isSubscribed ? "checkmark" : "plus")
                        .font(.system(size: 11, weight: .bold))
                    Text(isSubscribed ? "已订阅" : "订阅")
                        .font(.system(size: 12, weight: .bold))
                }
                .foregroundColor(isSubscribed ? AppTheme.Colors.securityGreen : AppTheme.Colors.onPrimary)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(
                    isSubscribed
                        ? AnyShapeStyle(AppTheme.Colors.securityGreen.opacity(0.15))
                        : AnyShapeStyle(AppTheme.Colors.primary)
                )
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            }
            .buttonStyle(SoftButtonStyle())
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }
}

// MARK: - 搜索结果分组卡

public struct SearchGroupCard: View {
    public let category: String
    public let docs: [SearchDoc]

    public var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            HStack(spacing: 6) {
                Image(systemName: "folder.fill")
                    .font(.system(size: 11))
                Text(category)
                    .font(.system(size: 12, weight: .bold))
                Spacer()
                Text("\(docs.count) 篇")
                    .font(.system(size: 11))
                    .foregroundColor(AppTheme.Colors.textTertiary)
            }
            .foregroundColor(AppTheme.Colors.accent)

            Divider()

            ForEach(docs) { doc in
                VStack(alignment: .leading, spacing: 3) {
                    Text(doc.title)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                        .lineLimit(1)
                    if !doc.snippet.isEmpty {
                        Text(doc.snippet)
                            .font(.system(size: 11))
                            .foregroundColor(AppTheme.Colors.textSecondary)
                            .lineLimit(2)
                    }
                }
                .padding(.vertical, 2)
            }
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }
}

// MARK: - 离线 Mock 数据

extension KnowledgeView {
    static let mockCatalog: [CatalogCategory] = [
        CatalogCategory(category: "wiki", pathPrefix: "wiki/", title: "编译知识条目", docCount: 128, open: true),
        CatalogCategory(category: "raw", pathPrefix: "raw/", title: "原始资料", docCount: 342, open: true),
        CatalogCategory(category: "研究系统", pathPrefix: "研究系统/", title: "研究报告与来源卡片", docCount: 56, open: true),
        CatalogCategory(category: "竞品情报", pathPrefix: "竞品情报/", title: "竞品分析", docCount: 87, open: true),
        CatalogCategory(category: "AI情报雷达", pathPrefix: "AI情报雷达/", title: "情报日报", docCount: 214, open: true),
        CatalogCategory(category: "产品设计", pathPrefix: "产品设计/", title: "产品文档", docCount: 43, open: true),
        CatalogCategory(category: "客户画像", pathPrefix: "客户画像/", title: "客户资料", docCount: 31, open: true),
        CatalogCategory(category: "任务记录", pathPrefix: "任务记录/", title: "项目任务记录", docCount: 76, open: true),
        CatalogCategory(category: "决策记录", pathPrefix: "决策记录/", title: "决策记录", docCount: 58, open: true),
        CatalogCategory(category: "knowledge/行业知识/金融", pathPrefix: "knowledge/行业知识/金融/", title: "金融", docCount: 23, open: true),
        CatalogCategory(category: "knowledge/行业知识/制造", pathPrefix: "knowledge/行业知识/制造/", title: "制造", docCount: 41, open: true),
    ]

    static let mockSubscriptions: [String] = ["wiki", "竞品情报"]

    static let mockDocs: [SearchDoc] = [
        SearchDoc(path: "wiki/模型观察.md", title: "模型观察", score: 12, snippet: "DeepSeek 新模型发布，推理成本显著下降。"),
        SearchDoc(path: "wiki/华为.md", title: "华为", score: 10, snippet: "芯片物理极限与昇腾 AI 集群。"),
        SearchDoc(path: "竞品情报/DeepSeek.md", title: "DeepSeek", score: 9, snippet: "竞品动态：开源模型与定价策略。"),
        SearchDoc(path: "knowledge/行业知识/金融/动态.md", title: "金融动态", score: 8, snippet: "分布式对账与防重放协议实践。"),
        SearchDoc(path: "knowledge/行业知识/制造/SMT.md", title: "SMT 设备健康指标", score: 7, snippet: "贴片机真空吸嘴负压告警阈值。"),
    ]
}

// MARK: - Xcode #Preview

#Preview("KnowledgeView - Light") {
    KnowledgeView()
        .environmentObject(AppState())
        .environmentObject(APIClient.shared)
}

#Preview("KnowledgeView - Dark") {
    KnowledgeView()
        .environmentObject(AppState())
        .environmentObject(APIClient.shared)
        .preferredColorScheme(.dark)
}
