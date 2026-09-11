import os
from pathlib import Path
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/update.sh"


@pytest.mark.parametrize("mode", ["match", "drift", "missing", "invalid", "legacy"])
def test_deploy_current_release_cas(tmp_path, mode):
    source = SCRIPT.read_text()
    start = source.index("# Re-read the active release only after acquiring")
    stop = source.index("# End active-release CAS", start)
    assert source.index("if ! flock -n 9;") < start
    assert source.index('CURRENT_DIR="$(readlink -f "$APP_LINK")"') == source.index(
        'CURRENT_DIR="$(readlink -f "$APP_LINK")"', start
    )
    release = tmp_path / "release"
    release.mkdir()
    app = tmp_path / "app"
    app.symlink_to(release, target_is_directory=True)
    if mode != "missing":
        (release / ".deployed-sha").write_text("a" * 40 + "\n")
    expected = "b" * 40 if mode == "drift" else "bad" if mode == "invalid" else "a" * 40
    env = {**os.environ, "APP_LINK": str(app), "AI_LAB_EXPECTED_CURRENT_SHA": expected}
    if mode == "legacy":
        env.pop("AI_LAB_EXPECTED_CURRENT_SHA")
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    result = subprocess.run(["bash", "-c", "set -e\n" + source[start:stop]], env=env, capture_output=True, text=True)
    assert (result.returncode == 0) == (mode in {"match", "legacy"}), result.stderr
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == before
