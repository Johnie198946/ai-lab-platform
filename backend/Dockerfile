# AI Lab Platform — API 镜像
# 轻量镜像: python:3.12-slim + 运行依赖
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# 先装依赖（利用层缓存；大陆服务器使用阿里云 pip 镜像加速）
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt pyyaml

# 再拷代码
COPY backend /app/backend
COPY config /app/config
COPY scripts /app/scripts

# 预建 harness 运行目录（manifests/runtime 由 runtime.py 懒创建，预建保证契约审计第一天即通过）
RUN mkdir -p /app/data/manifests /app/data/runtime

EXPOSE 8000

# 默认启动命令（compose 可覆盖）
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
