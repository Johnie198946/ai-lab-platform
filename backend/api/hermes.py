"""Hermes serve 集成 API — Tab 1 官方 Web 容器认证通道（B-2-2 落地）。

- `GET /api/v1/hermes/serve-token`：返回 Hermes Dashboard 会话 Token
  （服务器环境变量 `HERMES_SERVE_TOKEN`，部署时与 serve 进程的
  `HERMES_DASHBOARD_SESSION_TOKEN` 保持同值，否则 401）。

双 token 边界（C-2）：
- iOS Keychain JWT（FastAPI `/authen-api`）→ Tab 2-4 原生业务；
- `HERMES_SERVE_TOKEN`（Hermes Dashboard）→ Tab 1 官方 Web；
- 本端点由 `require_auth` 保护，仅已登录客户端可取 serve token，互不覆盖。
"""

from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from backend.api.auth import require_auth

router = APIRouter(prefix="/api/v1/hermes", tags=["hermes"])


@router.get("/serve-token")
async def get_serve_token(
    _: Dict[str, Any] = Depends(require_auth),
) -> Dict[str, str]:
    """返回 Hermes Dashboard 会话 Token（= HERMES_SERVE_TOKEN）。

    由 iOS QuantumWebContainerView 在 WKWebView 加载完成后经 JSBridge
    注入 `window.__HERMES_SESSION_TOKEN__`；令牌缺失时返回 503，
    客户端应提示「Hermes 引擎未配置」而非静默 401。
    """
    token = os.environ.get("HERMES_SERVE_TOKEN", "")
    if not token:
        raise HTTPException(
            status_code=503,
            detail="HERMES_SERVE_TOKEN 未配置: 服务器 serve 认证令牌缺失",
        )
    return {"token": token}
