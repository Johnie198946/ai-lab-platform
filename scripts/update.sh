#!/bin/bash
# 服务器端不可变发布：每个 SHA 解压到一个全新 release，验证后原子切换软链。
# 用法: bash scripts/update.sh <40位 commit SHA>

set -euo pipefail

if [ "$#" -ne 1 ] || [[ ! "$1" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "ERROR: 必须提供且仅提供一个精确的 40 位 commit SHA" >&2
  exit 2
fi

EXPECTED_SHA="${1,,}"
SHORT_SHA="${EXPECTED_SHA:0:12}"
APP_LINK="${AI_LAB_APP_LINK:-/opt/ai-lab-platform}"
RELEASE_ROOT="${AI_LAB_RELEASE_ROOT:-/opt/releases}"
SHARED_ROOT="${AI_LAB_SHARED_ROOT:-/opt/ai-lab-shared}"
COMPOSE_PROJECT="${AI_LAB_COMPOSE_PROJECT:-ai-lab-platform}"
RELEASE_DIR="$RELEASE_ROOT/ai-lab-platform-$SHORT_SHA"
CURRENT_DIR="$(readlink -f "$APP_LINK")"
TARBALL="$(mktemp /tmp/ailab-src.XXXXXX.tgz)"
STAGING_DIR="$(mktemp -d "$RELEASE_ROOT/.ai-lab-$SHORT_SHA.XXXXXX")"
SWITCHED=0
RUNTIME_CHANGED=0

case "$RELEASE_DIR" in
  "$RELEASE_ROOT"/ai-lab-platform-*) ;;
  *) echo "ERROR: 非法 release 路径: $RELEASE_DIR" >&2; exit 2 ;;
esac

if [ ! -d "$CURRENT_DIR" ]; then
  echo "ERROR: 当前 release 不存在: $CURRENT_DIR" >&2
  exit 1
fi
if [ -e "$RELEASE_DIR" ]; then
  echo "ERROR: release 已存在，拒绝覆盖: $RELEASE_DIR" >&2
  exit 1
fi

cleanup() {
  rc=$?
  trap - EXIT
  rm -f "$TARBALL"
  if [ "$rc" -ne 0 ] && [ "$RUNTIME_CHANGED" -eq 1 ]; then
    echo "WARN: 发布失败，恢复旧 release: $CURRENT_DIR" >&2
    if [ "$SWITCHED" -eq 1 ]; then
      rollback_link="$APP_LINK.rollback.$$"
      ln -s "$CURRENT_DIR" "$rollback_link"
      mv -Tf "$rollback_link" "$APP_LINK"
    fi
    cd "$CURRENT_DIR"
    docker compose -p "$COMPOSE_PROJECT" up -d --build || true
    systemctl restart hermes-bridge.service || true
  fi
  if [ "$SWITCHED" -eq 0 ] || [ "$rc" -ne 0 ]; then
    rm -rf "$STAGING_DIR"
    if [ -d "$RELEASE_DIR" ]; then
      rm -rf "$RELEASE_DIR"
    fi
  fi
  exit "$rc"
}
trap cleanup EXIT

echo "==> [1/6] 下载并解包 SHA $EXPECTED_SHA"
curl -fsSL --retry 3 \
  "https://codeload.github.com/Johnie198946/ai-lab-platform/tar.gz/$EXPECTED_SHA?cachebust=$EXPECTED_SHA-$(date +%s)" \
  -o "$TARBALL"
tar xzf "$TARBALL" --strip-components=1 -C "$STAGING_DIR"
test -f "$STAGING_DIR/docker-compose.yml"
test -f "$STAGING_DIR/scripts/update.sh"

echo "==> [2/6] 建立共享运行数据入口"
mkdir -p "$SHARED_ROOT"
if [ ! -f "$SHARED_ROOT/.env" ]; then
  install -m 600 "$CURRENT_DIR/.env" "$SHARED_ROOT/.env"
fi
for name in backups rollbacks; do
  if [ ! -e "$SHARED_ROOT/$name" ]; then
    if [ -e "$CURRENT_DIR/$name" ]; then
      cp -a "$CURRENT_DIR/$name" "$SHARED_ROOT/$name"
    else
      mkdir -p "$SHARED_ROOT/$name"
    fi
  fi
done
DATA_TARGET="$(readlink -f "$CURRENT_DIR/data")"
if [ ! -d "$DATA_TARGET" ]; then
  echo "ERROR: 持久数据目录不存在: $DATA_TARGET" >&2
  exit 1
fi
rm -rf "$STAGING_DIR/data" "$STAGING_DIR/backups" "$STAGING_DIR/rollbacks"
ln -s "$SHARED_ROOT/.env" "$STAGING_DIR/.env"
ln -s "$DATA_TARGET" "$STAGING_DIR/data"
ln -s "$SHARED_ROOT/backups" "$STAGING_DIR/backups"
ln -s "$SHARED_ROOT/rollbacks" "$STAGING_DIR/rollbacks"
mv "$STAGING_DIR" "$RELEASE_DIR"

cd "$RELEASE_DIR"
echo "==> [3/6] 重建 Compose 服务"
if ! /opt/hermes/venv/bin/python3 -c 'import ddgs' >/dev/null 2>&1; then
  /opt/hermes/venv/bin/pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple/ 'ddgs>=9.0'
fi
echo "==> [3a/6] 执行 QuantumWorkspace additive schema migration"
docker compose -p "$COMPOSE_PROJECT" build api
docker compose -p "$COMPOSE_PROJECT" run --rm --no-deps api \
  python scripts/migrate_quantum_workspace.py
RUNTIME_CHANGED=1
docker compose -p "$COMPOSE_PROJECT" up -d --build

echo "==> [4/6] API 健康检查与运行契约审计"
status=""
for _ in $(seq 1 30); do
  status="$(curl -sf http://127.0.0.1:8000/ready || true)"
  [ -n "$status" ] && break
  sleep 2
done
if [ -z "$status" ]; then
  echo "ERROR: API 30 秒内未就绪" >&2
  exit 1
fi
mkdir -p data/manifests data/runtime
if [ ! -e data/knowledge_matrix.json ]; then
  if [ ! -f data/vault/knowledge_matrix.json ]; then
    echo "ERROR: 缺少 Vault knowledge_matrix.json" >&2
    exit 1
  fi
  ln -s vault/knowledge_matrix.json data/knowledge_matrix.json
fi
docker compose -p "$COMPOSE_PROJECT" exec -T api \
  python scripts/audit_runtime_contracts.py --data-dir /app/data
printf '%s\n' "$EXPECTED_SHA" > .deployed-sha

echo "==> [5/6] 原子切换 release 并重启 Hermes Bridge"
LINK_TMP="$APP_LINK.next.$$"
ln -s "$RELEASE_DIR" "$LINK_TMP"
mv -Tf "$LINK_TMP" "$APP_LINK"
SWITCHED=1
systemctl restart hermes-bridge.service

echo "==> [6/6] 最终健康检查"
api_status=""
bridge_status=""
for _ in $(seq 1 30); do
  api_status="$(curl -fsS --max-time 5 http://127.0.0.1:8000/ready || true)"
  [ -n "$api_status" ] && break
  sleep 1
done
if [ -z "$api_status" ]; then
  echo "ERROR: 原子切换后 API 30 秒内未就绪" >&2
  exit 1
fi
printf '%s\n' "$api_status"
for _ in $(seq 1 30); do
  bridge_status="$(curl -fsS --max-time 5 http://127.0.0.1:9118/health || true)"
  [ -n "$bridge_status" ] && break
  sleep 1
done
if [ -z "$bridge_status" ]; then
  echo "ERROR: Hermes Bridge 重启后 30 秒内未就绪" >&2
  exit 1
fi
printf '%s\n' "$bridge_status"
echo "deployed_sha=$EXPECTED_SHA"
echo "release=$RELEASE_DIR"
echo "rollback_point=$CURRENT_DIR"
