"""Exercise the actual iOS consent DTO through Foundation's JSONEncoder."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_ios_consent_encoder_uses_backend_keys(tmp_path):
    swift = shutil.which("swift")
    if swift is None:
        pytest.skip("Swift SDK is required for the Foundation wire-contract check")
    root = Path(__file__).resolve().parents[1]
    source = (root / "ios/AIPlatformApp/Networking/APIClient.swift").read_text()
    start = source.index("private struct KnowledgeContributionConsentWrite:")
    end = source.index("\npublic struct ", start)
    script = tmp_path / "consent-wire.swift"
    script.write_text(
        "import Foundation\n" + source[start:end] + '''
private let body = KnowledgeContributionConsentWrite(
    serviceAgreementAccepted: true,
    serviceAgreementVersion: "contract-test",
    participationEnabled: true
)
let data = try JSONEncoder().encode(body)
let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]
assert(Set(json.keys) == Set([
    "service_agreement_accepted", "service_agreement_version", "participation_enabled"
]))
assert(json["service_agreement_accepted"] as? Bool == true)
assert(json["service_agreement_version"] as? String == "contract-test")
assert(json["participation_enabled"] as? Bool == true)
print("iOS consent Foundation encoding verified")
'''
    )
    result = subprocess.run([swift, str(script)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "encoding verified" in result.stdout
