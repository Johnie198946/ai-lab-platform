#!/bin/bash
# 服务器端不可变发布：每个 SHA 解压到一个全新 release，验证后原子切换软链。
# 用法: bash scripts/update.sh <40位 commit SHA>

set -euo pipefail

AI_LAB_HERMES_QUARANTINED="${AI_LAB_HERMES_QUARANTINED:-0}"
HERMES_ACCOUNT_HOME=/var/lib/quantumn-hermes
HERMES_HOME="$HERMES_ACCOUNT_HOME/.hermes"
HERMES_AGENT_ROOT="$HERMES_HOME/hermes-agent"
HERMES_PYTHON="$HERMES_AGENT_ROOT/venv/bin/python"
HERMES_LAUNCHER="$HERMES_ACCOUNT_HOME/.local/bin/hermes"
HERMES_RUNTIME_VERSION=0.21.1
BRIDGE_WORKER_VENV_LINK="$HERMES_ACCOUNT_HOME/bridge-worker-venv"
BRIDGE_WORKER_VENV_ROOT="$HERMES_ACCOUNT_HOME/bridge-worker-venvs"
BRIDGE_WORKER_PYTHON="$BRIDGE_WORKER_VENV_LINK/bin/python"
if [[ ! "$AI_LAB_HERMES_QUARANTINED" =~ ^[01]$ ]]; then
  echo "ERROR: AI_LAB_HERMES_QUARANTINED must be 0 or 1" >&2
  exit 2
fi

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

ensure_hermes_account() {
  if ! getent group quantumn-hermes >/dev/null; then
    groupadd --system quantumn-hermes
  fi
  if ! id -u quantumn-hermes >/dev/null 2>&1; then
    useradd --system --gid quantumn-hermes --home-dir /var/lib/quantumn-hermes \
      --shell /usr/sbin/nologin quantumn-hermes
  fi
  install -d -o quantumn-hermes -g quantumn-hermes -m 0700 \
    "$HERMES_ACCOUNT_HOME" "$HERMES_HOME"
}

verify_hermes_install() {
  if [ ! -d "$HERMES_AGENT_ROOT" ] || [ ! -x "$HERMES_PYTHON" ] || [ ! -x "$HERMES_LAUNCHER" ]; then
    echo "ERROR: official Hermes install is incomplete under $HERMES_ACCOUNT_HOME" >&2
    return 1
  fi
  if ! HERMES_RUNTIME_VERSION="$HERMES_RUNTIME_VERSION" "$HERMES_PYTHON" -c \
    'import importlib.metadata, os; assert importlib.metadata.version("hermes-agent") == os.environ["HERMES_RUNTIME_VERSION"]'; then
    echo "ERROR: Hermes runtime must be exactly $HERMES_RUNTIME_VERSION" >&2
    return 1
  fi
}

prepare_bridge_worker_venv() {
  local release_dir="$1" lock_digest target temp_dir=""
  lock_digest="$(printf '%s\0' "$HERMES_RUNTIME_VERSION" | cat - "$release_dir/requirements.lock" "$release_dir/requirements-bridge-worker.lock" "$release_dir/requirements-build.lock" | sha256sum | cut -d' ' -f1)"
  target="$BRIDGE_WORKER_VENV_ROOT/$lock_digest"
  install -d -o quantumn-hermes -g quantumn-hermes -m 0700 "$BRIDGE_WORKER_VENV_ROOT"
  if [ ! -x "$target/bin/python" ]; then
    temp_dir="$(mktemp -d "$BRIDGE_WORKER_VENV_ROOT/.build.XXXXXX")"
    chown quantumn-hermes:quantumn-hermes "$temp_dir"
    if ! runuser -u quantumn-hermes -- python3 -m venv "$temp_dir" \
      || ! runuser -u quantumn-hermes -- "$temp_dir/bin/python" -m pip install \
        --require-hashes -r "$release_dir/requirements-build.lock" \
      || ! runuser -u quantumn-hermes -- "$temp_dir/bin/python" -m pip install \
        --require-hashes --no-build-isolation -r "$release_dir/requirements.lock" \
      || ! runuser -u quantumn-hermes -- "$temp_dir/bin/python" -m pip install \
        --require-hashes --no-build-isolation -r "$release_dir/requirements-bridge-worker.lock" \
      || ! runuser -u quantumn-hermes -- "$temp_dir/bin/python" -m pip install \
        --no-deps --no-build-isolation --editable "$HERMES_AGENT_ROOT" \
      || ! runuser -u quantumn-hermes -- "$temp_dir/bin/python" -m pip check; then
      rm -rf -- "$temp_dir"
      return 1
    fi
    mv "$temp_dir" "$target"
  fi
  if ! HERMES_RUNTIME_VERSION="$HERMES_RUNTIME_VERSION" "$target/bin/python" -c \
    'from importlib.metadata import version; import os, httpx, sqlalchemy, run_agent; assert version("hermes-agent") == os.environ["HERMES_RUNTIME_VERSION"]'; then
    echo "ERROR: Bridge/Worker venv cannot import platform dependencies and fixed Hermes source" >&2
    return 1
  fi
  BRIDGE_WORKER_VENV_TARGET="$target"
}

activate_bridge_worker_venv() {
  local next_link="$BRIDGE_WORKER_VENV_LINK.next.$$"
  if [ -L "$BRIDGE_WORKER_VENV_LINK" ]; then
    BRIDGE_WORKER_VENV_BEFORE="$(readlink -f "$BRIDGE_WORKER_VENV_LINK")"
    BRIDGE_WORKER_VENV_HAD_LINK=1
  fi
  ln -s "$BRIDGE_WORKER_VENV_TARGET" "$next_link"
  mv -Tf "$next_link" "$BRIDGE_WORKER_VENV_LINK"
  BRIDGE_WORKER_VENV_SWITCHED=1
}

resolve_hermes_bridge_bind_address() {
  local address
  address="$(docker compose -p "$COMPOSE_PROJECT" exec -T api python -c \
    'import socket; print(socket.gethostbyname("host.docker.internal"))' 2>/dev/null)" || {
    echo "ERROR: cannot resolve host.docker.internal inside the API container" >&2
    return 1
  }
  if ! python3 - "$address" <<'PY'
import ipaddress
import sys

try:
    address = ipaddress.ip_address(sys.argv[1])
except ValueError:
    raise SystemExit(1)
allowed = tuple(ipaddress.ip_network(item) for item in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
raise SystemExit(0 if address.version == 4 and any(address in network for network in allowed) else 1)
PY
  then
    echo "ERROR: Docker host-gateway is not an RFC1918 IPv4 address: ${address:-<empty>}" >&2
    return 1
  fi
  if ! ip -4 -o addr show | awk '{sub(/\/.*/, "", $4); print $4}' | grep -Fqx "$address"; then
    echo "ERROR: Docker host-gateway is not assigned to this host: $address" >&2
    return 1
  fi
  printf '%s\n' "$address"
}

configure_hermes_bridge_network() {
  local env_dir=/etc/ai-lab-platform env_file temp_file
  HERMES_BRIDGE_BIND_ADDRESS="$(resolve_hermes_bridge_bind_address)"
  export HERMES_BRIDGE_BIND_ADDRESS
  install -d -o root -g root -m 0755 "$env_dir"
  env_file="$env_dir/hermes-bridge.env"
  temp_file="$(mktemp "$env_dir/.hermes-bridge.XXXXXX")"
  printf 'HERMES_BRIDGE_BIND_ADDRESS=%s\n' "$HERMES_BRIDGE_BIND_ADDRESS" > "$temp_file"
  chmod 0644 "$temp_file"
  mv -f "$temp_file" "$env_file"
}

verify_hermes_bridge_unit() {
  local bridge_effective worker_effective
  bridge_effective="$(systemctl show hermes-bridge.service --property=ExecStart --value)"
  worker_effective="$(systemctl show hermes-chat-worker.service --property=ExecStart --value)"
  if [[ "$bridge_effective" != *"$BRIDGE_WORKER_PYTHON"* || "$bridge_effective" != *"scripts/hermes_bridge.py"* || "$bridge_effective" == *"--host"* ]]; then
    echo "ERROR: effective hermes-bridge ExecStart bypasses the private bind contract: $bridge_effective" >&2
    return 1
  fi
  if [[ "$worker_effective" != *"$BRIDGE_WORKER_PYTHON"* || "$worker_effective" != *"scripts.chat_run_worker"* ]]; then
    echo "ERROR: effective hermes-chat-worker ExecStart bypasses the dedicated venv: $worker_effective" >&2
    return 1
  fi
}

install_hermes_units() {
  ensure_hermes_account
  configure_hermes_bridge_network
  install -m 0644 "$APP_LINK/ops/systemd/hermes-bridge.service" \
    /etc/systemd/system/hermes-bridge.service
  install -m 0644 "$APP_LINK/ops/systemd/hermes-chat-worker.service" \
    /etc/systemd/system/hermes-chat-worker.service
  systemctl daemon-reload
  verify_hermes_bridge_unit
}

restart_hermes_runtime() {
  local unit
  if [ "$AI_LAB_HERMES_QUARANTINED" = "1" ]; then
    echo "hermes_restart_status=skipped_quarantined"
    return 0
  fi
  for unit in hermes-serve.service hermes-serve-forward.service hermes-gateway.service \
    hermes-bridge.service hermes-chat-worker.service; do
    if systemctl cat "$unit" >/dev/null 2>&1; then
      systemctl restart "$unit"
    else
      echo "hermes_restart_status=skipped_absent unit=$unit"
    fi
  done
}

repair_runtime_store_permissions() {
  local data_root="$1" path
  chown quantumn-hermes:quantumn-hermes "$data_root"
  chmod 0755 "$data_root"
  for path in "$data_root"/hermes_chat_runs.sqlite3*; do
    [ -e "$path" ] || continue
    chown quantumn-hermes:quantumn-hermes "$path"
    chmod 0600 "$path"
  done
}

repair_vault_runtime_permissions() {
  local vault_root="$1" lock="$1/.incremental-compile.lock"
  chown quantumn-hermes:quantumn-hermes "$vault_root"
  chmod 0755 "$vault_root"
  if [ -e "$lock" ]; then
    chown quantumn-hermes:quantumn-hermes "$lock"
    chmod 0600 "$lock"
  fi
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
BRIDGE_WORKER_VENV_TARGET=""
BRIDGE_WORKER_VENV_BEFORE=""
BRIDGE_WORKER_VENV_HAD_LINK=0
BRIDGE_WORKER_VENV_SWITCHED=0
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
    if [ "$BRIDGE_WORKER_VENV_SWITCHED" -eq 1 ]; then
      if [ "$BRIDGE_WORKER_VENV_HAD_LINK" -eq 1 ]; then
        rollback_venv_link="$BRIDGE_WORKER_VENV_LINK.rollback.$$"
        ln -s "$BRIDGE_WORKER_VENV_BEFORE" "$rollback_venv_link"
        mv -Tf "$rollback_venv_link" "$BRIDGE_WORKER_VENV_LINK"
      else
        rm -f -- "$BRIDGE_WORKER_VENV_LINK"
      fi
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
chmod 0755 "$RELEASE_DIR"
test -f "$STAGING_DIR/docker-compose.yml"
test -f "$STAGING_DIR/scripts/update.sh"

echo "==> [2/6] 建立共享运行数据入口"
mkdir -p "$SHARED_ROOT"
if [ ! -f "$SHARED_ROOT/.env" ]; then
  install -m 600 "$CURRENT_DIR/.env" "$SHARED_ROOT/.env"
fi
ensure_hermes_account
export AI_LAB_RUNTIME_UID="$(id -u quantumn-hermes)"
export AI_LAB_RUNTIME_GID="$(id -g quantumn-hermes)"
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
repair_runtime_store_permissions "$DATA_TARGET"
rm -rf "$STAGING_DIR/data" "$STAGING_DIR/backups" "$STAGING_DIR/rollbacks"
ln -s "$SHARED_ROOT/.env" "$STAGING_DIR/.env"
ln -s "$DATA_TARGET" "$STAGING_DIR/data"
ln -s "$SHARED_ROOT/backups" "$STAGING_DIR/backups"
ln -s "$SHARED_ROOT/rollbacks" "$STAGING_DIR/rollbacks"
cd "$RELEASE_DIR"
echo "==> [3/6] 重建 Compose 服务"
verify_hermes_install
prepare_bridge_worker_venv "$RELEASE_DIR"
echo "==> [3a/6] 执行 QuantumWorkspace additive schema migration"
docker compose -p "$COMPOSE_PROJECT" build api
docker compose -p "$COMPOSE_PROJECT" run --rm --no-deps api \
  python scripts/migrate_quantum_workspace.py
docker compose -p "$COMPOSE_PROJECT" build taskboard
docker compose -p "$COMPOSE_PROJECT" run --rm --no-deps --user 0 --entrypoint chown taskboard \
  -R 1000:1000 /data
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
KNOWLEDGE_MATRIX_TARGET="$(readlink -f data/knowledge_matrix.json)"
chown quantumn-hermes:quantumn-hermes "$KNOWLEDGE_MATRIX_TARGET"
chmod 0640 "$KNOWLEDGE_MATRIX_TARGET"
docker compose -p "$COMPOSE_PROJECT" exec -T api \
  python scripts/audit_runtime_contracts.py --data-dir /app/data
printf '%s\n' "$EXPECTED_SHA" > .deployed-sha

echo "==> [4b/6] 建立 Hermes Vault 可见性链接并修复笔记共享权限"
VAULT_ROOT="$DATA_TARGET/vault"
repair_vault_runtime_permissions "$VAULT_ROOT"
bash scripts/link_release_vault.sh "$RELEASE_DIR" "$RELEASE_ROOT" "$VAULT_ROOT"
python3 scripts/repair_user_note_permissions.py \
  --owner-uid "$AI_LAB_RUNTIME_UID" --owner-gid "$AI_LAB_RUNTIME_GID" \
  "$VAULT_ROOT/raw/dialogues/tenants"
install -d -o quantumn-hermes -g quantumn-hermes -m 0700 "$VAULT_ROOT/wiki/tenant"
install -d -o quantumn-hermes -g quantumn-hermes -m 0755 "$VAULT_ROOT/wiki/contributions"

echo "==> [5/6] 原子切换 release 并重启 Hermes runtime"
LINK_TMP="$APP_LINK.next.$$"
ln -s "$RELEASE_DIR" "$LINK_TMP"
mv -Tf "$LINK_TMP" "$APP_LINK"
SWITCHED=1
activate_bridge_worker_venv
configure_cloud_agent_os_mode
install_hermes_units
restart_hermes_runtime
repair_runtime_store_permissions "$DATA_TARGET"
repair_vault_runtime_permissions "$VAULT_ROOT"
python3 scripts/repair_user_note_permissions.py \
  --owner-uid "$AI_LAB_RUNTIME_UID" --owner-gid "$AI_LAB_RUNTIME_GID" \
  "$VAULT_ROOT/raw/dialogues/tenants"
docker compose -p "$COMPOSE_PROJECT" exec -T api python -c \
  'import pathlib,tempfile; data=pathlib.Path("/app/data"); data_probe=pathlib.Path(tempfile.mkdtemp(prefix=".api-write-probe-",dir=data)); data_probe.rmdir(); vault=data/"vault"; lock=vault/".incremental-compile.lock"; lock.touch(exist_ok=True); root=vault/"raw/dialogues/tenants"; probe=pathlib.Path(tempfile.mkdtemp(prefix=".api-write-probe-",dir=root)); probe.rmdir()'

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
if [ "$AI_LAB_HERMES_QUARANTINED" = "1" ]; then
  echo "bridge_health_status=skipped_quarantined"
else
  for _ in $(seq 1 30); do
    bridge_status="$(curl -fsS --max-time 5 "http://$HERMES_BRIDGE_BIND_ADDRESS:9118/health" || true)"
    [ -n "$bridge_status" ] && break
    sleep 1
  done
  if [ -z "$bridge_status" ]; then
    echo "ERROR: Hermes Bridge 重启后 30 秒内未就绪" >&2
    exit 1
  fi
  printf '%s\n' "$bridge_status"
  systemctl is-active --quiet hermes-bridge.service hermes-chat-worker.service
  docker compose -p "$COMPOSE_PROJECT" exec -T api python -c \
    "import urllib.request; print(urllib.request.urlopen('http://$HERMES_BRIDGE_BIND_ADDRESS:9118/health', timeout=5).read().decode())"
fi
echo "deployed_sha=$EXPECTED_SHA"
echo "release=$RELEASE_DIR"
echo "rollback_point=$CURRENT_DIR"
