from pathlib import Path
import os
import subprocess

import yaml


UPDATE_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update.sh"
SYSTEMD_DIR = UPDATE_SCRIPT.parents[1] / "ops" / "systemd"
BRIDGE_SCRIPT = UPDATE_SCRIPT.parents[1] / "scripts" / "hermes_bridge.py"

HERMES_ACCOUNT_HOME = "/var/lib/quantumn-hermes"
HERMES_HOME = f"{HERMES_ACCOUNT_HOME}/.hermes"
HERMES_AGENT_ROOT = f"{HERMES_HOME}/hermes-agent"
HERMES_PYTHON = f"{HERMES_AGENT_ROOT}/venv/bin/python"
HERMES_LAUNCHER = f"{HERMES_ACCOUNT_HOME}/.local/bin/hermes"
BRIDGE_WORKER_PYTHON = f"{HERMES_ACCOUNT_HOME}/bridge-worker-venv/bin/python"


def test_server_deploy_pins_cloud_agent_os_mode_and_refreshes_runtime() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")

    assert "Environment=AI_LAB_AGENT_OS_MODE=cloud_multi_tenant" in script
    for unit in (
        "hermes-serve.service",
        "hermes-serve-forward.service",
        "hermes-gateway.service",
        "hermes-bridge.service",
    ):
        assert f"systemctl restart {unit}" in script


def test_server_deploy_does_not_manage_periodic_tasks() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8").casefold()

    forbidden = ("crontab", "cronjob", "systemctl start cron", "systemctl enable cron")
    assert not any(command in script for command in forbidden)


def test_server_deploy_prepares_private_red_and_public_green_projection_roots() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    assert 'install -d -o quantumn-hermes -g quantumn-hermes -m 0700 "$VAULT_ROOT/wiki/tenant"' in script
    assert 'install -d -o quantumn-hermes -g quantumn-hermes -m 0755 "$VAULT_ROOT/wiki/contributions"' in script


def test_server_deploy_rechecks_private_note_write_access_after_runtime_restart() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    restart = script.index("restart_hermes_runtime\n", script.index("SWITCHED=1"))
    second_repair = script.index("repair_user_note_permissions.py", restart)
    write_probe = script.index(".api-write-probe-", second_repair)
    final_health = script.index('echo "==> [6/6] 最终健康检查"', write_probe)
    assert restart < second_repair < write_probe < final_health


def test_server_deploy_repairs_durable_store_directory_and_probes_api_write_access() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    assert 'repair_runtime_store_permissions "$DATA_TARGET"' in script
    assert 'chmod 0755 "$RELEASE_DIR"' in script
    assert 'chmod 0600 "$path"' in script
    assert 'data_probe=pathlib.Path(tempfile.mkdtemp' in script


def test_hermes_units_share_hardened_unprivileged_runtime_contract() -> None:
    for name in ("hermes-bridge.service", "hermes-chat-worker.service"):
        unit = (SYSTEMD_DIR / name).read_text(encoding="utf-8")
        for contract in (
            "User=quantumn-hermes",
            "Group=quantumn-hermes",
            "WorkingDirectory=/opt/ai-lab-platform",
            "EnvironmentFile=/opt/ai-lab-platform/.env",
            f"Environment=HOME={HERMES_ACCOUNT_HOME}",
            f"Environment=HERMES_HOME={HERMES_HOME}",
            f"Environment=HERMES_AGENT_ROOT={HERMES_AGENT_ROOT}",
            f"Environment=HERMES_BIN={HERMES_LAUNCHER}",
            "Environment=HERMES_FAST_CHAT_MODEL=gpt-5.6-sol",
            "Environment=AI_LAB_AGENT_OS_MODE=cloud_multi_tenant",
            "Environment=HERMES_CHAT_RUN_DB=/opt/ai-lab-platform/data/hermes_chat_runs.sqlite3",
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "ProtectSystem=strict",
            "ReadWritePaths=/opt/ai-lab-platform/data /var/lib/quantumn-hermes/.hermes",
        ):
            assert contract in unit
        assert f"ExecStart={BRIDGE_WORKER_PYTHON}" in unit
        assert "PROVIDER=" not in unit
        assert "/opt/hermes" not in unit
        assert "127.0.0.1:7890" not in unit
        for proxy_variable in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
            assert f"Environment={proxy_variable}=" not in unit
    bridge = (SYSTEMD_DIR / "hermes-bridge.service").read_text(encoding="utf-8")
    worker = (SYSTEMD_DIR / "hermes-chat-worker.service").read_text(encoding="utf-8")
    assert "chat_run_worker" not in bridge
    assert "scripts.chat_run_worker" in worker
    assert "EnvironmentFile=/etc/ai-lab-platform/hermes-bridge.env" in bridge
    assert "--host" not in bridge
    assert "127.0.0.1" not in bridge


def test_compose_callers_share_the_docker_host_gateway_bridge_contract() -> None:
    compose = yaml.safe_load((UPDATE_SCRIPT.parents[1] / "docker-compose.yml").read_text(encoding="utf-8"))
    for name in ("api", "workflow-worker", "planning-worker", "agent-evaluation-worker"):
        service = compose["services"][name]
        assert service["environment"]["HERMES_BRIDGE_URL"] == (
            "${HERMES_BRIDGE_URL:-http://host.docker.internal:9118/v1/chat}"
        )
        assert "host.docker.internal:host-gateway" in service["extra_hosts"]


def test_runtime_scripts_use_the_official_dedicated_user_install() -> None:
    bridge = BRIDGE_SCRIPT.read_text(encoding="utf-8")
    update = UPDATE_SCRIPT.read_text(encoding="utf-8")

    assert HERMES_LAUNCHER in bridge
    assert "/opt/hermes" not in bridge
    for contract in (
        "HERMES_ACCOUNT_HOME=/var/lib/quantumn-hermes",
        'HERMES_HOME="$HERMES_ACCOUNT_HOME/.hermes"',
        'HERMES_AGENT_ROOT="$HERMES_HOME/hermes-agent"',
        'HERMES_PYTHON="$HERMES_AGENT_ROOT/venv/bin/python"',
        'HERMES_LAUNCHER="$HERMES_ACCOUNT_HOME/.local/bin/hermes"',
        "HERMES_RUNTIME_VERSION=0.21.1",
        'BRIDGE_WORKER_VENV_LINK="$HERMES_ACCOUNT_HOME/bridge-worker-venv"',
        "prepare_bridge_worker_venv",
        "activate_bridge_worker_venv",
        '--require-hashes --no-build-isolation -r "$release_dir/requirements.lock"',
        '--require-hashes --no-build-isolation -r "$release_dir/requirements-bridge-worker.lock"',
        '--no-deps --no-build-isolation --editable "$HERMES_AGENT_ROOT"',
        'version("hermes-agent") == os.environ["HERMES_RUNTIME_VERSION"]',
        "verify_hermes_install",
        "configure_hermes_bridge_network",
        "verify_hermes_bridge_unit",
    ):
        assert contract in update
    assert "/opt/hermes" not in update
    assert '"$HERMES_PYTHON" -m pip install' not in update
    assert "127.0.0.1:7890" not in update
    for proxy_variable in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        assert proxy_variable not in update


def test_bridge_binding_uses_the_local_private_docker_host_gateway() -> None:
    bridge = BRIDGE_SCRIPT.read_text(encoding="utf-8")
    update = UPDATE_SCRIPT.read_text(encoding="utf-8")

    assert 'os.environ.get("HERMES_BRIDGE_BIND_ADDRESS", "")' in bridge
    assert 'bind_address = _private_bridge_bind_address()' in bridge
    assert 'host=bind_address' in bridge
    assert 'host="0.0.0.0"' not in bridge
    assert 'socket.gethostbyname("host.docker.internal")' in update
    assert 'ip -4 -o addr show' in update
    assert 'http://$HERMES_BRIDGE_BIND_ADDRESS:9118/health' in update
    assert "urllib.request.urlopen('http://$HERMES_BRIDGE_BIND_ADDRESS:9118/health'" in update

    command = f'''source "{UPDATE_SCRIPT}"
docker() {{ printf '%s\\n' 172.17.0.1; }}
ip() {{ printf '%s\\n' '2: docker0 inet 172.17.0.1/16 brd 172.17.255.255 scope global docker0'; }}
resolve_hermes_bridge_bind_address
'''
    result = subprocess.run(
        ["bash", "-c", command],
        env={
            **os.environ,
            "AI_LAB_UPDATE_LIBRARY_ONLY": "1",
            "COMPOSE_PROJECT": "contract-test",
        },
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "172.17.0.1"


def test_bridge_binding_fails_closed_for_public_or_unassigned_addresses() -> None:
    for gateway, host_addresses in (
        ("203.0.113.10", "203.0.113.10/24"),
        ("172.17.0.1", "192.168.1.10/24"),
    ):
        command = f'''source "{UPDATE_SCRIPT}"
docker() {{ printf '%s\\n' {gateway}; }}
ip() {{ printf '%s\\n' '2: eth0 inet {host_addresses} brd 192.168.1.255 scope global eth0'; }}
resolve_hermes_bridge_bind_address
'''
        result = subprocess.run(
            ["bash", "-c", command],
            env={
                **os.environ,
                "AI_LAB_UPDATE_LIBRARY_ONLY": "1",
                "COMPOSE_PROJECT": "contract-test",
            },
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0


def test_bridge_install_rejects_effective_systemd_runtime_overrides() -> None:
    for bridge_effective, worker_effective, expected in (
        (
            f"{BRIDGE_WORKER_PYTHON} scripts/hermes_bridge.py",
            f"{BRIDGE_WORKER_PYTHON} -m scripts.chat_run_worker",
            0,
        ),
        (
            f"{BRIDGE_WORKER_PYTHON} -m uvicorn scripts.hermes_bridge:app --host 127.0.0.1 --port 9118",
            f"{BRIDGE_WORKER_PYTHON} -m scripts.chat_run_worker",
            1,
        ),
        (
            f"{BRIDGE_WORKER_PYTHON} scripts/hermes_bridge.py",
            f"{HERMES_PYTHON} -m scripts.chat_run_worker",
            1,
        ),
    ):
        command = f'''source "{UPDATE_SCRIPT}"
systemctl() {{
  case "$2" in
    hermes-bridge.service) printf '%s\\n' '{bridge_effective}' ;;
    hermes-chat-worker.service) printf '%s\\n' '{worker_effective}' ;;
  esac
}}
verify_hermes_bridge_unit
'''
        result = subprocess.run(
            ["bash", "-c", command],
            env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
            capture_output=True,
            text=True,
        )
        assert result.returncode == expected


def test_bridge_worker_venv_is_atomic_and_rollback_coupled() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")

    assert 'BRIDGE_WORKER_VENV_ROOT="$HERMES_ACCOUNT_HOME/bridge-worker-venvs"' in script
    assert '"$release_dir/requirements-bridge-worker.lock"' in script
    assert 'printf \'%s\\0\' "$HERMES_RUNTIME_VERSION"' in script
    assert 'chown quantumn-hermes:quantumn-hermes "$temp_dir"' in script
    assert 'mv -Tf "$next_link" "$BRIDGE_WORKER_VENV_LINK"' in script
    assert 'mv -Tf "$rollback_venv_link" "$BRIDGE_WORKER_VENV_LINK"' in script


def test_server_deploy_installs_units_without_starting_them_during_quarantine() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    install = script.index("install_hermes_units\n", script.index("SWITCHED=1"))
    restart = script.index("restart_hermes_runtime\n", install)
    assert install < restart
    assert "systemctl enable" not in script
    result = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{UPDATE_SCRIPT}"; systemctl() {{ echo unexpected-systemctl; }}; restart_hermes_runtime',
        ],
        env={"AI_LAB_UPDATE_LIBRARY_ONLY": "1", "AI_LAB_HERMES_QUARANTINED": "1"},
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "hermes_restart_status=skipped_quarantined"
