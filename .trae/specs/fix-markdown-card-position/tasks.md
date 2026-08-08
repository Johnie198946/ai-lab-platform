# Tasks
- [x] Task 1: 修改 OrchestrationPage 的前端代码，将 BorderGlow 移至左侧区域。
  - [x] SubTask 1.1: 在 `orch-summary-copy` 内部增加条件渲染。如果最新的消息是助手回复的 Markdown 消息，则渲染 `BorderGlow` 组件。
  - [x] SubTask 1.2: 如果需要渲染 `BorderGlow`，则不渲染原本的 `<TextType text="你好！今天又有什么新想法？" />` 以及 `Orb` 组件。
  - [x] SubTask 1.3: 从 `orch-role-grid` 内部移除之前编写的 `BorderGlow` 渲染逻辑。
  - [x] SubTask 1.4: 添加条件判断，当 `roles.length === 0` 时，可以直接不渲染 `<section className="orch-wall-panel">` 区域。
- [x] Task 2: 编译并部署前端代码到云服务器
  - [x] SubTask 2.1: 在本地进行代码构建或通过 rsync 同步至远端服务器 `120.24.248.58`。
  - [x] SubTask 2.2: 在服务器上执行 `docker compose build frontend && docker compose up -d frontend` 重启前端服务。
