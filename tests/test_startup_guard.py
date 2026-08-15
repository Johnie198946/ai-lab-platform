"""启动守卫测试：JWT secret 为空 → 开发态全可见 WARNING。"""
import logging

import pytest


def test_guard_warns_when_secret_empty(monkeypatch, caplog):
    import backend.api.auth as auth

    monkeypatch.setattr(auth, "AUTHEN_JWT_SECRET", "")
    with caplog.at_level(logging.WARNING):
        assert auth.check_dev_visibility_guard() is True
    assert any("隔离承诺不生效" in r.message for r in caplog.records)


def test_guard_silent_when_secret_present(monkeypatch, caplog):
    import backend.api.auth as auth

    monkeypatch.setattr(auth, "AUTHEN_JWT_SECRET", "real-secret")
    with caplog.at_level(logging.WARNING):
        assert auth.check_dev_visibility_guard() is False
    assert not any("隔离承诺不生效" in r.message for r in caplog.records)
