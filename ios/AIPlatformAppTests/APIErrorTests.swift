import XCTest
@testable import AIPlatformApp

final class APIErrorTests: XCTestCase {
    func testPublicAuthentication401PreservesBackendReason() throws {
        let body = try JSONSerialization.data(withJSONObject: [
            "detail": "登录票据无效或已过期"
        ])

        let error = APIError.fromHTTP(statusCode: 401, body: body)

        XCTAssertEqual(error.localizedDescription, "登录票据无效或已过期")
    }

    func testNonAuthenticationErrorExtractsFastAPIDetail() throws {
        let body = try JSONSerialization.data(withJSONObject: [
            "detail": "支付宝登录尚未配置"
        ])

        let error = APIError.fromHTTP(statusCode: 503, body: body)

        XCTAssertEqual(error.localizedDescription, "服务端正在更新或繁忙，请稍后重试（503）")
    }
}
