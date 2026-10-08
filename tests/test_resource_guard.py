from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "resource_guard.sh"
SERVICE = ROOT / "ops" / "systemd" / "ai-lab-resource-guard.service"
TIMER = ROOT / "ops" / "systemd" / "ai-lab-resource-guard.timer"


def test_resource_guard_uses_low_cost_health_signals() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert "MemAvailable" in script
    assert "/proc/loadavg" in script
    assert "SwapTotal" in script and "SwapFree" in script
    assert "--unix-socket /var/run/docker.sock" in script
    assert "http://localhost/_ping" in script
    assert "docker image" not in script
    assert "docker compose" not in script
    assert "logger -p daemon.warning" in script


def test_resource_guard_is_bounded_and_persistent() -> None:
    service = SERVICE.read_text(encoding="utf-8")
    timer = TIMER.read_text(encoding="utf-8")
    assert "Type=oneshot" in service
    assert "NoNewPrivileges=true" in service
    assert "ProtectSystem=strict" in service
    assert "StateDirectory=ai-lab-resource-guard" in service
    assert "OnUnitActiveSec=1min" in timer
    assert "Persistent=true" in timer
