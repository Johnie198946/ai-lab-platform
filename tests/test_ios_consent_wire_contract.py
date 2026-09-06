"""Exercise the unified iOS agreement DTO through Foundation's JSONEncoder."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_ios_unified_agreement_encoder_uses_backend_keys(tmp_path):
    swift = shutil.which("swift")
    if swift is None:
        pytest.skip("Swift SDK is required for the Foundation wire-contract check")
    root = Path(__file__).resolve().parents[1]
    source = (root / "ios/AIPlatformApp/Networking/APIClient.swift").read_text()
    start = source.index("public struct AgreementAcceptanceBody:")
    end = source.index("\npublic struct ", start + 1)
    script = tmp_path / "agreement-wire.swift"
    script.write_text(
        "import Foundation\n" + source[start:end] + '''
private let body = AgreementAcceptanceBody(
    agreementVersion: "contract-test",
    idempotencyKey: "00000000-0000-0000-0000-000000000001"
)
let data = try JSONEncoder().encode(body)
let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]
assert(Set(json.keys) == Set([
    "agreement_version", "idempotency_key", "source"
]))
assert(json["agreement_version"] as? String == "contract-test")
assert(json["idempotency_key"] as? String == "00000000-0000-0000-0000-000000000001")
assert(json["source"] as? String == "ios")
assert(json["knowledge_contribution_enabled"] == nil)
print("iOS unified agreement Foundation encoding verified")
'''
    )
    result = subprocess.run([swift, str(script)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "encoding verified" in result.stdout
