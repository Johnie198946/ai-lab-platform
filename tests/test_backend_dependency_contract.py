"""Release inputs must stay compatible with the reviewed hashed lock."""
from pathlib import Path
import re

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def test_deployment_lock_covers_direct_requirements_and_bootstrap():
    for source, lock in [
        ('requirements.txt', 'requirements.lock'),
        ('requirements-bridge-worker.in', 'requirements-bridge-worker.lock'),
        ('requirements-build.in', 'requirements-build.lock'),
    ]:
        locked = {}
        text = (ROOT / lock).read_text()
        for block in re.split(r'\n(?=[a-zA-Z])', text):
            first_line = block.splitlines()[0].removesuffix(' \\')
            try:
                locked_requirement = Requirement(first_line)
            except Exception:
                continue
            versions = [item.version for item in locked_requirement.specifier if item.operator == '==']
            if versions:
                locked[canonicalize_name(locked_requirement.name)] = versions[0]
                assert re.search(r'--hash=sha256:[a-f0-9]{64}', block)
        assert locked
        for line in (ROOT / source).read_text().splitlines():
            if not line.strip() or line.startswith('#'):
                continue
            requirement = Requirement(line)
            assert locked[canonicalize_name(requirement.name)] in requirement.specifier


def test_api_and_bridge_dependency_boundary_excludes_packaged_hermes():
    api_input = (ROOT / 'requirements.txt').read_text().casefold()
    api_lock = (ROOT / 'requirements.lock').read_text().casefold()
    bridge_input = (ROOT / 'requirements-bridge-worker.in').read_text().casefold()
    bridge_lock = (ROOT / 'requirements-bridge-worker.lock').read_text().casefold()

    assert 'hermes-agent' not in api_input
    assert 'hermes-agent==' not in api_lock
    assert 'hermes-agent==' not in bridge_input
    assert 'hermes-agent==' not in bridge_lock
    assert 'cryptography==50.0.0' in api_lock
    assert 'cryptography==50.0.0' in bridge_lock
    for dependency in ('firecrawl-anydoc', 'nemo-relay', 'snowballstemmer'):
        assert dependency in bridge_input
        assert f'{dependency}==' in bridge_lock


def test_docker_consumes_hash_locks_and_pinned_python_not_floating_input():
    dockerfile = (ROOT / 'backend/Dockerfile').read_text()
    assert re.search(r'FROM python:3\.12\.\d+-slim-bookworm@sha256:[a-f0-9]{64}', dockerfile)
    assert '--require-hashes -r requirements-build.lock' in dockerfile
    assert '--require-hashes --no-build-isolation -r requirements.lock' in dockerfile
    assert 'requirements-bridge-worker' not in dockerfile
    assert 'python -m pip check' in dockerfile
    assert '-r requirements.txt' not in dockerfile
