import XCTest
import CryptoKit

final class ProductionBookshelfUITests: XCTestCase {
    private struct ExpectedPublication {
        let bookID: String
        let seriesID: String
        let seriesTitle: String
        let title: String
        let bodyExcerpt: String
    }

    private let app = XCUIApplication(bundleIdentifier: "com.ailab.AIPlatformApp")
    private let expectedPublications = [
        ExpectedPublication(
            bookID: "publication-2d6c60b5e4cf4b0ff7186e2f483e8c95",
            seriesID: "ai-history",
            seriesTitle: "AI的前世今生",
            title: "机器能思考吗？图灵为什么先换了一个问题",
            bodyExcerpt: "这不是一次真实实验的现场报道"
        ),
        ExpectedPublication(
            bookID: "publication-f646759301bfb771d68a3ae7c031bd57",
            seriesID: "ai-practice",
            seriesTitle: "趣味AI落地经历",
            title: "让 AI 整理一个会变动的小型知识库：一次有失败记录的真实练习",
            bodyExcerpt: "收藏了一堆资料，真要用时却只记得"
        ),
    ]
    private let realModelPrompt = "这是 Quantumn 真机选书 Chat 生产验收。只回复 QUANTUMN_IOS_SELECTED_BOOK_CHAT_OK，不要输出其他内容。"
    private let realModelToken = "QUANTUMN_IOS_SELECTED_BOOK_CHAT_OK"
    private var subscribedDuringTestBookID: String?

    override func setUpWithError() throws {
        continueAfterFailure = false
        subscribedDuringTestBookID = nil
        app.launch()
    }

    override func tearDownWithError() throws {
        guard let bookID = subscribedDuringTestBookID else { return }
        restoreUnsubscribedState(bookID: bookID)
    }

    func testProductionBookshelfReadingAndSelectedBookChat() throws {
        guard requireAuthenticatedKnowledgeTab() != nil else { return }

        let chatTab = app.buttons["main-tab-0"]
        XCTAssertTrue(chatTab.waitForExistence(timeout: 10))
        chatTab.tap()
        let newSession = app.buttons["新建会话"]
        XCTAssertTrue(newSession.waitForExistence(timeout: 10))
        newSession.tap()
        let cleanSessionInput = try chatInput(timeout: 12)
        if cleanSessionInput.identifier != "selected-book-chat-input" {
            app.terminate()
            app.launch()
            XCTAssertTrue(app.buttons["main-tab-2"].waitForExistence(timeout: 10))
        }

        let freshKnowledgeTab = app.descendants(matching: .any)["main-tab-2"]
        XCTAssertTrue(freshKnowledgeTab.waitForExistence(timeout: 10))
        freshKnowledgeTab.tap()
        XCTAssertTrue(app.navigationBars["知识"].waitForExistence(timeout: 10))

        let discover = app.buttons["发现更多书籍"]
        if discover.waitForExistence(timeout: 8) {
            discover.tap()
        } else {
            let emptyShelf = app.buttons.containing(.staticText, identifier: "空书架也该被看见").firstMatch
            XCTAssertTrue(emptyShelf.waitForExistence(timeout: 8))
            emptyShelf.tap()
        }

        XCTAssertTrue(app.navigationBars["知识书架"].waitForExistence(timeout: 15))
        let bookshelfScroll = try preferredElement(
            app.scrollViews["publication-bookshelf-container"],
            fallback: app.scrollViews.firstMatch,
            timeout: 10,
            failureMessage: "生产书架滚动容器未出现。"
        )
        let refresh = app.buttons["publication-bookshelf-refresh"]
        if refresh.waitForExistence(timeout: 3) {
            refresh.tap()
        } else {
            bookshelfScroll.swipeDown()
        }

        let serialShelf = try preferredElement(
            app.buttons["bookshelf-collection.knowledge/publication/public"],
            fallback: app.buttons.matching(
                NSPredicate(format: "label BEGINSWITH %@", "Quantumn 每日测试连载，")
            ).firstMatch,
            timeout: 20,
            failureMessage: "真实刷新后未找到每日测试连载书架。"
        )
        attachScreenshot(named: "01-production-bookshelf-refreshed")
        serialShelf.tap()

        XCTAssertTrue(app.staticTexts["书架上的精选"].waitForExistence(timeout: 10))
        let (publishedBook, expected) = try expectedPublishedBook(timeout: 15)
        let selectedBookTitle = publishedBook.label.components(separatedBy: "，作者 ").first ?? ""
        XCTAssertEqual(selectedBookTitle, expected.title)
        attachScreenshot(named: "02-published-test-book-visible")
        publishedBook.tap()

        let serialBadge = app.staticTexts.matching(
            NSPredicate(format: "label CONTAINS %@", expected.seriesTitle)
        ).firstMatch
        XCTAssertTrue(serialBadge.waitForExistence(timeout: 12), "打开的书不是已发布测试连载。")

        let subscription = app.buttons["publication-subscription-control.\(expected.bookID)"]
        if subscription.waitForExistence(timeout: 3) {
            let originalSubscription = try XCTUnwrap(subscription.value as? String)
            XCTAssertTrue(["subscribed", "unsubscribed"].contains(originalSubscription))
            if originalSubscription == "unsubscribed" {
                subscribedDuringTestBookID = expected.bookID
                subscription.tap()
                XCTAssertTrue(waitForValue("subscribed", of: subscription, timeout: 20), "真实书籍订阅未成功。")
            }
            attachScreenshot(named: "03-test-book-subscribed")
            subscription.tap()
        } else {
            let subscribe = app.buttons.matching(
                NSPredicate(format: "label == %@", "加入我的笔记书架")
            ).firstMatch
            if subscribe.exists {
                subscribedDuringTestBookID = expected.bookID
                subscribe.tap()
            }
            let startReading = app.buttons.matching(
                NSPredicate(format: "label == %@", "开始阅读《\(expected.title)》")
            ).firstMatch
            XCTAssertTrue(startReading.waitForExistence(timeout: 20), "真实书籍订阅未成功。")
            attachScreenshot(named: "03-test-book-subscribed")
            startReading.tap()
        }

        let readerBody = try preferredElement(
            app.scrollViews["publication-reader-body.\(expected.bookID)"],
            fallback: app.scrollViews.firstMatch,
            timeout: 20,
            failureMessage: "真实书籍阅读器未出现。"
        )
        try verifyReader(readerBody, expected: expected)
        XCTAssertFalse(app.buttons["阅读进度未同步，点按重试。"].exists)
        attachScreenshot(named: "04-production-book-body-and-progress")

        app.buttons["返回书籍概述"].tap()
        let askChat = try preferredElement(
            app.buttons["selected-book-chat-open.\(expected.bookID)"],
            fallback: app.buttons.matching(
                NSPredicate(format: "label == %@", "围绕本期向 Chat 提问")
            ).firstMatch,
            timeout: 10,
            failureMessage: "围绕本期向 Chat 提问控件未出现。"
        )
        for _ in 0..<6 where !askChat.isHittable { app.scrollViews.firstMatch.swipeUp() }
        askChat.tap()

        let input = try chatInput(timeout: 12)
        let usesMessageIdentifiers = input.identifier == "selected-book-chat-input"
        let requestMarkers = app.descendants(matching: .any).matching(
            NSPredicate(format: "identifier == %@", "selected-book-chat-request")
        )
        let responseMarkers = app.descendants(matching: .any).matching(
            NSPredicate(format: "identifier == %@", "selected-book-chat-response")
        )
        let matchingPromptRequests = requestMarkers.containing(
            NSPredicate(format: "label CONTAINS %@", realModelPrompt)
        )
        let matchingTokenResponses = responseMarkers.containing(
            NSPredicate(format: "label CONTAINS %@", realModelToken)
        )
        let matchingLegacyRequests = app.staticTexts.matching(
            NSPredicate(format: "label == %@", realModelPrompt)
        )
        let matchingLegacyResponses = app.staticTexts.matching(
            NSPredicate(format: "label == %@", realModelToken)
        )
        let requestMarkerCountBeforeSend = requestMarkers.count
        let responseMarkerCountBeforeSend = responseMarkers.count
        let promptRequestCountBeforeSend = matchingPromptRequests.count
        let tokenResponseCountBeforeSend = matchingTokenResponses.count
        let legacyRequestCountBeforeSend = matchingLegacyRequests.count
        let legacyResponseCountBeforeSend = matchingLegacyResponses.count
        input.tap()
        input.typeKey("a", modifierFlags: .command)
        input.typeText(realModelPrompt)
        let send = try preferredElement(
            app.buttons["selected-book-chat-send"],
            fallback: app.buttons.matching(NSPredicate(format: "label == %@", "发送消息")).firstMatch,
            timeout: 10,
            failureMessage: "发送消息控件未出现。"
        )
        XCTAssertTrue(send.isHittable, "键盘显示时发送入口被遮挡。")
        send.tap()

        if usesMessageIdentifiers {
            XCTAssertTrue(
                waitForCountGreaterThan(requestMarkerCountBeforeSend, in: requestMarkers, timeout: 10),
                "未出现本次真实模型请求标记。"
            )
            XCTAssertTrue(
                waitForCountGreaterThan(promptRequestCountBeforeSend, in: matchingPromptRequests, timeout: 10),
                "未显示本次真实模型请求原文。"
            )
            XCTAssertTrue(
                waitForCountGreaterThan(responseMarkerCountBeforeSend, in: responseMarkers, timeout: 20),
                "未出现本次真实模型响应标记。"
            )
            XCTAssertTrue(
                waitForCountGreaterThan(tokenResponseCountBeforeSend, in: matchingTokenResponses, timeout: 360),
                "选书 Chat 未返回本次真实模型验收 token。"
            )
        } else {
            XCTAssertTrue(
                waitForCountGreaterThan(legacyRequestCountBeforeSend, in: matchingLegacyRequests, timeout: 10),
                "未显示本次真实模型请求原文。"
            )
            XCTAssertTrue(
                waitForCountGreaterThan(legacyResponseCountBeforeSend, in: matchingLegacyResponses, timeout: 360),
                "选书 Chat 未返回本次真实模型验收 token。"
            )
        }
        let visibleErrors = [app.staticTexts, app.buttons].flatMap {
            $0.matching(NSPredicate(
                format: "label CONTAINS %@ OR label CONTAINS %@", "HTTP 422", "服务暂时不可用"
            )).allElementsBoundByIndex.filter(\.isHittable)
        }
        XCTAssertTrue(visibleErrors.isEmpty, "截图前仍显示 HTTP 422 或服务暂时不可用。")
        attachScreenshot(named: "05-selected-book-chat-real-model-response")
    }

    private func requireAuthenticatedKnowledgeTab() -> XCUIElement? {
        let knowledgeTab = app.buttons["main-tab-2"]
        if knowledgeTab.waitForExistence(timeout: 3) { return knowledgeTab }

        let openLogin = app.buttons["打开登录"]
        guard openLogin.waitForExistence(timeout: 5) else {
            XCTFail("主导航未出现，且页面不是登录页。")
            return nil
        }

        let environment = ProcessInfo.processInfo.environment
        guard let phone = environment["QUANTUMN_UI_DEV_PHONE"], phone.count == 11 else {
            XCTFail("缺少有效的 QUANTUMN_UI_DEV_PHONE（必须为 11 位）。")
            return nil
        }
        guard let code = environment["QUANTUMN_UI_DEV_CODE"], code.count == 6 else {
            XCTFail("缺少有效的 QUANTUMN_UI_DEV_CODE（必须为 6 位）。")
            return nil
        }

        openLogin.tap()

        func replaceText(in field: XCUIElement, placeholder: String, with text: String) {
            field.tap()
            if let value = field.value as? String, !value.isEmpty, value != placeholder {
                field.typeKey("a", modifierFlags: .command)
                field.typeKey(.delete, modifierFlags: [])
            }
            field.typeText(text)
        }

        let phoneField = app.textFields["请输入手机号"]
        guard phoneField.waitForExistence(timeout: 10) else {
            XCTFail("登录页未出现手机号输入框。")
            return nil
        }
        replaceText(in: phoneField, placeholder: "请输入手机号", with: phone)

        let codeField = app.textFields["输入 6 位验证码"]
        guard codeField.waitForExistence(timeout: 5) else {
            XCTFail("登录页未出现验证码输入框。")
            return nil
        }
        replaceText(in: codeField, placeholder: "输入 6 位验证码", with: code)

        let agreement = app.buttons["login.agreement.checkbox"]
        guard agreement.waitForExistence(timeout: 5), let agreementState = agreement.value as? String else {
            XCTFail("登录页未出现可识别状态的协议勾选框。")
            return nil
        }
        guard ["已勾选", "未勾选"].contains(agreementState) else {
            XCTFail("登录页协议勾选框状态无效。")
            return nil
        }
        if agreementState == "未勾选" {
            agreement.tap()
            guard waitForValue("已勾选", of: agreement, timeout: 5) else {
                XCTFail("未能勾选登录协议。")
                return nil
            }
        }

        let login = app.buttons["登录 / 注册"]
        guard login.waitForExistence(timeout: 5) else {
            XCTFail("登录页未出现登录 / 注册按钮。")
            return nil
        }
        let enabledExpectation = expectation(
            for: NSPredicate(format: "enabled == true"), evaluatedWith: login
        )
        guard XCTWaiter.wait(for: [enabledExpectation], timeout: 5) == .completed else {
            XCTFail("登录 / 注册按钮不可用。")
            return nil
        }
        login.tap()

        guard knowledgeTab.waitForExistence(timeout: 45) else {
            XCTFail("登录后 45 秒内主导航未出现。")
            return nil
        }
        return knowledgeTab
    }

    private func preferredElement(
        _ identified: XCUIElement,
        fallback: XCUIElement,
        timeout: TimeInterval,
        failureMessage: String
    ) throws -> XCUIElement {
        if identified.waitForExistence(timeout: min(3, timeout)) { return identified }
        XCTAssertTrue(fallback.waitForExistence(timeout: timeout), failureMessage)
        return fallback
    }

    private func chatInput(timeout: TimeInterval) throws -> XCUIElement {
        let identified = app.textFields["selected-book-chat-input"]
        if identified.waitForExistence(timeout: min(3, timeout)) { return identified }

        XCTAssertTrue(app.textFields.firstMatch.waitForExistence(timeout: timeout), "Chat 输入框未出现。")
        let visibleFields = app.textFields.allElementsBoundByIndex.filter(\.isHittable)
        XCTAssertEqual(visibleFields.count, 1, "旧版 Chat 页面必须只有一个可见 TextField。")
        return try XCTUnwrap(visibleFields.first)
    }

    private func expectedPublishedBook(
        timeout: TimeInterval
    ) throws -> (XCUIElement, ExpectedPublication) {
        let identifierPredicates = expectedPublications.map {
            NSPredicate(format: "identifier == %@", "publication-book-card.\($0.seriesID).\($0.bookID)")
        }
        let identified = app.buttons.matching(
            NSCompoundPredicate(orPredicateWithSubpredicates: identifierPredicates)
        ).firstMatch
        if identified.waitForExistence(timeout: min(3, timeout)) {
            let expected = try XCTUnwrap(expectedPublications.first {
                identified.identifier == "publication-book-card.\($0.seriesID).\($0.bookID)"
            })
            return (identified, expected)
        }

        let titlePredicates = expectedPublications.map {
            NSPredicate(format: "label BEGINSWITH %@", "\($0.title)，作者 ")
        }
        let legacy = app.buttons.matching(
            NSCompoundPredicate(orPredicateWithSubpredicates: titlePredicates)
        ).firstMatch
        XCTAssertTrue(legacy.waitForExistence(timeout: timeout), "配置中的两本已发布 Quantumn 测试书均不可见。")
        let exactTitle = legacy.label.components(separatedBy: "，作者 ").first ?? ""
        return (legacy, try XCTUnwrap(expectedPublications.first { $0.title == exactTitle }))
    }

    private func verifyReader(_ readerBody: XCUIElement, expected: ExpectedPublication) throws {
        let identifiedProgress = app.staticTexts["publication-reader-progress.\(expected.bookID)"]
        if identifiedProgress.waitForExistence(timeout: 3) {
            let progressState = try XCTUnwrap(identifiedProgress.value as? String)
            XCTAssertTrue(progressState.hasPrefix("original="), "未捕获原始阅读进度。")
            let bodyContent = app.descendants(matching: .any)["publication-reader-content.\(expected.bookID)"]
            XCTAssertTrue(bodyContent.waitForExistence(timeout: 20), "已发布正文内容标记未出现。")
            let actualBody = try XCTUnwrap(bodyContent.value as? String)
            XCTAssertTrue(
                actualBody.contains(expected.bodyExcerpt),
                "真实正文未包含已审核清单中的稳定正文摘录：\(expected.bodyExcerpt)"
            )
            return
        }

        let progress = app.staticTexts.matching(
            NSPredicate(format: "label BEGINSWITH %@ AND label CONTAINS %@", "第 ", "已读 ")
        ).firstMatch
        XCTAssertTrue(progress.waitForExistence(timeout: 20), "真实书籍正文未加载。")
        let excerpt = app.descendants(matching: .any).matching(
            NSPredicate(format: "label CONTAINS %@", expected.bodyExcerpt)
        ).firstMatch
        for _ in 0..<5 {
            readerBody.swipeUp()
            if excerpt.exists { break }
        }
        XCTAssertTrue(
            excerpt.waitForExistence(timeout: 20),
            "真实正文未包含已审核清单中的稳定正文摘录：\(expected.bodyExcerpt)"
        )
        let positiveProgress = app.staticTexts.matching(
            NSPredicate(format: "label BEGINSWITH %@ AND NOT label CONTAINS %@", "第 ", "已读 0%")
        ).firstMatch
        XCTAssertTrue(positiveProgress.waitForExistence(timeout: 20), "阅读进度未前进。")
    }

    private func waitForValue(_ expected: String, of element: XCUIElement, timeout: TimeInterval) -> Bool {
        let valueExpectation = expectation(
            for: NSPredicate(format: "value == %@", expected), evaluatedWith: element
        )
        return XCTWaiter.wait(for: [valueExpectation], timeout: timeout) == .completed
    }

    private func waitForCountGreaterThan(
        _ baseline: Int, in query: XCUIElementQuery, timeout: TimeInterval
    ) -> Bool {
        let countExpectation = expectation(
            for: NSPredicate(format: "count > %d", baseline), evaluatedWith: query
        )
        return XCTWaiter.wait(for: [countExpectation], timeout: timeout) == .completed
    }

    private func restoreUnsubscribedState(bookID: String) {
        var knowledgeTab = app.buttons["main-tab-2"]
        if !knowledgeTab.waitForExistence(timeout: 3) {
            app.terminate()
            app.launch()
            knowledgeTab = app.buttons["main-tab-2"]
        }
        guard knowledgeTab.waitForExistence(timeout: 10) else {
            XCTFail("无法返回知识页恢复原始未订阅状态。")
            return
        }
        knowledgeTab.tap()
        let directRemove = app.buttons["publication-subscription-remove.\(bookID)"]
        if directRemove.waitForExistence(timeout: 3) {
            directRemove.tap()
            XCTAssertTrue(waitForValue(
                "unsubscribed", of: app.buttons["publication-subscription-control.\(bookID)"], timeout: 20
            ), "未恢复测试前的未订阅状态。")
            return
        }

        let discover = app.buttons["发现更多书籍"]
        if discover.waitForExistence(timeout: 8) { discover.tap() }
        let expected = expectedPublications.first { $0.bookID == bookID }
        guard let expected else {
            XCTFail("恢复订阅状态时书籍不在已审核生产清单中。")
            return
        }
        let identifiedCard = app.buttons["publication-book-card.\(expected.seriesID).\(bookID)"]
        let legacyCard = app.buttons.matching(
            NSPredicate(format: "label BEGINSWITH %@", "\(expected.title)，作者 ")
        ).firstMatch
        if !identifiedCard.waitForExistence(timeout: 3), !legacyCard.exists {
            let identifiedShelf = app.buttons["bookshelf-collection.knowledge/publication/public"]
            let legacyShelf = app.buttons.matching(
                NSPredicate(format: "label BEGINSWITH %@", "Quantumn 每日测试连载，")
            ).firstMatch
            let shelf = identifiedShelf.waitForExistence(timeout: 3) ? identifiedShelf : legacyShelf
            guard shelf.waitForExistence(timeout: 15) else {
                XCTFail("恢复订阅状态时未找到生产测试书架。")
                return
            }
            shelf.tap()
        }
        let card = identifiedCard.waitForExistence(timeout: 3) ? identifiedCard : legacyCard
        guard card.waitForExistence(timeout: 15) else {
            XCTFail("恢复订阅状态时未找到原书籍。")
            return
        }
        card.tap()
        let subscriptionControl = app.buttons["publication-subscription-control.\(bookID)"]
        if subscriptionControl.waitForExistence(timeout: 3),
           subscriptionControl.value as? String == "unsubscribed" {
            return
        }
        let identifiedRemove = app.buttons["publication-subscription-remove.\(bookID)"]
        let legacyRemove = app.buttons.matching(NSPredicate(format: "label == %@", "移出书架")).firstMatch
        let remove = identifiedRemove.waitForExistence(timeout: 3) ? identifiedRemove : legacyRemove
        guard remove.waitForExistence(timeout: 10) else {
            XCTFail("恢复订阅状态时未找到移出书架控件。")
            return
        }
        remove.tap()
        let subscription = app.buttons["publication-subscription-control.\(bookID)"]
        if subscription.exists {
            XCTAssertTrue(waitForValue("unsubscribed", of: subscription, timeout: 20), "未恢复测试前的未订阅状态。")
        } else {
            let subscribe = app.buttons.matching(
                NSPredicate(format: "label == %@", "加入我的笔记书架")
            ).firstMatch
            XCTAssertTrue(subscribe.waitForExistence(timeout: 20), "未恢复测试前的未订阅状态。")
        }
    }

    private func attachScreenshot(named name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}

final class ReaderFixtureUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication(bundleIdentifier: "com.ailab.AIPlatformApp")
    }

    func testMetadataBadgeAndSourceActionStayAvailable() {
        app.launchArguments = ["-bookshelfPreview", "-bookshelfSourcePreview", "-bookshelfBookPreview"]
        app.launch()

        XCTAssertTrue(app.descendants(matching: .any)["publication-type.source-preview"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["资料来源"].exists)
        let source = app.buttons["publication-source-open.source-preview"]
        XCTAssertTrue(source.waitForExistence(timeout: 10))
        XCTAssertTrue(source.isEnabled)
        XCTAssertTrue(source.isHittable)
        attachScreenshot(named: "fixture-metadata-source-action")
    }

    func testReaderQuestionKeyboardDismissesWhenTappingBlankSpace() {
        app.launchArguments = [
            "-prototypePreview", "v4/08-reader-question-annotation-v4-p02"
        ]
        app.launchEnvironment["AI_LAB_E2E_DISABLE_ANIMATIONS"] = "1"
        app.launch()

        let input = app.textFields["reader-question-input"]
        XCTAssertTrue(input.waitForExistence(timeout: 10))
        input.tap()
        input.typeText("是什么意思")
        let keyboard = app.keyboards.firstMatch
        XCTAssertTrue(keyboard.waitForExistence(timeout: 5))

        let sheet = app.scrollViews["reader-question-sheet"]
        XCTAssertTrue(sheet.waitForExistence(timeout: 5))
        sheet.coordinate(withNormalizedOffset: CGVector(dx: 0.96, dy: 0.18)).tap()
        expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: keyboard)
        waitForExpectations(timeout: 5)
    }

    func testLongReaderSurvivesSubscriptionFailureAndNavigatesExactSections() {
        app.launchArguments = [
            "-bookshelfPreview", "-bookshelfBookPreview", "-bookshelfSubscribedPreview",
            "-bookReadingPreview", "-bookReadingLongFixture"
        ]
        app.launch()

        XCTAssertTrue(app.scrollViews["publication-reader-body.product-map"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.descendants(matching: .any)["publication-reader-content.product-map"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.descendants(matching: .any)["publication-reader-progress-warning.product-map"].exists)
        let body = app.descendants(matching: .any)["publication-reader-content.product-map"]
        XCTAssertTrue((body.value as? String)?.contains("正文存活和章节导航") == true)

        openTableOfContentsAndTap("server-section-first")
        let first = app.staticTexts["第一章 起点"]
        XCTAssertTrue(first.waitForExistence(timeout: 5))
        assertBelowReaderChrome(first)
        attachScreenshot(named: "fixture-reader-first-subscription-failed")

        openTableOfContentsAndTap("server-section-middle")
        let middle = app.staticTexts["第五十一节 中段"]
        XCTAssertTrue(middle.waitForExistence(timeout: 5))
        assertBelowReaderChrome(middle)
        attachScreenshot(named: "fixture-reader-middle")

        openTableOfContentsAndTap("server-section-last")
        let last = app.staticTexts["第一百零一节 终章"]
        XCTAssertTrue(last.waitForExistence(timeout: 5))
        assertBelowReaderChrome(last)
        attachScreenshot(named: "fixture-reader-last")

        app.buttons["返回书籍概述"].tap()
        let ask = app.buttons["selected-book-chat-open.product-map"]
        XCTAssertTrue(ask.waitForExistence(timeout: 5))
        XCTAssertTrue(ask.label.contains("AI 产品全景图"))
        XCTAssertTrue(ask.label.contains("最近定位章节：第一百零一节 终章"))
    }

    private func openTableOfContentsAndTap(_ sectionID: String) {
        let tableOfContents = app.buttons["publication-reader-toc.product-map"]
        XCTAssertTrue(tableOfContents.waitForExistence(timeout: 5))
        tableOfContents.tap()
        let section = app.buttons["publication-reader-nav.\(sectionID)"]
        let menu = app.collectionViews.firstMatch
        XCTAssertTrue(menu.waitForExistence(timeout: 5))
        for _ in 0..<40 where !section.exists || !section.isHittable {
            menu.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.4))
                .press(forDuration: 0.05, thenDragTo: menu.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.1)))
        }
        XCTAssertTrue(section.exists)
        XCTAssertTrue(section.isHittable)
        section.tap()
    }

    private func assertBelowReaderChrome(_ element: XCUIElement) {
        let back = app.buttons["返回书籍概述"]
        let tableOfContents = app.buttons["publication-reader-toc.product-map"]
        XCTAssertTrue(back.exists)
        XCTAssertTrue(tableOfContents.exists)
        let chromeBottom = max(back.frame.maxY, tableOfContents.frame.maxY)
        XCTAssertGreaterThanOrEqual(
            element.frame.minY,
            chromeBottom + 24,
            "Reader content must remain visibly separated from navigation controls."
        )
    }

    private func attachScreenshot(named name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}

final class ChatKeyboardFixtureUITests: XCTestCase {
    func testKeyboardKeepsSendControlHittable() {
        let app = XCUIApplication(bundleIdentifier: "com.ailab.AIPlatformApp")
        app.launchArguments = ["-tabBarPreview"]
        app.launch()

        let input = app.textFields["selected-book-chat-input"]
        XCTAssertTrue(input.waitForExistence(timeout: 10))
        input.tap()
        input.typeText("键盘安全区回归")

        let send = app.buttons["selected-book-chat-send"]
        XCTAssertTrue(send.waitForExistence(timeout: 5))
        XCTAssertTrue(send.isHittable, "原生 keyboard safe area 未保留发送入口。")
    }
}

final class Batch4NoviceUXFixtureUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication(bundleIdentifier: "com.ailab.AIPlatformApp")
        app.launchArguments = ["-batch4Preview"]
        app.launch()
    }

    func testDescriptionsRetryAndProgressiveDisclosure() {
        let description = app.staticTexts["agent-description-知识助手"]
        XCTAssertTrue(description.waitForExistence(timeout: 10))
        XCTAssertTrue(description.label.contains("功能："))
        XCTAssertTrue(description.label.contains("适合："))
        XCTAssertTrue(description.label.contains("边界："))
        XCTAssertLessThanOrEqual(description.label.count, 100)

        let toggle = app.buttons["agent-description-toggle"]
        XCTAssertEqual(toggle.value as? String, "已折叠两行")
        toggle.tap()
        XCTAssertEqual(toggle.value as? String, "已展开")

        XCTAssertTrue(app.descendants(matching: .any)["workflow-failure-cause"].exists)
        let retry = app.buttons["workflow-retry-action"]
        XCTAssertTrue(retry.exists && retry.isHittable)
        retry.tap()
        XCTAssertEqual(app.staticTexts["batch4-feedback"].label, "已请求重试同一任务")

        let advancedContent = app.descendants(matching: .any)["batch4-advanced-content"]
        XCTAssertFalse(advancedContent.exists)
        app.buttons["高级选项"].tap()
        XCTAssertTrue(advancedContent.waitForExistence(timeout: 3))
        attachScreenshot(named: "batch4-description-retry-disclosure")
    }

    func testSmallScreenKeyboardKeepsCurrentPrimaryActionHittable() {
        let input = app.textFields["clarify-custom-input"]
        XCTAssertTrue(input.waitForExistence(timeout: 10))
        for _ in 0..<8 where !input.isHittable { app.swipeUp() }
        XCTAssertTrue(input.isHittable)
        input.tap()
        input.typeText("客户提案")
        let primary = app.buttons["clarify-keyboard-primary-action"]
        XCTAssertTrue(primary.waitForExistence(timeout: 5))
        XCTAssertTrue(primary.isHittable, "键盘出现后当前步骤主操作被遮挡。")
        attachScreenshot(named: "batch4-keyboard-primary-action")
        primary.tap()
        XCTAssertEqual(app.staticTexts["batch4-feedback"].label, "已确认并进入下一步")
    }

    private func attachScreenshot(named name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}

final class CollapsedTabBarAccessibilityUITests: XCTestCase {
    func testCollapsedTabBarHasKeyboardAccessibleRevealControl() {
        let app = XCUIApplication(bundleIdentifier: "com.ailab.AIPlatformApp")
        app.launchArguments = ["-tabBarPreview", "-collapsedTabBarPreview"]
        app.launch()
        let reveal = app.buttons["main-tab-reveal"]
        XCTAssertTrue(reveal.waitForExistence(timeout: 10))
        XCTAssertTrue(reveal.isHittable)
        reveal.tap()
        let tasks = app.buttons["main-tab-1"]
        XCTAssertTrue(tasks.waitForExistence(timeout: 5))
        XCTAssertTrue(tasks.isHittable)
        tasks.tap()
        XCTAssertTrue(tasks.isSelected)
    }
}

final class ProductionLongBookAcceptanceUITests: XCTestCase {
    private let app = XCUIApplication(bundleIdentifier: "com.ailab.AIPlatformApp")

    override func setUpWithError() throws {
        continueAfterFailure = false
        app.launchArguments = []
        app.launchEnvironment.removeValue(forKey: "AI_LAB_E2E_TOKEN")
        app.launchEnvironment.removeValue(forKey: "QUANTUMN_UI_DEV_PHONE")
        app.launchEnvironment.removeValue(forKey: "QUANTUMN_UI_DEV_CODE")
        app.launch()
    }

    func testExistingSessionReadsConfiguredLongBookTOC() throws {
        let environment = ProcessInfo.processInfo.environment
        let bookID = try XCTUnwrap(environment["QUANTUMN_UI_BOOK_ID"]?.trimmingCharacters(in: .whitespacesAndNewlines))
        guard !bookID.isEmpty else {
            XCTFail("QUANTUMN_UI_BOOK_ID 不能为空。")
            return
        }
        guard environment["SIMULATOR_DEVICE_NAME"] == nil else {
            XCTFail("此验收只允许在保留现有登录会话的真机上运行。")
            return
        }
        XCTAssertEqual(app.state, .runningForeground, "Quantumn 未在前台运行；真机可能仍锁定。")

        let knowledgeTab = app.buttons["main-tab-2"]
        if app.buttons["打开登录"].waitForExistence(timeout: 3) {
            XCTFail("缺少已安装 App 的现有登录会话；本验收不会自动登录或绕过同意流程。")
            return
        }
        // The production dock intentionally collapses after five seconds.
        // Reveal it using the existing left-edge gesture, without altering session state.
        if !knowledgeTab.exists {
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.04, dy: 0.5))
                .press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.4, dy: 0.5)))
        }
        XCTAssertTrue(knowledgeTab.waitForExistence(timeout: 8), "未找到已认证主导航；请解锁真机并保留现有登录会话。")
        knowledgeTab.tap()
        XCTAssertTrue(app.navigationBars["知识"].waitForExistence(timeout: 10))

        let discover = app.buttons["发现更多书籍"]
        if discover.waitForExistence(timeout: 8) {
            discover.tap()
        } else {
            let emptyShelf = app.buttons.containing(.staticText, identifier: "空书架也该被看见").firstMatch
            XCTAssertTrue(emptyShelf.waitForExistence(timeout: 8), "现有知识页未提供书架入口。")
            emptyShelf.tap()
        }
        XCTAssertTrue(app.navigationBars["知识书架"].waitForExistence(timeout: 15))

        let book = try findBook(id: bookID)
        book.tap()
        let readingControl = app.buttons["publication-subscription-control.\(bookID)"]
        XCTAssertTrue(readingControl.waitForExistence(timeout: 10), "目标书没有可阅读正文。")
        guard readingControl.value as? String == "subscribed" else {
            XCTFail("目标书必须已在现有书架；本验收不会更改订阅。")
            return
        }
        readingControl.tap()

        XCTAssertTrue(app.scrollViews["publication-reader-body.\(bookID)"].waitForExistence(timeout: 20), "真实阅读器未出现。")
        let content = app.descendants(matching: .any)["publication-reader-content.\(bookID)"]
        XCTAssertTrue(content.waitForExistence(timeout: 20), "真实正文标记未出现。")
        XCTAssertFalse(((content.value as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, "真实正文为空。")

        let sections = try tableOfContentsSections(bookID: bookID)
        guard sections.count >= 3 else {
            XCTFail("真实目录不足 3 节，无法验收前/中/末导航。")
            return
        }
        let targets = [sections[0], sections[sections.count / 2], sections[sections.count - 1]]
        for (index, target) in targets.enumerated() {
            navigate(bookID: bookID, sectionID: target.id, openMenu: index != 0)
            attachScreenshot(named: String(format: "real-long-book-%02d-%@", index + 1, target.id))
        }

        guard environment["QUANTUMN_UI_ALLOW_TEST_QUESTION"] == "1" else { return }
        app.buttons["返回书籍概述"].tap()
        let ask = app.buttons["selected-book-chat-open.\(bookID)"]
        XCTAssertTrue(ask.waitForExistence(timeout: 10), "现有选书提问入口未出现。")
        for _ in 0..<8 where !ask.isHittable { app.scrollViews.firstMatch.swipeUp() }
        XCTAssertTrue(ask.isHittable)
        ask.tap()
        let input = app.textFields["selected-book-chat-input"]
        XCTAssertTrue(input.waitForExistence(timeout: 12), "选书 Chat 输入框未出现。")
        input.tap()
        input.typeText("请概括我最近定位章节的核心论点，并说明证据边界。")
        let send = app.buttons["selected-book-chat-send"]
        XCTAssertTrue(send.waitForExistence(timeout: 8), "选书 Chat 发送按钮未出现。")
        send.tap()
        attachScreenshot(named: "real-long-book-04-authorized-question")
    }

    private func findBook(id bookID: String) throws -> XCUIElement {
        let target = app.buttons.matching(
            NSPredicate(format: "identifier ENDSWITH %@", ".\(bookID)")
        ).firstMatch
        let shelves = app.buttons.matching(
            NSPredicate(format: "identifier BEGINSWITH %@", "bookshelf-collection.")
        )
        var visited = Set<String>()
        let container = app.scrollViews["publication-bookshelf-container"]

        for _ in 0..<50 {
            if let shelf = shelves.allElementsBoundByIndex.first(where: {
                $0.isHittable && !visited.contains($0.identifier)
            }) {
                visited.insert(shelf.identifier)
                shelf.tap()
                for _ in 0..<25 {
                    if target.waitForExistence(timeout: 1), target.isHittable { return target }
                    app.scrollViews.firstMatch.swipeUp()
                }
                app.buttons["返回分类"].tap()
                continue
            }
            container.swipeUp()
        }
        XCTFail("在现有真实书架中未找到 QUANTUMN_UI_BOOK_ID=\(bookID)。")
        throw NSError(domain: "ProductionLongBookAcceptanceUITests", code: 1)
    }

    private func tableOfContentsSections(bookID: String) throws -> [(id: String, title: String)] {
        let menu = app.buttons["publication-reader-toc.\(bookID)"]
        XCTAssertTrue(menu.waitForExistence(timeout: 8), "真实阅读器目录按钮未出现。")
        menu.tap()
        let entries = app.buttons.matching(
            NSPredicate(format: "identifier BEGINSWITH %@", "publication-reader-nav.")
        )
        XCTAssertTrue(entries.firstMatch.waitForExistence(timeout: 5), "真实目录为空。")
        let result = entries.allElementsBoundByIndex.map {
            (id: String($0.identifier.dropFirst("publication-reader-nav.".count)), title: $0.label)
        }
        return result
    }

    private func navigate(bookID: String, sectionID: String, openMenu: Bool) {
        if openMenu { app.buttons["publication-reader-toc.\(bookID)"].tap() }
        let entry = app.buttons["publication-reader-nav.\(sectionID)"]
        let menu = app.collectionViews.firstMatch
        XCTAssertTrue(menu.waitForExistence(timeout: 5))
        for _ in 0..<40 where !entry.exists || !entry.isHittable {
            menu.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.4))
                .press(forDuration: 0.05, thenDragTo: menu.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.1)))
        }
        XCTAssertTrue(entry.exists, "目录缺少章节 \(sectionID)。")
        XCTAssertTrue(entry.isHittable, "目录章节不可点击：\(sectionID)。")
        entry.tap()
    }

    private func attachScreenshot(named name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}

final class StructuredReviewLocalE2EUITests: XCTestCase {
    private var baseURL: URL!
    private var token: String!

    override func setUpWithError() throws {
        continueAfterFailure = false
        let environment = ProcessInfo.processInfo.environment
        baseURL = try XCTUnwrap(URL(string: environment["LIVE_ACCEPTANCE_BASE_URL"] ?? "http://127.0.0.1:8765"))
        let tokenPath = environment["LIVE_ACCEPTANCE_JWT_FILE"] ?? "/tmp/quantumn-live-acceptance.jwt"
        token = try String(contentsOfFile: tokenPath, encoding: .utf8)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        XCTAssertFalse(token.isEmpty)
    }

    @MainActor
    func testCASConflictAndRelaunchPersistenceAgainstRealBackend() async throws {
        _ = try await request(
            "PUT", path: "/api/v1/me/agreement-acceptance",
            body: [
                "agreement_version": "2026-09-06",
                "idempotency_key": UUID().uuidString,
                "source": "ios",
            ]
        )
        let workflow = try await request(
            "POST", path: "/api/v1/workflows",
            body: [
                "title": "结构化审核本地 E2E",
                "description": "真实后端 CAS、冲突与重启持久化验收",
                "output_kind": "presentation",
            ]
        )
        let workflowJSON = try XCTUnwrap(workflow.json["workflow"] as? [String: Any])
        let workflowID = try XCTUnwrap(workflowJSON["id"] as? String)
        let path = "/api/v1/workflows/\(workflowID)/structured-reviews/final-draft"
        let initialDocument: [String: Any] = [
            "title": "可编辑全稿预览",
            "fields": [
                ["id": "title", "label": "标题", "type": "text", "required": true],
                ["id": "summary", "label": "摘要", "type": "textarea", "required": true],
                ["id": "agenda", "label": "内容清单", "type": "list", "required": false],
                ["id": "pages", "label": "页面结构", "type": "page_structure", "required": false],
                ["id": "hero", "label": "封面素材", "type": "asset", "required": false],
            ],
            "values": [
                "title": "伊斯坦布尔",
                "summary": "初稿",
                "agenda": [],
                "pages": [],
                "hero": ["id": "asset-original", "name": "原素材", "url": "https://example.invalid/original.jpg"],
            ],
        ]
        _ = try await request(
            "POST", path: path,
            body: ["schema_id": "workflow.structured-review.v2", "document": initialDocument]
        )

        let app = launchApp(workflowID: workflowID)
        let title = app.textFields["标题"]
        XCTAssertTrue(title.waitForExistence(timeout: 20))
        replace(title, with: "本地版本")
        title.typeKey(.return, modifierFlags: [])
        let addAgenda = app.buttons["structured-review-field-agenda-add"]
        XCTAssertTrue(scrollUntilHittable(addAgenda, in: app, timeout: 20))
        addAgenda.tap()
        let agendaItem = app.textFields["structured-review-field-agenda-item-0"]
        XCTAssertTrue(agendaItem.waitForExistence(timeout: 10))
        replace(agendaItem, with: "第一页结论")
        agendaItem.typeKey(.return, modifierFlags: [])
        let addPage = app.buttons["structured-review-field-pages-add"]
        XCTAssertTrue(scrollUntilHittable(addPage, in: app, timeout: 20))
        addPage.tap()
        let pageTitle = app.textFields["structured-review-field-pages-page-0-title"]
        XCTAssertTrue(pageTitle.waitForExistence(timeout: 10))
        replace(pageTitle, with: "开场页")
        pageTitle.typeKey(.return, modifierFlags: [])
        let assetName = app.textFields["structured-review-field-hero-name"]
        XCTAssertTrue(scrollUntilHittable(assetName, in: app, timeout: 20))
        replace(assetName, with: "hero.jpg")
        assetName.typeKey(.return, modifierFlags: [])
        let assetURL = app.textFields["structured-review-field-hero-url"]
        replace(assetURL, with: "https://example.invalid/hero.jpg")
        assetURL.typeKey(.return, modifierFlags: [])
        let assetPreview = app.descendants(matching: .any)["structured-review-field-hero-preview"]
        XCTAssertTrue(assetPreview.waitForExistence(timeout: 10))
        let restoreAsset = app.buttons["structured-review-field-hero-restore"]
        XCTAssertTrue(restoreAsset.waitForExistence(timeout: 10))
        restoreAsset.tap()
        XCTAssertEqual(assetName.value as? String, "原素材")
        XCTAssertEqual(assetURL.value as? String, "https://example.invalid/original.jpg")
        replace(assetName, with: "hero.jpg")
        assetName.typeKey(.return, modifierFlags: [])
        replace(assetURL, with: "https://example.invalid/hero.jpg")
        assetURL.typeKey(.return, modifierFlags: [])
        let save = app.buttons["structured-review-save"]
        XCTAssertTrue(scrollUntilHittable(save, in: app, timeout: 20))
        save.tap()
        XCTAssertTrue(app.staticTexts["版本 2"].waitForExistence(timeout: 20))

        let head = try await request("GET", path: path)
        let remoteDocument: [String: Any] = [
            "title": "可编辑全稿预览",
            "fields": initialDocument["fields"] as Any,
            "values": [
                "title": "服务端版本",
                "summary": "远端并发修改",
                "agenda": ["第一页结论"],
                "pages": [["id": "page-1", "title": "开场页", "summary": ""]],
                "hero": ["id": "hero", "name": "hero.jpg", "url": "https://example.invalid/hero.jpg"],
            ],
        ]
        _ = try await request(
            "PUT", path: path,
            headers: ["If-Match": try XCTUnwrap(head.etag)],
            body: ["schema_id": "workflow.structured-review.v2", "document": remoteDocument]
        )

        replace(title, with: "本地迟到版本")
        app.buttons["保存审核"].tap()
        XCTAssertTrue(app.staticTexts["发现版本冲突"].waitForExistence(timeout: 20))
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "本地迟到版本")).firstMatch.exists)
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "服务端版本")).firstMatch.exists)
        app.buttons["载入服务端版本"].tap()
        XCTAssertTrue(waitUntil(timeout: 20) { (title.value as? String) == "服务端版本" })
        replace(title, with: "持久化终稿")
        app.buttons["保存审核"].tap()
        XCTAssertTrue(app.staticTexts["版本 4"].waitForExistence(timeout: 20))
        app.buttons["撤销"].tap()
        XCTAssertTrue(app.staticTexts["版本 5"].waitForExistence(timeout: 20))
        XCTAssertTrue(waitUntil(timeout: 20) { (title.value as? String) == "服务端版本" })

        app.terminate()
        let relaunched = launchApp(workflowID: workflowID)
        let persisted = relaunched.textFields["标题"]
        XCTAssertTrue(persisted.waitForExistence(timeout: 20))
        XCTAssertEqual(persisted.value as? String, "服务端版本")
        let persistedAgenda = relaunched.textFields["structured-review-field-agenda-item-0"]
        XCTAssertTrue(scrollUntilHittable(persistedAgenda, in: relaunched, timeout: 20))
        XCTAssertEqual(persistedAgenda.value as? String, "第一页结论")
        let persistedPageTitle = relaunched.textFields["structured-review-field-pages-page-0-title"]
        XCTAssertTrue(scrollUntilHittable(persistedPageTitle, in: relaunched, timeout: 20))
        XCTAssertEqual(persistedPageTitle.value as? String, "开场页")
    }

    private func launchApp(workflowID: String) -> XCUIApplication {
        let app = XCUIApplication(bundleIdentifier: "com.ailab.AIPlatformApp")
        app.launchArguments = ["-structuredReviewE2E", "-autoLogin"]
        app.launchEnvironment["AI_LAB_E2E_BASE_URL"] = baseURL.absoluteString
        app.launchEnvironment["AI_LAB_E2E_TOKEN"] = token
        app.launchEnvironment["AI_LAB_E2E_WORKFLOW_ID"] = workflowID
        app.launchEnvironment["AI_LAB_E2E_REVIEW_KEY"] = "final-draft"
        app.launch()
        return app
    }

    private func replace(_ field: XCUIElement, with value: String) {
        field.tap()
        field.typeKey("a", modifierFlags: .command)
        field.typeText(value)
    }

    private func scrollUntilHittable(_ element: XCUIElement, in app: XCUIApplication, timeout: TimeInterval) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if element.exists && element.isHittable { return true }
            app.swipeUp()
        }
        return element.exists && element.isHittable
    }

    private func waitUntil(timeout: TimeInterval, condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.25))
        }
        return condition()
    }

    private func request(
        _ method: String,
        path: String,
        headers: [String: String] = [:],
        body: [String: Any]? = nil
    ) async throws -> (json: [String: Any], etag: String?) {
        var request = URLRequest(url: baseURL.appending(path: path))
        request.httpMethod = method
        request.setValue("Bearer \(token!)", forHTTPHeaderField: "Authorization")
        request.setValue("ios-unified-agreement-v1", forHTTPHeaderField: "X-Client-Contract")
        headers.forEach { request.setValue($0.value, forHTTPHeaderField: $0.key) }
        if let body {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        let http = try XCTUnwrap(response as? HTTPURLResponse)
        guard (200..<300).contains(http.statusCode) else {
            XCTFail("\(method) \(path) failed: \(http.statusCode) \(String(data: data, encoding: .utf8) ?? "")")
            throw URLError(.badServerResponse)
        }
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
        return (json, http.value(forHTTPHeaderField: "ETag"))
    }

    private func localToken() -> String {
        func encoded(_ value: Data) -> String {
            value.base64EncodedString()
                .replacingOccurrences(of: "+", with: "-")
                .replacingOccurrences(of: "/", with: "_")
                .replacingOccurrences(of: "=", with: "")
        }
        let header = encoded(Data(#"{"alg":"HS256","typ":"JWT"}"#.utf8))
        let expires = Int(Date().addingTimeInterval(3_600).timeIntervalSince1970)
        let payload = encoded(Data(#"{"sub":"local-e2e-owner","phone":"local-e2e-owner","tenant_id":"default","exp":\#(expires)}"#.utf8))
        let signingInput = "\(header).\(payload)"
        let signature = HMAC<SHA256>.authenticationCode(
            for: Data(signingInput.utf8),
            using: SymmetricKey(data: Data("test-secret".utf8))
        )
        return "\(signingInput).\(encoded(Data(signature)))"
    }
}

final class DocumentProductLiveE2ETests: XCTestCase {
    private struct CaseSpec {
        let title: String
        let prompt: String
        let revision: String
        let requiredText: [String]
        let forbiddenText: [String]
        let minimumPages: Int
    }

    private let app = XCUIApplication(bundleIdentifier: "com.ailab.AIPlatformApp")
    private var baseURL: URL!
    private var token: String!

    override func setUpWithError() throws {
        continueAfterFailure = false
        let environment = ProcessInfo.processInfo.environment
        XCTAssertEqual(environment["LIVE_ACCEPTANCE"], "1", "Document product E2E requires LIVE_ACCEPTANCE=1; absence is a failure, not a skip.")
        baseURL = try XCTUnwrap(URL(string: environment["LIVE_ACCEPTANCE_BASE_URL"] ?? "http://127.0.0.1:8765"))
        let tokenPath = environment["LIVE_ACCEPTANCE_JWT_FILE"] ?? "/tmp/quantumn-live-acceptance.jwt"
        token = try String(contentsOfFile: tokenPath, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines)
        XCTAssertFalse(token.isEmpty)
    }

    func testWordProductChainEditsTwoPlacesAndRedownloadsVersionedDOCX() throws {
        try run(CaseSpec(
            title: "B5-WORD-\(UUID().uuidString)",
            prompt: """
            请通过 document.word.create_from_text 产品能力创建多页可编辑 Word 文档。标题会在下一行给出，必须原样使用。
            TITLE_PLACEHOLDER
            材料：季度经营计划；收入目标 USD 2.0 million；Milestone Alpha 日期 15 October；每周五复盘；财务和交付共同签字。必须至少三页，正文保留以上原始值，先大纲后全文审核，最终提供 DOCX。
            """,
            revision: "请做两处且仅两处内容修改：把 USD 2.0 million 改为 USD 2.4 million；把 15 October 改为 22 October。其他事实保持不变。",
            requiredText: ["USD 2.4 million", "22 October", "财务", "交付"],
            forbiddenText: ["USD 2.0 million", "15 October"],
            minimumPages: 3
        ))
    }

    func testResearchReportProductChainKeepsThreeIndependentSourceCitations() throws {
        try run(CaseSpec(
            title: "B5-RESEARCH-\(UUID().uuidString)",
            prompt: """
            请通过 report.research.create_from_text 产品能力生成可编辑研究报告。标题会在下一行给出，必须原样使用。
            TITLE_PLACEHOLDER
            研究问题：权威证据对近期全球变暖建立了什么结论？只允许使用并逐条引用以下三个独立 HTTPS 来源：[S1] IPCC https://www.ipcc.ch/report/ar6/syr/ ；[S2] NASA https://science.nasa.gov/climate-change/evidence/ ；[S3] NOAA https://www.ncei.noaa.gov/access/monitoring/monthly-report/global/202413 。引用必须与参考文献逐项对应；必须至少两页；先大纲后全文审核，最终提供 DOCX。
            """,
            revision: "在建议部分增加且只增加 annual indicator refreshes，并保持 [S1]、[S2]、[S3] 的正文引用与三个来源逐项对应。",
            requiredText: ["[S1]", "[S2]", "[S3]", "ipcc.ch", "science.nasa.gov", "ncei.noaa.gov", "annual indicator refreshes"],
            forbiddenText: [],
            minimumPages: 2
        ))
    }

    func testAcademicPaperProductChainFailsClosedOnUnverifiedSource() throws {
        try run(CaseSpec(
            title: "B5-PAPER-\(UUID().uuidString)",
            prompt: """
            请通过 paper.academic.create_from_text 产品能力生成完整学术论文。标题会在下一行给出，必须原样使用。
            TITLE_PLACEHOLDER
            论文必须含 Abstract、Keywords、Introduction、Method、Results、Discussion、Conclusion、References，且文内引用与参考文献逐项对应。只允许引用 DOI 10.1038/s41562-016-0021、10.1371/journal.pbio.1001745、10.1038/sdata.2016.18。故意提供的未核实来源 https://unverified.invalid/fabricated-paper 必须 fail closed：不得写入正文或参考文献，也不得生成其事实。必须至少三页；先大纲后全文审核，最终提供 DOCX。
            """,
            revision: "在 Conclusion 增加一句 governed workflow binds plans, code practice, and reusable data to verifiable receipts；保持三条已核实引用逐项对应，继续拒绝 unverified.invalid。",
            requiredText: ["Abstract", "Introduction", "Method", "Results", "Discussion", "Conclusion", "References", "10.1038/s41562-016-0021", "10.1371/journal.pbio.1001745", "10.1038/sdata.2016.18", "verifiable receipts"],
            forbiddenText: ["unverified.invalid", "fabricated-paper"],
            minimumPages: 3
        ))
    }

    private func run(_ spec: CaseSpec) throws {
        launchCleanRoom()
        send(spec.prompt.replacingOccurrences(of: "TITLE_PLACEHOLDER", with: spec.title))
        advanceFromChatToExecution(taskTitle: spec.title)
        approveDocumentGate("确认大纲", timeout: 900)

        let feedback = app.textFields["说明正文要如何修改（退回时必填）"]
        XCTAssertTrue(scrollUntilHittable(feedback, timeout: 900), "没有进入 Word 全文审核门。")
        for _ in 0..<6 where feedback.frame.midY > app.frame.height * 0.58 {
            app.swipeUp()
        }
        feedback.tap()
        if !app.keyboards.firstMatch.waitForExistence(timeout: 3) {
            feedback.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        }
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5), "全文修改意见输入框未获得键盘焦点。")
        feedback.typeText(spec.revision)
        let revise = app.buttons["修改"]
        XCTAssertTrue(revise.isHittable)
        revise.tap()
        let running = app.buttons["取消执行"]
        XCTAssertTrue(
            running.waitForExistence(timeout: 60),
            "退回修改后没有进入重新生成状态。"
        )
        approveDocumentGate("确认全文", timeout: 900)

        let openReview = app.buttons["open-structured-review"]
        XCTAssertTrue(scrollUntilHittable(openReview, timeout: 900), "最终 DOCX 未进入 Structured Review。")
        for _ in 0..<8 where openReview.frame.midY > app.frame.height * 0.62 {
            app.swipeUp()
        }
        XCTAssertTrue(openReview.isHittable, "Structured Review 入口被固定审批底栏遮挡。")
        openReview.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.2)).tap()
        XCTAssertTrue(app.descendants(matching: .any)["structured-review-container"].waitForExistence(timeout: 30), "Structured Review 页面未打开。")
        editStructuredReview(title: spec.title)
        app.buttons["关闭"].tap()
        let approve = app.buttons["确认并下载"]
        XCTAssertTrue(scrollUntilHittable(approve, timeout: 120))
        approve.tap()
        XCTAssertTrue(app.staticTexts["已完成并归档"].waitForExistence(timeout: 300))
        try verifyReceipt(spec)
    }

    private func launchCleanRoom() {
        app.launchArguments = ["-autoLogin"]
        app.launchEnvironment["AI_LAB_E2E_TOKEN"] = token
        app.launchEnvironment["AI_LAB_E2E_BASE_URL"] = baseURL.absoluteString
        app.launchEnvironment["AI_LAB_E2E_DISABLE_PREWARM"] = "1"
        app.launchEnvironment["AI_LAB_E2E_DISABLE_ANIMATIONS"] = "1"
        app.launch()
        let agreement = app.buttons["agreement.cta"]
        if agreement.waitForExistence(timeout: 12) { agreement.tap() }
        let newSession = app.buttons["chat-new-session"]
        XCTAssertTrue(newSession.waitForExistence(timeout: 30))
        newSession.tap()
        XCTAssertTrue(app.textFields["selected-book-chat-input"].waitForExistence(timeout: 30))
    }

    private func send(_ text: String) {
        let input = app.textFields["selected-book-chat-input"]
        XCTAssertTrue(waitUntil(timeout: 60) { input.isEnabled && input.isHittable })
        input.tap()
        input.typeText(text)
        let send = app.buttons["selected-book-chat-send"]
        XCTAssertTrue(waitUntil(timeout: 30) { send.isEnabled && send.isHittable })
        send.tap()
    }

    private func advanceFromChatToExecution(taskTitle: String) {
        var visibleConfirm: XCUIElement?
        let choiceLabels = ["正式提交或汇报", "内部协作与沉淀", "对外说明或交付"]
        func visibleElement(_ query: XCUIElementQuery) -> XCUIElement? {
            query.allElementsBoundByIndex.reversed().first { element in
                guard element.exists else { return false }
                let frame = element.frame
                return frame.minX.isFinite
                    && frame.minY.isFinite
                    && frame.maxX.isFinite
                    && frame.maxY.isFinite
                    && frame.width.isFinite
                    && frame.height.isFinite
                    && frame.width > 1
                    && frame.height > 1
                    && frame.intersects(app.frame)
            }
        }
        func reopenCurrentTask() -> Bool {
            let revealNavigation = app.buttons["main-tab-reveal"]
            if revealNavigation.exists && revealNavigation.isHittable {
                revealNavigation.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
            }
            let taskTab = app.buttons["任务"]
            guard taskTab.waitForExistence(timeout: 30) else { return false }
            taskTab.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
            let stableCard = app.buttons["workflow-card-\(taskTitle)"]
            let titleText = app.staticTexts[taskTitle]
            let deadline = Date().addingTimeInterval(120)
            while Date() < deadline {
                if stableCard.exists && stableCard.isHittable {
                    stableCard.tap()
                    return true
                }
                if titleText.exists && titleText.isHittable {
                    titleText.tap()
                    return true
                }
                let matchingCard = visibleElement(
                    app.buttons.matching(NSPredicate(format: "label CONTAINS %@", taskTitle))
                )
                if let matchingCard {
                    matchingCard.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
                    return true
                }
                app.swipeUp()
                RunLoop.current.run(until: Date().addingTimeInterval(0.5))
            }
            return false
        }
        for _ in 0..<120 {
            let stableConfirm = app.buttons["capability-confirm-execute"]
            if stableConfirm.exists
                && stableConfirm.isHittable
                && stableConfirm.frame.intersects(app.frame)
                && stableConfirm.frame.maxY < app.frame.maxY - 120 {
                visibleConfirm = stableConfirm
                break
            }
            let confirms = app.buttons.matching(
                NSPredicate(format: "label IN %@", ["确认", "确认执行"])
            ).allElementsBoundByIndex
            visibleConfirm = confirms
                .filter {
                    $0.exists
                        && $0.isHittable
                        && $0.frame.intersects(app.frame)
                        && $0.frame.maxY < app.frame.maxY - 120
                }
                .max { $0.frame.maxY < $1.frame.maxY }
            if visibleConfirm != nil { break }
            if confirms.contains(where: { $0.exists }) {
                app.swipeUp()
                continue
            }

            let explicitChoice = visibleElement(
                app.buttons.matching(NSPredicate(format: "label IN %@", choiceLabels))
            )
            let legacyChoice = visibleElement(
                app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "未选择,"))
            ) ?? visibleElement(
                app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "未选择，"))
            )
            if let choice = explicitChoice ?? legacyChoice {
                choice.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
                let continueButton = visibleElement(
                    app.buttons.matching(NSPredicate(format: "label == %@", "确认并继续"))
                )
                continueButton?.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
            } else {
                app.swipeUp()
            }
            _ = app.buttons["确认执行"].waitForExistence(timeout: 5)
        }
        XCTAssertNotNil(visibleConfirm, "Hermes 未返回当前 document.created 产品确认事件。")
        let returnToTask = app.buttons["返回任务"]
        let accurate = app.buttons.matching(
            NSPredicate(format: "label BEGINSWITH %@", "未选择，内容准确")
        ).firstMatch
        visibleConfirm?.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        _ = waitUntil(timeout: 60) { returnToTask.exists || accurate.exists }

        if !returnToTask.exists && !accurate.exists {
            XCTAssertTrue(
                reopenCurrentTask(),
                "确认执行后未自动转换，任务列表也找不到当前工作流。"
            )
            _ = waitUntil(timeout: 60) { returnToTask.exists || accurate.exists }
        }
        XCTAssertTrue(
            returnToTask.exists || accurate.exists,
            "确认执行后既未显示‘返回任务’，也未进入需求确认页。"
        )
        for _ in 0..<20 where !accurate.exists {
            let explicitChoice = visibleElement(
                app.buttons.matching(NSPredicate(format: "label IN %@", choiceLabels))
            )
            let legacyChoice = visibleElement(
                app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "未选择，"))
            )
            if let taskChoice = explicitChoice ?? legacyChoice {
                taskChoice.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
                let continueButton = app.buttons["确认并继续"]
                if scrollUntilHittable(continueButton, timeout: 30) {
                    continueButton.tap()
                }
            } else {
                let createFirstWorkflow = app.buttons["创建第一个工作流"]
                if createFirstWorkflow.exists && createFirstWorkflow.isHittable {
                    createFirstWorkflow.tap()
                } else {
                    app.swipeUp()
                }
            }
            RunLoop.current.run(until: Date().addingTimeInterval(0.5))
        }
        XCTAssertTrue(accurate.waitForExistence(timeout: 60), "需求确认页没有‘内容准确’按钮。")
        accurate.tap()

        let generatePlan = app.buttons["确认并生成方案"]
        XCTAssertTrue(scrollUntilHittable(generatePlan, timeout: 60), "未能滚动到‘确认并生成方案’。")
        generatePlan.tap()
        let reviewPlan = app.buttons["查看并确认方案"]
        if !reviewPlan.waitForExistence(timeout: 30) {
            XCTAssertTrue(reopenCurrentTask(), "方案已生成，但未能返回当前任务。")
        }
        XCTAssertTrue(reviewPlan.waitForExistence(timeout: 420), "云端方案已生成，但任务页没有出现‘查看并确认方案’。")
        reviewPlan.tap()
        let buildAgent = app.buttons["确认并构建 Agent"]
        XCTAssertTrue(buildAgent.waitForExistence(timeout: 120))
        buildAgent.tap()
        let viewAgent = app.buttons["查看专属 Agent"]
        let startTask = app.buttons["启动任务"]
        XCTAssertTrue(waitUntil(timeout: 420) { viewAgent.exists || startTask.exists })
        if viewAgent.exists { viewAgent.tap() }
        XCTAssertTrue(waitUntil(timeout: 120) { startTask.exists && startTask.isHittable })
        startTask.tap()
    }

    private func approveDocumentGate(_ title: String, timeout: TimeInterval) {
        let button = app.buttons[title]
        XCTAssertTrue(
            waitUntil(timeout: timeout) { button.exists && button.isEnabled && button.isHittable },
            "没有进入文档门禁：\(title)"
        )
        button.tap()
    }

    private func editStructuredReview(title: String) {
        let deliverableTitle = app.textFields["structured-review-field-deliverable_title"]
        XCTAssertTrue(scrollUntilHittable(deliverableTitle, timeout: 60))
        deliverableTitle.tap()
        deliverableTitle.typeKey("a", modifierFlags: .command)
        deliverableTitle.typeText("\(title)-reviewed")
        dismissKeyboard()
        let notes = app.textFields["structured-review-field-review_notes"]
        XCTAssertTrue(scrollUntilHittable(notes, timeout: 30))
        notes.tap()
        notes.typeText("已核验两处修改、版本、引用与下载哈希")
        dismissKeyboard()
        let decision = app.descendants(matching: .any)["structured-review-field-decision"]
        XCTAssertTrue(scrollUntilHittable(decision, timeout: 30))
        decision.tap()
        app.buttons["可以确认"].tap()
        let checked = app.switches["structured-review-field-preview_checked"]
        XCTAssertTrue(scrollUntilHittable(checked, timeout: 30))
        if (checked.value as? String) != "1" { checked.tap() }
        let save = app.buttons["structured-review-save"]
        XCTAssertTrue(save.waitForExistence(timeout: 30))
        XCTAssertTrue(save.isHittable, "固定保存操作区在键盘关闭后不可达。")
        save.tap()
        let version = app.staticTexts["structured-review-version"]
        XCTAssertTrue(version.waitForExistence(timeout: 30))
        let versionUpdated = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "label == %@", "版本 2"),
            object: version
        )
        XCTAssertEqual(
            XCTWaiter.wait(for: [versionUpdated], timeout: 30),
            .completed,
            "Structured Review 两处修改未持久化到新版本。"
        )
    }

    private func verifyReceipt(_ spec: CaseSpec) throws {
        let workflows = try requestJSON("GET", path: "/api/v1/workflows") as? [[String: Any]] ?? []
        let workflow = try XCTUnwrap(workflows.first { ($0["title"] as? String) == spec.title })
        let workflowID = try XCTUnwrap(workflow["id"] as? String)
        let execution = try XCTUnwrap(workflow["latest_execution"] as? [String: Any])
        let executionID = try XCTUnwrap(execution["id"] as? String)
        XCTAssertEqual(execution["status"] as? String, "completed")
        let executionDetail = try XCTUnwrap(
            try requestJSON("GET", path: "/api/v1/workflow-executions/\(executionID)") as? [String: Any]
        )
        let nodeReceipts = executionDetail["nodes"] as? [[String: Any]] ?? []
        XCTAssertTrue(nodeReceipts.contains { node in
            let model = node["model_used"] as? String ?? ""
            let provider = node["provider_used"] as? String ?? ""
            let tokens = node["token_used"] as? Int ?? 0
            return !model.isEmpty && !provider.isEmpty && tokens > 0
        }, "缺少真实 Hermes 模型/Provider/Token 节点收据。")

        let artifacts = try requestJSON("GET", path: "/api/v1/workflow-executions/\(executionID)/artifacts") as? [[String: Any]] ?? []
        let document = try XCTUnwrap(artifacts.last {
            ($0["extension"] as? String) == "docx" && ($0["kind"] as? String) == "final"
        })
        let artifactID = try XCTUnwrap(document["id"] as? String)
        let expectedHash = try XCTUnwrap(document["content_hash"] as? String)
        let metadata = document["metadata"] as? [String: Any] ?? [:]
        XCTAssertGreaterThanOrEqual(metadata["artifact_version"] as? Int ?? 0, 2)
        let serverOwnerID = try XCTUnwrap(
            (workflow["agent"] as? [String: Any])?["owner_user_id"] as? String
        )
        let serverSessionID = try XCTUnwrap(workflow["source_client_session_id"] as? String)
        XCTAssertFalse(serverOwnerID.isEmpty)
        XCTAssertFalse(serverSessionID.isEmpty)
        XCTAssertEqual(metadata["owner_id"] as? String, serverOwnerID)
        XCTAssertEqual(metadata["source_client_session_id"] as? String, serverSessionID)
        XCTAssertGreaterThan(metadata["generation"] as? Int ?? 0, 0)

        let first = try requestData("GET", path: "/api/v1/workflow-executions/\(executionID)/artifacts/\(artifactID)/download")
        let second = try requestData("GET", path: "/api/v1/workflow-executions/\(executionID)/artifacts/\(artifactID)/download")
        XCTAssertEqual(first, second)
        XCTAssertEqual(SHA256.hash(data: first).map { String(format: "%02x", $0) }.joined(), expectedHash)
        XCTAssertEqual(Array(first.prefix(2)), [0x50, 0x4b], "下载结果不是 DOCX ZIP。")

        let contentJSON = try XCTUnwrap(try requestJSON("GET", path: "/api/v1/workflow-executions/\(executionID)/artifacts/\(artifactID)/content") as? [String: Any])
        let content = try XCTUnwrap(contentJSON["content"] as? String)
        spec.requiredText.forEach { XCTAssertTrue(content.localizedCaseInsensitiveContains($0), "DOCX 缺少：\($0)") }
        spec.forbiddenText.forEach { XCTAssertFalse(content.localizedCaseInsensitiveContains($0), "DOCX 不应包含：\($0)") }
        XCTAssertGreaterThanOrEqual(contentJSON["page_count"] as? Int ?? 0, spec.minimumPages)

        let review = try XCTUnwrap(try requestJSON("GET", path: "/api/v1/workflows/\(workflowID)/structured-reviews/final-draft") as? [String: Any])
        XCTAssertGreaterThanOrEqual(review["version"] as? Int ?? 0, 2)
    }

    private func requestJSON(_ method: String, path: String) throws -> Any {
        let data = try requestData(method, path: path)
        return try JSONSerialization.jsonObject(with: data)
    }

    private func requestData(_ method: String, path: String) throws -> Data {
        var request = URLRequest(url: baseURL.appending(path: path))
        request.httpMethod = method
        request.setValue("Bearer \(token!)", forHTTPHeaderField: "Authorization")
        request.setValue("ios-unified-agreement-v1", forHTTPHeaderField: "X-Client-Contract")
        let expectation = expectation(description: "\(method) \(path)")
        var result: Result<Data, Error>!
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error { result = .failure(error) }
            else if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                result = .failure(NSError(domain: "DocumentProductLiveE2E", code: http.statusCode, userInfo: [NSLocalizedDescriptionKey: String(data: data ?? Data(), encoding: .utf8) ?? ""]))
            } else { result = .success(data ?? Data()) }
            expectation.fulfill()
        }.resume()
        wait(for: [expectation], timeout: 120)
        return try result.get()
    }

    private func waitUntil(timeout: TimeInterval, condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.5))
        }
        return condition()
    }

    private func scrollUntilHittable(_ element: XCUIElement, timeout: TimeInterval) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        let fieldsScroll = app.scrollViews["structured-review-fields-scroll"]
        while Date() < deadline {
            if element.exists && element.isHittable { return true }
            if fieldsScroll.exists {
                fieldsScroll.swipeUp()
            } else {
                app.swipeUp()
            }
        }
        return element.exists && element.isHittable
    }

    private func dismissKeyboard() {
        let keyboard = app.keyboards.firstMatch
        guard keyboard.exists else { return }
        for label in ["完成", "Done", "收起键盘"] {
            let keyboardButton = keyboard.buttons[label]
            if keyboardButton.exists && keyboardButton.isHittable {
                keyboardButton.tap()
                _ = waitUntil(timeout: 5) { !keyboard.exists }
                return
            }
            let toolbarButton = app.buttons[label]
            if toolbarButton.exists && toolbarButton.isHittable {
                toolbarButton.tap()
                _ = waitUntil(timeout: 5) { !keyboard.exists }
                return
            }
        }
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.92, dy: 0.12)).tap()
        if keyboard.exists {
            keyboard.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.05))
                .press(forDuration: 0.1, thenDragTo: keyboard.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.95)))
        }
        XCTAssertTrue(waitUntil(timeout: 5) { !keyboard.exists }, "键盘未能稳定关闭。")
    }
}

final class IstanbulPresentationLiveE2ETests: XCTestCase {
    private let app = XCUIApplication(bundleIdentifier: "com.ailab.AIPlatformApp")

    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    func testContinueNewestIstanbulWorkflowThroughPPTXDownload() throws {
        app.launch()
        let taskTab = app.buttons["任务"]
        XCTAssertTrue(taskTab.waitForExistence(timeout: 30), "找不到任务入口。")
        taskTab.tap()
        let activity = app.descendants(matching: .any).matching(NSPredicate(format: "label BEGINSWITH %@", "穷游伊斯坦布尔")).firstMatch
        XCTAssertTrue(activity.waitForExistence(timeout: 60), "任务列表中找不到上一轮伊斯坦布尔工作流。")
        activity.tap()

        let confirmOutline = app.buttons["确认大纲"]
        if !confirmOutline.exists {
            let viewAgent = app.buttons["查看专属 Agent"]
            let startTask = app.buttons["启动任务"]
            XCTAssertTrue(waitUntil(timeout: 420) { viewAgent.exists || startTask.exists }, "专属 Agent 未恢复到可启动状态。")
            if viewAgent.exists { viewAgent.tap() }
            XCTAssertTrue(waitUntil(timeout: 120) { startTask.exists && startTask.isHittable }, "启动入口未稳定显示。")
            startTask.tap()
        }

        try reviewGate(approveButton: "确认并下载", timeout: 900, screenshotName: "istanbul-full-deck-preview")
        verifyCompletedPPTX()
    }

    func testFreshRequestCreatesWorkflowAndAutoOpensTask() throws {
        app.launch()
        try completeFreshIstanbulWorkflow()
    }

    func testCleanRoomIstanbulPresentationCompletesThreeStepFlowAndDownloadsPPTX() throws {
        let environment = ProcessInfo.processInfo.environment
        guard environment["LIVE_ACCEPTANCE"] == "1" else {
            throw XCTSkip("Set LIVE_ACCEPTANCE=1 for the production clean-room test.")
        }
        let baseURL = environment["LIVE_ACCEPTANCE_BASE_URL"]
        let token: String
        if let tokenPath = environment["LIVE_ACCEPTANCE_JWT_FILE"] {
            token = try String(contentsOfFile: tokenPath, encoding: .utf8)
                .trimmingCharacters(in: .whitespacesAndNewlines)
        } else if baseURL == "http://127.0.0.1:8765" {
            token = try String(contentsOfFile: "/tmp/quantumn-live-acceptance.jwt", encoding: .utf8)
                .trimmingCharacters(in: .whitespacesAndNewlines)
        } else {
            token = try XCTUnwrap(environment["LIVE_ACCEPTANCE_JWT"])
        }
        XCTAssertFalse(token.isEmpty)
        app.launchArguments = ["-autoLogin"]
        app.launchEnvironment["AI_LAB_E2E_TOKEN"] = token
        app.launchEnvironment["AI_LAB_E2E_DISABLE_PREWARM"] = "1"
        if let baseURL {
            app.launchEnvironment["AI_LAB_E2E_BASE_URL"] = baseURL
        }
        addUIInterruptionMonitor(withDescription: "Local network access") { alert in
            let allow = alert.buttons["允许"]
            if allow.exists {
                allow.tap()
                return true
            }
            let ok = alert.buttons["好"]
            if ok.exists {
                ok.tap()
                return true
            }
            return false
        }
        app.launch()
        app.tap()
        acceptAgreementIfNeeded()
        startCleanSession()
        try completeFreshIstanbulWorkflow()
    }

    private func startCleanSession() {
        // The production app persists chat history. Reusing that transcript made
        // repeated acceptance runs append another full source document to an
        // already very large accessibility tree; the real-device XCTest runner
        // was then killed while querying the composer. A clean-room run must
        // explicitly create a fresh client session before entering its fixture.
        let newSession = app.buttons["chat-new-session"]
        XCTAssertTrue(newSession.waitForExistence(timeout: 30), "找不到新建会话入口。")
        newSession.tap()
        let input = app.textFields["selected-book-chat-input"]
        XCTAssertTrue(waitUntil(timeout: 30) {
            input.exists && input.isEnabled && input.isHittable
                && self.app.descendants(matching: .any)
                    .matching(identifier: "selected-book-chat-request").count == 0
        }, "新会话没有进入空白且可输入的 clean-room 状态。")
    }

    private func completeFreshIstanbulWorkflow() throws {
        let exactInputHash = SHA256.hash(data: Data(sourceMaterial.utf8)).map { String(format: "%02x", $0) }.joined()
        XCTAssertEqual(exactInputHash, "7f817d92d614362b12b928d8547f90018397793acb0c8484ba11610111ca3440", "模拟器没有使用用户提供的完整原文。")
        send(
            """
            【原文开始】
            \(sourceMaterial)
            【原文结束】
            【编排任务】基于以上原文生成信息丰富的可编辑 PPT。text_material 必须逐字复制【原文开始】与【原文结束】之间的内容，不得把任务说明写入原文；地图行程、住宿、美食、避坑和拍照玩法必须逐项基于原文，推导和外部补充须单独标注。
            """
        )

        let confirmExecution = app.buttons["确认执行"]
        for _ in 0..<20 where !confirmExecution.waitForExistence(timeout: 45) {
            let choice = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "未选择，")).firstMatch
            if choice.exists {
                if !choice.isHittable { app.swipeUp() }
                guard choice.isHittable else { continue }
                choice.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
                let confirmChoice = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "确认")).allElementsBoundByIndex.first {
                    $0.label != "确认执行" && $0.isHittable
                }
                confirmChoice?.tap()
            }
        }
        XCTAssertTrue(confirmExecution.waitForExistence(timeout: 20), "没有收到工作流确认卡。")
        confirmExecution.tap()

        let backToTasks = app.buttons["返回任务"]
        XCTAssertTrue(backToTasks.waitForExistence(timeout: 120), "工作流创建后没有自动打开任务详情。")
        XCTAssertTrue(app.staticTexts["需求"].waitForExistence(timeout: 30), "任务详情没有显示需求阶段。")

        let accurate = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "内容准确")).firstMatch
        XCTAssertTrue(scrollUntilHittable(accurate, timeout: 60), "需求确认单没有可点击的“内容准确”选项。")
        accurate.tap()
        let generatePlan = app.buttons["确认并生成方案"]
        XCTAssertTrue(scrollUntilHittable(generatePlan, timeout: 30))
        generatePlan.tap()

        let reviewPlan = app.buttons["查看并确认方案"]
        XCTAssertTrue(reviewPlan.waitForExistence(timeout: 420), "云端未生成可确认方案。")
        reviewPlan.tap()
        let buildAgent = app.buttons["确认并构建 Agent"]
        XCTAssertTrue(buildAgent.waitForExistence(timeout: 120), "方案确认页未加载。")
        buildAgent.tap()

        let viewAgent = app.buttons["查看专属 Agent"]
        let startTask = app.buttons["启动任务"]
        XCTAssertTrue(
            waitUntil(timeout: 420) { viewAgent.exists || startTask.exists },
            "专属 Agent 未构建完成。"
        )
        if viewAgent.exists {
            viewAgent.tap()
        }
        XCTAssertTrue(waitUntil(timeout: 120) { startTask.exists && startTask.isHittable }, "Agent 已构建但启动入口未稳定显示。")
        startTask.tap()

        XCTAssertTrue(
            app.otherElements["presentation.three-step-header"].waitForExistence(timeout: 120),
            "PPT 任务没有显示三步产品路径。"
        )
        let confirmDownload = app.buttons["确认并下载"]
        let confirmOutline = app.buttons["确认大纲"]
        let confirmDesign = app.buttons["确认并生成全稿"]
        XCTAssertTrue(
            waitUntil(timeout: 900) {
                confirmDownload.exists || confirmOutline.exists || confirmDesign.exists
            },
            "默认路径没有进入全稿预览。"
        )
        XCTAssertFalse(confirmOutline.exists, "默认路径不应要求用户确认内部大纲节点。")
        XCTAssertFalse(confirmDesign.exists, "默认路径不应要求用户确认内部设计节点。")
        try reviewGate(approveButton: "确认并下载", timeout: 30, screenshotName: "istanbul-full-deck-preview")
        verifyCompletedPPTX()
    }

    private func send(_ text: String) {
        let input = app.textFields["selected-book-chat-input"]
        XCTAssertTrue(input.waitForExistence(timeout: 30))
        guard waitUntil(timeout: 120, condition: { input.isEnabled && input.isHittable }) else {
            XCTFail("Istanbul chat input never became interactive.")
            return
        }
        input.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        if !app.keyboards.firstMatch.waitForExistence(timeout: 5) {
            input.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        }
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        input.typeText(text)
        let button = app.buttons["selected-book-chat-send"]
        XCTAssertTrue(waitUntil(timeout: 30) { button.isEnabled && button.isHittable })
        button.tap()
    }

    private func acceptAgreementIfNeeded() {
        let cta = app.buttons["agreement.cta"]
        guard cta.waitForExistence(timeout: 12) else { return }
        // The agreement screen can complete asynchronously while XCTest still holds
        // a stale XCUIElement snapshot. Disappearance means the gate resolved; it is
        // not a failure. Only require actionability while the CTA remains present.
        guard waitUntil(timeout: 60, condition: {
            !cta.exists || (cta.isEnabled && cta.isHittable)
        }) else {
            XCTFail("Required service agreement never became actionable.")
            return
        }
        guard cta.exists else { return }
        cta.tap()
        XCTAssertTrue(waitUntil(timeout: 60) { !cta.exists })
    }

    private func waitUntil(timeout: TimeInterval, condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.5))
        }
        return condition()
    }

    private func scrollUntilHittable(_ element: XCUIElement, timeout: TimeInterval) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if element.exists && element.isHittable { return true }
            let scroll = app.scrollViews.firstMatch
            if scroll.exists { scroll.swipeUp() }
            RunLoop.current.run(until: Date().addingTimeInterval(0.5))
        }
        return element.exists && element.isHittable
    }

    private func reviewGate(approveButton title: String, timeout: TimeInterval, screenshotName: String) throws {
        let approve = app.buttons[title]
        XCTAssertTrue(approve.waitForExistence(timeout: timeout), "没有进入验收门：\(title)")
        let expectedArtifactTitle: String
        switch title {
        case "确认大纲": expectedArtifactTitle = "生成演示文稿大纲"
        case "确认并生成全稿": expectedArtifactTitle = "生成代表页设计样稿"
        default: expectedArtifactTitle = "生成可编辑演示文稿"
        }
        let preview = app.descendants(matching: .any).matching(NSPredicate(
            format: "identifier BEGINSWITH %@ AND label CONTAINS %@",
            "workflow-artifact-preview-",
            expectedArtifactTitle
        )).firstMatch
        XCTAssertTrue(scrollUntilHittable(preview, timeout: 120), "验收门 \(title) 没有露出可点击预览。")
        preview.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.25)).tap()
        let done = app.buttons["完成"]
        XCTAssertTrue(done.waitForExistence(timeout: 60), "验收门 \(title) 的预览未打开。")
        RunLoop.current.run(until: Date().addingTimeInterval(5))
        attachScreenshot(named: screenshotName)
        done.tap()
        XCTAssertTrue(approve.waitForExistence(timeout: 30))
        approve.tap()
        if title == "确认并下载" {
            XCTAssertTrue(app.staticTexts["已完成并归档"].waitForExistence(timeout: 300), "确认全稿后未进入完成态。")
        }
    }

    private func verifyCompletedPPTX() {
        let completedPreview = app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH %@", "workflow-artifact-preview-")).firstMatch
        XCTAssertTrue(completedPreview.waitForExistence(timeout: 180), "完成后 PPTX 预览入口未出现。")
        completedPreview.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        XCTAssertTrue(app.buttons["完成"].waitForExistence(timeout: 60), "完成态 PPTX 预览未打开。")
        let download = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "下载可编辑 PPTX")).firstMatch
        XCTAssertTrue(download.waitForExistence(timeout: 60), "完成态未开放可编辑 PPTX 下载/分享。")
        download.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        XCTAssertTrue(waitUntil(timeout: 30) {
            !download.isHittable
        }, "PPTX 下载/分享面板未打开。")
        attachScreenshot(named: "istanbul-completed-pptx-download")
    }

    private func attachScreenshot(named name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    private var sourceMaterial: String {
        """
        穷游土耳其？教你躲开伊斯坦布尔的“价格刺客”，还能拍出大片！🌅
        第二次来伊斯坦布尔了，相比于第一次，的确被物价背刺不少…
        先给大家一个总纲，后续我会针对重点景点给一些细节的攻略：
        📖伊斯坦布尔入境
        土耳其对中国大陆免签。伊斯坦布尔IST机场Passport Control排队盖章入境即可
        🚃交通方法
        🔷如果乘坐公共交通：
        1️⃣在IST拿完行李，找到9号门附近的一排ATM机，找蓝色的 “is bankasi”，汇率不错免本地手续费。
        2️⃣找到红色标志 u METRO，顺着标志到地铁站内，在负二楼地铁站内有青色、蓝色、黄色三种机器，找蓝色机器买卡（制卡费165里拉）
        3️⃣使用Yandex Metro这个app可以看路线：搭乘M11第一站坐到Gayrettepe，下车换乘M2坐到Veznecıler - İstanbul Ünıversıtesı，出站向南走一条街到Laleli-İstanbul Üniversitesi，搭乘T1到Sultanahmet（蓝色清真寺/圣索菲亚大教堂）
        ⚠️注意：公共交通虽然便宜，但只适合行李较少，腿脚麻利的人。不适合女生，不适合扶老携幼的家庭。不要问我为什么，因为爬高上低走路换乘真的很崩溃
        🔷如果打车：
        土耳其价格刺客太多了，建议打uber。从机场到蓝色清真寺，大概4500里拉
        🚶玩法
        一般来说，2天可以走完大多数主要景点，我的行程参考为：
        🚢D1: 欧洲区
        1️⃣蓝色清真寺/圣索菲亚大教堂：建议住在附近，走路前往。圣索菲亚是价格刺客！！对于历史爱好者建议前往，其他人慎重❗️
        2️⃣苏莱曼尼清真寺：在一个山头上，需要步行，不爱爬山的人慎重前往
        3️⃣İBB Sarayburnu Parkı看海：位于托普卡皮皇宫前方的海边，人少，可以从「居尔哈尼公园」穿过去
        4️⃣加拉塔大桥：步行前往，桥上很多当地人在钓鱼，拍照很出片
        5️⃣大巴扎（周边有007拍摄地 Sirkeci Lokantası 1912）：一个普通集市，人比较多，建议逛逛即可（撒盐哥的牛排店就在这里）
        6️⃣彩色巴拉特街区 Colorful Stairs：马卡龙色系的街区，很适合喝茶发呆，但是唯一需要的就是脚力，因为要爬山
        7️⃣seven hills 楼顶：我就住在这里，直接上楼喂海鸥
        8️⃣黄昏轮渡：算好时间，在轮渡上可以看日落黄昏，很棒
        9️⃣Kadırga Hamamı/Cemberlitas Hammam：如果有空可以去感受个土耳其浴。Kadırga Hamamı便宜一些，Cemberlitas Hammam由于过于知名，所以比较贵
        ⭐️D2:亚洲区
        1️⃣独立大街：坐轮渡过去
        2️⃣加拉塔石塔：位于金角湾对面山顶上，也需要爬山，同时也是个价格刺客。为了拍照，可以选旁边的Galata Konak Cafe，立省30欧
        3️⃣奥塔科伊清真寺：潮汐🌊网红清真寺，个人觉得日落时分真的美炸了
        4️⃣库兹衮库克 Kuzguncuk Evleri：新晋的亚洲区休闲街区，适合买杯咖啡发呆一下午
        5️⃣撒盐哥的牛排店 Nusr-Et Steakhouse Kapalıçarşı Nusr-et Sandal Bedesteni：位于大巴扎，价格略贵，但是品质是可以的
        """
    }
}
