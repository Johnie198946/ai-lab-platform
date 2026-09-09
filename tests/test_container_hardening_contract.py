from pathlib import Path
import json
import re

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _dockerfile(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_runtime_images_are_pinned_reproducible_non_root_and_healthy() -> None:
    dockerfiles = {
        "backend/Dockerfile": "ailab",
        "apps/dashi-taskboard/Dockerfile": "node",
        "frontend/Dockerfile": "nginx",
    }
    for path, user in dockerfiles.items():
        text = _dockerfile(path)
        assert re.search(r"^FROM .+@sha256:[a-f0-9]{64}", text, re.MULTILINE)
        assert "apt-get upgrade" not in text
        assert "apk upgrade" not in text
        assert "registry.npmmirror.com" not in text
        assert f"USER {user}" in text
        assert "HEALTHCHECK" in text
    assert "registry.npmmirror.com" not in _dockerfile("frontend/package-lock.json")


def test_current_image_vulnerability_blockers_are_fixed() -> None:
    node_image = (
        "node:22.23.2-bookworm-slim@sha256:"
        "83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5"
    )
    taskboard = _dockerfile("apps/dashi-taskboard/Dockerfile")
    frontend = _dockerfile("frontend/Dockerfile")

    assert re.findall(r"^FROM (\S+)", taskboard, re.MULTILINE) == [node_image, node_image]
    assert frontend.startswith(
        "FROM node:22.23.2-alpine3.24@sha256:"
        "c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS build\n"
    )
    assert (
        "FROM nginxinc/nginx-unprivileged:1.30.4-alpine3.24@sha256:"
        "442753882674b49ae2c1de83ed67896131c0777f56df5005e356e62bc3f7e7ce"
        in frontend
    )
    assert "apt-get upgrade" not in taskboard + frontend
    assert "apk upgrade" not in taskboard + frontend

    runtime = taskboard.split(f"FROM {node_image}\n", 1)[1]
    assert "rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack" in runtime
    for link in ("npm", "npx", "corepack", "yarn", "yarnpkg", "pnpm", "pnpx"):
        assert f"/usr/local/bin/{link}" in runtime
    assert "USER node" in runtime
    assert "HEALTHCHECK" in runtime
    assert "wget" not in runtime
    assert "fetch('http://127.0.0.1:47823/api/meta')" in runtime
    assert "process.exit(r.ok?0:1)" in runtime


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
    assert services["taskboard"]["healthcheck"]["test"] == [
        "CMD", "node", "-e",
        "fetch('http://127.0.0.1:47823/api/meta').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))",
    ]
    assert "wget" not in str(services["taskboard"]["healthcheck"]["test"])
    assert "443:443" in services["frontend"]["ports"]
    assert "127.0.0.1:9081:9081" in services["frontend"]["ports"]
    assert all(volume.endswith(":ro") for volume in services["frontend"]["volumes"])
    assert services["frontend"]["sysctls"]["net.ipv4.ip_unprivileged_port_start"] == "0"


def test_application_services_are_read_only_and_do_not_mount_host_hermes_state() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    for name in (
        "api", "workflow-worker", "planning-worker",
        "agent-evaluation-worker", "taskboard", "frontend",
    ):
        service = services[name]
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert "cap_add" not in service
        assert "no-new-privileges:true" in service["security_opt"]
        assert service["tmpfs"]
        assert all("size=" in mount for mount in service["tmpfs"])
        assert service.get("healthcheck", {}).get("disable") is not True
        assert not any(
            "quantumn-hermes/.hermes" in volume
            for volume in service.get("volumes", [])
        )


def test_production_requires_bridge_secret_and_closes_public_hermes_socket_routes() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    required = "${HERMES_BRIDGE_INTERNAL_TOKEN:?Set a non-empty HERMES_BRIDGE_INTERNAL_TOKEN in .env}"
    for name in (
        "api", "workflow-worker", "planning-worker", "agent-evaluation-worker", "taskboard",
    ):
        assert compose["services"][name]["environment"]["HERMES_BRIDGE_INTERNAL_TOKEN"] == required
    nginx = _dockerfile("frontend/Dockerfile")
    assert nginx.count("location = /api/ws { return 404; }") == 2
    assert nginx.count("location = /api/pty { return 404; }") == 2


def test_production_cors_is_explicit_and_api_docs_are_disabled() -> None:
    main = (ROOT / "backend/main.py").read_text(encoding="utf-8")
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    assert compose["services"]["api"]["environment"]["AI_LAB_ENV"] == "production"
    assert 'origin.strip() != "*"' in main
    assert 'docs_url=None if _production else "/docs"' in main
    assert 'redoc_url=None if _production else "/redoc"' in main
    assert 'openapi_url=None if _production else "/openapi.json"' in main
    assert "allow_origins=_cors_origins if _production else [\"*\"]" in main


def test_api_identity_is_attested_and_shared_mount_access_uses_acl() -> None:
    script = (ROOT / "scripts/update.sh").read_text(encoding="utf-8")
    dockerfile = _dockerfile("backend/Dockerfile")

    assert "resolve_api_runtime_identity" in script
    assert 'configure_shared_data_acl "$DATA_TARGET" "$API_RUNTIME_UID" "$AI_LAB_RUNTIME_UID"' in script
    assert 'groupadd --gid "$AI_LAB_RUNTIME_GID" ailab' in dockerfile
    assert 'useradd --uid "$AI_LAB_RUNTIME_UID" --gid ailab' in dockerfile
    assert "HOME=/home/ailab" in dockerfile
    assert "USER ailab" in dockerfile
    assert 'verify_shared_data_access "$DATA_TARGET" "$API_RUNTIME_IMAGE" "$API_RUNTIME_UID"' in script


def test_deploy_repairs_existing_taskboard_volume() -> None:
    script = (ROOT / "scripts/update.sh").read_text(encoding="utf-8")

    helper = script[script.index("repair_taskboard_data_permissions() {"):script.index(
        "managed_unit_paths() {"
    )]
    for restriction in (
        'docker run --rm --pull never --network none --read-only',
        '--cap-drop ALL --cap-add CHOWN --security-opt no-new-privileges --user 0',
        '--mount "type=volume,src=$volume,dst=/data" --entrypoint chown "$image"',
        '-R 1000:1000 /data',
        'label=com.docker.compose.project=$COMPOSE_PROJECT',
        'label=com.docker.compose.volume=taskboard_data',
    ):
        assert restriction in helper
    assert "docker compose" not in helper[helper.index("docker run"):]
    assert "/var/run/docker.sock" not in helper
    assert "type=bind" not in helper
    deployment = script[script.index('echo "==> [3/6]'):]
    assert deployment.index("RUNTIME_CHANGED=1") < deployment.index(
        "repair_taskboard_data_permissions\n"
    ) < deployment.index('up -d --no-build --pull never')


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
    assert package_lock["packages"][""]["dependencies"]["js-yaml"] == "4.3.2"
    assert package_lock["packages"]["node_modules/js-yaml"]["version"] == "4.3.2"
    assert "rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack" in taskboard_dockerfile
