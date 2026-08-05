"""
统一错误处理中间件

所有异常 → 结构化 JSON 响应 + 日志
产品不能崩：每个请求都有兜底
"""

import traceback
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """全局异常兜底"""

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)

        except ValueError as e:
            return JSONResponse(
                status_code=400, content={"error": "bad_request", "detail": str(e)}
            )

        except PermissionError as e:
            return JSONResponse(
                status_code=403, content={"error": "forbidden", "detail": str(e)}
            )

        except LookupError as e:
            return JSONResponse(
                status_code=404, content={"error": "not_found", "detail": str(e)}
            )

        except Exception:
            # 未知异常：记录完整堆栈，返回通用错误
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={
                    "error": "internal_error",
                    "detail": (
                        "An unexpected error occurred."
                        " The team has been notified."
                    ),
                },
            )


def register_error_handlers(app):
    """注册到 FastAPI app"""
    app.add_middleware(ErrorHandlerMiddleware)
