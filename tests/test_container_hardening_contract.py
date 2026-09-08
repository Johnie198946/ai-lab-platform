from pathlib import Path
import json
import re

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _dockerfile(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_runtime_images_are_pinned_patched_non_root_and_healthy() -> None:
    dockerfiles = {
        "backend/Dockerfile": "ailab",
        "apps/dashi-taskboard/Dockerfile": "node",
        "frontend/Dockerfile": "nginx",
    }
    for path, user in dockerfiles.items():
        text = _dockerfile(path)
        assert re.search(r"^FROM .+@sha256:[a-f0-9]{64}", text, re.MULTILINE)
        assert "upgrade" in text
        assert f"USER {user}" in text
        assert "HEALTHCHECK" in text


def test_frontend_image_never_receives_or_copies_tls_private_keys() -> None:
    dockerfile = _dockerfile("frontend/Dockerfile")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert not re.search(r"^COPY .*\.(?:key|crt)\b", dockerfile, re.MULTILINE)
    assert "frontend/nginx/*.key" in dockerignore


def test_compose_preserves_storage_tls_routes_and_non_root_users() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    api_build_args = services["api"]["build"]["args"]
    assert api_build_args == {
        "AI_LAB_RUNTIME_UID": "${AI_LAB_RUNTIME_UID:-10001}",
        "AI_LAB_RUNTIME_GID": "${AI_LAB_RUNTIME_GID:-10001}",
    }
    assert "user" not in services["api"]
    assert services["taskboard"]["user"] == "1000:1000"
    assert services["frontend"]["user"] == "101:101"
    assert "./data:/app/data" in services["api"]["volumes"]
    assert "taskboard_data:/data" in services["taskboard"]["volumes"]
    assert "/opt/ai-lab-platform:/workspace:ro" in services["taskboard"]["volumes"]
    assert "443:443" in services["frontend"]["ports"]
    assert "127.0.0.1:9081:9081" in services["frontend"]["ports"]
    assert all(volume.endswith(":ro") for volume in services["frontend"]["volumes"])
    assert services["frontend"]["sysctls"]["net.ipv4.ip_unprivileged_port_start"] == "0"


def test_api_identity_and_host_owned_mounts_use_the_same_uid() -> None:
    script = (ROOT / "scripts/update.sh").read_text(encoding="utf-8")
    dockerfile = _dockerfile("backend/Dockerfile")

    assert 'export AI_LAB_RUNTIME_UID="$(id -u quantumn-hermes)"' in script
    assert 'export AI_LAB_RUNTIME_GID="$(id -g quantumn-hermes)"' in script
    assert 'groupadd --gid "$AI_LAB_RUNTIME_GID" ailab' in dockerfile
    assert 'useradd --uid "$AI_LAB_RUNTIME_UID" --gid ailab' in dockerfile
    assert "HOME=/home/ailab" in dockerfile
    assert "USER ailab" in dockerfile
    assert 'repair_runtime_store_permissions "$DATA_TARGET"' in script
    assert '--owner-uid "$AI_LAB_RUNTIME_UID" --owner-gid "$AI_LAB_RUNTIME_GID"' in script


def test_deploy_repairs_existing_taskboard_volume() -> None:
    script = (ROOT / "scripts/update.sh").read_text(encoding="utf-8")

    assert "--user 0 --entrypoint chown taskboard" in script
    assert "-R 1000:1000 /data" in script


def test_measured_language_findings_are_removed_from_runtime() -> None:
    requirements = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    bridge_requirements = (ROOT / "requirements-bridge-worker.lock").read_text(encoding="utf-8")
    build_requirements = (ROOT / "requirements-build.lock").read_text(encoding="utf-8")
    api_dockerfile = _dockerfile("backend/Dockerfile")
    taskboard_dockerfile = _dockerfile("apps/dashi-taskboard/Dockerfile")
    package_lock = json.loads(
        (ROOT / "apps/dashi-taskboard/package-lock.json").read_text(encoding="utf-8")
    )

    assert "cryptography==50.0.0" in requirements
    assert "hermes-agent==" not in requirements
    assert "cryptography==50.0.0" in bridge_requirements
    assert "hermes-agent==" not in bridge_requirements
    assert "pillow==12.3.0" in requirements
    assert "packaging==26.0" in build_requirements
    assert "wheel==0.46.2" in build_requirements
    assert "pip uninstall -y setuptools wheel" in api_dockerfile
    assert package_lock["packages"][""]["dependencies"]["js-yaml"] == "4.3.1"
    assert package_lock["packages"]["node_modules/js-yaml"]["version"] == "4.3.1"
    assert "rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack" in taskboard_dockerfile
