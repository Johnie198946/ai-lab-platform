"""pytest 全局配置 — 测试环境使用 SQLite 文件库(无本地 Postgres 也能跑 DB 测试)。

在 import 任何 backend 模块前设置 DATABASE_URL, 使 backend.db 创建 SQLite 引擎。
"""

from __future__ import annotations

import os

# Legacy API fixtures mint minimal local JWTs. Provenance-specific tests enable
# strict mode explicitly; production defaults to strict mode.
os.environ.setdefault("AUTHEN_JWT_STRICT_PROVENANCE", "false")
import tempfile
from pathlib import Path

_TMP_DB = Path(tempfile.mkdtemp(prefix="ai-lab-test-")) / "test.db"
os.environ.setdefault(
    "DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DB}"
)
os.environ.setdefault("AUTHEN_JWT_SECRET", "test-secret")
# 知识库指向临时 vault(避免污染真实知识库)
os.environ.setdefault("AI_LAB_HOME", str(Path(tempfile.mkdtemp(prefix="ai-lab-vault-"))))


import asyncio

import pytest


@pytest.fixture(scope="session", autouse=True)
def _init_test_db():
    """所有测试前建表(TestClient 模块级创建不触发 lifespan, 需手动 init)。"""
    from backend.db import init_db

    asyncio.run(init_db())
    yield
