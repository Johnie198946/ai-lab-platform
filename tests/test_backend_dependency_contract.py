"""Release inputs must stay compatible with the reviewed hashed lock."""
from pathlib import Path
import re

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]


def test_deployment_lock_covers_direct_requirements_and_bootstrap():
    for source, lock in [('requirements.txt', 'requirements.lock'), ('requirements-build.in', 'requirements-build.lock')]:
        locked = {}
        text = (ROOT / lock).read_text()
        for block in re.split(r'\n(?=[a-zA-Z])', text):
            match = re.search(r'^([\w.-]+)==([^\s]+) \\', block, re.M)
            if match:
                name, version = match.groups()
                locked[name.lower().replace('_', '-')] = version
                assert re.search(r'--hash=sha256:[a-f0-9]{64}', block)
        assert locked
        for line in (ROOT / source).read_text().splitlines():
            if not line.strip() or line.startswith('#'):
                continue
            requirement = Requirement(line)
            assert locked[requirement.name.lower().replace('_', '-')] in requirement.specifier


def test_docker_consumes_hash_locks_and_pinned_python_not_floating_input():
    dockerfile = (ROOT / 'backend/Dockerfile').read_text()
    assert re.search(r'FROM python:3\.12\.\d+-slim-bookworm@sha256:[a-f0-9]{64}', dockerfile)
    assert '--require-hashes -r requirements-build.lock' in dockerfile
    assert '--require-hashes --no-build-isolation -r requirements.lock' in dockerfile
    assert 'python -m pip check' in dockerfile
    assert '-r requirements.txt' not in dockerfile
