//
//  ChatInFlightPlaceholderView.swift
//  AIPlatformApp
//
//  InFlight Placeholder & Status Dispatcher for ChatView
//  Extracted from ChatView for minimal footprint.
//

import SwiftUI

public struct ChatInFlightPlaceholderView: View {
    public let req: InFlightRequest
    public let coordinator: TenantSessionCoordinator

    public init(req: InFlightRequest, coordinator: TenantSessionCoordinator) {
        self.req = req
        self.coordinator = coordinator
    }

    public var body: some View {
        switch req.phase {
        case .thinking:
            ThinkingPlaceholderView(
                seconds: coordinator.waitingSeconds,
                progress: coordinator.liveProgress,
                phase: coordinator.thinkingPhase,
                phaseDetail: coordinator.thinkingDetail,
                onCancel: { coordinator.cancelInFlight() }
            )
        case .timeout:
            StatusCardView(
                icon: "exclamationmark.triangle.fill",
                iconColor: AppTheme.Colors.securityYellow,
                title: "长任务超时(300s)",
                message: "任务仍在后端后台执行中，可重试重连或切换至演示模式。",
                primary: (label: "重试重连", action: { coordinator.probeAndResumeCurrentInFlight() }),
                secondary: (label: "切换演示模式", action: { coordinator.switchToDemoMode() })
            )
        case .networkError:
            StatusCardView(
                icon: "wifi.exclamationmark",
                iconColor: AppTheme.Colors.securityYellow,
                title: "网络连接失败",
                message: "无法连接到 AI 服务端，请检查网络设置或切换至演示模式。",
                primary: (label: "重试", action: { coordinator.retryCurrentInFlight() }),
                secondary: (label: "切换演示模式", action: { coordinator.switchToDemoMode() })
            )
        case .serverError(let err):
            StatusCardView(
                icon: "xmark.octagon.fill",
                iconColor: AppTheme.Colors.securityRed,
                title: "服务端错误",
                message: err,
                primary: (label: "重试", action: { coordinator.retryCurrentInFlight() }),
                secondary: (label: "切换演示模式", action: { coordinator.switchToDemoMode() })
            )
        }
    }
}
