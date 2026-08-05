# 体验中台 · 执行方案

## 一句话

部署一套 AI Lab 平台 → 配一个 YAML 描述各体验系统的入口和操作 → 语音入口 → Computer Use Agent 自动串联。

## 不做的事

- 不要求每个系统开放 API
- 不对接 SDK
- 不写适配代码
- 不依赖对方开发团队配合

## 做的事

### 第一层：统一身份

场景入口放一个 PAD 或 NFC 手环。访客扫一次 → 令牌注入 Hermes Agent → 后续所有系统的登录由 Agent 自动完成。不需要用户手动输入任何账号密码。

### 第二层：场景配置

一个 YAML 文件描述所有体验系统。管理员部署时只需写这个文件：

```yaml
identity: pad  # pad / nfc / qrcode

scenes:
  - id: ai-coding
    url: https://coding.xfusion.com
    actions: ["创建项目", "写代码", "查看结果"]
    
  - id: chatbot  
    url: https://chatbot.xfusion.com
    actions: ["上传知识库", "测试问答"]
    
  - id: office
    url: https://copilot.xfusion.com
    actions: ["总结邮件", "生成报告"]
    
  - id: video
    url: https://video.xfusion.com
    actions: ["生成短片", "预览"]
```

### 第三层：Computer Use 执行

Hermes Agent 收到语音指令 → 拆解为操作序列 → 逐步执行：

```
语音: "帮我把 AI Coding 刚生成的代码放到对话机器人里测试"

Agent 执行:
  1. browser_navigate("https://coding.xfusion.com")
  2. 自动登录(统一身份注入)
  3. 获取刚生成的代码 URL
  4. browser_navigate("https://chatbot.xfusion.com")
  5. 自动登录
  6. 上传代码 → 激活
  7. 返回: "已完成，请测试"
```

### 第四层：知识库共享

所有体验的产出都写入同一个 LLM Wiki。AI Coding 生成的代码页面 → wikilink 到对话机器人的测试结果页面。访客参观完可以拿到一份"今天你的体验轨迹"报告。

## 部署清单

| 组件 | 配置 |
|---|---|
| AI Lab 平台 | 一台云服务器 + 域名 |
| 各系统 URL | YAML 文件里配置 |
| 各系统登录 | SSO 或固定测试账号(自动注入) |
| 语音入口 | 网页端/PAD 上的语音按钮 |
| Computer Use | Hermes browser toolkit |
