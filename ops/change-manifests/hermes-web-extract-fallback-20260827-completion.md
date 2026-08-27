# Hermes Web Extract Fallback Completion

- task_id: `hermes-web-extract-fallback-20260827`
- objective: 同时修复 Mac 与云端 Hermes 的 `web_extract` 后端错配，并约束链接研究的安全降级顺序。
- status: `VERIFIED`
- branch: `codex/hermes-web-extract-fallback-20260827`
- worktree: `/private/tmp/ai-lab-hermes-web-extract-fallback-20260827`

## 开工前盘点

- root_status: 共享根工作区 `feature/gsap-motion-system` 存在用户/其他任务修改与未跟踪文件；本任务未触碰、暂存或混入。
- root_branch: `feature/gsap-motion-system`
- root_head: `b9864543191be059b7b51a592b9b105c6b4bfb85`
- task_base: `f46b20d687fad53e016db71c8c0ac20220abeb03`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`。
- worktree: 独立任务分支与 Worktree；其他 Worktree 未改动。

## 变更

- `native_extract_provider.py`: 新增无密钥 HTML/text 抽取 Provider；沿用 Hermes SSRF 和网站策略，逐跳校验重定向，限制 5 次跳转、2 MB 响应体、内容类型和 20 秒请求。
- `capability_router.py`: URL 研究每轮只允许一次 `web_extract`；重复抽取与 `terminal/curl` 被 `pre_tool_call` 门禁阻止；降级顺序固定为 extract → browser → search。
- `configure_hermes_web_extract.py`: 原子备份插件和配置，保留既有配置，设置 `search_backend=ddgs` 与 `extract_backend=ai-lab-native`。
- `install_agency_hermes.sh`: 安装后统一执行安全网页抽取配置。
- 插件版本升级为 `1.3.0`，补充单元和集成测试。

## 测试与校验

- `py_compile`: PASS。
- 路由/插件专项：`26 passed, 2 warnings`。
- Ruff: PASS。
- `bash -n scripts/install_agency_hermes.sh`: PASS。
- `git diff --check`: PASS。
- 部署前联网实测：`https://example.com/report` 返回标题 `Example Domain`、HTTP 404、559 bytes，并成功提取可读正文。

## 交付状态

- implementation_commit: `fe963c34c27849d5e21dc076ba84a20455d3072f`；部署清洁性补丁 `62e3ad7b5f082a9ce93acd50a46c99291b8d1ca8`。
- remote_sha: GitHub `main` 与 `codex/hermes-web-extract-fallback-20260827` 已通过 `git ls-remote` 核验为 `62e3ad7b5f082a9ce93acd50a46c99291b8d1ca8`；后续 completion manifest-only 提交不改变运行代码。
- server_before: 平台 `.deployed-sha=d21686e48e91f7ad40a2930f0c745b7afeace97c`；release `/opt/releases/ai-lab-platform-d21686e48e91`；`hermes-bridge.service=active`；Bridge health `status=ok/version=v6.0`；网页配置为空且无付费抽取 Provider 凭据。
- server_after: 平台 `.deployed-sha` 与 release 保持 `d21686e48e91f7ad40a2930f0c745b7afeace97c` / `/opt/releases/ai-lab-platform-d21686e48e91`；仅将 `/root/.hermes/plugins/ai-lab-capabilities` 升级到 `1.3.0`，配置为 `search_backend=ddgs`、`extract_backend=ai-lab-native`。
- health_check: 云端 `hermes-bridge.service=active`；Bridge `/health` 返回 `status=ok/version=v6.0`；插件列表显示 `agency-agents-router 1.0.0 enabled` 与 `ai-lab-capabilities 1.3.0 enabled`。
- functional_check: 云端真实 Hermes `web_extract_tool` 对 `https://example.com/report` 一次成功，返回 `Example Domain` 正文；首个抽取允许、重复抽取阻止、terminal 抓取阻止。Mac 同一真实工具链结果一致。两端 `capability_router.py` SHA-256 均为 `42a4237f411253c6adf7e54c38ccfac46af9a09f05783059f3deee7652ffe680`，`native_extract_provider.py` 均为 `61b0b584cfb907f5f27aa09211be8790dee82b64b7007c070b35812bcc524279`。
- rollback_point: 云端 `/opt/ai-lab-rollbacks/hermes-web-extract-20260827T154500Z`；恢复其中插件与配置后重启 `hermes-bridge.service`。平台无需回滚，因为 release/SHA 未改变。
- mac_before: Gateway PID `95020`；Feishu/Weixin connected；插件 `1.2.0`；网页配置为空，自动选择 DDGS 导致 `web_extract` 必然失败。
- mac_after: 插件 `1.3.0`；Gateway launchd PID `2706`；Feishu/Weixin connected；配置为 `search_backend=ddgs`、`extract_backend=ai-lab-native`；真实 `web_extract_tool` 一次返回 `Example Domain` 正文。
- mac_rollback_point: `/Users/dengzhaoyu/.hermes/backups/hermes-web-extract-20260827T154214Z`；恢复其中插件与配置后执行 `hermes gateway restart`。
- remaining_risks:
  - 原生 Provider 面向 HTML、纯文本、JSON 和 XML；PDF/OCR、重 JS 或登录态页面仍需浏览器或未来配置 Firecrawl/Tavily/Exa/Parallel。
  - 云端功能验证期间出现既有用户插件目录 `hermes-internal` 缺少 `__init__.py` 的警告；不影响本插件注册、抽取或 Bridge 健康，本任务未擅自删除该未知目录。
  - SSH 客户端提示云端连接未使用后量子密钥交换；与本次功能无关，应作为服务器 SSH 加固任务单独处理。
