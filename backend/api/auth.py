"""
Authen 统一认证集成 — Bearer JWT 本地验签

平台 API 要求 `Authorization: Bearer <Authen 签发的 JWT>`。
与 Authen 共享 HS256 对称密钥（AUTHEN_JWT_SECRET），本地验签，无需回调 Authen。

配置: AUTHEN_JWT_SECRET 为空时认证关闭（本地开发），配置后强制启用。
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

try:
    from jose import JWTError, jwt
except ImportError:  # pragma: no cover - jose 未装时给出明确错误
    jwt = None  # type: ignore
    JWTError = Exception  # type: ignore

AUTHEN_JWT_SECRET = os.environ.get("AUTHEN_JWT_SECRET", "")
AUTHEN_JWT_ALGORITHM = "HS256"

security = HTTPBearer(auto_error=False)


def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Dict[str, Any]:
    """FastAPI 依赖: 校验 Authen Bearer JWT，返回 token 载荷。"""
    if not AUTHEN_JWT_SECRET:
        # 认证未配置 → 放行（本地开发模式）
        return {"sub": "", "username": "dev"}
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="未认证: 缺少 Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if jwt is None:
        raise HTTPException(status_code=503, detail="python-jose 未安装")
    try:
        payload = jwt.decode(
            credentials.credentials,
            AUTHEN_JWT_SECRET,
            algorithms=[AUTHEN_JWT_ALGORITHM],
        )
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload
