from pathlib import Path


UPDATE_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update.sh"


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
