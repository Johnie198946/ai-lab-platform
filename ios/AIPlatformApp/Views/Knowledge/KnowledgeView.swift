//
//  KnowledgeView.swift
//  AIPlatformApp
//
//  知识库 Tab 两层重构：
//   上层 = 知识钱包偏好（不授予权限）
//   下层 = 当前租户有效知识范围内的内容浏览
//  双轨：联网真实 API，离线/失败自动切本地 Mock 并标注「演示数据」。
//

import SwiftUI

private enum KnowledgeRecoveryAction: Equatable {
    case dismiss
    case retry
    case refreshCatalog
    case viewPlans
}

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
    @State private var selectedCategory: CatalogCategory? = nil
    @State private var permissionMessage: String? = nil
    @State private var recoveryAction: KnowledgeRecoveryAction = .dismiss
    @State private var showingSubscriptionCenter: Bool = false
    @State private var highlightedEntitlementKey: String? = nil
    @State private var walletBusyCategory: String? = nil
    @State private var successMessage: String? = nil
    @State private var pendingReviewCount: Int = 0

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

    private var availableCategoryCount: Int {
        catalog.filter { !$0.requiresKnowledgePack }.count
    }

    public var body: some View {
        NavigationStack {
            ZStack {
                QuantumMistBackground()

                ScrollView {
                    VStack(spacing: AppTheme.Spacing.md) {
                        knowledgeHero

                        if api.isOfflineMode {
                            demoModeBanner
                        }

                        if appState.currentProfile.role == .masterAdmin && pendingReviewCount > 0 {
                            governanceReviewBanner
                        }

                        knowledgeWalletSection
                        categorySubscriptionSection
                        subscribedContentSection
                    }
                    .padding(.horizontal, AppTheme.Metrics.contentGutter)
                    .padding(.top, AppTheme.Spacing.md)
                    .padding(.bottom, AppTheme.Spacing.xl)
                }
            }
            .navigationTitle("知识")
            .searchable(text: $searchText, prompt: "搜索当前可用知识...")
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
            .fullScreenCover(item: $selectedCategory) { category in
                KnowledgeWalletDetail(
                    category: category,
                    isSubscribed: subscriptions.contains(category.category),
                    onToggle: { toggleSubscription(category) },
                    onDismiss: { selectedCategory = nil }
                )
            }
            .sheet(isPresented: $showingSubscriptionCenter) {
                NavigationStack {
                    SubscriptionCenterView(highlightedEntitlementKey: highlightedEntitlementKey)
                }
            }
            .alert("知识权限", isPresented: Binding(
                get: { permissionMessage != nil },
                set: { if !$0 { permissionMessage = nil } }
            )) {
                if recoveryAction == .viewPlans {
                    Button("查看套餐") {
                        permissionMessage = nil
                        showingSubscriptionCenter = true
                    }
                }
                if recoveryAction == .retry || recoveryAction == .refreshCatalog {
                    Button(recoveryAction == .refreshCatalog ? "刷新目录" : "重试") {
                        permissionMessage = nil
                        Task { await initialLoad() }
                    }
                }
                Button("关闭", role: .cancel) { permissionMessage = nil }
            } message: {
                Text(permissionMessage ?? "套餐或知识权限已变化")
            }
            .overlay(alignment: .top) {
                if let successMessage {
                    Label(successMessage, systemImage: "checkmark.circle.fill")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                        .padding(.horizontal, AppTheme.Spacing.md)
                        .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                        .background(AppTheme.Colors.successSurface)
                        .clipShape(Capsule())
                        .overlay { Capsule().stroke(AppTheme.Colors.border, lineWidth: 0.75) }
                        .padding(.top, AppTheme.Spacing.sm)
                        .transition(.move(edge: .top).combined(with: .opacity))
                        .accessibilityAddTraits(.isStaticText)
                }
            }
        }
    }

    private var knowledgeHero: some View {
        HStack(alignment: .center, spacing: AppTheme.Spacing.lg) {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                Text("KNOWLEDGE · LIVE CONTEXT")
                    .font(AppTheme.Typography.micro)
                    .tracking(0.8)
                    .foregroundColor(AppTheme.Icons.interactive)

                Text("让知识随任务而来")
                    .font(AppTheme.Typography.sectionTitle)
                    .foregroundColor(AppTheme.Colors.textPrimary)

                Text("钱包 \(subscriptions.count) 张 · 当前可用 \(availableCategoryCount) 个类目")
                    .font(AppTheme.Typography.supporting)
                    .foregroundColor(AppTheme.Colors.textSecondary)

                Label("上下文已就绪", systemImage: "checkmark.circle.fill")
                    .font(AppTheme.Typography.micro)
                    .foregroundColor(AppTheme.Colors.statusCompleted)
            }

            Spacer(minLength: 0)

            Image(systemName: "books.vertical.fill")
                .font(.system(size: 34, weight: .semibold))
                .foregroundColor(AppTheme.Icons.intelligence)
                .frame(width: 68, height: 68)
                .background(AppTheme.Colors.selectionTint)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        }
        .padding(AppTheme.Spacing.xl)
        .background(
            LinearGradient(
                colors: [AppTheme.Colors.cardBackground, AppTheme.Colors.surfaceTint],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                .stroke(AppTheme.Colors.border.opacity(0.8), lineWidth: 0.75)
        }
        .shadow(color: Color(hex: "3D437E").opacity(0.08), radius: 18, y: 6)
        .accessibilityElement(children: .combine)
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

    private var governanceReviewBanner: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: "checklist.unchecked")
                .font(.system(size: 13, weight: .semibold))
            VStack(alignment: .leading, spacing: 2) {
                Text("知识治理待复核")
                    .font(.system(size: 12, weight: .bold))
                Text("还有 \(pendingReviewCount) 篇知识未完成权限与准入确认，不会进入检索。")
                    .font(.system(size: 11))
            }
            Spacer()
        }
        .foregroundColor(AppTheme.Colors.textPrimary)
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.warningSurface)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        .accessibilityElement(children: .combine)
    }

    // MARK: - 上层：类目订阅卡

    private var subscribedCategories: [CatalogCategory] {
        orderedCatalog.filter { subscriptions.contains($0.category) }
    }

    private var knowledgeWalletSection: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("知识钱包")
                        .font(AppTheme.Typography.sectionTitle)
                        .foregroundColor(AppTheme.Colors.textPrimary)
                    Text("上下滑动卡组；加入钱包只影响默认检索优先级")
                        .font(AppTheme.Typography.supporting)
                        .foregroundColor(AppTheme.Colors.textSecondary)
                }
                Spacer()
                Text("\(subscribedCategories.count) 张")
                    .font(AppTheme.Typography.label)
                    .foregroundColor(AppTheme.Colors.primary)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 7)
                    .background(AppTheme.Colors.selectionTint)
                    .clipShape(Capsule())
            }

            if subscribedCategories.isEmpty {
                emptySubscriptionsHint
            } else {
                ScrollView(.vertical, showsIndicators: false) {
                    LazyVStack(spacing: -116) {
                        ForEach(Array(subscribedCategories.enumerated()), id: \.element.id) { index, category in
                            Button {
                                #if os(iOS)
                                UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                                #endif
                                selectedCategory = category
                            } label: {
                                KnowledgeWalletCard(category: category, index: index)
                            }
                            .buttonStyle(SoftButtonStyle())
                            .zIndex(Double(subscribedCategories.count - index))
                            .accessibilityHint("双击抽出此知识库卡片")
                        }
                    }
                    .padding(.horizontal, 2)
                    .padding(.bottom, 116)
                }
                .frame(height: min(330, 184 + CGFloat(max(0, subscribedCategories.count - 1)) * 42))
                .scrollClipDisabled()
            }
        }
    }

    private var categorySubscriptionSection: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            sectionHeader(icon: "square.grid.2x2.fill", title: "知识目录与权限")

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
                            isLoading: walletBusyCategory == cat.category,
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
            sectionHeader(icon: "text.book.closed.fill", title: "钱包内容（按类目分组）")

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
                .foregroundColor(AppTheme.Icons.tertiary)
            Text("知识钱包还是空的")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(AppTheme.Colors.textSecondary)
            Text("绿色公共知识默认可用；加入钱包后会优先参与聊天与工作流检索。")
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
                        .foregroundColor(AppTheme.Icons.intelligence)
                    Text(cat.title)
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                    Spacer()
                    Text("\(cat.docCount) 篇")
                        .font(.system(size: 12))
                        .foregroundColor(AppTheme.Colors.textTertiary)
                }
                .padding(AppTheme.Spacing.md)
                .background(AppTheme.Colors.surfaceElevated)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                .overlay {
                    RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                        .stroke(AppTheme.Colors.border.opacity(0.7), lineWidth: 0.75)
                }
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
                .foregroundColor(AppTheme.Icons.tertiary)
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
                .foregroundColor(AppTheme.Icons.intelligence)
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
            do {
                let response = try await api.fetchCatalog()
                catalog = response.catalog
                pendingReviewCount = response.pendingReviewCount ?? 0
            } catch {
                if api.isOfflineMode && catalog.isEmpty {
                    catalog = Self.mockCatalog
                } else {
                    catalog = []
                    pendingReviewCount = 0
                    permissionMessage = "知识目录不可用或权限已经变化，请刷新后重试。"
                    recoveryAction = .refreshCatalog
                }
            }
            // 我的知识钱包（旧 subscriptions 接口仅作一个版本兼容）
            if let subs = try? await api.fetchSubscriptions() {
                let validCategories = Set(catalog.map(\.category))
                subscriptions = Set(subs).intersection(validCategories)
            } else if !catalog.isEmpty {
                subscriptions = Set(catalog.filter { $0.inWallet == true }.map(\.category))
            } else if subscriptions.isEmpty {
                subscriptions = Set(Self.mockSubscriptions)
            }
            isLoadingCatalog = false
        }
        await loadTask?.value
    }

    private func toggleSubscription(_ cat: CatalogCategory) {
        if cat.requiresKnowledgePack {
            highlightedEntitlementKey = cat.entitlementKey
            selectedCategory = nil
            DispatchQueue.main.async { showingSubscriptionCenter = true }
            return
        }
        guard walletBusyCategory == nil else { return }
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
            walletBusyCategory = cat.category
            defer { walletBusyCategory = nil }
            do {
                let removing = subscriptions.contains(cat.category)
                if subscriptions.contains(cat.category) {
                    let subs = try await api.unsubscribe(category: cat.category)
                    let validCategories = Set(catalog.map(\.category))
                    subscriptions = Set(subs).intersection(validCategories)
                } else {
                    let subs = try await api.subscribe(category: cat.category)
                    let validCategories = Set(catalog.map(\.category))
                    subscriptions = Set(subs).intersection(validCategories)
                }
                showSuccess(removing ? "已移出知识钱包" : "已加入知识钱包")
            } catch {
                handleKnowledgeError(error, category: cat)
            }
        }
    }

    private func showSuccess(_ message: String) {
        withAnimation(.easeOut(duration: 0.2)) { successMessage = message }
        Task {
            try? await Task.sleep(nanoseconds: 2_400_000_000)
            await MainActor.run {
                withAnimation(.easeIn(duration: 0.16)) { successMessage = nil }
            }
        }
    }

    private func handleKnowledgeError(_ error: Error, category: CatalogCategory? = nil) {
        if let apiError = error as? APIError, let detail = apiError.actionable {
            permissionMessage = detail.message
            switch detail.action {
            case "view_plans":
                highlightedEntitlementKey = category?.entitlementKey
                recoveryAction = .viewPlans
            case "refresh_catalog", "refresh_permissions":
                recoveryAction = .refreshCatalog
            case "retry":
                recoveryAction = .retry
            default:
                recoveryAction = .dismiss
            }
        } else {
            permissionMessage = error.localizedDescription
            recoveryAction = api.isOfflineMode ? .retry : .refreshCatalog
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
        do {
            searchDocs = try await api.search(query: q)
        } catch {
            if api.isOfflineMode {
                searchDocs = Self.mockDocs.filter {
                    $0.title.localizedCaseInsensitiveContains(q)
                        || $0.snippet.localizedCaseInsensitiveContains(q)
                }
            } else {
                searchDocs = []
                handleKnowledgeError(error)
            }
        }
    }
}

// MARK: - Knowledge Wallet

private struct KnowledgeWalletCard: View {
    let category: CatalogCategory
    let index: Int

    private var palette: [Color] {
        let palettes: [[Color]] = [
            [Color(hex: "8D69EA"), Color(hex: "6C4FD6")],
            [Color(hex: "55BEEB"), Color(hex: "467CE2")],
            [Color(hex: "42D0C4"), Color(hex: "3199C9")],
            [Color(hex: "D58BD3"), Color(hex: "8C63DE")]
        ]
        return palettes[index % palettes.count]
    }

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack(alignment: .top) {
                Image(systemName: "books.vertical.fill")
                    .font(.title3.weight(.semibold))
                    .foregroundColor(.white)
                    .frame(width: 44, height: 44)
                    .background(Color.white.opacity(0.18))
                    .clipShape(Circle())
                Spacer()
                Text("QUANTUM KNOWLEDGE")
                    .font(.system(size: 9, weight: .bold, design: .rounded))
                    .tracking(1.0)
                    .foregroundColor(.white.opacity(0.76))
            }

            Spacer(minLength: 0)

            Text(category.title)
                .font(.system(size: 21, weight: .semibold, design: .rounded))
                .foregroundColor(.white)
                .lineLimit(1)

            HStack {
                Text("\(category.docCount) 篇文档")
                Spacer()
                Label(category.securityLabel, systemImage: category.securityIcon)
            }
            .font(AppTheme.Typography.micro)
            .foregroundColor(.white.opacity(0.86))
        }
        .padding(AppTheme.Spacing.lg)
        .frame(maxWidth: .infinity)
        .frame(height: 184)
        .background(
            LinearGradient(colors: palette, startPoint: .topLeading, endPoint: .bottomTrailing)
        )
        .overlay(alignment: .topTrailing) {
            Circle()
                .fill(Color.white.opacity(0.12))
                .frame(width: 150, height: 150)
                .offset(x: 55, y: -70)
        }
        .clipShape(RoundedRectangle(cornerRadius: 26, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 26, style: .continuous)
                .stroke(Color.white.opacity(0.36), lineWidth: 0.8)
        }
        .shadow(color: palette.last!.opacity(0.23), radius: 22, y: 11)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(category.title)，\(category.docCount) 篇文档，\(category.securityLabel)，已加入知识钱包")
    }
}

private struct KnowledgeWalletDetail: View {
    let category: CatalogCategory
    let isSubscribed: Bool
    let onToggle: () -> Void
    let onDismiss: () -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var appeared = false

    var body: some View {
        ZStack {
            QuantumMistBackground()

            ScrollView(showsIndicators: false) {
                VStack(spacing: AppTheme.Spacing.xxl) {
                    HStack {
                        Button(action: onDismiss) {
                            Image(systemName: "chevron.down")
                                .font(.body.weight(.semibold))
                                .foregroundColor(AppTheme.Colors.textPrimary)
                                .minimumTouchTarget()
                                .background(AppTheme.Colors.cardBackground)
                                .clipShape(Circle())
                        }
                        .buttonStyle(SoftButtonStyle())
                        Spacer()
                        Text("知识库详情")
                            .font(AppTheme.Typography.cardTitle)
                            .foregroundColor(AppTheme.Colors.textPrimary)
                        Spacer()
                        Color.clear.frame(width: 44, height: 44)
                    }

                    KnowledgeWalletCard(category: category, index: category.category.count)
                        .scaleEffect(appeared ? 1 : (reduceMotion ? 1 : 0.88))
                        .offset(y: appeared ? 0 : (reduceMotion ? 0 : 72))
                        .opacity(appeared ? 1 : 0)

                    VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                        detailRow("安全等级", value: category.securityLabel, icon: category.securityIcon)
                        detailRow("权限来源", value: category.permissionSource, icon: "key.fill")
                        detailRow("钱包状态", value: isSubscribed ? "参与默认检索" : "未加入", icon: "checkmark.seal.fill")
                        detailRow("内容规模", value: "\(category.docCount) 篇", icon: "doc.on.doc.fill")
                        detailRow("知识成熟度", value: category.maturityLabel, icon: "chart.line.uptrend.xyaxis")
                        detailRow("新鲜度", value: category.freshnessLabel, icon: "clock.badge.checkmark.fill")
                        detailRow("来源证据", value: "\(category.sourceCount ?? 0) 条", icon: "link.badge.plus")

                        Button(action: onToggle) {
                            Label(category.walletActionLabel(isInWallet: isSubscribed), systemImage: isSubscribed ? "minus" : "plus")
                        }
                        .buttonStyle(QuantumPrimaryButtonStyle())
                    }
                    .padding(AppTheme.Spacing.xl)
                    .background(AppTheme.Colors.cardBackground)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
                    .overlay {
                        RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                            .stroke(AppTheme.Colors.border, lineWidth: 0.75)
                    }
                }
                .padding(.horizontal, AppTheme.Metrics.contentGutter)
                .padding(.top, AppTheme.Spacing.lg)
                .padding(.bottom, AppTheme.Spacing.xxxl)
            }
        }
        .onAppear {
            withAnimation(reduceMotion ? nil : .spring(response: 0.42, dampingFraction: 0.82)) {
                appeared = true
            }
        }
    }

    private func detailRow(_ title: String, value: String, icon: String) -> some View {
        HStack(spacing: AppTheme.Spacing.md) {
            Image(systemName: icon)
                .foregroundColor(AppTheme.Icons.interactive)
                .frame(width: 40, height: 40)
                .background(AppTheme.Colors.selectionTint)
                .clipShape(Circle())
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(AppTheme.Typography.micro)
                    .foregroundColor(AppTheme.Colors.textTertiary)
                Text(value)
                    .font(AppTheme.Typography.supporting.weight(.semibold))
                    .foregroundColor(AppTheme.Colors.textPrimary)
                    .lineLimit(2)
            }
            Spacer()
        }
    }
}

// MARK: - 类目订阅卡

public struct CategorySubscriptionCard: View {
    public let category: CatalogCategory
    public let isSubscribed: Bool
    public let isLoading: Bool
    public var onToggle: () -> Void

    public var body: some View {
        HStack(spacing: AppTheme.Spacing.md) {
            Image(systemName: isSubscribed ? "folder.fill" : "folder")
                .font(.system(size: 20))
                .foregroundColor(isSubscribed ? AppTheme.Icons.intelligence : AppTheme.Icons.tertiary)
                .frame(width: 30)

            VStack(alignment: .leading, spacing: 3) {
                Text(category.title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.textPrimary)
                    .lineLimit(1)
                Text("\(category.docCount) 篇 · \(category.maturityLabel) · \(category.freshnessLabel)")
                    .font(.system(size: 11))
                    .foregroundColor(AppTheme.Colors.textTertiary)
                    .lineLimit(1)
                Label(category.permissionSource, systemImage: category.securityIcon)
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.textSecondary)
            }

            Spacer()

            Button(action: onToggle) {
                HStack(spacing: 4) {
                    if isLoading {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Image(systemName: category.requiresKnowledgePack ? "lock.fill" : (isSubscribed ? "checkmark" : "plus"))
                            .font(.system(size: 11, weight: .bold))
                    }
                    Text(category.walletActionLabel(isInWallet: isSubscribed))
                        .font(.system(size: 12, weight: .bold))
                }
                .foregroundColor(isSubscribed ? AppTheme.Icons.success : AppTheme.Icons.onAccent)
                .padding(.horizontal, 12)
                .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                .background(
                    isSubscribed
                        ? AnyShapeStyle(AppTheme.Colors.successSurface)
                        : AnyShapeStyle(AppTheme.Colors.primary)
                )
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            }
            .buttonStyle(SoftButtonStyle())
            .disabled(isLoading)
            .accessibilityLabel(isLoading ? "正在更新知识钱包" : category.walletActionLabel(isInWallet: isSubscribed))
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                .stroke(AppTheme.Colors.border.opacity(0.7), lineWidth: 0.75)
        }
    }
}

private extension CatalogCategory {
    var securityLabel: String {
        switch securityLevel {
        case "red": return "红色 · 租户私有"
        case "yellow": return "黄色 · 套餐受限"
        default: return "绿色 · 公共知识"
        }
    }

    var securityIcon: String {
        switch securityLevel {
        case "red": return "lock.shield.fill"
        case "yellow": return "checkmark.shield.fill"
        default: return "globe.asia.australia.fill"
        }
    }

    var permissionSource: String {
        switch subscriptionState ?? accessState {
        case "pack_included": return "当前组织知识包已开通"
        case "pack_available": return "可随平台套餐申请"
        case "approval_pending": return "组织申请正在审批"
        case "governance_pending": return "知识治理建设中"
        case "public_available": return "正式租户默认可用"
        case "included": return "当前组织套餐已包含"
        case "upgrade_required": return "当前套餐未包含"
        case "private": return "所属租户私有资产"
        default: return "正式租户默认可用"
        }
    }

    var maturityLabel: String {
        switch knowledgeLevel {
        case "K5": return "K5 · 正式知识"
        case "K4": return "K4 · 已蒸馏"
        default: return "未完成治理"
        }
    }

    var freshnessLabel: String {
        freshness == "stale" ? "需要复核" : "当前有效"
    }

    func walletActionLabel(isInWallet: Bool) -> String {
        if requiresKnowledgePack { return "查看套餐" }
        return isInWallet ? "已加入" : "加入钱包"
    }

    var requiresKnowledgePack: Bool {
        subscriptionState == "pack_available" || accessState == "upgrade_required"
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
        CatalogCategory(category: "knowledge/methodology/public", pathPrefix: "wiki/", title: "公共方法论", docCount: 18, open: true, securityLevel: "green", accessState: "available", inWallet: true, knowledgeLevel: "K5", classificationStatus: "approved", freshness: "current", sourceCount: 46),
        CatalogCategory(category: "knowledge/competitor-topic/entitlement/premium-intelligence", pathPrefix: "wiki/", title: "专业竞品情报", docCount: 12, open: true, securityLevel: "yellow", entitlementKey: "premium-intelligence", accessState: "upgrade_required", inWallet: false, knowledgeLevel: "K5", classificationStatus: "approved", freshness: "current", sourceCount: 38),
        CatalogCategory(category: "knowledge/customer/private/demo", pathPrefix: "wiki/", title: "租户私有客户知识", docCount: 6, open: true, securityLevel: "red", ownerTenant: "demo", accessState: "private", inWallet: true, knowledgeLevel: "K5", classificationStatus: "approved", freshness: "stale", sourceCount: 17),
    ]

    static let mockSubscriptions: [String] = ["knowledge/methodology/public", "knowledge/customer/private/demo"]

    static let mockDocs: [SearchDoc] = [
        SearchDoc(path: "wiki/方法论/模型观察.md", title: "模型观察", score: 12, snippet: "演示数据：正式 K5 知识摘要。", knowledgePack: "knowledge/methodology/public", knowledgeLevel: "K5", classificationStatus: "approved", securityLevel: "green", freshness: "current", sourceCount: 2),
        SearchDoc(path: "wiki/客户/示例客户.md", title: "示例客户", score: 10, snippet: "演示数据：租户私有知识。", knowledgePack: "knowledge/customer/private/demo", knowledgeLevel: "K5", classificationStatus: "approved", securityLevel: "red", freshness: "current", sourceCount: 3),
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
