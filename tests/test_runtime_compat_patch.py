"""The shipped compatibility patch must be accepted by Git's parser."""
from pathlib import Path
import subprocess


def test_native_runtime_patch_is_parseable():
    root = Path(__file__).resolve().parents[1]
    path = root / "ops/hermes-runtime-patches/0001-transform-output-task-scope.patch"
    result = subprocess.run(
        ["git", "apply", "--numstat", str(path)],
        cwd=root, capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == "2\t0\tagent/turn_finalizer.py"
