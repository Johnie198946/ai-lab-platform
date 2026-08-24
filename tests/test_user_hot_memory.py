from pathlib import Path

import pytest

from backend.services.user_hot_memory import (
    HERMES_USER_MEMORY_MAX_CHARS,
    MemoryOverflowError,
    add_memory,
    list_memory,
    snapshot,
)


def test_user_memory_isolated_by_tenant_and_user(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AI_LAB_USER_MEMORY_ROOT", str(tmp_path))
    add_memory("tenant-a", "user-a", kind="preference", content="用户偏好结论先行", status="confirmed")
    add_memory("tenant-a", "user-b", kind="preference", content="用户 B 的私有偏好", status="confirmed")
    add_memory("tenant-b", "user-a", kind="preference", content="租户 B 的私有偏好", status="confirmed")
    value = snapshot("tenant-a", "user-a")
    assert "用户偏好结论先行" in value
    assert "用户 B 的私有偏好" not in value
    assert "租户 B 的私有偏好" not in value


def test_snapshot_respects_hermes_user_limit(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AI_LAB_USER_MEMORY_ROOT", str(tmp_path))
    add_memory("tenant-a", "user-a", kind="preference", content="稳定偏好" * 20, status="confirmed")
    assert len(snapshot("tenant-a", "user-a")) <= HERMES_USER_MEMORY_MAX_CHARS


def test_overflow_is_rejected_without_silent_truncation(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AI_LAB_USER_MEMORY_ROOT", str(tmp_path))
    with pytest.raises(MemoryOverflowError):
        add_memory("tenant-a", "user-a", kind="constraint", content="重要约束" * 500, status="confirmed")
    assert list_memory("tenant-a", "user-a") == []


def test_only_confirmed_memory_enters_snapshot(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AI_LAB_USER_MEMORY_ROOT", str(tmp_path))
    add_memory("tenant-a", "user-a", kind="preference", content="候选记忆", status="candidate")
    add_memory("tenant-a", "user-a", kind="preference", content="已确认记忆", status="confirmed")
    value = snapshot("tenant-a", "user-a")
    assert "已确认记忆" in value
    assert "候选记忆" not in value
