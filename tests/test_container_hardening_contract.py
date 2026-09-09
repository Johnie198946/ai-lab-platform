from pathlib import Path
import json
import os
import re
import subprocess

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


def test_infrastructure_wrappers_are_exact_non_root_and_healthy() -> None:
    postgres = _dockerfile("infrastructure/postgres/Dockerfile")
    redis = _dockerfile("infrastructure/redis/Dockerfile")

    assert postgres.startswith(
        "FROM postgres@sha256:"
        "075f7ba66bc9b3ce7d6b8b635208ff61cd7cf1a67d71ec530eec5d7ae0cbe571\n"
    )
    assert redis.startswith(
        "FROM redis@sha256:"
        "1db42ccef14898aa29bae778452d567534b59c107129cbc1163fb552de184d3c\n"
    )
    assert re.findall(r"^RUN apk add --no-cache (.+?) \\$", postgres, re.MULTILINE) == [
        "libcrypto3=3.5.8-r0 libssl3=3.5.8-r0 libuuid=2.42.3-r1"
    ]
    assert not re.search(r"\b(?:libcrypto3|libssl3|libuuid)(?=\s|\\|$)", postgres)
    assert "apk upgrade" not in postgres + redis
    assert "rm -f /usr/local/bin/gosu" in postgres
    assert "USER postgres" in postgres
    assert 'pg_isready -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-postgres}"' in postgres
    assert "USER redis" in redis
    assert 'CMD ["sh", "-c", "REDISCLI_AUTH=\\"$REDIS_PASSWORD\\" redis-cli ping"]' in redis
    assert 'CMD ["CMD-SHELL",' not in redis
    assert not re.search(r"REDISCLI_AUTH=\s", redis)
    assert "HEALTHCHECK" in postgres
    assert "HEALTHCHECK" in redis
    assert "ENTRYPOINT" not in postgres + redis
    assert not re.search(r"^CMD ", postgres + redis, re.MULTILINE)


def test_current_image_vulnerability_blockers_are_fixed() -> None:
    node_image = (
        "node:22.23.2-alpine3.23@sha256:"
        "46825fbbd4e996a78b7a2cdc08d75e38a5a505bdab95dcda55605359bf124bc6"
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
    assert "RUN apk add --no-cache libcrypto3=3.5.8-r0 libssl3=3.5.8-r0 \\" in runtime
    assert not re.search(r"\b(?:libcrypto3|libssl3)(?=\s|\\|$)", runtime)
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


def test_frontend_tls_files_are_untracked_and_require_explicit_host_paths() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    tracked_keys = subprocess.run(
        ["git", "ls-files", "--", "frontend/nginx/*.key"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    assert all(not (ROOT / path).exists() for path in tracked_keys)
    assert "/frontend/nginx/*.key" in gitignore
    assert (
        "${AI_LAB_TLS_CERT_FILE:?Set a non-empty AI_LAB_TLS_CERT_FILE to the host TLS certificate path}"
        in compose
    )
    assert (
        "${AI_LAB_TLS_KEY_FILE:?Set a non-empty AI_LAB_TLS_KEY_FILE to the host TLS private key path}"
        in compose
    )
    assert "./frontend/nginx/ailab.crt" not in compose
    assert "./frontend/nginx/ailab.key" not in compose
    assert "AI_LAB_TLS_CERT_FILE=/path/to/tls/fullchain.pem" in env_example
    assert "AI_LAB_TLS_KEY_FILE=/path/to/tls/privkey.pem" in env_example


def test_compose_preserves_storage_tls_routes_and_non_root_users() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert services["postgres"]["image"] == (
        "${AI_LAB_POSTGRES_IMAGE:-ai-lab-platform-postgres:offline}"
    )
    assert services["redis"]["image"] == (
        "${AI_LAB_REDIS_IMAGE:-ai-lab-platform-redis:offline}"
    )
    assert services["postgres"]["build"] == {
        "context": "./infrastructure/postgres",
        "dockerfile": "Dockerfile",
    }
    assert services["redis"]["build"] == {
        "context": "./infrastructure/redis",
        "dockerfile": "Dockerfile",
    }
    assert "postgres:16-alpine" not in (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "redis:7-alpine" not in (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for name, binding in (("postgres", "127.0.0.1:5432:5432"), ("redis", "127.0.0.1:6379:6379")):
        assert services[name]["ports"] == [binding]
    assert services["postgres"]["healthcheck"]["test"][0] == "CMD-SHELL"
    assert services["postgres"]["healthcheck"]["interval"] == "5s"
    assert services["postgres"]["healthcheck"]["timeout"] == "3s"
    assert services["postgres"]["healthcheck"]["retries"] == 10
    assert "healthcheck" not in services["redis"]

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


def test_rendered_compose_uses_redis_image_healthcheck_without_embedding_its_secret() -> None:
    rendered = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=ROOT,
        env={
            **os.environ,
            "REDIS_PASSWORD": "0123456789abcdef0123456789abcdef",
            "HERMES_BRIDGE_INTERNAL_TOKEN": "dummy-internal-token",
            "AUTHEN_JWT_SECRET": "0123456789abcdef0123456789abcdef",
            "AUTHEN_JWT_ISSUER": "contract-issuer",
            "AUTHEN_JWT_AUDIENCE": "contract-audience",
            "AUTHEN_JWT_STRICT_PROVENANCE": "true",
            "AI_LAB_TLS_CERT_FILE": "/tmp/dummy.crt",
            "AI_LAB_TLS_KEY_FILE": "/tmp/dummy.key",
        },
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    redis = json.loads(rendered)["services"]["redis"]

    assert "healthcheck" not in redis
    assert "REDISCLI_AUTH" not in json.dumps(redis)


def test_production_jwt_provenance_configuration_fails_closed() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    api = compose["services"]["api"]
    required = {
        "AUTHEN_JWT_SECRET": (
            "${AUTHEN_JWT_SECRET:?Set a non-empty AUTHEN_JWT_SECRET in .env}"
        ),
        "AUTHEN_JWT_ISSUER": "${AUTHEN_JWT_ISSUER:?Set a non-empty AUTHEN_JWT_ISSUER in .env}",
        "AUTHEN_JWT_AUDIENCE": "${AUTHEN_JWT_AUDIENCE:?Set a non-empty AUTHEN_JWT_AUDIENCE in .env}",
        "AUTHEN_JWT_STRICT_PROVENANCE": (
            "${AUTHEN_JWT_STRICT_PROVENANCE:?Set AUTHEN_JWT_STRICT_PROVENANCE=true in .env}"
        ),
    }
    assert {name: api["environment"][name] for name in required} == required

    valid_env = {
        **os.environ,
        "REDIS_PASSWORD": "0123456789abcdef0123456789abcdef",
        "HERMES_BRIDGE_INTERNAL_TOKEN": "dummy-internal-token",
        "AI_LAB_TLS_CERT_FILE": "/tmp/dummy.crt",
        "AI_LAB_TLS_KEY_FILE": "/tmp/dummy.key",
        "AUTHEN_JWT_SECRET": "0123456789abcdef0123456789abcdef",
        "AUTHEN_JWT_ISSUER": "contract-issuer",
        "AUTHEN_JWT_AUDIENCE": "contract-audience",
        "AUTHEN_JWT_STRICT_PROVENANCE": "true",
    }
    for name in required:
        for value in (None, ""):
            env = dict(valid_env)
            if value is None:
                env.pop(name, None)
            else:
                env[name] = value
            result = subprocess.run(
                ["docker", "compose", "--env-file", "/dev/null", "config"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
            )
            assert result.returncode != 0
            assert name in result.stderr

    command = api["command"]
    assert command[:2] == ["/bin/sh", "-c"]
    assert '[ "$${#AUTHEN_JWT_SECRET}" -lt 32 ]' in command[2]
    assert 'case "$$AUTHEN_JWT_ISSUER" in' in command[2]
    assert 'case "$$AUTHEN_JWT_AUDIENCE" in' in command[2]
    assert '[ "$$AUTHEN_JWT_STRICT_PROVENANCE" = true ]' in command[2]
    preflight = command[2].split("exec uvicorn", 1)[0].replace("$$", "$") + "exit 0\n"
    assert subprocess.run(
        [*command[:2], preflight],
        cwd=ROOT,
        env=valid_env,
        capture_output=True,
        text=True,
        timeout=3,
    ).returncode == 0
    invalid_startup = (
        ("AUTHEN_JWT_SECRET", None, "AUTHEN_JWT_SECRET must be at least 32 characters"),
        ("AUTHEN_JWT_SECRET", "", "AUTHEN_JWT_SECRET must be at least 32 characters"),
        ("AUTHEN_JWT_SECRET", "short", "AUTHEN_JWT_SECRET must be at least 32 characters"),
        ("AUTHEN_JWT_ISSUER", " \t", "AUTHEN_JWT_ISSUER must contain a non-whitespace character"),
        ("AUTHEN_JWT_AUDIENCE", "\n", "AUTHEN_JWT_AUDIENCE must contain a non-whitespace character"),
        ("AUTHEN_JWT_STRICT_PROVENANCE", "false", "AUTHEN_JWT_STRICT_PROVENANCE must be literal true"),
        ("AUTHEN_JWT_STRICT_PROVENANCE", "TRUE", "AUTHEN_JWT_STRICT_PROVENANCE must be literal true"),
        ("AUTHEN_JWT_STRICT_PROVENANCE", "1", "AUTHEN_JWT_STRICT_PROVENANCE must be literal true"),
        ("AUTHEN_JWT_STRICT_PROVENANCE", " true", "AUTHEN_JWT_STRICT_PROVENANCE must be literal true"),
        ("AUTHEN_JWT_STRICT_PROVENANCE", "true ", "AUTHEN_JWT_STRICT_PROVENANCE must be literal true"),
    )
    for name, value, error in invalid_startup:
        env = dict(valid_env)
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
        result = subprocess.run(
            [*command[:2], preflight],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=3,
        )
        assert result.returncode != 0
        assert result.stderr.strip() == f"ERROR: {error}"


def test_all_services_are_hardened_with_only_required_writable_storage() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    expected = {
        "postgres", "redis", "api", "workflow-worker", "planning-worker",
        "agent-evaluation-worker", "taskboard", "frontend",
    }
    assert set(services) == expected
    for name in expected:
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

    assert services["postgres"]["volumes"] == ["pgdata:/var/lib/postgresql/data"]
    assert services["postgres"]["tmpfs"] == [
        "/tmp:rw,noexec,nosuid,size=64m",
        "/var/run/postgresql:rw,noexec,nosuid,size=16m,uid=70,gid=70,mode=0775",
    ]
    assert not services["redis"].get("volumes")
    assert "redis" not in compose.get("volumes", {})
    assert services["redis"]["tmpfs"] == ["/tmp:rw,noexec,nosuid,size=16m"]
    redis_command = services["redis"]["command"][0]
    assert "save \"\"\\n" in redis_command
    assert "appendonly no\\n" in redis_command
    assert "dir /tmp\\n" in redis_command
    assert "exec redis-server /tmp/redis.conf" in redis_command


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
    assert 'ARG AI_LAB_RUNTIME_UID=10001' in dockerfile
    assert 'ARG AI_LAB_RUNTIME_GID=10001' in dockerfile
    assert 'addgroup -S -g "$AI_LAB_RUNTIME_GID" ailab' in dockerfile
    assert (
        'adduser -S -D -u "$AI_LAB_RUNTIME_UID" -G ailab '
        '-h /home/ailab -s /sbin/nologin ailab'
    ) in dockerfile
    assert "groupadd" not in dockerfile
    assert "useradd" not in dockerfile
    assert "HOME=/home/ailab" in dockerfile
    assert "USER ailab" in dockerfile
    assert 'verify_shared_data_access "$DATA_TARGET" "$API_RUNTIME_IMAGE" "$API_RUNTIME_UID"' in script


def test_deploy_repairs_existing_taskboard_volume() -> None:
    script = (ROOT / "scripts/update.sh").read_text(encoding="utf-8")

    helper = script[script.index("repair_taskboard_data_permissions() {"):script.index(
        "managed_compose_services() {"
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


def test_taskboard_openssl_vex_is_bound_to_the_deployed_tcp_runtime() -> None:
    node_image = (
        "node:22.23.2-alpine3.23@sha256:"
        "46825fbbd4e996a78b7a2cdc08d75e38a5a505bdab95dcda55605359bf124bc6"
    )
    vex = (ROOT / "ops/change-manifests/node-openssl-cve-2026-14456-vex.md").read_text(
        encoding="utf-8"
    )
    taskboard_dockerfile = _dockerfile("apps/dashi-taskboard/Dockerfile")
    entrypoint = _dockerfile("apps/dashi-taskboard/server/index.mjs")
    server = _dockerfile("apps/dashi-taskboard/server/app.mjs")
    taskboard = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))[
        "services"
    ]["taskboard"]

    assert re.findall(r"^FROM (\S+)", taskboard_dockerfile, re.MULTILINE) == [
        node_image,
        node_image,
    ]
    assert 'CMD ["node", "server/index.mjs"]' in taskboard_dockerfile
    assert re.findall(r"^EXPOSE (\S+)", taskboard_dockerfile, re.MULTILINE) == ["47823"]
    assert taskboard["environment"]["CODEX_TASKBOARD_PORT"] == 47823
    assert taskboard.get("ports", []) == []
    assert 'import { createServer } from "node:http";' in server
    forbidden_import = re.compile(
        r'(?:from\s+|import\s*\(\s*|require\(\s*)["\'](?:node:)?(?:quic|http3|dgram)["\']'
    )
    assert forbidden_import.search(entrypoint + server) is None
    assert node_image in vex
    assert "process.versions.openssl=3.5.7" in vex
    assert "https://openssl-library.org/news/secadv/20260813.txt" in vex
