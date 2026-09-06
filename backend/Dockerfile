# AI Lab Platform — API 镜像
# Keep the deployed Python minor; immutable multi-platform base + hashed locks.
FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

# Source requirements describe intent; deployments install only reviewed locks.
# Bootstrap is pinned too: jieba ships an sdist, so no floating PEP517 downloads.
COPY requirements.lock requirements-build.lock /app/
RUN python -m pip install --require-hashes -r requirements-build.lock \
    && python -m pip install --require-hashes --no-build-isolation -r requirements.lock \
    && python -m pip check

# 再拷代码
COPY backend /app/backend
COPY config /app/config
COPY scripts /app/scripts

# 预建 harness 运行目录（manifests/runtime 由 runtime.py 懒创建，预建保证契约审计第一天即通过）
RUN mkdir -p /app/data/manifests /app/data/runtime

EXPOSE 8000

# 默认启动命令（compose 可覆盖）
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
