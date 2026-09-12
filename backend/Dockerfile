# AI Lab Platform — API 镜像
# Keep the deployed Python minor; immutable multi-platform base + hashed locks.
FROM python:3.12.14-alpine3.23@sha256:167bc85084c9df34480efc26b4528fb68feaa8a79183b5658952137025b6f061

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    HOME=/home/ailab

ARG AI_LAB_RUNTIME_UID=10001
ARG AI_LAB_RUNTIME_GID=10001
RUN apk add --no-cache libuuid=2.41.6-r1 \
        libreoffice font-noto font-noto-cjk=0_git20220127-r1 \
    && addgroup -S -g "$AI_LAB_RUNTIME_GID" ailab \
    && adduser -S -D -u "$AI_LAB_RUNTIME_UID" -G ailab -h /home/ailab -s /sbin/nologin ailab

WORKDIR /app

# Source requirements describe intent; deployments install only reviewed locks.
# Bootstrap is pinned too: jieba ships an sdist, so no floating PEP517 downloads.
COPY requirements.lock requirements-build.lock /app/
RUN python -m pip install --require-hashes -r requirements-build.lock \
    && python -m pip install --require-hashes --no-build-isolation -r requirements.lock \
    && python -m pip uninstall -y setuptools wheel \
    && python -m pip check

# 再拷代码
COPY backend /app/backend
COPY config /app/config
COPY scripts /app/scripts

# 预建 harness 运行目录（manifests/runtime 由 runtime.py 懒创建，预建保证契约审计第一天即通过）
RUN mkdir -p /app/data/manifests /app/data/runtime /home/ailab/.hermes/skills /home/ailab/.hermes/profiles \
    && chown -R ailab:ailab /app/data /home/ailab

ARG AI_LAB_SOURCE_SHA
LABEL org.opencontainers.image.revision=$AI_LAB_SOURCE_SHA

EXPOSE 8000

USER ailab

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3)"]

# 默认启动命令（compose 可覆盖）
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
