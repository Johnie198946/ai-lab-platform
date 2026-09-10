from pathlib import Path
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile

import pytest
import yaml


UPDATE_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update.sh"
SYSTEMD_DIR = UPDATE_SCRIPT.parents[1] / "ops" / "systemd"
BRIDGE_SCRIPT = UPDATE_SCRIPT.parents[1] / "scripts" / "hermes_bridge.py"
EGRESS_TUNNEL_SCRIPT = UPDATE_SCRIPT.parents[1] / "ops" / "scripts" / "clash-verge-egress-tunnel.sh"

HERMES_ACCOUNT_HOME = "/var/lib/quantumn-hermes"
HERMES_HOME = f"{HERMES_ACCOUNT_HOME}/.hermes"
HERMES_AGENT_ROOT = f"{HERMES_HOME}/hermes-agent"
HERMES_PYTHON = f"{HERMES_AGENT_ROOT}/venv/bin/python"
HERMES_LAUNCHER = f"{HERMES_ACCOUNT_HOME}/.local/bin/hermes"
BRIDGE_WORKER_PYTHON = f"{HERMES_ACCOUNT_HOME}/bridge-worker-venv/bin/python"
RUNTIME_SHA256 = "72748da13197c1fb161e3afeef20a6a385ff24f2165e6e2758e47008e7faba4c"
CERTBOT_ARCHIVE_SHA256 = "c701b7929a9073d0b005ea7833f5f9ee38ac30f2805c0cf64aad683fb418a685"
MANAGED_COMPOSE_SERVICES = (
    "postgres", "redis", "api", "workflow-worker", "planning-worker",
    "agent-evaluation-worker", "taskboard", "frontend",
)
PRODUCTION_ROLLBACK_REFS = {
    "postgres": "postgres:16-alpine",
    "redis": "redis:7-alpine",
    **{
        service: f"ai-lab-platform-{service}"
        for service in MANAGED_COMPOSE_SERVICES[2:]
    },
}


def test_server_deploy_pins_cloud_agent_os_mode_and_refreshes_runtime() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")

    assert "Environment=AI_LAB_AGENT_OS_MODE=cloud_multi_tenant" in script
    for unit in (
        "hermes-serve.service",
        "hermes-serve-forward.service",
        "hermes-gateway.service",
        "hermes-bridge.service",
    ):
        assert unit in script
    assert 'if systemctl cat "$unit" >/dev/null 2>&1; then' in script
    assert 'systemctl restart "$unit" || return 1' in script
    assert 'hermes_restart_status=skipped_absent unit=$unit' in script
    restart_function = script[script.index("restart_hermes_runtime() {"):script.index(
        "repair_runtime_store_permissions() {"
    )]
    assert restart_function.rstrip().endswith("return 0\n}")


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
    acl_repair = script.index('configure_shared_data_acl "$DATA_TARGET"', second_repair)
    write_probe = script.index('verify_shared_data_access "$DATA_TARGET"', acl_repair)
    final_health = script.index('echo "==> [6/6] 最终健康检查"', write_probe)
    assert restart < second_repair < acl_repair < write_probe < final_health


def test_server_deploy_repairs_durable_store_directory_and_probes_api_write_access() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    assert 'repair_runtime_store_permissions "$DATA_TARGET"' in script
    assert 'repair_vault_runtime_permissions "$VAULT_ROOT"' in script
    assert 'repair_note_path_ancestors "$VAULT_ROOT"' in script
    assert 'chmod 0755 "$RELEASE_DIR"' in script
    assert 'chmod 0600 "$path"' in script
    assert 'local vault_root="$1" lock="$1/.incremental-compile.lock"' in script
    assert 'chmod 0600 "$lock"' in script
    assert 'for path in "$vault_root/raw" "$vault_root/raw/dialogues"' in script
    assert 'echo "ERROR: note path ancestor must be a real directory: $path"' in script
    assert 'verify_shared_data_access "$DATA_TARGET" "$API_RUNTIME_IMAGE" "$API_RUNTIME_UID"' in script


def test_server_deploy_repairs_knowledge_matrix_before_non_root_audit() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    repair = script.index('KNOWLEDGE_MATRIX_TARGET="$(readlink -f data/knowledge_matrix.json)"')
    chown = script.index('chown quantumn-hermes:quantumn-hermes "$KNOWLEDGE_MATRIX_TARGET"', repair)
    chmod = script.index('chmod 0640 "$KNOWLEDGE_MATRIX_TARGET"', chown)
    audit = script.index("python scripts/audit_runtime_contracts.py", chmod)
    assert repair < chown < chmod < audit


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


def test_optional_hermes_egress_is_file_only_and_not_inlined() -> None:
    for name in ("hermes-bridge.service", "hermes-chat-worker.service"):
        unit = (SYSTEMD_DIR / name).read_text(encoding="utf-8")
        assert unit.count("EnvironmentFile=-/etc/ai-lab-platform/hermes-egress.env") == 1
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
            assert f"Environment={key}=" not in unit


def _verify_egress_env(
    tmp_path: Path,
    content: str,
    metadata: str = "0:0:600:160",
    bridge: str = "172.18.0.1",
) -> subprocess.CompletedProcess[str]:
    env_file = tmp_path / "hermes-egress.env"
    env_file.write_text(content, encoding="utf-8")
    command = f'''source "{UPDATE_SCRIPT}"
stat() {{ printf '%s\n' '{metadata}'; }}
HERMES_EGRESS_ENV_FILE='{env_file}'
verify_hermes_egress_env '{bridge}'
'''
    return subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True,
        text=True,
    )


def test_hermes_egress_env_accepts_only_exact_metadata_and_loopback_contract(
    tmp_path: Path,
) -> None:
    valid = (
        "HTTPS_PROXY=http://127.0.0.1:17897\n"
        "HTTP_PROXY=http://127.0.0.1:17897\n"
        "NO_PROXY=localhost,127.0.0.1,172.18.0.1,::1\n"
    )
    result = _verify_egress_env(tmp_path, valid)
    assert result.returncode == 0, result.stderr
    for metadata in (
        "1:0:600:160", "0:1:600:160", "0:0:640:160", "0:0:600:0", "0:0:600:1025",
    ):
        assert _verify_egress_env(tmp_path, valid, metadata=metadata).returncode != 0

    env_file = tmp_path / "hermes-egress.env"
    env_file.unlink()
    env_file.symlink_to(tmp_path / "missing-target")
    result = subprocess.run(
        ["bash", "-c", f'''source "{UPDATE_SCRIPT}"
HERMES_EGRESS_ENV_FILE='{env_file}'
verify_hermes_egress_env 172.18.0.1
'''],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


@pytest.mark.parametrize(
    "content",
    (
        "HTTPS_PROXY=http://127.0.0.1:17897\nHTTP_PROXY=http://127.0.0.1:17897\nNO_PROXY=localhost,127.0.0.1,172.18.0.1\nALL_PROXY=http://127.0.0.1:17897\n",
        "HTTPS_PROXY=http://127.0.0.1:17897\nhttp_proxy=http://127.0.0.1:17897\nNO_PROXY=localhost,127.0.0.1,172.18.0.1\n",
        "HTTPS_PROXY=http://user:pass@127.0.0.1:17897\nHTTP_PROXY=http://127.0.0.1:17897\nNO_PROXY=localhost,127.0.0.1,172.18.0.1\n",
        "HTTPS_PROXY=http://192.0.2.1:17897\nHTTP_PROXY=http://127.0.0.1:17897\nNO_PROXY=localhost,127.0.0.1,172.18.0.1\n",
        "HTTPS_PROXY=http://127.0.0.1:7897\nHTTP_PROXY=http://127.0.0.1:17897\nNO_PROXY=localhost,127.0.0.1,172.18.0.1\n",
        "HTTPS_PROXY=http://127.0.0.1:17897\nHTTPS_PROXY=http://127.0.0.1:17897\nNO_PROXY=localhost,127.0.0.1,172.18.0.1\n",
        "HTTPS_PROXY=http://127.0.0.1:17897\nUNKNOWN=value\nNO_PROXY=localhost,127.0.0.1,172.18.0.1\n",
        "HTTPS_PROXY=http://127.0.0.1:17897\nHTTP_PROXY=http://127.0.0.1:17897\nNO_PROXY=localhost,127.0.0.1,$(id)\n",
    ),
)
def test_hermes_egress_env_rejects_unsafe_keys_values_and_expansion(
    tmp_path: Path, content: str,
) -> None:
    assert _verify_egress_env(tmp_path, content).returncode != 0


def test_hermes_egress_env_is_optional_but_present_file_requires_bind(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        ["bash", "-c", f'''source "{UPDATE_SCRIPT}"
HERMES_EGRESS_ENV_FILE='{tmp_path / "absent"}'
unset HERMES_BRIDGE_BIND_ADDRESS
verify_hermes_egress_env
'''],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    result = _verify_egress_env(
        tmp_path,
        "HTTPS_PROXY=http://127.0.0.1:17897\nHTTP_PROXY=http://127.0.0.1:17897\nNO_PROXY=localhost,127.0.0.1,172.18.0.1\n",
        bridge="",
    )
    assert result.returncode != 0
    assert "initialized Bridge bind address" in result.stderr


def test_egress_verifier_guards_restart_final_verification_and_rollback() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    switched = script.index("SWITCHED=1")
    pre_restart = script.index("verify_hermes_egress_env\n", switched)
    restart = script.index("restart_hermes_runtime\n", pre_restart)
    final = script.index('echo "==> [6/6]')
    final_verify = script.index("verify_hermes_egress_env\n", final)
    assert pre_restart < restart < final < final_verify

    rollback_health = script[script.index("verify_rollback_health() {"):script.index(
        "rollback_deployment() {"
    )]
    restored = rollback_health.index('restored_address="${line#HERMES_BRIDGE_BIND_ADDRESS=}"')
    egress = rollback_health.index('verify_hermes_egress_env "$restored_address"', restored)
    health = rollback_health.index("http://$restored_address:9118/health", egress)
    assert restored < egress < health


def test_macos_clash_tunnel_is_loopback_only_and_noninteractive() -> None:
    script = EGRESS_TUNNEL_SCRIPT.read_text(encoding="utf-8")
    assert "/usr/bin/nc -z -w 3 127.0.0.1 7897" in script
    assert "lsof" not in script
    assert "-R 127.0.0.1:17897:127.0.0.1:7897" in script
    assert "StrictHostKeyChecking=yes" in script
    assert 'require_private_file "$identity_file" "SSH identity"' in script
    assert "require_known_hosts" in script
    for contract in (
        "-N -T", "RequestTTY=no", "ForwardAgent=no", "ForwardX11=no", "PermitLocalCommand=no",
    ):
        assert contract in script
    for forbidden in (
        "0.0.0.0:17897", "*:17897", "GatewayPorts=yes", "StrictHostKeyChecking=no",
        "ProxyCommand", "subscription", "controller-secret", "secret:",
    ):
        assert forbidden not in script


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
        "HERMES_RUNTIME_COMMIT=c8aa5608c24e3636e77c267650c0f1f52e44adb0",
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
    bridge_config = update[update.index("configure_hermes_bridge_network() {"):update.index(
        "verify_hermes_bridge_unit() {"
    )]
    for proxy_variable in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        assert f"export {proxy_variable}=" not in update
        assert f"Environment={proxy_variable}=" not in update
        assert f"{proxy_variable}=" not in bridge_config


@pytest.mark.parametrize(
    ("runtime_commit", "runtime_status", "expected_returncode", "expected_error", "expected_commands"),
    (
        (
            "c8aa5608c24e3636e77c267650c0f1f52e44adb0",
            "",
            0,
            "",
            ("rev-parse HEAD", "status --porcelain"),
        ),
        (
            "0000000000000000000000000000000000000000",
            "",
            1,
            "Hermes runtime source must be exactly c8aa5608c24e3636e77c267650c0f1f52e44adb0",
            ("rev-parse HEAD",),
        ),
        (
            "c8aa5608c24e3636e77c267650c0f1f52e44adb0",
            " M tracked-file\n?? untracked-file",
            1,
            "Hermes runtime source checkout must be clean",
            ("rev-parse HEAD", "status --porcelain"),
        ),
    ),
)
def test_verify_hermes_install_checks_repository_as_owner_and_fails_closed(
    tmp_path: Path,
    runtime_commit: str,
    runtime_status: str,
    expected_returncode: int,
    expected_error: str,
    expected_commands: tuple[str, ...],
) -> None:
    events = tmp_path / "events"
    command = f'''source "{UPDATE_SCRIPT}"
HERMES_AGENT_ROOT='{tmp_path}'
HERMES_PYTHON="$(type -P true)"
HERMES_LAUNCHER="$HERMES_PYTHON"
runuser() {{
  printf '%s\n' "$*" >> '{events}'
  [ "$1" = -u ] && [ "$2" = quantumn-hermes ] && [ "$3" = -- ] \
    && [ "$4" = git ] && [ "$5" = -C ] && [ "$6" = "$HERMES_AGENT_ROOT" ] || return 90
  case "$7 $8" in
    'rev-parse HEAD') printf '%s\n' '{runtime_commit}' ;;
    'status --porcelain') printf '%s\n' '{runtime_status}' ;;
    *) return 91 ;;
  esac
}}
verify_hermes_install
'''
    result = subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == expected_returncode
    assert expected_error in result.stderr
    prefix = f"-u quantumn-hermes -- git -C {tmp_path} "
    assert events.read_text(encoding="utf-8").splitlines() == [
        prefix + git_command for git_command in expected_commands
    ]


def test_bridge_preflight_accepts_existing_health_without_starting_probe(tmp_path: Path) -> None:
    bridge = BRIDGE_SCRIPT.read_text(encoding="utf-8")
    update = UPDATE_SCRIPT.read_text(encoding="utf-8")

    assert 'os.environ.get("HERMES_BRIDGE_BIND_ADDRESS", "")' in bridge
    assert 'bind_address = _private_bridge_bind_address()' in bridge
    assert 'host=bind_address' in bridge
    assert 'host="0.0.0.0"' not in bridge
    assert "socket.gethostbyname('host.docker.internal')" in update
    assert 'ip -4 -o addr show' in update
    assert 'http://$HERMES_BRIDGE_BIND_ADDRESS:9118/health' in update
    assert "urllib.request.urlopen('http://$HERMES_BRIDGE_BIND_ADDRESS:9118/health'" in update
    preflight = update[update.index("preflight_hermes_bridge_network() {"):update.index(
        "verify_hermes_bridge_network() {"
    )]
    resolver = update[update.index("resolve_hermes_bridge_bind_address() {"):update.index(
        "preflight_hermes_bridge_network() {"
    )]
    assert "signal.alarm(5)" in resolver
    assert "docker inspect" not in resolver
    assert 'python3 - "$HERMES_BRIDGE_BIND_ADDRESS" "$probe_dir/ready"' in preflight
    assert "HTTPServer((sys.argv[1], 9118), Handler)" in preflight
    assert "0.0.0.0" not in preflight
    assert preflight.index('kill "$probe_pid"') < preflight.index('wait "$probe_pid"')
    assert preflight.count(".get('status') == 'ok'") == 2

    events = tmp_path / "events"
    command = f'''source "{UPDATE_SCRIPT}"
resolve_hermes_bridge_bind_address() {{ printf '%s\n' 172.17.0.1; }}
docker() {{
  printf '%s\n' existing-health >> '{events}'
  [[ "$*" == *"http://172.17.0.1:9118/health"* && "$*" == *"status"* ]]
}}
python3() {{ printf '%s\n' unexpected-probe >> '{events}'; return 1; }}
preflight_hermes_bridge_network
printf '%s\\n' "$HERMES_BRIDGE_BIND_ADDRESS"
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
    assert events.read_text(encoding="utf-8").splitlines() == ["existing-health"]


def test_bridge_preflight_temporary_probe_is_private_reachable_and_reaped(tmp_path: Path) -> None:
    events = tmp_path / "events"
    command = f'''source "{UPDATE_SCRIPT}"
real_python="$(type -P python3)"
resolve_hermes_bridge_bind_address() {{ printf '%s\n' 172.17.0.1; }}
docker() {{
  printf '%s\n' container-health >> '{events}'
  [ "$(wc -l < '{events}')" -gt 2 ]
}}
python3() {{
  [ "$1" = - ] && [ "$2" = 172.17.0.1 ] || return 99
  exec "$real_python" -c 'import os,pathlib,sys,time; pathlib.Path(sys.argv[1]).open("a").write(f"probe-started {{os.getpid()}}\\n"); pathlib.Path(sys.argv[2]).touch(); time.sleep(60)' '{events}' "$3"
}}
preflight_hermes_bridge_network
probe_pid="$(awk '$1 == "probe-started" {{print $2}}' '{events}')"
! kill -0 "$probe_pid" 2>/dev/null
printf '%s\n' probe-reaped >> '{events}'
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
    assert result.returncode == 0, result.stderr
    lines = events.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "container-health"
    assert lines[1].startswith("probe-started ")
    assert lines[2:] == ["container-health", "probe-reaped"]


def test_bridge_preflight_refuses_occupied_or_unreachable_port_and_reaps_probe(tmp_path: Path) -> None:
    for mode in ("occupied", "unreachable"):
        events = tmp_path / mode
        command = f'''source "{UPDATE_SCRIPT}"
real_python="$(type -P python3)"
resolve_hermes_bridge_bind_address() {{ printf '%s\n' 172.17.0.1; }}
docker() {{ printf '%s\n' container-health >> '{events}'; return 1; }}
python3() {{
  if [ '{mode}' = occupied ]; then return 1; fi
  exec "$real_python" -c 'import os,pathlib,sys,time; pathlib.Path(sys.argv[1]).open("a").write(f"probe-started {{os.getpid()}}\\n"); pathlib.Path(sys.argv[2]).touch(); time.sleep(60)' '{events}' "$3"
}}
if preflight_hermes_bridge_network; then exit 0; fi
if [ '{mode}' = unreachable ]; then
  probe_pid="$(awk '$1 == "probe-started" {{print $2}}' '{events}')"
  ! kill -0 "$probe_pid" 2>/dev/null
  printf '%s\n' probe-reaped >> '{events}'
fi
exit 1
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
        lines = events.read_text(encoding="utf-8").splitlines()
        if mode == "occupied":
            assert lines == ["container-health"]
        else:
            assert lines[0] == "container-health"
            assert lines[1].startswith("probe-started ")
            assert lines[2:] == ["container-health", "probe-reaped"]


def test_bridge_binding_resolves_host_gateway_inside_api_container() -> None:
    command = f'''source "{UPDATE_SCRIPT}"
docker() {{
  if [[ "$*" == *"ps -q api"* ]]; then printf '%s\n' api-container;
  elif [[ "$*" == *"gethostbyname('host.docker.internal')"* ]]; then printf '%s\n' 172.18.0.1;
  else return 99; fi
}}
ip() {{ printf '%s\n' '2: docker0 inet 172.18.0.1/16 scope global docker0'; }}
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
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "172.18.0.1"


@pytest.mark.parametrize(
    ("resolved", "host_addresses"),
    (
        ("", "172.18.0.1/16"),
        ("172.18.0.1\n172.19.0.1", "172.18.0.1/16"),
        ("not-an-address", "172.18.0.1/16"),
        ("203.0.113.10", "203.0.113.10/24"),
        ("172.18.0.1", "192.168.1.10/24"),
    ),
)
def test_bridge_binding_rejects_empty_multiple_malformed_public_or_unassigned_addresses(
    resolved: str, host_addresses: str,
) -> None:
    command = f'''source "{UPDATE_SCRIPT}"
docker() {{
  if [[ "$*" == *"ps -q api"* ]]; then printf '%s\\n' api-container;
  elif [[ "$*" == *"gethostbyname('host.docker.internal')"* ]]; then printf '%s\\n' '{resolved}';
  else return 99; fi
}}
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


def test_candidate_bridge_network_is_verified_after_runtime_restart() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    up = script.index('docker compose -p "$COMPOSE_PROJECT" up -d --no-build --pull never',
                      script.index('echo "==> [3/6]'))
    install = script.index("install_hermes_units\n", script.index("SWITCHED=1"))
    restart = script.index("restart_hermes_runtime\n", install)
    verify = script.index("verify_hermes_bridge_network\n", restart)
    final = script.index('echo "==> [6/6]', verify)
    assert up < install < restart < verify < final
    assert 'if [ "$AI_LAB_HERMES_QUARANTINED" != "1" ]' in script[restart:verify]

    function = script[script.index("verify_hermes_bridge_network() {"):script.index(
        "configure_hermes_bridge_network() {"
    )]
    candidate_check = function.index('[ "$candidate_address" != "$HERMES_BRIDGE_BIND_ADDRESS" ]')
    hostname_check = function.index(
        "socket.gethostbyname('host.docker.internal') == '$HERMES_BRIDGE_BIND_ADDRESS'"
    )
    health_check = function.index("http://$HERMES_BRIDGE_BIND_ADDRESS:9118/health")
    assert candidate_check < hostname_check < health_check
    assert ".get('status') == 'ok'" in function
    assert "for attempt in $(seq 1 30)" in function
    assert "|| true" not in function


def test_candidate_bridge_health_retries_until_success(tmp_path: Path) -> None:
    attempts = tmp_path / "attempts"
    sleeps = tmp_path / "sleeps"
    command = f'''source "{UPDATE_SCRIPT}"
resolve_hermes_bridge_bind_address() {{ printf '%s\n' 172.17.0.1; }}
docker() {{
  [[ "$*" == *"host.docker.internal"* ]] && return 0
  printf '%s\n' attempt >> '{attempts}'
  [ "$(wc -l < '{attempts}')" -eq 3 ] && return 0
  printf '%s\n' 'Traceback: Bridge starting' >&2
  return 1
}}
sleep() {{ printf '%s\n' "$1" >> '{sleeps}'; }}
HERMES_BRIDGE_BIND_ADDRESS=172.17.0.1
verify_hermes_bridge_network
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
    assert result.returncode == 0, result.stderr
    assert attempts.read_text(encoding="utf-8").splitlines() == ["attempt"] * 3
    assert sleeps.read_text(encoding="utf-8").splitlines() == ["1"] * 2
    assert "Traceback" not in result.stderr


def test_candidate_bridge_health_fails_after_30_attempts(tmp_path: Path) -> None:
    attempts = tmp_path / "attempts"
    sleeps = tmp_path / "sleeps"
    command = f'''source "{UPDATE_SCRIPT}"
resolve_hermes_bridge_bind_address() {{ printf '%s\n' 172.17.0.1; }}
docker() {{
  [[ "$*" == *"host.docker.internal"* ]] && return 0
  printf '%s\n' attempt >> '{attempts}'
  printf '%s\n' 'Traceback: Bridge starting' >&2
  return 1
}}
sleep() {{ printf '%s\n' "$1" >> '{sleeps}'; }}
HERMES_BRIDGE_BIND_ADDRESS=172.17.0.1
verify_hermes_bridge_network
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
    assert attempts.read_text(encoding="utf-8").splitlines() == ["attempt"] * 30
    assert sleeps.read_text(encoding="utf-8").splitlines() == ["1"] * 29
    assert "ERROR: Hermes Bridge did not become healthy" in result.stderr
    assert "Traceback" not in result.stderr


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
    assert RUNTIME_SHA256 in script
    assert 'printf \'%s\\0%s\\0%s\\0\'' in script
    assert '"$BRIDGE_WORKER_RUNTIME_PYTHON" -m venv' in script
    assert "runuser -u quantumn-hermes -- python3 -m venv" not in script
    assert 'chown quantumn-hermes:quantumn-hermes "$temp_dir"' in script
    assert 'mv -Tf "$next_link" "$BRIDGE_WORKER_VENV_LINK"' in script
    assert 'mv -Tf "$rollback_venv_link" "$BRIDGE_WORKER_VENV_LINK"' in script
    changed = script.index("RUNTIME_CHANGED=1", script.index("snapshot_managed_images\n"))
    activation = script.index("activate_bridge_worker_venv\n", changed)
    assert changed < activation


def test_certbot_runtime_is_fixed_offline_and_hash_verified() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    prepare = script[script.index("prepare_certbot_venv() {"):script.index(
        "activate_certbot_venv() {"
    )]

    for contract in (
        "CERTBOT_PYTHON_RUNTIME_ROOT=/opt/certbot-python-runtimes",
        'CERTBOT_PYTHON_RUNTIME_DIR="$CERTBOT_PYTHON_RUNTIME_ROOT/$BRIDGE_WORKER_RUNTIME_SHA256"',
        'CERTBOT_PYTHON_RUNTIME_PYTHON="$CERTBOT_PYTHON_RUNTIME_DIR/bin/python3"',
        "CERTBOT_VERSION=5.8.0",
        "CERTBOT_ARCHIVE=/home/deploy/certbot-wheelhouse-5.8.0-linux-amd64.tar.zst",
        f"CERTBOT_ARCHIVE_SHA256={CERTBOT_ARCHIVE_SHA256}",
        "CERTBOT_VENV_LINK=/opt/certbot-venv",
        "CERTBOT_VENV_ROOT=/opt/certbot-venvs",
        'CERTBOT_VENV_DIR="$CERTBOT_VENV_ROOT/$CERTBOT_VERSION-linux-amd64-${CERTBOT_ARCHIVE_SHA256:0:12}"',
        '[ "$actual_sha" != "$CERTBOT_ARCHIVE_SHA256" ]',
        '"$CERTBOT_PYTHON_RUNTIME_PYTHON" -m venv "$temp_dir/venv"',
        "import configargparse",
        'assert version("certbot") == __import__("os").environ["CERTBOT_VERSION"]',
        '[ "$(TERM=dumb "$certbot" --version 2>/dev/null)" = "certbot $CERTBOT_VERSION" ]',
    ):
        assert contract in script
    assert "import ConfigArgParse" not in script
    assert '"$BRIDGE_WORKER_RUNTIME_PYTHON"' not in prepare


def test_certbot_python_runtime_is_root_only_and_safely_extracted() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    prepare = script[script.index("verify_certbot_python_runtime_tree() {"):script.index(
        "verify_bridge_worker_venv() {"
    )]

    for contract in (
        'local archive="$BRIDGE_WORKER_RUNTIME_ARCHIVE" target="$CERTBOT_PYTHON_RUNTIME_DIR"',
        '[ "$(uname -s)" != Linux ] || [ "$(uname -m)" != x86_64 ]',
        '[ "$actual_sha" != "$BRIDGE_WORKER_RUNTIME_SHA256" ]',
        '[ -L "$CERTBOT_PYTHON_RUNTIME_ROOT" ] || [ ! -d "$CERTBOT_PYTHON_RUNTIME_ROOT" ]',
        'install -d -o root -g root -m 0755 "$CERTBOT_PYTHON_RUNTIME_ROOT"',
        'stat -c \'%u\' "$CERTBOT_PYTHON_RUNTIME_ROOT"',
        '[ -L "$target" ]',
        'extract_python_runtime_archive "$archive" "$temp_dir"',
        'verify_certbot_python_runtime_tree "$temp_dir/python"',
        'mv -T "$temp_dir/python" "$target"',
        'assert sys.platform == "linux"',
        'assert platform.machine() == "x86_64"',
    ):
        assert contract in prepare
    assert "/var/lib/quantumn-hermes" not in prepare


def test_certbot_wheelhouse_is_safely_extracted_and_complete() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    prepare = script[script.index("prepare_certbot_venv() {"):script.index(
        "activate_certbot_venv() {"
    )]

    for contract in (
        'path.parts[0] != root or ".." in path.parts',
        "member.isdir() or member.isfile()",
        'source.extractall(output, members=members, filter="data")',
        'if len(entries) != 19 or files != {*entries, "manifest.sha256"}:',
        "Certbot wheelhouse manifest does not cover exactly 19 files",
        "hashlib.sha256((root / name).read_bytes()).hexdigest() != expected",
        "len(requirements) != 18 or len(set(requirements)) != 18",
        're.compile(r"[A-Za-z0-9_.-]+==[^ ]+ --hash=sha256:[0-9a-f]{64}")',
        "pip install --no-index",
        "--require-hashes",
    ):
        assert contract in prepare
    assert "tar -xf" not in prepare


def test_certbot_venv_enforces_root_ownership_and_verifies_real_target() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    verifier = script[script.index("verify_certbot_venv() {"):script.index(
        "prepare_certbot_venv() {"
    )]
    activation = script[script.index("activate_certbot_venv() {"):script.index(
        "validate_private_host_address() {"
    )]

    assert '[ -L "$venv" ] || [ ! -d "$venv" ]' in verifier
    assert 'stat -c \'%u\' "$venv"' in verifier
    assert 'find "$venv" ! -user root -print -quit' in verifier
    assert 'find "$venv" \\( -type f -o -type d \\) -perm /022 -print -quit' in verifier
    assert 'find "$venv" ! -type f ! -type d ! -type l -print -quit' in verifier
    assert "bin/python|bin/python3|bin/python3.12)" in verifier
    assert '[ "$resolved" = "$runtime_python" ]' in verifier
    assert "lib64)" in verifier
    assert '[ "$resolved" = "$venv_lib" ]' in verifier
    assert "Certbot venv contains an unexpected symlink" in verifier
    assert '[ -L "$certbot" ] || [ ! -f "$certbot" ]' in verifier
    assert 'stat -c \'%u\' "$certbot"' in verifier
    assert 'stat -c \'%a\' "$certbot"' in verifier
    assert '[ "$certbot_first_line" != "#!$venv/bin/python" ]' in verifier
    assert '[ "$(TERM=dumb "$certbot" --version 2>/dev/null)" = "certbot $CERTBOT_VERSION" ]' in verifier
    assert "$certbot --version 2>&1" not in verifier
    assert 'resolved_target="$(readlink -f -- "$CERTBOT_VENV_LINK")"' in activation
    assert '[ "$resolved_target" != "$CERTBOT_VENV_TARGET" ]' in activation
    assert 'verify_certbot_venv "$resolved_target"' in activation
    assert 'verify_certbot_venv "$CERTBOT_VENV_LINK"' not in activation


def test_certbot_venv_rewrites_staging_shebangs_before_relocation(tmp_path: Path) -> None:
    staging = tmp_path / "build" / "venv"
    target = tmp_path / "certbot-venv"
    (staging / "bin").mkdir(parents=True)
    old_shebang = f"#!{staging}/bin/python"
    (staging / "bin" / "certbot").write_text(f"{old_shebang}\nprint('certbot')\n")
    (staging / "bin" / "pip").write_text(f"#!{staging}/bin/python3\n")
    (staging / "bin" / "python-tool").write_text(f"#!{staging}/bin/python3.12\n")
    (staging / "bin" / "unchanged").write_text("#!/usr/bin/python3\n")
    activation_helpers = ("activate", "activate.csh", "activate.fish", "Activate.ps1")
    for helper in activation_helpers:
        (staging / "bin" / helper).write_text(f"VIRTUAL_ENV={staging}\n")
    (staging / "pyvenv.cfg").write_text(f"command = python -m venv {staging}\n")
    pycache = staging / "lib" / "python3.12" / "site-packages" / "__pycache__"
    pycache.mkdir(parents=True)
    (pycache / "typing_extensions.cpython-312.pyc").write_bytes(bytes(str(staging), "utf-8"))
    loose_pyc = staging / "lib" / "orphan.pyc"
    loose_pyc.write_bytes(bytes(str(staging), "utf-8"))

    result = subprocess.run(
        ["bash", "-c", f'''source "{UPDATE_SCRIPT}"
CERTBOT_PYTHON_RUNTIME_PYTHON={json.dumps(sys.executable)}
relocate_certbot_venv {json.dumps(str(staging))} {json.dumps(str(target))}
'''],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (staging / "bin" / "certbot").read_text().splitlines()[0] == f"#!{target}/bin/python"
    assert (staging / "bin" / "pip").read_text().splitlines()[0] == f"#!{target}/bin/python"
    assert (staging / "bin" / "python-tool").read_text().splitlines()[0] == f"#!{target}/bin/python"
    assert (staging / "bin" / "unchanged").read_text().splitlines()[0] == "#!/usr/bin/python3"
    assert all(not (staging / "bin" / helper).exists() for helper in activation_helpers)
    assert str(staging) not in (staging / "pyvenv.cfg").read_text()
    assert not pycache.exists()
    assert not loose_pyc.exists()


def test_certbot_venv_relocation_rejects_any_staging_prefix_remnant(tmp_path: Path) -> None:
    staging = tmp_path / "build" / "venv"
    target = tmp_path / "certbot-venv"
    (staging / "bin").mkdir(parents=True)
    (staging / "bin" / "certbot").write_text(f"#!{staging}/bin/python\n")
    binary = staging / "staging-reference.bin"
    binary.write_bytes(bytes(str(staging), "utf-8"))
    (staging / "pyvenv.cfg").write_text("clean\n")

    result = subprocess.run(
        ["bash", "-c", f'''source "{UPDATE_SCRIPT}"
CERTBOT_PYTHON_RUNTIME_PYTHON={json.dumps(sys.executable)}
relocate_certbot_venv {json.dumps(str(staging))} {json.dumps(str(target))}
'''],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True, text=True,
    )

    assert result.returncode != 0
    assert "Certbot venv retains staging path" in result.stderr
    assert binary.exists()


@pytest.mark.parametrize("active", (False, True), ids=("inactive-rebuild", "active-fail-closed"))
def test_invalid_certbot_target_is_only_removed_when_inactive(tmp_path: Path, active: bool) -> None:
    target = tmp_path / "invalid-certbot"
    target.mkdir()
    link = tmp_path / "certbot-venv"
    if active:
        link.symlink_to(target)
    command = f'''source "{UPDATE_SCRIPT}"
verify_certbot_venv() {{ return 1; }}
CERTBOT_VENV_LINK={json.dumps(str(link))}
discard_invalid_inactive_certbot_venv {json.dumps(str(target))}
'''
    result = subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True, text=True,
    )

    assert result.returncode == int(active)
    assert target.exists() is active
    if active:
        assert "refusing to delete it" in result.stderr


def test_runtime_activation_precedes_tls_preflight_and_compose_changes() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    stage = script[script.index('echo "==> [3/6]'):script.index('echo "==> [4/6]')]

    ordered = (
        "snapshot_managed_units\n",
        "snapshot_managed_images\n",
        "RUNTIME_CHANGED=1\n",
        "activate_bridge_worker_venv\n",
        "activate_certbot_venv\n",
        "AI_LAB_DEPLOY_LOCK_HELD=1 bash scripts/renew_tls_certificate.sh --preflight-only\n",
        'echo "==> [3a/6]',
        "docker compose",
    )
    positions = [stage.index(item) for item in ordered]
    assert positions == sorted(positions)


def test_bridge_worker_runtime_is_fixed_offline_and_version_gated() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")

    for contract in (
        "/opt/ai-lab-shared/offline-runtime/cpython-3.12.14+20260901-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
        'BRIDGE_WORKER_RUNTIME_DIR="$BRIDGE_WORKER_RUNTIME_ROOT/cpython-3.12.14+20260901"',
        '[ -L "$archive" ]',
        "stat -c '%u' \"$archive\"",
        '[ "$actual_sha" != "$BRIDGE_WORKER_RUNTIME_SHA256" ]',
        'mv -T "$temp_dir/python" "$target"',
        'assert sys.version_info[:3] == (3, 12, 14)',
        'assert sqlite3.sqlite_version_info == (3, 53, 1)',
        're.search(r"\\b(\\d+)\\.(\\d+)\\.(\\d+)\\b", ssl.OPENSSL_VERSION)',
        'tuple(map(int, openssl_version.groups())) == (3, 5, 8)',
        "assert sys.version_info >= (3, 12)",
        'source.extractall(staging_dir, members=members, filter="data")',
        'verify_bridge_worker_venv "$target/bin/python"',
        'verify_bridge_worker_venv "$BRIDGE_WORKER_PYTHON"',
    ):
        assert contract in script
    assert "OPENSSL_VERSION_INFO" not in script
    assert "tar -tzf" not in script
    assert "tar -xzf" not in script[script.index("prepare_bridge_worker_python_runtime() {"):]


def test_bridge_worker_python_parses_openssl_semantic_version(tmp_path: Path) -> None:
    python = tmp_path / "python3"
    python.write_text(
        """#!/usr/bin/env python3
import sys
import types
sys.version_info = (3, 12, 14)
sys.modules["sqlite3"] = types.SimpleNamespace(sqlite_version_info=(3, 53, 1))
sys.modules["ssl"] = types.SimpleNamespace(
    OPENSSL_VERSION="OpenSSL 3.5.8 25 Aug 2026",
    OPENSSL_VERSION_INFO=(3, 5, 0, 8, 0),
)
exec(sys.argv[2])
""",
        encoding="utf-8",
    )
    python.chmod(0o755)
    result = subprocess.run(
        ["bash", "-c", f'source "{UPDATE_SCRIPT}"; verify_bridge_worker_python "{python}"'],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_bridge_worker_runtime_allows_internal_symlink_and_rejects_escape(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime"
    (runtime / "bin").mkdir(parents=True)
    (runtime / "lib").mkdir()
    internal_python = runtime / "lib" / "python3"
    internal_python.write_text("#!/bin/sh\n", encoding="utf-8")
    internal_python.chmod(0o755)
    python_link = runtime / "bin" / "python3"
    python_link.symlink_to("../lib/python3")
    common = f'''source "{UPDATE_SCRIPT}"
stat() {{ [ "$2" = '%u' ] && printf '0\\n' || printf '755\\n'; }}
find() {{
  if [[ "$*" == *"! -user root"* ]]; then
    [[ "$*" == *"! -type l"* ]] || printf '%s\\n' '{python_link}'
  else
    command find "$@"
  fi
}}
readlink() {{
  [ "$1" = -f ] && python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "${{@: -1}}"
}}
verify_bridge_worker_python() {{ return 0; }}
verify_bridge_worker_runtime_tree '{runtime}'
'''
    safe = subprocess.run(
        ["bash", "-c", common],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True,
        text=True,
    )
    assert safe.returncode == 0, safe.stderr

    python_link.unlink()
    python_link.symlink_to(tmp_path / "outside-python")
    escaping = subprocess.run(
        ["bash", "-c", common],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True,
        text=True,
    )
    assert escaping.returncode != 0
    assert "runtime symlink escapes its root" in escaping.stderr


@pytest.mark.parametrize(
    "kind", ("absolute", "traversal", "symlink", "hardlink", "device")
)
def test_bridge_worker_runtime_rejects_malicious_archive(
    tmp_path: Path, kind: str,
) -> None:
    archive = tmp_path / "python.tar.gz"
    member = tarfile.TarInfo("python/entry")
    if kind == "absolute":
        member.name = "/python/escape"
        member.size = 1
    elif kind == "traversal":
        member.name = "python/../../escape"
        member.size = 1
    elif kind == "symlink":
        member.type = tarfile.SYMTYPE
        member.linkname = "../../escape"
    elif kind == "hardlink":
        member.type = tarfile.LNKTYPE
        member.linkname = "../../escape"
    else:
        member.type = tarfile.CHRTYPE
        member.devmajor = 1
        member.devminor = 3
    with tarfile.open(archive, "w:gz") as target:
        target.addfile(member, io.BytesIO(b"x") if member.size else None)

    command = f'''source "{UPDATE_SCRIPT}"
stat() {{ [ "$2" = '%u' ] && printf '0\\n' || printf '600\\n'; }}
install() {{ mkdir -p "${{@: -1}}"; }}
BRIDGE_WORKER_RUNTIME_ARCHIVE='{archive}'
BRIDGE_WORKER_RUNTIME_SHA256='{hashlib.sha256(archive.read_bytes()).hexdigest()}'
BRIDGE_WORKER_RUNTIME_ROOT='{tmp_path / "runtimes"}'
BRIDGE_WORKER_RUNTIME_DIR="$BRIDGE_WORKER_RUNTIME_ROOT/cpython-3.12.14+20260901"
prepare_bridge_worker_python_runtime
'''
    result = subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "archive has unsafe contents" in result.stderr
    assert not (tmp_path / "escape").exists()


@pytest.mark.parametrize("mode", ("missing", "symlink", "wrong-owner", "wrong-hash"))
def test_bridge_worker_runtime_rejects_untrusted_archive(tmp_path: Path, mode: str) -> None:
    archive = tmp_path / "python.tar.gz"
    if mode == "symlink":
        target = tmp_path / "target.tar.gz"
        target.write_bytes(b"archive")
        archive.symlink_to(target)
    elif mode != "missing":
        archive.write_bytes(b"archive")
    stat_override = 'stat() { [ "$2" = \'%u\' ] && printf \'1000\\n\' || printf \'600\\n\'; }'
    if mode in ("symlink", "wrong-hash"):
        stat_override = "stat() { [ \"$2\" = '%u' ] && printf '0\\n' || printf '600\\n'; }"
    command = f'''source "{UPDATE_SCRIPT}"
{stat_override}
BRIDGE_WORKER_RUNTIME_ARCHIVE='{archive}'
BRIDGE_WORKER_RUNTIME_ROOT='{tmp_path / "runtimes"}'
BRIDGE_WORKER_RUNTIME_DIR="$BRIDGE_WORKER_RUNTIME_ROOT/cpython-3.12.14+20260901"
prepare_bridge_worker_python_runtime
'''
    result = subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_bridge_worker_venv_does_not_fallback_when_offline_runtime_is_unavailable(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "system-python-used"
    command = f'''source "{UPDATE_SCRIPT}"
prepare_bridge_worker_python_runtime() {{ return 1; }}
python3() {{ touch '{marker}'; return 0; }}
prepare_bridge_worker_venv '{tmp_path}'
'''
    result = subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not marker.exists()


@pytest.mark.parametrize("mode", ("python", "sqlite", "openssl"))
def test_bridge_worker_python_rejects_unsafe_runtime_versions(tmp_path: Path, mode: str) -> None:
    python = tmp_path / "python3"
    python.write_text(f"#!/bin/sh\n[ '{mode}' = safe ]\n", encoding="utf-8")
    python.chmod(0o755)
    result = subprocess.run(
        ["bash", "-c", f'source "{UPDATE_SCRIPT}"; verify_bridge_worker_python "{python}"'],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_restart_hermes_runtime_absent_units_succeed_and_restart_failure_propagates() -> None:
    absent = subprocess.run(
        ["bash", "-c", f'source "{UPDATE_SCRIPT}"; systemctl() {{ return 1; }}; restart_hermes_runtime'],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"}, capture_output=True, text=True,
    )
    assert absent.returncode == 0, absent.stderr
    assert absent.stdout.count("hermes_restart_status=skipped_absent") == 5

    failed = subprocess.run(
        ["bash", "-c", f'''source "{UPDATE_SCRIPT}"
systemctl() {{ [ "$1" = cat ] && return 0; [ "$1" = restart ] && return 23; }}
if restart_hermes_runtime; then exit 0; else exit $?; fi
'''],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"}, capture_output=True, text=True,
    )
    assert failed.returncode != 0


def test_server_deploy_enables_units_without_starting_them_during_quarantine() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    install = script.index("install_hermes_units\n", script.index("SWITCHED=1"))
    restart = script.index("restart_hermes_runtime\n", install)
    assert install < restart
    assert "systemctl enable --now ai-lab-certbot-renew.timer" in script
    install_function = script[script.index("install_hermes_units() {"):script.index(
        "restart_hermes_runtime() {"
    )]
    enable = install_function.index(
        "systemctl enable hermes-bridge.service hermes-chat-worker.service"
    )
    enabled_check = install_function.index("verify_hermes_units_enabled", enable)
    assert enable < enabled_check
    assert "systemctl enable --now hermes-bridge" not in script
    final = script.index('echo "==> [6/6]')
    assert script.index("verify_hermes_units_enabled\n", final) < script.index(
        'if [ "$AI_LAB_HERMES_QUARANTINED" = "1" ]', final
    )
    verify_function = script[script.index("verify_hermes_units_enabled() {"):script.index(
        "restart_hermes_runtime() {"
    )]
    for unit in ("hermes-bridge.service", "hermes-chat-worker.service"):
        assert f"systemctl is-enabled --quiet {unit}" in verify_function
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


def test_taskboard_health_probe_uses_node_fetch_instead_of_wget() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    assert """docker compose -p "$COMPOSE_PROJECT" exec -T taskboard \\
    node -e "fetch('http://127.0.0.1:47823/api/meta').then(response => process.exit(response.ok ? 0 : 1)).catch(() => process.exit(1))" || return 1""" in script
    assert "exec -T taskboard \\" + "\n    wget " not in script


@pytest.mark.parametrize(
    ("volumes", "expected_returncode"),
    (("contract_taskboard_data", 0), ("", 1), ("first\nsecond", 1)),
)
def test_taskboard_permission_helper_is_exact_and_fails_closed(
    tmp_path: Path, volumes: str, expected_returncode: int,
) -> None:
    events = tmp_path / "events"
    lookup = tmp_path / "lookup"
    config = json.dumps({"services": {"taskboard": {"image": "registry.local/taskboard@sha256:" + "a" * 64}}})
    command = f'''source "{UPDATE_SCRIPT}"
docker() {{
  if [ "$1" = compose ]; then printf '%s\n' "$CONFIG"; return; fi
  if [ "$1 $2" = 'volume ls' ]; then printf '<%s>\n' "$@" > '{lookup}'; printf '%s\n' "$VOLUMES"; return; fi
  printf '<%s>\n' "$@" > '{events}'
}}
COMPOSE_PROJECT=contract-test
repair_taskboard_data_permissions
'''
    result = subprocess.run(
        ["bash", "-c", command],
        env={
            **os.environ,
            "AI_LAB_UPDATE_LIBRARY_ONLY": "1",
            "CONFIG": config,
            "VOLUMES": volumes,
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == expected_returncode
    if expected_returncode:
        assert not events.exists()
        assert "expected exactly one Compose taskboard_data volume" in result.stderr
        return
    assert lookup.read_text(encoding="utf-8").splitlines() == [
        "<volume>", "<ls>", "<--filter>",
        "<label=com.docker.compose.project=contract-test>", "<--filter>",
        "<label=com.docker.compose.volume=taskboard_data>", "<--format>", "<{{.Name}}>",
    ]
    assert events.read_text(encoding="utf-8").splitlines() == [
        "<run>", "<--rm>", "<--pull>", "<never>", "<--network>", "<none>",
        "<--read-only>", "<--cap-drop>", "<ALL>", "<--cap-add>", "<CHOWN>",
        "<--security-opt>", "<no-new-privileges>", "<--user>", "<0>", "<--mount>",
        "<type=volume,src=contract_taskboard_data,dst=/data>", "<--entrypoint>",
        "<chown>", "<registry.local/taskboard@sha256:" + "a" * 64 + ">",
        "<-R>", "<1000:1000>", "</data>",
    ]


@pytest.mark.parametrize(
    ("image", "volume", "expected_error"),
    (
        ("--privileged", "contract_taskboard_data", "invalid taskboard image reference"),
        ("registry.local/taskboard:release", "../host", "invalid taskboard_data volume name"),
    ),
)
def test_taskboard_permission_helper_rejects_invalid_image_and_volume_values(
    tmp_path: Path, image: str, volume: str, expected_error: str,
) -> None:
    events = tmp_path / "events"
    config = json.dumps({"services": {"taskboard": {"image": image}}})
    command = f'''source "{UPDATE_SCRIPT}"
docker() {{
  if [ "$1" = compose ]; then printf '%s\n' "$CONFIG"; return; fi
  if [ "$1 $2" = 'volume ls' ]; then printf '%s\n' "$VOLUME"; return; fi
  printf '%s\n' unexpected-run > '{events}'
}}
COMPOSE_PROJECT=contract-test
repair_taskboard_data_permissions
'''
    result = subprocess.run(
        ["bash", "-c", command],
        env={
            **os.environ,
            "AI_LAB_UPDATE_LIBRARY_ONLY": "1",
            "CONFIG": config,
            "VOLUME": volume,
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert expected_error in result.stderr
    assert not events.exists()


@pytest.mark.parametrize(
    ("runtime_uid", "expected"),
    (("10001", 0), ("0", 1), ("", 1), ("root", 1), ("12x", 1)),
)
def test_api_runtime_uid_is_read_from_hardened_attested_image_and_validated(
    tmp_path: Path, runtime_uid: str, expected: int,
) -> None:
    events = tmp_path / "events"
    image = "registry.local/api@sha256:" + "a" * 64
    config = json.dumps({"services": {"api": {"image": image}}})
    command = f'''source "{UPDATE_SCRIPT}"
docker() {{
  if [ "$1" = compose ]; then printf '%s\n' "$CONFIG"; return; fi
  printf '<%s>\n' "$@" > '{events}'
  printf '%s\n' "$RUNTIME_UID"
}}
COMPOSE_PROJECT=contract-test
ATTESTED_API_IMAGE='{image}'
resolve_api_runtime_identity
'''
    result = subprocess.run(
        ["bash", "-c", command],
        env={
            **os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1",
            "CONFIG": config, "RUNTIME_UID": runtime_uid,
        },
        capture_output=True, text=True,
    )
    assert result.returncode == expected
    assert events.read_text(encoding="utf-8").splitlines() == [
        "<run>", "<--rm>", "<--pull>", "<never>", "<--network>", "<none>",
        "<--read-only>", "<--cap-drop>", "<ALL>", "<--security-opt>",
        "<no-new-privileges>", "<--entrypoint>", "<id>", f"<{image}>", "<-u>",
    ]
    if expected:
        assert "runtime UID must be a non-zero integer" in result.stderr


@pytest.mark.parametrize("missing", ("setfacl", "getfacl"))
def test_shared_data_acl_requires_acl_tools(tmp_path: Path, missing: str) -> None:
    shared = tmp_path / "shared"
    data = shared / "data"
    data.mkdir(parents=True)
    command = f'''source "{UPDATE_SCRIPT}"
command() {{ [ "$1" = -v ] || return 99; [ "$2" != "$MISSING" ]; }}
SHARED_ROOT='{shared}'
configure_shared_data_acl '{data}' 10001 995
'''
    result = subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1", "MISSING": missing},
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert f"{missing} is required" in result.stderr


def test_shared_data_acl_is_exact_bounded_recursive_and_defaulted(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    data = shared / "data"
    (data / "nested").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    events = tmp_path / "events"
    command = f'''source "{UPDATE_SCRIPT}"
command() {{ [ "$1" = -v ]; }}
setfacl() {{ printf '<%s>\n' "$@" >> '{events}'; }}
getfacl() {{ printf '%s\n' user:10001:rwx user:995:rwx default:user:10001:rwx default:user:995:rwx; }}
SHARED_ROOT='{shared}'
configure_shared_data_acl "$TARGET" 10001 995
'''
    rejected = subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1", "TARGET": str(outside)},
        capture_output=True, text=True,
    )
    assert rejected.returncode != 0
    assert "exact shared data tree" in rejected.stderr
    assert not events.exists()

    accepted = subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1", "TARGET": str(data)},
        capture_output=True, text=True,
    )
    assert accepted.returncode == 0, accepted.stderr
    calls = events.read_text(encoding="utf-8")
    assert "<-P>" in calls and "<u:10001:rwX,u:995:rwX,m::rwX>" in calls
    assert calls.count("<d:u:10001:rwx,d:u:995:rwx,d:m::rwx>") == 2
    assert f"<{data}>" in calls and f"<{data / 'nested'}>" in calls
    assert "o::" not in calls and str(outside) not in calls


def test_shared_data_runtime_probes_use_only_exact_data_mount_and_both_identities(
    tmp_path: Path,
) -> None:
    events = tmp_path / "events"
    data = tmp_path / "shared" / "data"
    data.mkdir(parents=True)
    image = "registry.local/api@sha256:" + "b" * 64
    command = f'''source "{UPDATE_SCRIPT}"
docker() {{ printf 'docker <%s>\n' "$@" >> '{events}'; }}
runuser() {{ printf 'runuser <%s>\n' "$@" >> '{events}'; }}
SHARED_ROOT='{data.parent}'
verify_shared_data_access '{data}' '{image}' 10001
'''
    result = subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    calls = events.read_text(encoding="utf-8")
    for token in (
        "docker <--pull>", "docker <never>", "docker <--network>", "docker <none>",
        "docker <--read-only>", "docker <--cap-drop>", "docker <ALL>",
        "docker <no-new-privileges>",
        f"docker <type=bind,src={data},dst=/app/data>", "docker <EXPECTED_UID=10001>",
        "knowledge_matrix.json", "hermes_chat_runs.sqlite3", ".incremental-compile.lock",
        "vault/raw/dialogues/tenants", "runuser <-u>", "runuser <quantumn-hermes>",
    ):
        assert token in calls
    assert calls.count("docker <type=bind,") == 1


def test_rollback_health_uses_restored_legacy_bridge_address_not_candidate(tmp_path: Path) -> None:
    env_file = tmp_path / "hermes-bridge.env"
    env_file.write_text("HERMES_BRIDGE_BIND_ADDRESS=172.18.0.1\n", encoding="utf-8")
    events = tmp_path / "events"
    command = f'''source "{UPDATE_SCRIPT}"
verify_application_services() {{ printf '%s\n' applications >> '{events}'; }}
systemctl() {{ return 0; }}
ip() {{ printf '%s\n' '7: br-old inet 172.18.0.1/16 scope global br-old'; }}
docker() {{ printf '%s\n' "$*" >> '{events}'; [[ "$*" == *172.18.0.1* ]]; }}
HERMES_BRIDGE_ENV_FILE='{env_file}'
HERMES_BRIDGE_BIND_ADDRESS=172.19.0.1
COMPOSE_PROJECT=contract-test
BRIDGE_WAS_ACTIVE=1
CHAT_WORKER_WAS_ACTIVE=1
verify_rollback_health
'''
    result = subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    calls = events.read_text(encoding="utf-8")
    assert "host.docker.internal" in calls
    assert "http://172.18.0.1:9118/health" in calls
    assert "172.19.0.1" not in calls


@pytest.mark.parametrize("restored", ("172.18.0.1;true", "203.0.113.8", "172.18.0.2"))
def test_rollback_health_rejects_malformed_public_or_unassigned_restored_address(
    tmp_path: Path, restored: str,
) -> None:
    env_file = tmp_path / "hermes-bridge.env"
    env_file.write_text(f"HERMES_BRIDGE_BIND_ADDRESS={restored}\n", encoding="utf-8")
    command = f'''source "{UPDATE_SCRIPT}"
verify_application_services() {{ return 0; }}
systemctl() {{ return 0; }}
ip() {{ printf '%s\n' '7: br-old inet 172.18.0.1/16 scope global br-old'; }}
docker() {{ return 99; }}
HERMES_BRIDGE_ENV_FILE='{env_file}'
BRIDGE_WAS_ACTIVE=1
CHAT_WORKER_WAS_ACTIVE=1
verify_rollback_health
'''
    result = subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True, text=True,
    )
    assert result.returncode != 0


def test_rollback_image_snapshot_uses_container_refs_for_build_only_services(
    tmp_path: Path,
) -> None:
    current = tmp_path / "current"
    rollback = tmp_path / "rollback"
    current.mkdir()
    rollback.mkdir()
    config = json.dumps({"services": {
        service: (
            {"image": PRODUCTION_ROLLBACK_REFS[service]}
            if service in ("postgres", "redis")
            else {"build": {"context": "."}}
        )
        for service in MANAGED_COMPOSE_SERVICES
    }})
    image_ids = {service: "sha256:" + f"{index:x}" * 64
                 for index, service in enumerate(MANAGED_COMPOSE_SERVICES, 1)}
    inspect_cases = "\n".join(
        f"    {service}-container) image_id='{image_id}'; "
        f"image_ref='{PRODUCTION_ROLLBACK_REFS[service]}' ;;"
        for service, image_id in image_ids.items()
    )
    command = f'''source "{UPDATE_SCRIPT}"
docker() {{
  if [ "$1" = compose ] && [[ "$*" == *" config --format json"* ]]; then printf '%s\n' "$CONFIG"; return; fi
  if [ "$1" = compose ] && [[ "$*" == *" ps -q --all "* ]]; then printf '%s-container\n' "${{@: -1}}"; return; fi
  if [ "$1 $2" = 'image inspect' ]; then printf '%s\n' "${{@: -1}}"; return; fi
  if [ "$1" = inspect ]; then
    case "${{@: -1}}" in
{inspect_cases}
      *) return 98 ;;
    esac
    if [[ "$3" == *Config.Image* ]]; then printf '%s\n' "$image_ref"; else printf '%s\n' "$image_id"; fi
    return
  fi
  return 99
}}
CURRENT_DIR='{current}'
UNIT_BACKUP_DIR='{rollback}'
COMPOSE_PROJECT=contract-test
snapshot_managed_images
'''
    result = subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1", "CONFIG": config},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (rollback / "compose-images.tsv").read_text(encoding="utf-8").splitlines() == [
        f"{service}\t{image_ids[service]}\t"
        f"{PRODUCTION_ROLLBACK_REFS[service]}{'' if service in ('postgres', 'redis') else ':latest'}"
        for service in MANAGED_COMPOSE_SERVICES
    ]


def test_rollback_image_reference_normalization_is_registry_port_aware() -> None:
    command = f'''source "{UPDATE_SCRIPT}"
normalize_mutable_image_reference registry.local:5000/team/api
normalize_mutable_image_reference registry.local:5000/team/api:old
'''
    result = subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "registry.local:5000/team/api:latest",
        "registry.local:5000/team/api:old",
    ]


@pytest.mark.parametrize("mode", (
    "missing-service", "missing-container", "duplicate-container", "missing-ref",
    "digest-ref", "id-ref", "malformed-ref", "bad-id",
))
def test_rollback_image_snapshot_fails_closed_for_missing_or_invalid_state(
    tmp_path: Path, mode: str,
) -> None:
    current = tmp_path / "current"
    rollback = tmp_path / "rollback"
    current.mkdir()
    rollback.mkdir()
    services = {name: {"build": {"context": "."}} for name in MANAGED_COMPOSE_SERVICES}
    if mode == "missing-service":
        del services["redis"]
    command = f'''source "{UPDATE_SCRIPT}"
docker() {{
  if [ "$1" = compose ] && [[ "$*" == *" config --format json"* ]]; then printf '%s\n' "$CONFIG"; return; fi
  if [ "$1" = compose ]; then
    service="${{@: -1}}"
    [ "$MODE" = missing-container ] && [ "$service" = redis ] && return
    printf '%s-container\n' "$service"
    [ "$MODE" = duplicate-container ] && [ "$service" = redis ] && printf '%s-container-2\n' "$service"
    return
  fi
  if [ "$1" = inspect ]; then
    image_id="sha256:$(printf '%064d' 0)"
    image_ref="registry.local:5000/team/${{@: -1}}"
    [ "$MODE" = bad-id ] && [ "${{@: -1}}" = redis-container ] && image_id=invalid
    [ "$MODE" = missing-ref ] && [ "${{@: -1}}" = redis-container ] && image_ref=
    [ "$MODE" = digest-ref ] && [ "${{@: -1}}" = redis-container ] && image_ref="redis@sha256:$(printf '%064d' 0)"
    [ "$MODE" = id-ref ] && [ "${{@: -1}}" = redis-container ] && image_ref="sha256:$(printf '%064d' 0)"
    [ "$MODE" = malformed-ref ] && [ "${{@: -1}}" = redis-container ] && image_ref='UPPER/repo'
    if [[ "$3" == *Config.Image* ]]; then printf '%s\n' "$image_ref"; else printf '%s\n' "$image_id"; fi
    return
  fi
  printf 'sha256:%064d\n' 0
}}
CURRENT_DIR='{current}'
UNIT_BACKUP_DIR='{rollback}'
COMPOSE_PROJECT=contract-test
snapshot_managed_images
'''
    result = subprocess.run(
        ["bash", "-c", command],
        env={
            **os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1",
            "CONFIG": json.dumps({"services": services}), "MODE": mode,
        },
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert not (rollback / "compose-images.tsv").exists()


def test_rollback_retags_and_verifies_every_old_image_before_compose_up(tmp_path: Path) -> None:
    snapshot = tmp_path / "compose-images.tsv"
    records = []
    cases = []
    for index, service in enumerate(MANAGED_COMPOSE_SERVICES, 1):
        image_id = "sha256:" + f"{index:x}" * 64
        ref = PRODUCTION_ROLLBACK_REFS[service]
        if service not in ("postgres", "redis"):
            ref += ":latest"
        records.append(f"{service}\t{image_id}\t{ref}\n")
        cases.append(f"    {ref}) printf '%s\\n' '{image_id}' ;;")
    snapshot.write_text("".join(records), encoding="utf-8")
    events = tmp_path / "events"
    command = f'''source "{UPDATE_SCRIPT}"
stat() {{ [ "$2" = '%u' ] && printf '0\n' || printf '600\n'; }}
restore_managed_units() {{ return 0; }}
restart_hermes_runtime() {{ return 0; }}
verify_rollback_health() {{ return 0; }}
docker() {{
  if [ "$1 $2" = 'image tag' ]; then printf 'tag %s %s\n' "$3" "$4" >> '{events}'; return; fi
  if [ "$1 $2" = 'image inspect' ]; then
    printf 'inspect %s\n' "${{@: -1}}" >> '{events}'
    case "${{@: -1}}" in
{chr(10).join(cases)}
      *) return 98 ;;
    esac
    return
  fi
  printf 'compose %s\n' "$*" >> '{events}'
}}
IMAGE_ROLLBACK_FILE='{snapshot}'
CURRENT_DIR='{tmp_path}'
COMPOSE_PROJECT=contract-test
SWITCHED=0
BRIDGE_WORKER_VENV_SWITCHED=0
rollback_deployment
'''
    result = subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    lines = events.read_text(encoding="utf-8").splitlines()
    compose_index = next(i for i, line in enumerate(lines) if line.startswith("compose "))
    assert compose_index == 16
    assert all(line.startswith("tag ") for line in lines[:8])
    assert all(line.startswith("inspect ") for line in lines[8:16])
    assert lines[compose_index] == "compose compose -p contract-test up -d --no-build --pull never"


@pytest.mark.parametrize("mode", ("missing-record", "identity-mismatch"))
def test_rollback_image_restore_fails_closed_for_missing_record_or_identity_mismatch(
    tmp_path: Path, mode: str,
) -> None:
    snapshot = tmp_path / "compose-images.tsv"
    records = []
    for service in MANAGED_COMPOSE_SERVICES:
        if mode == "missing-record" and service == "redis":
            continue
        records.append(f"{service}\t{'sha256:' + 'a' * 64}\tregistry.local/{service}:old\n")
    snapshot.write_text("".join(records), encoding="utf-8")
    command = f'''source "{UPDATE_SCRIPT}"
stat() {{ [ "$2" = '%u' ] && printf '0\n' || printf '600\n'; }}
docker() {{
  [ "$1 $2" = 'image tag' ] && return
  [ "$MODE" = identity-mismatch ] && [ "${{@: -1}}" = registry.local/redis:old ] && {{ printf 'sha256:%064d\n' 0; return; }}
  printf 'sha256:%064s\n' a | tr ' ' a
}}
IMAGE_ROLLBACK_FILE='{snapshot}'
restore_managed_images
'''
    result = subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1", "MODE": mode},
        capture_output=True, text=True,
    )
    assert result.returncode != 0


def test_code_only_symlink_rollback_cannot_pass_without_image_snapshot(tmp_path: Path) -> None:
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.mkdir()
    new.mkdir()
    app = tmp_path / "app"
    app.symlink_to(new)
    events = tmp_path / "events"
    command = f'''source "{UPDATE_SCRIPT}"
restore_managed_units() {{ return 0; }}
mv() {{ rm -f "$3"; command mv "$2" "$3"; }}
docker() {{ printf '%s\n' "$*" >> '{events}'; }}
CURRENT_DIR='{old}'
APP_LINK='{app}'
IMAGE_ROLLBACK_FILE='{tmp_path / "missing.tsv"}'
SWITCHED=1
BRIDGE_WORKER_VENV_SWITCHED=0
rollback_deployment
'''
    result = subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert app.resolve() == old
    assert not events.exists()


def test_offline_images_extract_each_field_without_separator_parsing_and_validate_metadata(
    tmp_path: Path,
) -> None:
    services = (
        "postgres", "redis", "api", "workflow-worker", "planning-worker",
        "agent-evaluation-worker", "taskboard", "frontend",
    )
    digest = "sha256:" + "a" * 64
    service_configs = {
        service: {"image": f"registry.local/{service}:release"} for service in services
    }
    service_configs["postgres"]["healthcheck"] = {"test": ["CMD-SHELL", "true"]}
    for service in ("postgres", "redis"):
        service_configs[service]["ports"] = [{"host_ip": "127.0.0.1"}]
    attestations = tmp_path / "images.attested"
    attestations.write_text(
        "".join(f"{service}={digest}\n" for service in services), encoding="utf-8"
    )
    command = f'''source "{UPDATE_SCRIPT}"
stat() {{ [ "$2" = '%u' ] && printf '0\n' || printf '600\n'; }}
docker() {{
  if [ "$1" = compose ]; then printf '%s\n' "$CONFIG"; return; fi
  image="${{@: -1}}"
  service="${{image#registry.local/}}"; service="${{service%:release}}"
  [ "$CHECK" = missing ] && [ "$service" = redis ] && return 1
  operating_system=linux; architecture=amd64; user=1000; health='{{"Test":["CMD","true"]}}'; actual='{digest}'
  [ "$CHECK" = os ] && [ "$service" = postgres ] && operating_system=windows
  [ "$CHECK" = architecture ] && [ "$service" = redis ] && architecture=arm64
  [ "$CHECK" = hash ] && [ "$service" = postgres ] && actual='sha256:{'b' * 64}'
  case "$CHECK" in root|0|00|00:1000) [ "$service" = postgres ] && user="$CHECK" ;; esac
  [ "$CHECK" = health ] && [ "$service" = redis ] && health=null
  [ "$CHECK" = disabled-health ] && [ "$service" = redis ] && health='{{"Test":["NONE"]}}'
  [ "$CHECK" = empty-health ] && [ "$service" = redis ] && health='{{"Test":["CMD-SHELL",""]}}'
  [ "$CHECK" = missing-health-command ] && [ "$service" = redis ] && health='{{"Test":["CMD-SHELL"]}}'
  case "$4" in
    '{{{{.Id}}}}') printf '%s\n' "$actual" ;;
    '{{{{.Os}}}}') printf '%s\n' "$operating_system" ;;
    '{{{{.Architecture}}}}') printf '%s\n' "$architecture" ;;
    '{{{{.Config.User}}}}') printf '%s\n' "$user" ;;
    '{{{{json .Config.Healthcheck}}}}') printf '%s\n' "$health" ;;
    *'\\t'*) printf '%s\\\\t%s\\\\t%s\\\\t%s\n' "$actual" "$architecture" "$user" "$health" ;;
    *) return 98 ;;
  esac
}}
SHARED_ROOT='{tmp_path}'
COMPOSE_PROJECT=contract-test
AI_LAB_OFFLINE_IMAGE_ATTESTATIONS='{attestations}'
verify_offline_images
'''
    cases = (
        ("valid", 0), ("missing", 1), ("os", 1), ("architecture", 1), ("hash", 1),
        ("root", 1), ("0", 1), ("00", 1), ("00:1000", 1), ("health", 1),
        ("disabled-health", 1), ("empty-health", 1), ("missing-health-command", 1),
        ("missing-record", 1), ("duplicate", 1),
        ("unexpected", 1), ("malformed", 1), ("compose-health", 1),
        ("public-binding", 1),
    )
    for check, expected in cases:
        config = json.loads(json.dumps({"services": service_configs}))
        if check == "compose-health":
            config["services"]["postgres"]["healthcheck"] = {"test": ["NONE"]}
        elif check == "public-binding":
            config["services"]["redis"]["ports"][0]["host_ip"] = "0.0.0.0"
        records = [f"{service}={digest}" for service in services]
        if check == "missing-record":
            records.pop()
        elif check == "duplicate":
            records.append(records[0])
        elif check == "unexpected":
            records.append(f"other={digest}")
        elif check == "malformed":
            records[0] += " trailing"
        attestations.write_text("\n".join(records) + "\n", encoding="utf-8")
        result = subprocess.run(
            ["bash", "-c", command],
            env={
                **os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1",
                "CONFIG": json.dumps(config), "CHECK": check,
            },
            capture_output=True, text=True,
        )
        assert result.returncode == expected, f"{check}: {result.stderr}"


def test_production_update_is_serialized_preflighted_and_offline_only() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    preflight = script.index("preflight_hermes_bridge_network\n", script.index("CURRENT_DIR="))
    first_container_switch = script.index('docker compose -p "$COMPOSE_PROJECT" run --rm')
    first_unit_switch = script.index("install_hermes_units\n", script.index("SWITCHED=1"))
    assert "flock -n 9" in script
    assert preflight < first_container_switch < first_unit_switch
    assert "candidate host-gateway address does not match the preflight address" in script
    assert "verify_offline_images\n" in script
    assert 'up -d --no-build --pull never' in script
    assert script.count('run --rm --no-deps --pull never') == 1
    assert 'docker run --rm --pull never --network none --read-only' in script
    assert 'docker compose -p "$COMPOSE_PROJECT" build' not in script
    assert 'up -d --build' not in script


def test_rollback_restores_units_links_and_verifies_runtime_without_suppression() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    rollback = script[script.index("rollback_deployment() {"):script.index(
        "if [ \"${AI_LAB_UPDATE_LIBRARY_ONLY", script.index("rollback_deployment() {")
    )]
    for contract in (
        "restore_managed_units || return 1",
        "systemctl daemon-reload || return 1",
        'mv -Tf "$rollback_venv_link" "$BRIDGE_WORKER_VENV_LINK" || return 1',
        'mv -Tf "$rollback_certbot_link" "$CERTBOT_VENV_LINK" || return 1',
        'mv -Tf "$rollback_link" "$APP_LINK" || return 1',
        "verify_application_services || return 1",
    ):
        assert contract in script
    assert "|| true" not in rollback


@pytest.mark.parametrize("had_link", (False, True))
def test_rollback_restores_or_removes_certbot_link(tmp_path: Path, had_link: bool) -> None:
    old = tmp_path / "old-certbot"
    new = tmp_path / "new-certbot"
    for target in (old, new):
        (target / "bin").mkdir(parents=True)
        certbot = target / "bin" / "certbot"
        certbot.touch()
        certbot.chmod(0o755)
    link = tmp_path / "certbot-venv"
    link.symlink_to(new)
    command = f'''source "{UPDATE_SCRIPT}"
restore_managed_units() {{ return 0; }}
restore_managed_images() {{ return 0; }}
restart_hermes_runtime() {{ return 0; }}
verify_rollback_health() {{ return 0; }}
docker() {{ return 0; }}
mv() {{ rm -f "$3"; command mv "$2" "$3"; }}
CURRENT_DIR='{tmp_path}'
COMPOSE_PROJECT=contract-test
SWITCHED=0
BRIDGE_WORKER_VENV_SWITCHED=0
CERTBOT_VENV_LINK='{link}'
CERTBOT_VENV_BEFORE='{old}'
CERTBOT_VENV_HAD_LINK={int(had_link)}
CERTBOT_VENV_SWITCHED=1
rollback_deployment
'''
    result = subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    if had_link:
        assert link.resolve() == old
    else:
        assert not link.exists() and not link.is_symlink()


def test_failed_release_diagnostics_run_before_rollback_restore() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    cleanup = script[script.index("cleanup() {"):script.index("trap cleanup EXIT")]
    assert cleanup.index("capture_failed_release_diagnostics\n") < cleanup.index(
        "rollback_deployment"
    )

    command = f'''source "{UPDATE_SCRIPT}"
docker() {{ return 1; }}
COMPOSE_PROJECT=contract-test
capture_failed_release_diagnostics
printf 'rollback-continues\n'
'''
    result = subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1"},
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert result.stdout == "rollback-continues\n"


def test_failed_release_diagnostics_are_bounded_and_do_not_inspect_secrets() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    diagnostics = script[script.index("capture_failed_release_diagnostics() {"):script.index(
        "normalize_mutable_image_reference() {"
    )]
    assert "managed_compose_services" in diagnostics
    assert "docker compose" in diagnostics and " ps --format " in diagnostics
    assert "docker logs --timestamps --since 10m --tail 200" in diagnostics
    assert ".Config.Image" in diagnostics
    assert ".State.Health.Log" in diagnostics
    for forbidden in (
        ".Config.Env", ".Config.Cmd", ".Config.Labels", ".Mounts",
        "docker compose config", "environment",
    ):
        assert forbidden not in diagnostics


def test_certificate_renewal_units_use_safe_locked_wrapper() -> None:
    service = (SYSTEMD_DIR / "ai-lab-certbot-renew.service").read_text(encoding="utf-8")
    timer = (SYSTEMD_DIR / "ai-lab-certbot-renew.timer").read_text(encoding="utf-8")
    wrapper = (UPDATE_SCRIPT.parents[1] / "scripts/renew_tls_certificate.sh").read_text(encoding="utf-8")
    assert "scripts/renew_tls_certificate.sh" in service
    assert "Persistent=true" in timer
    assert "flock -n 9" in wrapper
    assert "setfacl -m u:101:r--" in wrapper
    assert "setpriv --reuid=101" in wrapper
    assert 'TERM=dumb "$CERTBOT" renew --cert-name "$TLS_CERT_NAME" --non-interactive --quiet' in wrapper
    assert '"$CERTBOT" renew --cert-name "$TLS_CERT_NAME" --non-interactive --quiet' in wrapper
    assert "certificate and key do not match" in wrapper
    assert "frontend recovery after certificate renewal failed" in wrapper


def test_certificate_renewal_preflight_requires_exact_certbot_runtime() -> None:
    wrapper = (UPDATE_SCRIPT.parents[1] / "scripts/renew_tls_certificate.sh").read_text(encoding="utf-8")
    assert "CERTBOT=/opt/certbot-venv/bin/certbot" in wrapper
    assert "CERTBOT_VERSION=5.8.0" in wrapper
    assert '[ -x "$CERTBOT" ]' in wrapper
    assert '[ "$(TERM=dumb "$CERTBOT" --version 2>/dev/null)" = "certbot $CERTBOT_VERSION" ]' in wrapper
    assert "$CERTBOT --version 2>&1" not in wrapper
    assert wrapper.index("verify_certbot_runtime\n") < wrapper.index(
        '[ "${1:-}" = "--preflight-only" ] && exit 0'
    )
    assert 'TERM=dumb "$CERTBOT" renew --cert-name "$TLS_CERT_NAME" --non-interactive --quiet' in wrapper


def test_certificate_renewal_frontend_starts_are_dependency_safe() -> None:
    wrapper = (UPDATE_SCRIPT.parents[1] / "scripts/renew_tls_certificate.sh").read_text(encoding="utf-8")
    command = 'docker compose -p "$COMPOSE_PROJECT" up -d --no-deps --no-build --pull never frontend'
    assert wrapper.count(command) == 2
    assert 'up -d --no-build --pull never frontend' not in wrapper


def test_every_backend_execution_client_sends_the_internal_token() -> None:
    root = UPDATE_SCRIPT.parents[1]
    expected_counts = {
        "backend/api/chat.py": 8,
        "backend/api/agents.py": 1,
        "backend/api/orchestration.py": 2,
        "backend/services/agent_scheduler.py": 1,
        "backend/services/clarification_planner.py": 1,
        "backend/services/workflow_planner.py": 1,
        "backend/services/workflow_planning.py": 1,
        "backend/services/workflow_executor.py": 1,
        "backend/services/agent_evaluation.py": 1,
    }
    for path, minimum in expected_counts.items():
        text = (root / path).read_text(encoding="utf-8")
        assert text.count("X-Hermes-Internal-Token") >= minimum, path


def test_bridge_execution_routes_all_use_the_strict_guard() -> None:
    bridge = BRIDGE_SCRIPT.read_text(encoding="utf-8")
    assert "def _require_internal(token: str | None)" in bridge
    assert "_require_internal_strict(token)" in bridge
    for function in (
        "chat_stream", "chat", "start_workflow_plan", "workflow_plan",
        "start_agent_evaluation", "start_workflow_run",
    ):
        start = bridge.index(f"async def {function}(")
        body = bridge[start:bridge.find("\n\n@app.", start)]
        assert "_require_internal" in body, function
