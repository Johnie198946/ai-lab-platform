//
//  AttachmentCard.swift
//  AIPlatformApp
//
//  附件卡片：类型图标（word/pdf/ppt/excel）+ 文件名 + 大小 + 打开提示。
//  点击触觉反馈并提示「演示环境暂不支持打开附件」。
//

import SwiftUI
import QuickLook

public struct AttachmentCard: View {
    public let block: AttachmentBlock
    @State private var localURL: URL?
    @State private var showPreview = false
    @State private var extractedText: String?
    @State private var errorMessage: String?
    @State private var isLoading = false

    public init(block: AttachmentBlock) {
        self.block = block
    }

    public var body: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            HStack(spacing: AppTheme.Spacing.md) {
                // 文档类型图标
                Image(systemName: block.fileType.iconName)
                    .font(.system(size: 22))
                    .foregroundColor(AppTheme.Icons.interactive)
                    .frame(width: 40, height: 40)
                    .background(AppTheme.Colors.primary.opacity(0.08))
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))

                // 文件名 + 大小
                VStack(alignment: .leading, spacing: 2) {
                    Text(block.fileName)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                        .lineLimit(1)
                    Text(block.statusMessage ?? block.fileSize)
                        .font(.system(size: 11))
                        .foregroundColor(AppTheme.Icons.tertiary)
                }

                Spacer()

                // 打开提示（触觉反馈后短暂显示）
                if isLoading { ProgressView().tint(AppTheme.Colors.primary) }
                else { Image(systemName: stateIcon).foregroundColor(stateColor) }
            }
            if block.sourceId != nil {
                HStack {
                    Button("原件预览 / 下载") { Task { await loadOriginal() } }
                    if block.state == .ready { Button("查看提取文本") { Task { await loadText() } } }
                    if let localURL { ShareLink(item: localURL) { Label("存储或分享", systemImage: "square.and.arrow.up") } }
                }.font(.system(size: 11, weight: .semibold)).foregroundColor(AppTheme.Colors.primary)
            }
            if let errorMessage { Text(errorMessage).font(.caption).foregroundColor(AppTheme.Colors.securityRed) }
        }
        .padding(AppTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous).stroke(AppTheme.Colors.border, lineWidth: 0.5))
        .buttonStyle(SoftButtonStyle())
        .sheet(isPresented: $showPreview) { if let localURL { QuickLookPreview(url: localURL) } }
        .sheet(isPresented: Binding(get: { extractedText != nil }, set: { if !$0 { extractedText = nil } })) {
            NavigationStack { ScrollView { Text(extractedText ?? "").textSelection(.enabled).padding() }.navigationTitle("提取文本").navigationBarTitleDisplayMode(.inline) }
                .preferredColorScheme(.light)
        }
    }

    private var stateIcon: String { switch block.state { case .uploading: return "arrow.up.circle"; case .parseFailed, .failed: return "exclamationmark.triangle"; default: return "checkmark.circle" } }
    private var stateColor: Color { block.state == .parseFailed || block.state == .failed ? AppTheme.Colors.securityRed : AppTheme.Colors.primary }

    @MainActor private func loadOriginal() async {
        guard let sourceId = block.sourceId, let hash = block.contentHash, let revision = block.sourceRevision else { return }
        isLoading = true; errorMessage = nil; defer { isLoading = false }
        do {
            let data = try await APIClient.shared.downloadAuthenticated(path: "documents/\(sourceId)/download", expectedHash: hash)
            localURL = try InboxFileManager.shared.storePrivateFile(data, sourceId: sourceId, revision: revision, filename: block.fileName)
            showPreview = true
        } catch { errorMessage = error.localizedDescription }
    }

    @MainActor private func loadText() async {
        guard let sourceId = block.sourceId else { return }
        isLoading = true; errorMessage = nil; defer { isLoading = false }
        do { extractedText = try await APIClient.shared.fetchAuthenticatedText(path: "documents/\(sourceId)/text") }
        catch { errorMessage = error.localizedDescription }
    }
}

private struct QuickLookPreview: UIViewControllerRepresentable {
    let url: URL
    func makeCoordinator() -> Coordinator { Coordinator(url: url) }
    func makeUIViewController(context: Context) -> QLPreviewController { let controller = QLPreviewController(); controller.dataSource = context.coordinator; return controller }
    func updateUIViewController(_ controller: QLPreviewController, context: Context) {}
    final class Coordinator: NSObject, QLPreviewControllerDataSource {
        let url: URL; init(url: URL) { self.url = url }
        func numberOfPreviewItems(in controller: QLPreviewController) -> Int { 1 }
        func previewController(_ controller: QLPreviewController, previewItemAt index: Int) -> QLPreviewItem { url as NSURL }
    }
}

public extension AttachmentFileType {
    /// 文档类型 → SF Symbol 图标映射
    var iconName: String {
        switch self {
        case .word: return "doc.text.fill"
        case .pdf: return "doc.richtext.fill"
        case .ppt: return "chart.bar.doc.horizontal.fill"
        case .excel: return "tablecells.fill"
        case .generic: return "doc.fill"
        }
    }
}

// MARK: - Xcode #Preview

#Preview("AttachmentCard - Light") {
    AttachmentCard(block: AttachmentBlock(fileName: "AI竞品周报_2026W33.pdf", fileType: .pdf, fileSize: "2.4 MB"))
        .padding()
        .background(AppTheme.Colors.groupedBackground)
}
