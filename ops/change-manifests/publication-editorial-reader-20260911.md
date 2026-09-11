---
title: 书籍出版与阅读修复：代码交付清单
tags:
  - publication
  - ios
  - delivery
status: tested
---

# 书籍出版与阅读修复

## 授权与范围

用户已接受审计建议并授权解决。复用 PublicationStore、现有作者/独立审稿/确定性发行 Cron、Hermes 原生会话和 iOS 书架；不新增 AI Runtime。保留第三方版权门禁，资料来源不得冒充全文；旧已发行正文/版次不覆盖。

## 已实现

- 来源明确为 `metadata_only/readable=false`，仍保留元数据与可点击原始来源；正文、订阅请求解耦，订阅/进度错误单独提示。
- 新原创分 `chapter` / `book`，完整性不再充当作品类型；旧条目保守投影为短文，新增非日更 `quantumn-originals` 集合。
- 沿现有 scoped `knowledge_search` 实现书籍目录、精确版次/章节读取；iOS 传选定书、版次、最近显式定位章节，未声称精确屏幕可见段落。
- 现有 store 中持久化逐 issue/revision/attempt 审核状态和研究缺口；旧待发行稿不享有 grandfather 资格。新稿、返工稿、批准及来源绑定，拒稿三轮上限，未知/不完整状态 fail closed。
- 纯确定性门禁校验有效汉字、章节覆盖、重复段落、逐章引文锚点/证据、合同联合 hash。字数只是必要非充分条件，不以模型自评分替代内容审校。
- Mac 只读原生 Hermes 终态证明首尾有效消息、实际稿件/合同/来源及独立 reviewer，签名后才可进入现有发行流程。管理员及本地签名密钥属于信任边界，不宣称抵御管理员篡改或保证事实质量。
- 新接力 CLI 复用 SSH/operator、显式文件清单、hash 和回读。部署后仍需安装、配置 Cron 和真实运行，不将源码存在说成自动化已生效。
- iOS 1.0.3 build 32 候选；真实 App Store Connect 当时最高 build 31。未 Archive/上传，构建前再次确认占用号。

## 实际门禁

- 三轮设计对攻及最终独立代码复核已完成。最终代码复核允许提交/后端部署，不放行样书出版或 iOS 上传。
- 最终独立后端全套：1920 passed、2 既有 showroom V1 skip、0 failure；14 subtests 与母测试重叠，不相加宣传。父 JUnit 1922 testcase、0 failure、0 error、2 skip。
- 全量 Ruff（backend/scripts/tests/能力插件）与 `git diff --check` 通过。能力路由清理只去除未使用变量，保留 malformed JSON 异常路径。
- 原生模拟器：165/165、0 failed、0 skipped；有 xcodebuild exit 0 与可解析 xcresult。含签名 Keychain、完整单元、两个 ReaderFixture UI 测试，不等于全部生产 UI 套件。
- 父已查看真实模拟器来源/首节/中段/末节截图，101节为明确 DEBUG 演示内容，未当作正式书正文。
- amd64 API 镜像已构建；API/frontend/taskboard/postgres/redis 五种实际镜像 Trivy HIGH/CRITICAL 均为0，四个 Python 服务复用 API image。未把 vulnerability JSON生成本身当扫描通过。

证据目录：`/Users/dengzhaoyu/Projects/book-remediation-20260911/`。包括 `final-code-review.txt`、`full-suite-r4.receipt.json`、JUnit、`ios-r3-exit.json`、`ios-r3.xcresult`、扫描 JSON 和后续独立运行回执。运行素材、书稿、私钥不入 Git。

## 发布与回滚边界

- 基线 main：`32c0e37ad2e7dedae17ad6c6eb273f9ee739475e`。
- 本次最新生产前置回读：`860a52e02645a86cfe2dea67507276d1fd15531b`，活动 `/opt/releases/ai-lab-platform-860a52e02645.qxO7cm`，Bridge active、8容器 healthy。
- 提交/推送 SHA、部署后 marker/源码 hash/服务/功能结果写仓库外最终回执，不在此自指未来 SHA。
- 部署前保存出版状态的 SQLite 一致快照与不可变正文，确认旧 release/image 可恢复。schema 增量迁移正常回滚只退代码；不得自动用旧快照覆盖部署后新内容。
- 回滚须暂停本次出版 Cron，保留 intake/稿件/审核证据，恢复上一已核验代码/镜像/插件及配置；不随意重置 Hermes 原生 DB 或写“成功”状态。

## 尚未完成（不得以局部通过替代）

- GitHub 推送、后端 exact-SHA 部署、active 插件/运行脚本/Cron 接线与回读。
- 样书 v2 已多万字、完成一轮真实缺口修订；独立再审、生产分配 revision、最终 native 审核、签名/stage/release/完整正文回读尚待完成。
- 真实登录、正式长书首中末阅读/问答、真机视觉验收、发行签名及 TestFlight 上传/处理/测试组可用性尚待完成。
- 私人/Wiki书籍的所有不可读个例仍不能从公开资料来源统计推断已修复；需具体记录验收。
