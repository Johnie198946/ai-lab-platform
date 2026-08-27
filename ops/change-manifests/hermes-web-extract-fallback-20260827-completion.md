# Hermes Web Extract Fallback Completion

- task_id: `hermes-web-extract-fallback-20260827`
- objective: 同时修复 Mac 与云端 Hermes 的 `web_extract` 后端错配，并约束链接研究的安全降级顺序。
- status: `TESTED`
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

- implementation_commit: 待提交。
- remote_sha: 待推送与 `git ls-remote` 核验。
- server_before: 平台 `.deployed-sha=d21686e48e91f7ad40a2930f0c745b7afeace97c`；release `/opt/releases/ai-lab-platform-d21686e48e91`；`hermes-bridge.service=active`；Bridge health `status=ok/version=v6.0`；网页配置为空且无付费抽取 Provider 凭据。
- server_after: 待部署；为避免覆盖领先于 GitHub main 的平台版本，只部署 Hermes 插件和配置，平台 release/SHA 保持不变。
- health_check: 待执行。
- functional_check: 待执行。
- rollback_point: 待创建。
- mac_before: Gateway PID `95020`；Feishu/Weixin connected；插件 `1.2.0`；网页配置为空，自动选择 DDGS 导致 `web_extract` 必然失败。
- mac_after: 待部署。
- remaining_risks: 原生 Provider 面向 HTML、纯文本、JSON 和 XML；PDF/OCR、重 JS 或登录态页面仍需浏览器或未来配置 Firecrawl/Tavily/Exa/Parallel。
