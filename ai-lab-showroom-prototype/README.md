# AI Lab 共创体验中心多屏原型

这是用于验证参观动线、屏幕角色和统一视觉语言的可点击高保真原型。V2 采用暖木、银白和元气智能风格，并覆盖完整主演示及五个独立体验中心。

## 查看方式

在当前目录运行：

```bash
python3 -m http.server 4173
```

然后访问：

- `http://127.0.0.1:4173/`：iPad 导览主控
- `http://127.0.0.1:4173/?view=screen-00`：AI Lab 序章与简短介绍
- `http://127.0.0.1:4173/?view=screen-00&direct=1`：序章直接上屏并自动播放
- `http://127.0.0.1:4173/screen-00-replacement.html`：可独立替换的单文件序章方案
- `http://127.0.0.1:4173/?view=screen-03`：需求问诊台
- `http://127.0.0.1:4173/?view=screen-06`：7290 共创工作台主屏
- `http://127.0.0.1:4173/?view=experience-01`：独立体验中心 01
- 任意页面添加 `&direct=1`：直接上屏模式

## 原型范围

- 展示统一导航和全场 8 块主演示屏在线状态
- 支持 5 站动线切换与主控状态反馈
- 覆盖主演示 7 块屏幕的完整内容
- 覆盖 5 个独立体验中心及 7 步完整用户流程
- 支持键盘焦点、触控反馈和减少动态效果
- 纯 HTML/CSS/JavaScript，无网络依赖

## GSAP 动效系统

原型使用本地 `vendor/gsap.min.js`，不依赖 CDN。动效覆盖屏幕切换、IPD 阶段推进、Agent 协作播放、交付件预览、飞书审批、数字人讲解和 05→06 跨屏投放。

- 页面和组件采用 `power2` 动效语言，交互时长控制在 160–760 ms。
- Agent 协作仅在用户点击“播放协作”后循环，并可随时暂停。
- 动效开关会同步暂停 GSAP 时间线和原有 CSS 动画。
- `prefers-reduced-motion: reduce` 下跳过位移、缩放和循环动画，内容及交互保持完整。
- 所有动画只使用 transform 与 opacity，不改变 IPD 业务状态和审核结果。

设计系统位于 `design-system/ai-lab-showroom/MASTER.md`。

首屏完整拆解位于 `SCREEN-00-DESIGN-SPEC.md`；独立替换文件为 `screen-00-replacement.html`。

新版预览图位于 `previews-v2/`。
