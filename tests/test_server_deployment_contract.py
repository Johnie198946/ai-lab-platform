from pathlib import Path
import json
import os
import subprocess

import pytest
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
        assert unit in script
    assert 'if systemctl cat "$unit" >/dev/null 2>&1; then' in script
    assert 'systemctl restart "$unit"' in script
    assert 'hermes_restart_status=skipped_absent unit=$unit' in script


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
    assert 'repair_vault_runtime_permissions "$VAULT_ROOT"' in script
    assert 'repair_note_path_ancestors "$VAULT_ROOT"' in script
    assert 'chmod 0755 "$RELEASE_DIR"' in script
    assert 'chmod 0600 "$path"' in script
    assert 'local vault_root="$1" lock="$1/.incremental-compile.lock"' in script
    assert 'chmod 0600 "$lock"' in script
    assert 'for path in "$vault_root/raw" "$vault_root/raw/dialogues"' in script
    assert 'echo "ERROR: note path ancestor must be a real directory: $path"' in script
    assert 'data_probe=pathlib.Path(tempfile.mkdtemp' in script


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
    for proxy_variable in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        assert proxy_variable not in update


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


def test_bridge_binding_fails_closed_for_public_or_unassigned_addresses() -> None:
    for gateway, host_addresses in (
        ("203.0.113.10", "203.0.113.10/24"),
        ("172.17.0.1", "192.168.1.10/24"),
    ):
        command = f'''source "{UPDATE_SCRIPT}"
docker() {{
  if [ "$1" = compose ] && [[ "$*" == *"ps -q api"* ]]; then printf '%s\\n' api-container;
  elif [ "$1" = inspect ]; then printf '%s\\n' 'contract_default {gateway}';
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
    gateway_check = function.index('[ "$candidate_address" != "$HERMES_BRIDGE_BIND_ADDRESS" ]')
    hostname_check = function.index(
        "socket.gethostbyname('host.docker.internal') == '$HERMES_BRIDGE_BIND_ADDRESS'"
    )
    health_check = function.index("http://$HERMES_BRIDGE_BIND_ADDRESS:9118/health")
    assert gateway_check < hostname_check < health_check
    assert ".get('status') == 'ok'" in function


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
    assert 'printf \'%s\\0%s\\0\' "$HERMES_RUNTIME_VERSION" "$HERMES_RUNTIME_COMMIT"' in script
    assert 'chown quantumn-hermes:quantumn-hermes "$temp_dir"' in script
    assert 'mv -Tf "$next_link" "$BRIDGE_WORKER_VENV_LINK"' in script
    assert 'mv -Tf "$rollback_venv_link" "$BRIDGE_WORKER_VENV_LINK"' in script


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


def test_offline_images_use_compose_service_mapping_and_strict_metadata(tmp_path: Path) -> None:
    services = (
        "api", "workflow-worker", "planning-worker",
        "agent-evaluation-worker", "taskboard", "frontend",
    )
    digest = "sha256:" + "a" * 64
    config = json.dumps({
        "services": {service: {"image": f"registry.local/{service}:release"} for service in services}
    })
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
  [ "$CHECK" = missing ] && [ "$service" = workflow-worker ] && return 1
  architecture=amd64; user=1000; health='{{"Test":["CMD","true"]}}'; actual='{digest}'
  [ "$CHECK" = architecture ] && [ "$service" = planning-worker ] && architecture=arm64
  [ "$CHECK" = hash ] && [ "$service" = api ] && actual='sha256:{'b' * 64}'
  case "$CHECK" in root|0|00|00:1000) [ "$service" = taskboard ] && user="$CHECK" ;; esac
  [ "$CHECK" = health ] && [ "$service" = frontend ] && health=null
  [ "$CHECK" = disabled-health ] && [ "$service" = frontend ] && health='{{"Test":["NONE"]}}'
  printf '%s\t%s\t%s\t%s\n' "$actual" "$architecture" "$user" "$health"
}}
SHARED_ROOT='{tmp_path}'
COMPOSE_PROJECT=contract-test
AI_LAB_OFFLINE_IMAGE_ATTESTATIONS='{attestations}'
verify_offline_images
'''
    for check, expected in (
        ("valid", 0), ("missing", 1), ("architecture", 1), ("hash", 1),
        ("root", 1), ("0", 1), ("00", 1), ("00:1000", 1), ("health", 1),
        ("disabled-health", 1),
    ):
        result = subprocess.run(
            ["bash", "-c", command],
            env={
                **os.environ, "AI_LAB_UPDATE_LIBRARY_ONLY": "1",
                "CONFIG": config, "CHECK": check,
            },
            capture_output=True, text=True,
        )
        assert result.returncode == expected, result.stderr


def test_production_update_is_serialized_preflighted_and_offline_only() -> None:
    script = UPDATE_SCRIPT.read_text(encoding="utf-8")
    preflight = script.index("preflight_hermes_bridge_network\n", script.index("CURRENT_DIR="))
    first_container_switch = script.index('docker compose -p "$COMPOSE_PROJECT" run --rm')
    first_unit_switch = script.index("install_hermes_units\n", script.index("SWITCHED=1"))
    assert "flock -n 9" in script
    assert preflight < first_container_switch < first_unit_switch
    assert "candidate API Compose gateway does not match the preflight gateway" in script
    assert "verify_offline_images\n" in script
    assert 'up -d --no-build --pull never' in script
    assert script.count('run --rm --no-deps --pull never') == 2
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
        'mv -Tf "$rollback_link" "$APP_LINK" || return 1',
        "verify_application_services || return 1",
    ):
        assert contract in script
    assert "|| true" not in rollback


def test_certificate_renewal_units_use_safe_locked_wrapper() -> None:
    service = (SYSTEMD_DIR / "ai-lab-certbot-renew.service").read_text(encoding="utf-8")
    timer = (SYSTEMD_DIR / "ai-lab-certbot-renew.timer").read_text(encoding="utf-8")
    wrapper = (UPDATE_SCRIPT.parents[1] / "scripts/renew_tls_certificate.sh").read_text(encoding="utf-8")
    assert "scripts/renew_tls_certificate.sh" in service
    assert "Persistent=true" in timer
    assert "flock -n 9" in wrapper
    assert "setfacl -m u:101:r--" in wrapper
    assert "setpriv --reuid=101" in wrapper
    assert 'certbot renew --cert-name "$TLS_CERT_NAME"' in wrapper
    assert "certificate and key do not match" in wrapper
    assert "frontend recovery after certificate renewal failed" in wrapper


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
