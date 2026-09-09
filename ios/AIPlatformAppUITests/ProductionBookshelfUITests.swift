import XCTest

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
        guard let knowledgeTab = requireAuthenticatedKnowledgeTab() else { return }

        let chatTab = app.buttons["main-tab-0"]
        XCTAssertTrue(chatTab.waitForExistence(timeout: 10))
        chatTab.tap()
        let newSession = app.buttons["新建会话"]
        XCTAssertTrue(newSession.waitForExistence(timeout: 10))
        newSession.tap()
        XCTAssertTrue(app.textFields["selected-book-chat-input"].waitForExistence(timeout: 12))

        knowledgeTab.tap()
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
        let bookshelfScroll = app.scrollViews["publication-bookshelf-container"]
        XCTAssertTrue(bookshelfScroll.waitForExistence(timeout: 10))
        let refresh = app.buttons["publication-bookshelf-refresh"]
        XCTAssertTrue(refresh.waitForExistence(timeout: 10))
        refresh.tap()

        let serialShelf = app.buttons["bookshelf-collection.knowledge/publication/public"]
        XCTAssertTrue(serialShelf.waitForExistence(timeout: 20), "真实刷新后未找到每日测试连载书架。")
        attachScreenshot(named: "01-production-bookshelf-refreshed")
        serialShelf.tap()

        XCTAssertTrue(app.staticTexts["书架上的精选"].waitForExistence(timeout: 10))
        let expectedCardIdentifiers = expectedPublications.map {
            "publication-book-card.\($0.seriesID).\($0.bookID)"
        }
        let publishedBook = app.buttons.matching(NSPredicate(
            format: "identifier == %@ OR identifier == %@",
            expectedCardIdentifiers[0], expectedCardIdentifiers[1]
        )).firstMatch
        XCTAssertTrue(publishedBook.waitForExistence(timeout: 15), "配置中的两本已发布 Quantumn 测试书均不可见。")
        let identity = try publicationIdentity(from: publishedBook)
        let expected = try XCTUnwrap(expectedPublications.first { $0.bookID == identity.bookID })
        XCTAssertEqual(identity.seriesID, expected.seriesID)
        let selectedBookTitle = publishedBook.label.components(separatedBy: "，作者 ").first ?? ""
        XCTAssertEqual(selectedBookTitle, expected.title)
        attachScreenshot(named: "02-published-test-book-visible")
        publishedBook.tap()

        let serialBadge = app.staticTexts.matching(
            NSPredicate(format: "label CONTAINS %@", expected.seriesTitle)
        ).firstMatch
        XCTAssertTrue(serialBadge.waitForExistence(timeout: 12), "打开的书不是已发布测试连载。")

        let subscription = app.buttons["publication-subscription-control.\(identity.bookID)"]
        XCTAssertTrue(subscription.waitForExistence(timeout: 10))
        let originalSubscription = try XCTUnwrap(subscription.value as? String)
        XCTAssertTrue(["subscribed", "unsubscribed"].contains(originalSubscription))
        if originalSubscription == "unsubscribed" {
            subscribedDuringTestBookID = identity.bookID
            subscription.tap()
            XCTAssertTrue(waitForValue("subscribed", of: subscription, timeout: 20), "真实书籍订阅未成功。")
        }
        attachScreenshot(named: "03-test-book-subscribed")
        subscription.tap()

        let readerBody = app.scrollViews["publication-reader-body.\(identity.bookID)"]
        XCTAssertTrue(readerBody.waitForExistence(timeout: 20), "真实书籍阅读器未出现。")
        let progress = app.staticTexts["publication-reader-progress.\(identity.bookID)"]
        XCTAssertTrue(progress.waitForExistence(timeout: 20), "真实书籍正文未加载。")
        let progressState = try XCTUnwrap(progress.value as? String)
        XCTAssertTrue(progressState.hasPrefix("original="), "未捕获原始阅读进度。")
        let bodyContent = app.descendants(matching: .any)["publication-reader-content.\(identity.bookID)"]
        XCTAssertTrue(bodyContent.waitForExistence(timeout: 20), "已发布正文内容标记未出现。")
        let actualBody = try XCTUnwrap(bodyContent.value as? String)
        XCTAssertTrue(actualBody.contains(expected.bodyExcerpt), "真实正文未包含已审核清单中的稳定正文摘录：\(expected.bodyExcerpt)")
        XCTAssertFalse(app.buttons["阅读进度未同步，点按重试。"].exists)
        attachScreenshot(named: "04-production-book-body-and-progress")

        app.buttons["返回书籍概述"].tap()
        let askChat = app.buttons["selected-book-chat-open.\(identity.bookID)"]
        for _ in 0..<6 where !askChat.isHittable { app.scrollViews.firstMatch.swipeUp() }
        XCTAssertTrue(askChat.waitForExistence(timeout: 10))
        askChat.tap()

        let input = app.textFields["selected-book-chat-input"]
        XCTAssertTrue(input.waitForExistence(timeout: 12))
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
        let requestMarkerCountBeforeSend = requestMarkers.count
        let responseMarkerCountBeforeSend = responseMarkers.count
        let promptRequestCountBeforeSend = matchingPromptRequests.count
        let tokenResponseCountBeforeSend = matchingTokenResponses.count
        input.tap()
        input.typeKey("a", modifierFlags: .command)
        input.typeText(realModelPrompt)
        app.buttons["selected-book-chat-send"].tap()

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
            waitForCountGreaterThan(tokenResponseCountBeforeSend, in: matchingTokenResponses, timeout: 180),
            "选书 Chat 未返回本次真实模型验收 token。"
        )
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

    private func publicationIdentity(from element: XCUIElement) throws -> (seriesID: String, bookID: String) {
        let prefix = "publication-book-card."
        let identifier = element.identifier
        XCTAssertTrue(identifier.hasPrefix(prefix))
        let components = identifier.dropFirst(prefix.count).split(separator: ".", maxSplits: 1).map(String.init)
        XCTAssertEqual(components.count, 2)
        return (try XCTUnwrap(components.first), try XCTUnwrap(components.last))
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
        let knowledgeTab = app.buttons["main-tab-2"]
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
        let card = app.buttons["publication-book-card.\(expected.seriesID).\(bookID)"]
        if !card.waitForExistence(timeout: 3) {
            let shelf = app.buttons["bookshelf-collection.knowledge/publication/public"]
            guard shelf.waitForExistence(timeout: 15) else {
                XCTFail("恢复订阅状态时未找到生产测试书架。")
                return
            }
            shelf.tap()
        }
        guard card.waitForExistence(timeout: 15) else {
            XCTFail("恢复订阅状态时未找到原书籍。")
            return
        }
        card.tap()
        let remove = app.buttons["publication-subscription-remove.\(bookID)"]
        guard remove.waitForExistence(timeout: 10) else {
            XCTFail("恢复订阅状态时未找到移出书架控件。")
            return
        }
        remove.tap()
        XCTAssertTrue(waitForValue(
            "unsubscribed", of: app.buttons["publication-subscription-control.\(bookID)"], timeout: 20
        ), "未恢复测试前的未订阅状态。")
    }

    private func attachScreenshot(named name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
