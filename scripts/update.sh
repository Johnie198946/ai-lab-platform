#!/bin/bash
# 服务器端不可变发布：每个 SHA 解压到一个全新 release，验证后原子切换软链。
# 用法: bash scripts/update.sh <40位 commit SHA>

set -euo pipefail

allocate_release_dir() {
  local release_root="$1"
  local short_sha="$2"
  mktemp -d "$release_root/ai-lab-platform-$short_sha.XXXXXX"
}

configure_cloud_agent_os_mode() {
  local unit dropin_dir dropin_file temp_file changed=0
  for unit in hermes-bridge.service hermes-serve.service hermes-gateway.service; do
    dropin_dir="/etc/systemd/system/$unit.d"
    dropin_file="$dropin_dir/agent-os-mode.conf"
    mkdir -p "$dropin_dir"
    temp_file="$(mktemp "$dropin_dir/.agent-os-mode.XXXXXX")"
    printf '%s\n' \
      '[Service]' \
      'Environment=AI_LAB_AGENT_OS_MODE=cloud_multi_tenant' > "$temp_file"
    chmod 0644 "$temp_file"
    if ! cmp -s "$temp_file" "$dropin_file"; then
      mv -f "$temp_file" "$dropin_file"
      changed=1
    else
      rm -f "$temp_file"
    fi
  done
  if [ "$changed" -eq 1 ]; then
    systemctl daemon-reload
  fi
}

restart_hermes_runtime() {
  systemctl restart hermes-serve.service
  systemctl restart hermes-serve-forward.service
  systemctl restart hermes-gateway.service
  systemctl restart hermes-bridge.service
  systemctl restart hermes-chat-worker.service
}

if [ "${AI_LAB_UPDATE_LIBRARY_ONLY:-0}" = "1" ]; then
  return 0 2>/dev/null || exit 0
fi

if [ "$#" -ne 1 ] || [[ ! "$1" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "ERROR: 必须提供且仅提供一个精确的 40 位 commit SHA" >&2
  exit 2
fi

EXPECTED_SHA="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
SHORT_SHA="${EXPECTED_SHA:0:12}"
APP_LINK="${AI_LAB_APP_LINK:-/opt/ai-lab-platform}"
RELEASE_ROOT="${AI_LAB_RELEASE_ROOT:-/opt/releases}"
SHARED_ROOT="${AI_LAB_SHARED_ROOT:-/opt/ai-lab-shared}"
COMPOSE_PROJECT="${AI_LAB_COMPOSE_PROJECT:-ai-lab-platform}"
CURRENT_DIR=""
TARBALL=""
RELEASE_DIR=""
STAGING_DIR=""
TARBALL_VALIDATED=0
RELEASE_VALIDATED=0
SWITCHED=0
RUNTIME_CHANGED=0
cleanup() {
  rc=$?
  trap - EXIT
  if [ "$TARBALL_VALIDATED" -eq 1 ] && [ -n "$TARBALL" ]; then
    rm -f "$TARBALL"
  fi
  if [ "$rc" -ne 0 ] && [ "$RUNTIME_CHANGED" -eq 1 ]; then
    echo "WARN: 发布失败，恢复旧 release: $CURRENT_DIR" >&2
    if [ "$SWITCHED" -eq 1 ]; then
      rollback_link="$APP_LINK.rollback.$$"
      ln -s "$CURRENT_DIR" "$rollback_link"
      mv -Tf "$rollback_link" "$APP_LINK"
    fi
    cd "$CURRENT_DIR"
    docker compose -p "$COMPOSE_PROJECT" up -d --build || true
    configure_cloud_agent_os_mode || true
    restart_hermes_runtime || true
  fi
  if { [ "$SWITCHED" -eq 0 ] || [ "$rc" -ne 0 ]; } && [ "$RELEASE_VALIDATED" -eq 1 ]; then
    if [ -n "$STAGING_DIR" ] && [ -d "$STAGING_DIR" ]; then
      rm -rf "$STAGING_DIR"
    fi
    if [ -n "$RELEASE_DIR" ] && [ "$RELEASE_DIR" != "$STAGING_DIR" ] && [ -d "$RELEASE_DIR" ]; then
      rm -rf "$RELEASE_DIR"
    fi
  fi
  exit "$rc"
}
trap cleanup EXIT

CURRENT_DIR="$(readlink -f "$APP_LINK")"
if [ ! -d "$CURRENT_DIR" ]; then
  echo "ERROR: 当前 release 不存在: $CURRENT_DIR" >&2
  exit 1
fi
if [ ! -d "$RELEASE_ROOT" ] || [ -L "$RELEASE_ROOT" ]; then
  echo "ERROR: release root 必须是非符号链接目录: $RELEASE_ROOT" >&2
  exit 1
fi
RELEASE_ROOT_REAL="$(cd "$RELEASE_ROOT" && pwd -P)"
if [ "$RELEASE_ROOT" != "$RELEASE_ROOT_REAL" ]; then
  echo "ERROR: release root 必须使用规范物理路径" >&2
  exit 1
fi

TARBALL="$(mktemp /tmp/ailab-src.XXXXXX)"
if [[ ! "$TARBALL" =~ ^/tmp/ailab-src\.[A-Za-z0-9]{6}$ ]] || [ ! -f "$TARBALL" ] || [ -L "$TARBALL" ]; then
  echo "ERROR: mktemp 未返回受控 tarball 路径" >&2
  exit 1
fi
TARBALL_VALIDATED=1
RELEASE_DIR="$(allocate_release_dir "$RELEASE_ROOT" "$SHORT_SHA")"
STAGING_DIR="$RELEASE_DIR"
if [ ! -d "$RELEASE_DIR" ] || [ -L "$RELEASE_DIR" ]; then
  echo "ERROR: 非法 release 路径: $RELEASE_DIR" >&2
  exit 2
fi
RELEASE_REAL="$(cd "$RELEASE_DIR" && pwd -P)"
RELEASE_BASE="$(basename "$RELEASE_REAL")"
if [ "$RELEASE_DIR" != "$RELEASE_REAL" ] || [ "$(dirname "$RELEASE_REAL")" != "$RELEASE_ROOT_REAL" ] || [[ ! "$RELEASE_BASE" =~ ^ai-lab-platform-[0-9a-f]{12}\.[A-Za-z0-9]{6}$ ]]; then
  echo "ERROR: 非法 release 路径: $RELEASE_DIR" >&2
  exit 2
fi
RELEASE_VALIDATED=1

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

echo "==> [4b/6] 建立 Hermes Vault 可见性链接并修复笔记共享权限"
VAULT_ROOT="$DATA_TARGET/vault"
bash scripts/link_release_vault.sh "$RELEASE_DIR" "$RELEASE_ROOT" "$VAULT_ROOT"
python3 scripts/repair_user_note_permissions.py \
  --owner-uid 0 --owner-gid 0 \
  "$VAULT_ROOT/raw/dialogues/tenants"

echo "==> [5/6] 原子切换 release 并重启 Hermes runtime"
LINK_TMP="$APP_LINK.next.$$"
ln -s "$RELEASE_DIR" "$LINK_TMP"
mv -Tf "$LINK_TMP" "$APP_LINK"
SWITCHED=1
configure_cloud_agent_os_mode
restart_hermes_runtime

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
