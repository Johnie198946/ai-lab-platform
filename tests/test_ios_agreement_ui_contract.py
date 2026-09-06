from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOGIN = ROOT / "ios/AIPlatformApp/Views/Auth/LoginView.swift"
SHEET = ROOT / "ios/AIPlatformApp/Views/Auth/AgreementSheet.swift"


def test_login_uses_one_unframed_unified_agreement_row():
    source = LOGIN.read_text(encoding="utf-8")
    footer = source.split("private var footerTermsSection", 1)[1].split(
        "private var isCurrentAgreementAccepted", 1
    )[0]
    assert 'Text("我已阅读")' in footer
    assert 'Text("服务协议")' in footer
    assert '.foregroundColor(AppTheme.Colors.primary)' in footer
    assert '.frame(width: 44, height: 44)' in footer
    assert '.frame(minWidth: 44, minHeight: 44)' in footer
    assert '.contentShape(Rectangle())' in footer
    assert "Toggle(" not in footer
    assert "DisclosureGroup(" not in footer
    assert "参与知识共建" not in footer
    assert ".background(" not in footer
    assert ".overlay" not in footer


def test_agreement_sheet_is_one_continuous_selection_free_scroll_view():
    source = SHEET.read_text(encoding="utf-8")
    assert source.count("ScrollView {") == 1
    assert "safeAreaInset(edge: .bottom" in source
    assert 'Text("我已阅读并同意全部协议")' in source
    assert '.background(AppTheme.Colors.surfaceTint, in: Circle())' in source
    assert '.accessibilityElement(children: .combine)' in source
    assert source.count("onAccept") == 2
    assert "Button(action: onAccept)" in source
    for identifier in (
        "agreement.title",
        "agreement.version",
        "agreement.chapter.\\(index + 1)",
        "agreement.cta",
        "agreement.close",
    ):
        assert identifier in source
    assert '.frame(maxWidth: AppTheme.Metrics.readableContentWidth)' in source
    for forbidden in ("Toggle(", "DisclosureGroup(", "TabView(", "checkbox"):
        assert forbidden not in source


def test_native_sheet_uses_shared_scrim_and_partial_full_detents():
    login = LOGIN.read_text(encoding="utf-8")
    root = (ROOT / "ios/AIPlatformApp/AIPlatformApp.swift").read_text(encoding="utf-8")
    for source in (login, root):
        assert "AppTheme.Colors.scrim" in source
        assert ".presentationDetents([.medium, .large])" in source
        assert ".presentationBackgroundInteraction(.disabled)" in source
        assert ".presentationBackgroundInteraction(.enabled" not in source
    assert login.count("acceptCurrentAgreement") == 2
    assert root.count("acceptRequiredAgreement") == 2


def test_all_login_channels_share_unified_authenticated_completion():
    source = LOGIN.read_text(encoding="utf-8")
    assert "fetchKnowledgeContributionConsent" not in source
    assert "updateKnowledgeContributionConsent" not in source
    assert "private func executePendingAuth" in source
    assert source.count("private func completeAuthenticatedLogin") == 1
    assert "APIClient.shared.clearToken()" not in source
    settings = (ROOT / "ios/AIPlatformApp/Views/Settings/SettingsView.swift").read_text(
        encoding="utf-8"
    )
    assert "knowledgeContributionCard" not in settings
    assert "updateKnowledgeContributionConsent" not in settings


def test_new_ios_has_one_agreement_contract_and_no_legacy_contribution_endpoint():
    source = (ROOT / "ios/AIPlatformApp/Networking/APIClient.swift").read_text(encoding="utf-8")
    assert 'clientContract = "ios-unified-agreement-v1"' in source
    assert source.count('forHTTPHeaderField: "Authorization"') == 1
    assert "X-Agreement-Contract" not in source
    assert "KnowledgeContributionConsentDTO" not in source
    assert 'path: "knowledge-contribution/me"' not in source


def test_keychain_update_does_not_delete_existing_credential_before_save():
    source = (ROOT / "ios/AIPlatformApp/Networking/APIClient.swift").read_text(encoding="utf-8")
    save = source.split("public static func save(_ value: String)", 1)[1].split(
        "public static func load()", 1
    )[0]
    assert "SecItemAdd" in save
    assert "SecItemUpdate" in save
    assert "SecItemDelete" not in save
    assert "UserDefaults.standard.set" not in save
