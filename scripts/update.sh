#!/bin/bash
# 服务器端一键更新：从 GitHub 拉取最新代码并重建
# 用法: bash scripts/update.sh [40位 commit SHA]
#
# 说明: 服务器位于中国大陆，github.com 直连被墙，但 codeload.github.com
# （代码包下载源）可达，因此通过官方 tarball 拉取，无需 git/deploy key。
# .env / data/（vault 镜像 + 数据库卷）不在仓库内，更新不受影响。

set -euo pipefail
cd "$(dirname "$0")/.."

if [ "$#" -ne 1 ] || [[ ! "$1" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "ERROR: 必须提供且仅提供一个精确的 40 位 commit SHA" >&2
  exit 2
fi
EXPECTED_SHA="$1"
SOURCE_REF="$EXPECTED_SHA"

echo "==> [1/4] 从 GitHub 拉取最新代码 (codeload)"
TARBALL=$(mktemp /tmp/ailab-src.XXXXXX.tgz)
cleanup() { rm -f "$TARBALL"; }
trap cleanup EXIT
curl -fsSL --retry 3 "https://codeload.github.com/Johnie198946/ai-lab-platform/tar.gz/$SOURCE_REF?cachebust=${EXPECTED_SHA}-$(date +%s)" \
  -o "$TARBALL"
tar xzf "$TARBALL" --strip-components=1 -C .
echo "    代码已更新: $(git log --oneline -1 2>/dev/null || echo '(无 git 元数据, 以文件为准)')"

echo "==> [2/4] 重建并重启服务"
# Hermes Bridge runs in its dedicated venv (outside the API image).  Install the
# credential-free DDGS provider when absent so the built-in web toolset passes
# Hermes' availability gate in the production sandbox.
if ! /opt/hermes/venv/bin/python3 -c 'import ddgs' >/dev/null 2>&1; then
  echo "    安装 Hermes DDGS 联网 provider"
  /opt/hermes/venv/bin/pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ 'ddgs>=9.0'
fi
docker compose up -d --build

echo "==> [3/4] 健康检查"
status=""
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
mkdir -p data/manifests data/runtime
if [ ! -e data/knowledge_matrix.json ]; then
  if [ ! -f data/vault/knowledge_matrix.json ]; then
    echo "ERROR: 缺少 Vault knowledge_matrix.json，无法建立运行契约入口" >&2
    exit 1
  fi
  rm -f data/knowledge_matrix.json
  ln -s vault/knowledge_matrix.json data/knowledge_matrix.json
fi
docker compose exec -T api python scripts/audit_runtime_contracts.py --data-dir /app/data

marker_tmp=$(mktemp .deployed-sha.XXXXXX)
trap 'rm -f "$TARBALL" "$marker_tmp"' EXIT
printf '%s\n' "$EXPECTED_SHA" > "$marker_tmp"
mv -f "$marker_tmp" .deployed-sha
