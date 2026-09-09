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
os.environ.setdefault("HERMES_BRIDGE_INTERNAL_TOKEN", "test-internal-token")
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


@pytest.fixture(autouse=True)
def _business_tests_assume_agreement(request):
    """Business-unit fixtures assume acceptance; agreement integration tests don't.

    This is a test-only dependency override, never an environment bypass. It
    leaves real JWT authentication and all runtime contribution fences intact.
    """
    if request.node.path.name.startswith("test_agreement"):
        yield
        return
    from backend.main import app
    from backend.api.agreement import require_current_agreement
    from backend.api.auth import require_auth
    from fastapi import Depends

    async def accepted_business_principal(payload=Depends(require_auth)):
        return payload

    previous = app.dependency_overrides.get(require_current_agreement)
    app.dependency_overrides[require_current_agreement] = accepted_business_principal
    yield
    if previous is None:
        app.dependency_overrides.pop(require_current_agreement, None)
    else:
        app.dependency_overrides[require_current_agreement] = previous
