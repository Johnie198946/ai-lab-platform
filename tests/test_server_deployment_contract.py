from pathlib import Path
import subprocess


UPDATE_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update.sh"
SYSTEMD_DIR = UPDATE_SCRIPT.parents[1] / "ops" / "systemd"
BRIDGE_SCRIPT = UPDATE_SCRIPT.parents[1] / "scripts" / "hermes_bridge.py"

HERMES_ACCOUNT_HOME = "/var/lib/quantumn-hermes"
HERMES_HOME = f"{HERMES_ACCOUNT_HOME}/.hermes"
HERMES_AGENT_ROOT = f"{HERMES_HOME}/hermes-agent"
HERMES_PYTHON = f"{HERMES_AGENT_ROOT}/venv/bin/python"
HERMES_LAUNCHER = f"{HERMES_ACCOUNT_HOME}/.local/bin/hermes"


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
    assert 'install -d -o 0 -g 0 -m 0700 "$VAULT_ROOT/wiki/tenant"' in script
    assert 'install -d -o 0 -g 0 -m 0755 "$VAULT_ROOT/wiki/contributions"' in script


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
        assert f"ExecStart={HERMES_PYTHON}" in unit
        assert "PROVIDER=" not in unit
        assert "/opt/hermes" not in unit
        assert "127.0.0.1:7890" not in unit
        for proxy_variable in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
            assert f"Environment={proxy_variable}=" not in unit
    bridge = (SYSTEMD_DIR / "hermes-bridge.service").read_text(encoding="utf-8")
    worker = (SYSTEMD_DIR / "hermes-chat-worker.service").read_text(encoding="utf-8")
    assert "chat_run_worker" not in bridge
    assert "scripts.chat_run_worker" in worker


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
        "verify_hermes_install",
    ):
        assert contract in update
    assert "/opt/hermes" not in update
    assert "127.0.0.1:7890" not in update
    for proxy_variable in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        assert proxy_variable not in update


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
