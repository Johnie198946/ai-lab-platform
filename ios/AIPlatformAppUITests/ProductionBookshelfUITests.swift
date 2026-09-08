import XCTest

final class ProductionBookshelfUITests: XCTestCase {
    private let app = XCUIApplication()
    private let realModelPrompt = "这是 Quantumn 真机选书 Chat 生产验收。只回复 QUANTUMN_IOS_SELECTED_BOOK_CHAT_OK，不要输出其他内容。"
    private let realModelToken = "QUANTUMN_IOS_SELECTED_BOOK_CHAT_OK"

    override func setUpWithError() throws {
        continueAfterFailure = false
        app.launch()
    }

    func testProductionBookshelfReadingAndSelectedBookChat() throws {
        let knowledgeTab = app.buttons["main-tab-2"]
        guard knowledgeTab.waitForExistence(timeout: 12) else {
            if app.buttons["打开登录"].exists {
                throw XCTSkip("设备当前未登录；保留 Keychain 与应用数据，跳过生产书架验收。")
            }
            XCTFail("主导航未出现，且页面不是登录页。")
            return
        }

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
        let bookshelfScroll = app.scrollViews.firstMatch
        XCTAssertTrue(bookshelfScroll.waitForExistence(timeout: 10))
        bookshelfScroll.swipeDown()

        let serialShelf = app.buttons.matching(
            NSPredicate(format: "label BEGINSWITH %@", "Quantumn 每日测试连载，")
        ).firstMatch
        XCTAssertTrue(serialShelf.waitForExistence(timeout: 20), "真实刷新后未找到每日测试连载书架。")
        attachScreenshot(named: "01-production-bookshelf-refreshed")
        serialShelf.tap()

        XCTAssertTrue(app.staticTexts["书架上的精选"].waitForExistence(timeout: 10))
        let publishedBook = app.buttons.matching(
            NSPredicate(format: "label CONTAINS %@", "，作者 ")
        ).firstMatch
        XCTAssertTrue(publishedBook.waitForExistence(timeout: 15), "两本已发布测试书均不可见。")
        let bookLabel = publishedBook.label
        XCTAssertFalse(bookLabel.isEmpty)
        attachScreenshot(named: "02-published-test-book-visible")
        publishedBook.tap()

        let serialBadge = app.staticTexts.matching(
            NSPredicate(format: "label BEGINSWITH %@", "测试连载 · ")
        ).firstMatch
        XCTAssertTrue(serialBadge.waitForExistence(timeout: 12), "打开的书不是已发布测试连载。")

        let subscribe = app.buttons["加入我的笔记书架"]
        if subscribe.exists {
            subscribe.tap()
        }
        let startReading = app.buttons.matching(
            NSPredicate(format: "label BEGINSWITH %@", "开始阅读《")
        ).firstMatch
        XCTAssertTrue(startReading.waitForExistence(timeout: 20), "真实书籍订阅未成功。")
        attachScreenshot(named: "03-test-book-subscribed")
        startReading.tap()

        let progress = app.staticTexts.matching(
            NSPredicate(format: "label BEGINSWITH %@ AND label CONTAINS %@", "第 ", "已读 ")
        ).firstMatch
        XCTAssertTrue(progress.waitForExistence(timeout: 20), "真实书籍正文未加载。")
        let readingScroll = app.scrollViews.firstMatch
        for _ in 0..<5 { readingScroll.swipeUp() }
        let positiveProgress = app.staticTexts.matching(
            NSPredicate(format: "label BEGINSWITH %@ AND NOT label CONTAINS %@", "第 ", "已读 0%")
        ).firstMatch
        XCTAssertTrue(positiveProgress.waitForExistence(timeout: 20), "阅读进度未前进。")
        XCTAssertFalse(app.buttons["阅读进度未同步，点按重试。"].exists)
        attachScreenshot(named: "04-production-book-body-and-progress")

        app.buttons["返回书籍概述"].tap()
        let askChat = app.buttons["围绕本期向 Chat 提问"]
        for _ in 0..<6 where !askChat.isHittable { app.scrollViews.firstMatch.swipeUp() }
        XCTAssertTrue(askChat.waitForExistence(timeout: 10))
        askChat.tap()

        let input = app.textFields.firstMatch
        XCTAssertTrue(input.waitForExistence(timeout: 12))
        input.tap()
        input.typeKey("a", modifierFlags: .command)
        input.typeText(realModelPrompt)
        app.buttons["发送消息"].tap()

        XCTAssertTrue(app.staticTexts[realModelPrompt].waitForExistence(timeout: 10))
        let realModelResponse = app.staticTexts.matching(
            NSPredicate(format: "label CONTAINS %@", realModelToken)
        ).firstMatch
        XCTAssertTrue(realModelResponse.waitForExistence(timeout: 180), "选书 Chat 未返回真实模型验收 token。")
        attachScreenshot(named: "05-selected-book-chat-real-model-response")
    }

    private func attachScreenshot(named name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
