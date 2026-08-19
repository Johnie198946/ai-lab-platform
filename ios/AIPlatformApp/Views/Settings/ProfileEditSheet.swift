//
//  ProfileEditSheet.swift
//  AIPlatformApp
//
//  个人信息修改 Sheet（⑤）：姓名 TextField + 头像 SF Symbol 预设 6 选 1
//  + 租户/角色只读；保存更新 AppState 并 PATCH /api/v1/me（离线自动降级本地 Mock）。
//

import SwiftUI

public struct ProfileEditSheet: View {
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var api: APIClient
    @Environment(\.dismiss) private var dismiss

    @State private var name: String = ""
    @State private var avatarSymbol: String = "person.crop.circle.fill"
    @State private var isSaving: Bool = false

    private let avatarOptions = [
        "person.crop.circle.fill",
        "person.circle.fill",
        "face.smiling",
        "star.circle.fill",
        "bolt.circle.fill",
        "leaf.circle.fill",
    ]

    private let columns = [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())]

    public init() {}

    public var body: some View {
        NavigationStack {
            Form {
                Section("头像") {
                    LazyVGrid(columns: columns, spacing: AppTheme.Spacing.md) {
                        ForEach(avatarOptions, id: \.self) { symbol in
                            let selected = avatarSymbol == symbol
                            Button(action: {
                                #if os(iOS)
                                UIImpactFeedbackGenerator(style: .light).impactOccurred()
                                #endif
                                avatarSymbol = symbol
                            }) {
                                Image(systemName: symbol)
                                    .font(.system(size: 26))
                                    .foregroundColor(
                    selected ? AppTheme.Icons.onAccent : AppTheme.Icons.secondary
                                    )
                                    .frame(width: 56, height: 56)
                                    .background(
                                        selected
                                            ? AnyShapeStyle(AppTheme.Colors.primary)
                                            : AnyShapeStyle(AppTheme.Colors.secondaryBackground)
                                    )
                                    .clipShape(Circle())
                                    .overlay(
                                        Circle().stroke(
                                            selected ? AppTheme.Colors.primary : AppTheme.Colors.border,
                                            lineWidth: 1
                                        )
                                    )
                            }
                            .buttonStyle(SoftButtonStyle())
                        }
                    }
                    .padding(.vertical, AppTheme.Spacing.xs)
                }

                Section("姓名") {
                    TextField("姓名", text: $name)
                        .font(.system(size: 15))
                }

                Section("租户与角色（只读）") {
                    LabeledContent("租户标识", value: appState.currentProfile.tenantId)
                    LabeledContent("角色", value: appState.currentProfile.role.displayName)
                }
            }
            .navigationTitle("编辑个人信息")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: save) {
                        if isSaving {
                            ProgressView()
                        } else {
                            Text("保存")
                                .font(.system(size: 15, weight: .bold))
                        }
                    }
                    .disabled(isSaving || name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
        .onAppear {
            name = appState.currentProfile.name
            avatarSymbol = appState.currentProfile.avatarUrl ?? "person.crop.circle.fill"
        }
    }

    // MARK: - Actions

    private func save() {
        let trimmedName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedName.isEmpty else { return }
        isSaving = true
        #if os(iOS)
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        #endif

        // 本地 AppState 即时更新
        appState.currentProfile.name = trimmedName
        appState.currentProfile.avatarUrl = avatarSymbol

        // 联网同步后端（离线自动降级）
        Task {
            if !api.isOfflineMode {
                _ = try? await api.patchMe(username: trimmedName, avatarUrl: avatarSymbol)
            }
            isSaving = false
            dismiss()
        }
    }
}

// MARK: - Xcode #Preview

#Preview("ProfileEditSheet - Light") {
    ProfileEditSheet()
        .environmentObject(AppState())
        .environmentObject(APIClient.shared)
}

#Preview("ProfileEditSheet - Dark") {
    ProfileEditSheet()
        .environmentObject(AppState())
        .environmentObject(APIClient.shared)
        .preferredColorScheme(.dark)
}
