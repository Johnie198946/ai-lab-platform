//
//  PlusMenuSheet.swift
//  AIPlatformApp
//
//  对话页「+」号四入口扩展面板：
//   1. 📸 照片图库（PhotosPicker，客户端 2048px 等比降采样 JPEG 0.85）
//   2. 📄 文档文件（fileImporter，读取 Data 前 resourceValues(.fileSizeKey) 50MB 前置预检）
//   3. 💬 微信导入（WeChatLinkValidator 校验 mp.weixin.qq.com 白名单 + 非法 Toast）
//   4. 🧠 引用知识（选取已订阅知识条目）
//

import SwiftUI
import PhotosUI
import UniformTypeIdentifiers

public struct PlusMenuSheet: View {

    public var onPhotoPicked: (Data) -> Void
    public var onDocumentPicked: (URL) -> Void
    public var onWeChatImported: (String) -> Void
    public var onKnowledgeReferenced: (KnowledgeItem) -> Void

    @Environment(\.dismiss) private var dismiss

    @State private var photoItem: PhotosPickerItem? = nil
    @State private var isFileImporterPresented: Bool = false
    @State private var showWeChatImport: Bool = false
    @State private var wechatLink: String = ""
    @State private var showKnowledgePicker: Bool = false
    @State private var toast: ToastState? = nil

    public init(
        onPhotoPicked: @escaping (Data) -> Void,
        onDocumentPicked: @escaping (URL) -> Void,
        onWeChatImported: @escaping (String) -> Void,
        onKnowledgeReferenced: @escaping (KnowledgeItem) -> Void
    ) {
        self.onPhotoPicked = onPhotoPicked
        self.onDocumentPicked = onDocumentPicked
        self.onWeChatImported = onWeChatImported
        self.onKnowledgeReferenced = onKnowledgeReferenced
    }

    public var body: some View {
        NavigationStack {
            ZStack {
                AppTheme.Colors.groupedBackground
                    .ignoresSafeArea()

                ScrollView {
                    VStack(spacing: AppTheme.Spacing.md) {
                        photosEntry
                        documentEntry
                        wechatEntry
                        if showWeChatImport {
                            wechatImportSection
                                .transition(.opacity.combined(with: .move(edge: .top)))
                        }
                        knowledgeEntry
                        if showKnowledgePicker {
                            knowledgePickerSection
                                .transition(.opacity.combined(with: .move(edge: .top)))
                        }
                    }
                    .padding(AppTheme.Spacing.lg)
                }
            }
            .navigationTitle("添加内容")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("完成") { dismiss() }
                        .foregroundColor(AppTheme.Colors.primary)
                }
            }
            .fileImporter(
                isPresented: $isFileImporterPresented,
                allowedContentTypes: [.item, .pdf, .image, .text, .data],
                allowsMultipleSelection: false,
                onCompletion: handleDocumentImport
            )
            .onChange(of: photoItem) { _, item in
                loadPhoto(item)
            }
            .overlay {
                if let toast = toast {
                    toastView(toast)
                }
            }
        }
    }

    // MARK: - 四入口

    private var photosEntry: some View {
        PhotosPicker(selection: $photoItem, matching: .images, photoLibrary: .shared()) {
            entryRow(
                icon: "photo.on.rectangle.angled",
                title: "照片图库",
                subtitle: "客户端 2048px 等比降采样 · JPEG 0.85",
                tint: AppTheme.Colors.quantumCyan
            )
        }
    }

    private var documentEntry: some View {
        Button {
            isFileImporterPresented = true
        } label: {
            entryRow(
                icon: "doc.fill",
                title: "文档文件",
                subtitle: "50MB 前置预检拦截",
                tint: AppTheme.Colors.quantumBlue
            )
        }
        .buttonStyle(SoftButtonStyle())
    }

    private var wechatEntry: some View {
        Button {
            withAnimation(.easeInOut(duration: 0.2)) { showWeChatImport.toggle() }
        } label: {
            entryRow(
                icon: "message.fill",
                title: "微信导入",
                subtitle: "mp.weixin.qq.com 白名单校验",
                tint: AppTheme.Colors.thirdPartyWeChat
            )
        }
        .buttonStyle(SoftButtonStyle())
    }

    private var knowledgeEntry: some View {
        Button {
            withAnimation(.easeInOut(duration: 0.2)) { showKnowledgePicker.toggle() }
        } label: {
            entryRow(
                icon: "brain.head.profile",
                title: "引用知识",
                subtitle: "选取已订阅知识条目",
                tint: AppTheme.Colors.quantumViolet
            )
        }
        .buttonStyle(SoftButtonStyle())
    }

    // MARK: - 微信导入子面板

    private var wechatImportSection: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Text("粘贴微信公众号文章链接")
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(AppTheme.Colors.textSecondary)

            HStack(spacing: AppTheme.Spacing.sm) {
                TextField("https://mp.weixin.qq.com/s/...", text: $wechatLink)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                    .font(.system(size: 13))
                    .padding(.horizontal, AppTheme.Spacing.sm)
                    .padding(.vertical, 10)
                    .background(AppTheme.Colors.secondaryBackground)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))

                Button("校验导入") { validateWeChatLink() }
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(AppTheme.Colors.onPrimary)
                    .padding(.horizontal, AppTheme.Spacing.md)
                    .padding(.vertical, 10)
                    .background(AppTheme.Colors.primary)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
                    .buttonStyle(SoftButtonStyle())
            }

            Text("文章内容抓取由后端引擎承接（后续轮次）；本轮仅做域名白名单校验。")
                .font(.system(size: 11))
                .foregroundColor(AppTheme.Colors.textTertiary)
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    // MARK: - 引用知识子面板

    private var subscribedKnowledgeItems: [KnowledgeItem] {
        let subscribed = MockData.knowledgeItems.filter { $0.isSubscribed }
        return subscribed.isEmpty ? Array(MockData.knowledgeItems) : subscribed
    }

    private var knowledgePickerSection: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
            ForEach(subscribedKnowledgeItems) { item in
                Button {
                    onKnowledgeReferenced(item)
                    showToast("已引用知识条目", isError: false)
                    dismiss()
                } label: {
                    HStack(spacing: AppTheme.Spacing.sm) {
                        Image(systemName: item.securityLevel.iconName)
                            .font(.system(size: 14))
                            .foregroundColor(item.securityLevel.color)
                            .frame(width: 20)

                        VStack(alignment: .leading, spacing: 2) {
                            Text(item.title)
                                .font(.system(size: 13, weight: .medium))
                                .foregroundColor(AppTheme.Colors.textPrimary)
                                .lineLimit(1)
                            Text(item.domain)
                                .font(.system(size: 11))
                                .foregroundColor(AppTheme.Colors.textTertiary)
                        }

                        Spacer()

                        Image(systemName: "quote.bubble")
                            .font(.system(size: 14))
                            .foregroundColor(AppTheme.Icons.tertiary)
                    }
                    .padding(AppTheme.Spacing.sm)
                    .background(AppTheme.Colors.secondaryBackground)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
                }
                .buttonStyle(SoftButtonStyle())
            }
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    // MARK: - 入口行

    private func entryRow(icon: String, title: String, subtitle: String, tint: Color) -> some View {
        HStack(spacing: AppTheme.Spacing.md) {
            ZStack {
                RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                    .fill(tint.opacity(0.14))
                    .frame(width: 44, height: 44)
                Image(systemName: icon)
                    .font(.system(size: 19, weight: .semibold))
                    .foregroundColor(tint)
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.textPrimary)
                Text(subtitle)
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textTertiary)
            }

            Spacer()

            Image(systemName: "chevron.right")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(AppTheme.Icons.tertiary)
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    // MARK: - Toast

    private struct ToastState {
        let message: String
        let isError: Bool
    }

    private func toastView(_ toast: ToastState) -> some View {
        VStack {
            Spacer()
            Text(toast.message)
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(AppTheme.Colors.onPrimary)
                .padding(.horizontal, AppTheme.Spacing.lg)
                .padding(.vertical, AppTheme.Spacing.sm + 2)
                .background(toast.isError ? AppTheme.Colors.securityRed : AppTheme.Colors.quantumBlue)
                .clipShape(Capsule())
                .shadow(color: Color.black.opacity(0.2), radius: 8, y: 3)
                .padding(.bottom, AppTheme.Spacing.xl)
        }
        .allowsHitTesting(false)
    }

    private func showToast(_ message: String, isError: Bool) {
        withAnimation(.easeInOut(duration: 0.15)) {
            toast = ToastState(message: message, isError: isError)
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            withAnimation(.easeInOut(duration: 0.15)) {
                toast = nil
            }
        }
    }

    // MARK: - Actions

    private func loadPhoto(_ item: PhotosPickerItem?) {
        guard let item = item else { return }
        photoItem = nil // 复位，允许再次选择同一张

        Task {
            guard let data = try? await item.loadTransferable(type: Data.self) else {
                showToast("照片加载失败", isError: true)
                return
            }
            guard let downsampled = InboxFileManager.shared.downsampleImage(data: data) else {
                showToast("图片解码失败", isError: true)
                return
            }
            onPhotoPicked(downsampled)
            showToast("已降采样至 2048px 并导入", isError: false)
            dismiss()
        }
    }

    private func handleDocumentImport(_ result: Result<[URL], Error>) {
        switch result {
        case .success(let urls):
            guard let url = urls.first else { return }
            // 前置预检：读取 Data 前通过 resourceValues(.fileSizeKey) 拦截超限
            if let size = InboxFileManager.shared.fileSizeBytes(at: url),
               size > InboxFileManager.maxFileSizeBytes {
                showToast("文件超过 50MB，已拦截", isError: true)
                return
            }
            onDocumentPicked(url)
            showToast("文档已导入", isError: false)
            dismiss()
        case .failure:
            showToast("文档读取失败", isError: true)
        }
    }

    private func validateWeChatLink() {
        let result = WeChatLinkValidator.validate(wechatLink)
        if result.isValid {
            onWeChatImported(wechatLink.trimmingCharacters(in: .whitespacesAndNewlines))
            showToast(result.reason, isError: false)
            withAnimation(.easeInOut(duration: 0.2)) { showWeChatImport = false }
        } else {
            showToast(result.reason, isError: true)
        }
    }
}

// MARK: - Xcode #Preview

#Preview("PlusMenuSheet - Light") {
    PlusMenuSheet(
        onPhotoPicked: { _ in },
        onDocumentPicked: { _ in },
        onWeChatImported: { _ in },
        onKnowledgeReferenced: { _ in }
    )
}

#Preview("PlusMenuSheet - Dark") {
    PlusMenuSheet(
        onPhotoPicked: { _ in },
        onDocumentPicked: { _ in },
        onWeChatImported: { _ in },
        onKnowledgeReferenced: { _ in }
    )
    .preferredColorScheme(.dark)
}
