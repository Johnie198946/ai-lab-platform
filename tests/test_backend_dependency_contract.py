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
    assert re.search(r'^pyjwt==2\.13\.0 \\$', api_lock, re.MULTILINE)
    assert not re.search(r'^(?:python-jose|ecdsa|rsa|pyasn1)==', api_lock, re.MULTILINE)
    assert 'sha256:7cec5b856506da6defb290f30c9ee687d5f5e8cb0bd3f6459dde43b0b4fa40ef' in api_lock
    assert 'sha256:1489e263a8048bb8b6a8bac662eb2d402ea5d2b7b4699b72f385f1e2772db105' in api_lock
    assert 'sha256:0dd2064cbc55aaec028ef5fbb60fa47bb6c3e7918e07ff17935284b227a9d2df' in api_lock
    assert 'sha256:e491916b378fba47242221bb9ead245211b70d504f495d105d17b14a24b4907c' in api_lock
    for dependency in ('firecrawl-anydoc', 'nemo-relay', 'snowballstemmer'):
        assert dependency in bridge_input
        assert f'{dependency}==' in bridge_lock


def test_docker_consumes_hash_locks_and_pinned_python_not_floating_input():
    dockerfile = (ROOT / 'backend/Dockerfile').read_text()
    assert re.findall(r'^FROM (\S+)', dockerfile, re.MULTILINE) == [
        'python:3.12.14-alpine3.23@sha256:'
        '167bc85084c9df34480efc26b4528fb68feaa8a79183b5658952137025b6f061'
    ]
    assert 'RUN apk add --no-cache libuuid=2.41.6-r1 \\' in dockerfile
    assert 'apk upgrade' not in dockerfile
    assert not re.search(r'\blibuuid(?=\s|\\|$)', dockerfile)
    assert '--require-hashes -r requirements-build.lock' in dockerfile
    assert '--require-hashes --no-build-isolation -r requirements.lock' in dockerfile
    assert 'requirements-bridge-worker' not in dockerfile
    assert 'python -m pip check' in dockerfile
    assert '-r requirements.txt' not in dockerfile
