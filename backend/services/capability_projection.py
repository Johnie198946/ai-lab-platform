"""Project capability truth from server facts only."""

from datetime import datetime, timedelta, timezone


def project_capability(*, connected: bool, checked_at: datetime | None, ttl_seconds: int, now: datetime | None = None) -> dict[str, object]:
    current = now or datetime.now(timezone.utc)
    if checked_at is None or checked_at.tzinfo is None:
        status = "UNCONNECTED"
    else:
        status = "CONNECTED" if connected and checked_at + timedelta(seconds=ttl_seconds) > current else "UNCONNECTED"
    return {"status": status, "truth": "LIVE" if status == "CONNECTED" else "UNCONNECTED", "checked_at": checked_at.isoformat() if checked_at else None}


def project_plan_capability(
    *,
    compiler_status: str,
    checked_at: datetime | None,
    ttl_seconds: int,
    now: datetime | None = None,
) -> dict[str, object]:
    """Project readiness from a server compiler check, never from model DSL fields."""
    return project_capability(
        connected=compiler_status == "compiled",
        checked_at=checked_at,
        ttl_seconds=ttl_seconds,
        now=now,
    )
