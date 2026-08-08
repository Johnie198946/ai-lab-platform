# 修复 Markdown 卡片显示位置问题

## Why
目前在通用交互（非编排场景）中，LLM 返回 Markdown 结果后，带有流光特效（BorderGlow）的卡片被渲染在了页面的下方（即 `orch-role-grid` 区域），导致用户在当前视口下看不到。根据设计要求，Markdown 内容大纲应该直接显示在对话框的左侧（即 `orch-summary-copy` 区域）。

## What Changes
- 将 `BorderGlow` 卡片的渲染位置从 `orch-stage-body` 移动到左侧的 `orch-summary-copy` 区域中。
- 当助手回复的内容是 Markdown 时（`isMarkdown === true`），左侧区域隐藏原来的“工作总结”标题和 Orb 特效球，替换为显示 `BorderGlow` 卡片。
- 当 `roles` 为空且不需要展示 Markdown 详情时，可以隐藏底部的 `orch-stage-body`（角色卡画廊区域）以节省空间。

## Impact
- Affected specs: 通用交互场景下的内容展示布局。
- Affected code: `frontend/src/pages/OrchestrationPage.jsx`

## MODIFIED Requirements
### Requirement: 通用交互场景 UI 布局
当后端的回复被标记为 Markdown（`isMarkdown: true`）时：
- **WHEN** 渲染 OrchestrationPage 时
- **THEN** 左侧（`orch-summary-copy` 区域）不再展示默认的文字与球体动画，而是展示 `BorderGlow` 特效包裹的 Markdown 内容大纲。点击该区域依然可以弹出模态框查看全文。
- **THEN** 下方不再渲染空的 `role-grid` 区域。
