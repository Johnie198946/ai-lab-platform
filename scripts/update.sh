#!/bin/bash
# 服务器端一键更新：从 GitHub 拉取最新代码并重建
# 用法: bash scripts/update.sh
#
# 说明: 服务器位于中国大陆，github.com 直连被墙，但 codeload.github.com
# （代码包下载源）可达，因此通过官方 tarball 拉取，无需 git/deploy key。
# .env / data/（vault 镜像 + 数据库卷）不在仓库内，更新不受影响。

set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> [1/3] 从 GitHub 拉取最新代码 (codeload)"
TARBALL=$(mktemp /tmp/ailab-src.XXXXXX.tgz)
curl -fsSL --retry 3 https://codeload.github.com/Johnie198946/ai-lab-platform/tar.gz/refs/heads/main \
  -o "$TARBALL"
tar xzf "$TARBALL" --strip-components=1 -C .
rm -f "$TARBALL"
echo "    代码已更新: $(git log --oneline -1 2>/dev/null || echo '(无 git 元数据, 以文件为准)')"

echo "==> [2/3] 重建并重启服务"
docker compose up -d --build

echo "==> [3/4] 健康检查"
for i in $(seq 1 30); do
  status=$(curl -sf http://127.0.0.1:8000/health || true)
  if [ -n "$status" ]; then
    echo "    API 就绪: $status"
    break
  fi
  sleep 2
done
if [ -z "${status:-}" ]; then
  echo "WARN: 30 秒内未就绪，请查看: docker compose logs api"
  exit 1
fi

echo "==> [4/4] 运行平台契约审计（容器内 Python 3.12，宿主机 3.6 兼容问题规避）"
docker compose exec -T api python scripts/audit_runtime_contracts.py --data-dir /app/data \
  || { echo "WARN: 契约审计未通过，请检查 harness 运行目录"; }
