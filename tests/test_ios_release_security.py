from __future__ import annotations

import plistlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ios_release_does_not_allow_arbitrary_network_loads() -> None:
    with (ROOT / "ios/AIPlatformApp/Info.plist").open("rb") as handle:
        info = plistlib.load(handle)

    assert info.get("NSAppTransportSecurity", {}).get("NSAllowsArbitraryLoads") is not True
