#!/bin/bash
# 服务器端不可变发布：每个 SHA 解压到一个全新 release，验证后原子切换软链。
# 用法: bash scripts/update.sh <40位 commit SHA>

set -euo pipefail

AI_LAB_HERMES_QUARANTINED="${AI_LAB_HERMES_QUARANTINED:-0}"
AI_LAB_OFFLINE_IMAGES="${AI_LAB_OFFLINE_IMAGES:-1}"
HERMES_ACCOUNT_HOME=/var/lib/quantumn-hermes
HERMES_HOME="$HERMES_ACCOUNT_HOME/.hermes"
HERMES_AGENT_ROOT="$HERMES_HOME/hermes-agent"
HERMES_PYTHON="$HERMES_AGENT_ROOT/venv/bin/python"
HERMES_LAUNCHER="$HERMES_ACCOUNT_HOME/.local/bin/hermes"
HERMES_RUNTIME_VERSION=0.21.1
HERMES_RUNTIME_COMMIT=c8aa5608c24e3636e77c267650c0f1f52e44adb0
BRIDGE_WORKER_VENV_LINK="$HERMES_ACCOUNT_HOME/bridge-worker-venv"
BRIDGE_WORKER_VENV_ROOT="$HERMES_ACCOUNT_HOME/bridge-worker-venvs"
BRIDGE_WORKER_PYTHON="$BRIDGE_WORKER_VENV_LINK/bin/python"
BRIDGE_WORKER_RUNTIME_ARCHIVE=/opt/ai-lab-shared/offline-runtime/cpython-3.12.14+20260901-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz
BRIDGE_WORKER_RUNTIME_SHA256=72748da13197c1fb161e3afeef20a6a385ff24f2165e6e2758e47008e7faba4c
BRIDGE_WORKER_RUNTIME_ROOT="$HERMES_ACCOUNT_HOME/python-runtimes"
BRIDGE_WORKER_RUNTIME_DIR="$BRIDGE_WORKER_RUNTIME_ROOT/cpython-3.12.14+20260901"
BRIDGE_WORKER_RUNTIME_PYTHON="$BRIDGE_WORKER_RUNTIME_DIR/bin/python3"
CERTBOT_PYTHON_RUNTIME_ROOT=/opt/certbot-python-runtimes
CERTBOT_PYTHON_RUNTIME_DIR="$CERTBOT_PYTHON_RUNTIME_ROOT/$BRIDGE_WORKER_RUNTIME_SHA256"
CERTBOT_PYTHON_RUNTIME_PYTHON="$CERTBOT_PYTHON_RUNTIME_DIR/bin/python3"
CERTBOT_VERSION=5.8.0
CERTBOT_ARCHIVE=/home/deploy/certbot-wheelhouse-5.8.0-linux-amd64.tar.zst
CERTBOT_ARCHIVE_SHA256=c701b7929a9073d0b005ea7833f5f9ee38ac30f2805c0cf64aad683fb418a685
CERTBOT_VENV_LINK=/opt/certbot-venv
CERTBOT_VENV_ROOT=/opt/certbot-venvs
CERTBOT_VENV_DIR="$CERTBOT_VENV_ROOT/$CERTBOT_VERSION-linux-amd64-${CERTBOT_ARCHIVE_SHA256:0:12}"
HERMES_BRIDGE_ENV_FILE=/etc/ai-lab-platform/hermes-bridge.env
if [[ ! "$AI_LAB_HERMES_QUARANTINED" =~ ^[01]$ ]]; then
  echo "ERROR: AI_LAB_HERMES_QUARANTINED must be 0 or 1" >&2
  exit 2
fi
if [ "$AI_LAB_OFFLINE_IMAGES" != "1" ]; then
  echo "ERROR: production deployment requires AI_LAB_OFFLINE_IMAGES=1" >&2
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
  local runtime_commit runtime_status
  if [ ! -d "$HERMES_AGENT_ROOT" ] || [ ! -x "$HERMES_PYTHON" ] || [ ! -x "$HERMES_LAUNCHER" ]; then
    echo "ERROR: official Hermes install is incomplete under $HERMES_ACCOUNT_HOME" >&2
    return 1
  fi
  if ! runtime_commit="$(runuser -u quantumn-hermes -- git -C "$HERMES_AGENT_ROOT" rev-parse HEAD 2>/dev/null)" \
    || [ "$runtime_commit" != "$HERMES_RUNTIME_COMMIT" ]; then
    echo "ERROR: Hermes runtime source must be exactly $HERMES_RUNTIME_COMMIT" >&2
    return 1
  fi
  if ! runtime_status="$(runuser -u quantumn-hermes -- git -C "$HERMES_AGENT_ROOT" status --porcelain 2>/dev/null)" \
    || [ -n "$runtime_status" ]; then
    echo "ERROR: Hermes runtime source checkout must be clean" >&2
    return 1
  fi
  if ! HERMES_RUNTIME_VERSION="$HERMES_RUNTIME_VERSION" "$HERMES_PYTHON" -c \
    'import importlib.metadata, os; assert importlib.metadata.version("hermes-agent") == os.environ["HERMES_RUNTIME_VERSION"]'; then
    echo "ERROR: Hermes runtime must be exactly $HERMES_RUNTIME_VERSION" >&2
    return 1
  fi
}

verify_bridge_worker_python() {
  local python="$1"
  "$python" -c '
import sqlite3
import re
import ssl
import sys

assert sys.version_info[:3] == (3, 12, 14)
assert sqlite3.sqlite_version_info == (3, 53, 1)
assert ssl.OPENSSL_VERSION.startswith("OpenSSL ")
openssl_version = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", ssl.OPENSSL_VERSION)
assert openssl_version and tuple(map(int, openssl_version.groups())) == (3, 5, 8)
'
}

verify_python_runtime_tree() {
  local runtime_dir="$1" python="$2" path resolved
  if [ -L "$runtime_dir" ] || [ ! -d "$runtime_dir" ] \
    || [ "$(stat -c '%u' "$runtime_dir")" -ne 0 ] \
    || [ $((8#$(stat -c '%a' "$runtime_dir") & 8#022)) -ne 0 ] \
    || [ -n "$(find "$runtime_dir" ! -type l \( ! -user root -o -perm /022 \) -print -quit)" ]; then
    echo "ERROR: Python runtime must be root-owned and not group/world writable" >&2
    return 1
  fi
  while IFS= read -r -d '' path; do
    resolved="$(readlink -f -- "$path")" || return 1
    if [[ "$resolved" != "$runtime_dir/"* ]]; then
      echo "ERROR: Python runtime symlink escapes its root: $path" >&2
      return 1
    fi
  done < <(find "$runtime_dir" -type l -print0)
  [ -x "$python" ] || return 1
  verify_bridge_worker_python "$python"
}

verify_bridge_worker_runtime_tree() {
  verify_python_runtime_tree "$1" "$1/bin/python3"
}

extract_python_runtime_archive() {
  local archive="$1" staging_dir="$2"
  python3 - "$archive" "$staging_dir" <<'PY'
import pathlib
import sys
import tarfile

assert sys.version_info >= (3, 12)
archive, staging_dir = sys.argv[1:]
with tarfile.open(archive, "r:gz") as source:
    members = source.getmembers()
    if not members:
        raise ValueError("empty runtime archive")
    for member in members:
        path = pathlib.PurePosixPath(member.name)
        if not path.parts or path.parts[0] != "python" or ".." in path.parts:
            raise ValueError(f"archive member is outside python/: {member.name}")
        if member.isdev() or member.isfifo():
            raise ValueError(f"archive member is a device or FIFO: {member.name}")
    source.extractall(staging_dir, members=members, filter="data")
PY
}

prepare_bridge_worker_python_runtime() {
  local archive="$BRIDGE_WORKER_RUNTIME_ARCHIVE" target="$BRIDGE_WORKER_RUNTIME_DIR"
  local temp_dir="" actual_sha
  if [ -L "$archive" ] || [ ! -f "$archive" ] \
    || [ "$(stat -c '%u' "$archive")" -ne 0 ] \
    || [ $((8#$(stat -c '%a' "$archive") & 8#022)) -ne 0 ]; then
    echo "ERROR: offline Bridge/Worker Python archive must be a root-owned, non-writable regular file" >&2
    return 1
  fi
  actual_sha="$(sha256sum "$archive" | cut -d' ' -f1)"
  if [ "$actual_sha" != "$BRIDGE_WORKER_RUNTIME_SHA256" ]; then
    echo "ERROR: offline Bridge/Worker Python archive SHA256 mismatch" >&2
    return 1
  fi
  if [ -e "$BRIDGE_WORKER_RUNTIME_ROOT" ] \
    && { [ -L "$BRIDGE_WORKER_RUNTIME_ROOT" ] || [ ! -d "$BRIDGE_WORKER_RUNTIME_ROOT" ]; }; then
    echo "ERROR: Bridge/Worker Python runtime root must be a real directory" >&2
    return 1
  fi
  install -d -o root -g root -m 0755 "$BRIDGE_WORKER_RUNTIME_ROOT"
  if [ -L "$target" ]; then
    echo "ERROR: Bridge/Worker Python runtime target must not be a symlink" >&2
    return 1
  fi
  if [ ! -e "$target" ]; then
    temp_dir="$(mktemp -d "$BRIDGE_WORKER_RUNTIME_ROOT/.build.XXXXXX")"
    if ! extract_python_runtime_archive "$archive" "$temp_dir"; then
      echo "ERROR: offline Bridge/Worker Python archive has unsafe contents" >&2
      rm -rf -- "$temp_dir"
      return 1
    fi
    if ! chown -R root:root "$temp_dir/python" \
      || ! chmod -R go-w,u-s,g-s "$temp_dir/python" \
      || ! verify_bridge_worker_runtime_tree "$temp_dir/python" \
      || ! mv -T "$temp_dir/python" "$target"; then
      rm -rf -- "$temp_dir"
      return 1
    fi
    rmdir "$temp_dir"
  fi
  verify_bridge_worker_runtime_tree "$target"
}

verify_certbot_python_runtime_tree() {
  local runtime_dir="$1" python="$1/bin/python3"
  verify_python_runtime_tree "$runtime_dir" "$python" || return 1
  "$python" -c '
import hashlib
import pathlib
import platform
import sys
import tarfile
import venv
assert sys.platform == "linux"
assert platform.machine() == "x86_64"
'
}

prepare_certbot_python_runtime() {
  local archive="$BRIDGE_WORKER_RUNTIME_ARCHIVE" target="$CERTBOT_PYTHON_RUNTIME_DIR"
  local temp_dir="" actual_sha
  if [ "$(uname -s)" != Linux ] || [ "$(uname -m)" != x86_64 ]; then
    echo "ERROR: Certbot Python runtime requires Linux x86_64" >&2
    return 1
  fi
  if [ -L "$archive" ] || [ ! -f "$archive" ] \
    || [ "$(stat -c '%u' "$archive")" -ne 0 ] \
    || [ $((8#$(stat -c '%a' "$archive") & 8#022)) -ne 0 ]; then
    echo "ERROR: offline Certbot Python archive must be a root-owned, non-writable regular file" >&2
    return 1
  fi
  actual_sha="$(sha256sum "$archive" | cut -d' ' -f1)"
  if [ "$actual_sha" != "$BRIDGE_WORKER_RUNTIME_SHA256" ]; then
    echo "ERROR: offline Certbot Python archive SHA256 mismatch" >&2
    return 1
  fi
  if [ -e "$CERTBOT_PYTHON_RUNTIME_ROOT" ] \
    && { [ -L "$CERTBOT_PYTHON_RUNTIME_ROOT" ] || [ ! -d "$CERTBOT_PYTHON_RUNTIME_ROOT" ]; }; then
    echo "ERROR: Certbot Python runtime root must be a real directory" >&2
    return 1
  fi
  install -d -o root -g root -m 0755 "$CERTBOT_PYTHON_RUNTIME_ROOT"
  if [ "$(stat -c '%u' "$CERTBOT_PYTHON_RUNTIME_ROOT")" -ne 0 ] \
    || [ $((8#$(stat -c '%a' "$CERTBOT_PYTHON_RUNTIME_ROOT") & 8#022)) -ne 0 ]; then
    echo "ERROR: Certbot Python runtime root must be root-owned and not group/world writable" >&2
    return 1
  fi
  if [ -L "$target" ]; then
    echo "ERROR: versioned Certbot Python runtime target must not be a symlink" >&2
    return 1
  fi
  if [ ! -e "$target" ]; then
    temp_dir="$(mktemp -d "$CERTBOT_PYTHON_RUNTIME_ROOT/.build.XXXXXX")"
    if ! extract_python_runtime_archive "$archive" "$temp_dir" \
      || ! chown -R root:root "$temp_dir/python" \
      || ! chmod -R go-w,u-s,g-s "$temp_dir/python" \
      || ! verify_certbot_python_runtime_tree "$temp_dir/python" \
      || ! mv -T "$temp_dir/python" "$target"; then
      echo "ERROR: offline Certbot Python runtime extraction or verification failed" >&2
      rm -rf -- "$temp_dir"
      return 1
    fi
    rmdir "$temp_dir"
  fi
  verify_certbot_python_runtime_tree "$target"
}

verify_bridge_worker_venv() {
  local python="$1"
  verify_bridge_worker_python "$python" || return 1
  HERMES_RUNTIME_VERSION="$HERMES_RUNTIME_VERSION" "$python" -c \
    'from importlib.metadata import version; import os, httpx, sqlalchemy, run_agent; assert version("hermes-agent") == os.environ["HERMES_RUNTIME_VERSION"]'
}

prepare_bridge_worker_venv() {
  local release_dir="$1" lock_digest target temp_dir=""
  prepare_bridge_worker_python_runtime || return 1
  lock_digest="$(printf '%s\0%s\0%s\0' "$HERMES_RUNTIME_VERSION" "$HERMES_RUNTIME_COMMIT" "$BRIDGE_WORKER_RUNTIME_SHA256" | cat - "$release_dir/requirements.lock" "$release_dir/requirements-bridge-worker.lock" "$release_dir/requirements-build.lock" | sha256sum | cut -d' ' -f1)"
  target="$BRIDGE_WORKER_VENV_ROOT/$lock_digest"
  install -d -o quantumn-hermes -g quantumn-hermes -m 0700 "$BRIDGE_WORKER_VENV_ROOT"
  if [ ! -x "$target/bin/python" ]; then
    temp_dir="$(mktemp -d "$BRIDGE_WORKER_VENV_ROOT/.build.XXXXXX")"
    chown quantumn-hermes:quantumn-hermes "$temp_dir"
    if ! runuser -u quantumn-hermes -- "$BRIDGE_WORKER_RUNTIME_PYTHON" -m venv "$temp_dir" \
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
  if ! verify_bridge_worker_venv "$target/bin/python"; then
    echo "ERROR: Bridge/Worker venv cannot import platform dependencies and fixed Hermes source" >&2
    return 1
  fi
  BRIDGE_WORKER_VENV_TARGET="$target"
}

activate_bridge_worker_venv() {
  local next_link="$BRIDGE_WORKER_VENV_LINK.next.$$" rollback_link
  if [ -e "$BRIDGE_WORKER_VENV_LINK" ] && [ ! -L "$BRIDGE_WORKER_VENV_LINK" ]; then
    echo "ERROR: Bridge/Worker venv link path is not a symlink" >&2
    return 1
  fi
  if [ -L "$BRIDGE_WORKER_VENV_LINK" ]; then
    BRIDGE_WORKER_VENV_BEFORE="$(readlink -f "$BRIDGE_WORKER_VENV_LINK")"
    BRIDGE_WORKER_VENV_HAD_LINK=1
  fi
  ln -s "$BRIDGE_WORKER_VENV_TARGET" "$next_link"
  mv -Tf "$next_link" "$BRIDGE_WORKER_VENV_LINK"
  BRIDGE_WORKER_VENV_SWITCHED=1
  if ! verify_bridge_worker_venv "$BRIDGE_WORKER_PYTHON"; then
    if [ "$BRIDGE_WORKER_VENV_HAD_LINK" -eq 1 ]; then
      rollback_link="$BRIDGE_WORKER_VENV_LINK.rollback.$$"
      ln -s "$BRIDGE_WORKER_VENV_BEFORE" "$rollback_link"
      mv -Tf "$rollback_link" "$BRIDGE_WORKER_VENV_LINK"
    else
      rm -f -- "$BRIDGE_WORKER_VENV_LINK"
    fi
    BRIDGE_WORKER_VENV_SWITCHED=0
    return 1
  fi
}

relocate_certbot_venv() {
  local staging="$1" target="$2"
  rm -f -- "$staging/bin/activate" "$staging/bin/activate.csh" \
    "$staging/bin/activate.fish" "$staging/bin/Activate.ps1" || return 1
  "$CERTBOT_PYTHON_RUNTIME_PYTHON" - "$staging" "$target" <<'PY'
import pathlib
import shutil
import sys

staging, target = map(pathlib.Path, sys.argv[1:])
old = {
    f"#!{staging}/bin/{interpreter}".encode()
    for interpreter in ("python", "python3", "python3.12")
}
new = f"#!{target}/bin/python".encode()
for path in (staging / "bin").iterdir():
    if path.is_symlink() or not path.is_file():
        continue
    data = path.read_bytes()
    first, separator, rest = data.partition(b"\n")
    if first.removesuffix(b"\r") in old:
        ending = b"\r\n" if first.endswith(b"\r") else separator
        path.write_bytes(new + ending + rest)

config = staging / "pyvenv.cfg"
data = config.read_bytes()
config.write_bytes(data.replace(str(staging).encode(), str(target).encode()))

for path in sorted(staging.rglob("__pycache__"), reverse=True):
    if not path.is_symlink() and path.is_dir():
        shutil.rmtree(path)
for path in sorted(staging.rglob("*.pyc")):
    if not path.is_symlink() and path.is_file():
        path.unlink()

prefix = str(staging).encode()
for path in staging.rglob("*"):
    if not path.is_symlink() and path.is_file() and prefix in path.read_bytes():
        raise ValueError(f"Certbot venv retains staging path: {path}")
PY
}

discard_invalid_inactive_certbot_venv() {
  local target="$1" active_target=""
  [ -e "$target" ] || return 0
  verify_certbot_venv "$target" && return 0
  if [ -L "$CERTBOT_VENV_LINK" ]; then
    active_target="$(readlink -f -- "$CERTBOT_VENV_LINK")" || active_target=""
  fi
  if [ "$active_target" = "$target" ]; then
    echo "ERROR: active Certbot venv target failed verification; refusing to delete it" >&2
    return 1
  fi
  rm -rf -- "$target"
}

verify_certbot_venv() {
  local venv="$1" python="$1/bin/python" certbot="$1/bin/certbot" path relative resolved
  local runtime_python venv_lib certbot_first_line
  if [ -L "$venv" ] || [ ! -d "$venv" ] \
    || [ "$(stat -c '%u' "$venv")" -ne 0 ] \
    || [ -n "$(find "$venv" ! -user root -print -quit)" ] \
    || [ -n "$(find "$venv" \( -type f -o -type d \) -perm /022 -print -quit)" ] \
    || [ -n "$(find "$venv" ! -type f ! -type d ! -type l -print -quit)" ] \
    || [ ! -x "$python" ] || [ ! -x "$certbot" ]; then
    echo "ERROR: Certbot venv must be root-owned, non-writable, and executable" >&2
    return 1
  fi
  IFS= read -r certbot_first_line < "$certbot" || return 1
  if [ -L "$certbot" ] || [ ! -f "$certbot" ] \
    || [ "$(stat -c '%u' "$certbot")" -ne 0 ] \
    || [ $((8#$(stat -c '%a' "$certbot") & 8#022)) -ne 0 ] \
    || [ "$certbot_first_line" != "#!$venv/bin/python" ]; then
    echo "ERROR: Certbot launcher must be a root-owned, non-writable regular file with the expected shebang" >&2
    return 1
  fi
  runtime_python="$(readlink -f -- "$CERTBOT_PYTHON_RUNTIME_PYTHON")" || return 1
  venv_lib="$(readlink -f -- "$venv/lib")" || return 1
  while IFS= read -r -d '' path; do
    relative="${path#"$venv"/}"
    resolved="$(readlink -f -- "$path")" || return 1
    case "$relative" in
      bin/python|bin/python3|bin/python3.12)
        [ "$resolved" = "$runtime_python" ] || {
          echo "ERROR: Certbot venv Python symlink has an untrusted target: $path" >&2
          return 1
        }
        ;;
      lib64)
        [ "$resolved" = "$venv_lib" ] || {
          echo "ERROR: Certbot venv lib64 symlink escapes its lib directory" >&2
          return 1
        }
        ;;
      *)
        echo "ERROR: Certbot venv contains an unexpected symlink: $path" >&2
        return 1
        ;;
    esac
  done < <(find "$venv" -type l -print0)
  verify_bridge_worker_python "$python" || return 1
  CERTBOT_VERSION="$CERTBOT_VERSION" "$python" -c '
import platform
from importlib.metadata import version
import configargparse, OpenSSL, _cffi_backend, acme, certbot, certifi, charset_normalizer
import configobj, cryptography, distro, idna, josepy, parsedatetime, pycparser
import pyrfc3339, requests, typing_extensions, urllib3
assert platform.machine() == "x86_64"
assert version("certbot") == __import__("os").environ["CERTBOT_VERSION"]
' || return 1
  [ "$(TERM=dumb "$certbot" --version 2>/dev/null)" = "certbot $CERTBOT_VERSION" ]
}

prepare_certbot_venv() {
  local archive="$CERTBOT_ARCHIVE" target="$CERTBOT_VENV_DIR" actual_sha temp_dir wheelhouse
  if [ "$(uname -s)" != Linux ] || [ "$(uname -m)" != x86_64 ]; then
    echo "ERROR: Certbot wheelhouse requires Linux x86_64" >&2
    return 1
  fi
  prepare_certbot_python_runtime || return 1
  if [ -L "$archive" ] || [ ! -f "$archive" ]; then
    echo "ERROR: Certbot wheelhouse archive is missing or not a regular file: $archive" >&2
    return 1
  fi
  actual_sha="$(sha256sum "$archive" | cut -d' ' -f1)"
  if [ "$actual_sha" != "$CERTBOT_ARCHIVE_SHA256" ]; then
    echo "ERROR: Certbot wheelhouse archive SHA256 mismatch" >&2
    return 1
  fi
  if [ -e "$CERTBOT_VENV_ROOT" ] \
    && { [ -L "$CERTBOT_VENV_ROOT" ] || [ ! -d "$CERTBOT_VENV_ROOT" ]; }; then
    echo "ERROR: Certbot venv root must be a real directory" >&2
    return 1
  fi
  install -d -o root -g root -m 0755 "$CERTBOT_VENV_ROOT"
  if [ -L "$target" ]; then
    echo "ERROR: versioned Certbot venv target must not be a symlink" >&2
    return 1
  fi
  discard_invalid_inactive_certbot_venv "$target" || return 1
  if [ ! -e "$target" ]; then
    command -v zstd >/dev/null || {
      echo "ERROR: zstd is required to extract the Certbot wheelhouse" >&2
      return 1
    }
    temp_dir="$(mktemp -d "$CERTBOT_VENV_ROOT/.build.XXXXXX")"
    wheelhouse="$temp_dir/certbot-wheelhouse-$CERTBOT_VERSION"
    if ! zstd -dc -- "$archive" > "$temp_dir/wheelhouse.tar" \
      || ! "$CERTBOT_PYTHON_RUNTIME_PYTHON" - "$temp_dir/wheelhouse.tar" "$temp_dir" "$CERTBOT_VERSION" <<'PY'
import pathlib
import sys
import tarfile

archive, output, version = sys.argv[1:]
root = f"certbot-wheelhouse-{version}"
with tarfile.open(archive, "r:") as source:
    members = source.getmembers()
    if not members:
        raise ValueError("empty Certbot wheelhouse archive")
    for member in members:
        path = pathlib.PurePosixPath(member.name)
        if not path.parts or path.parts[0] != root or ".." in path.parts:
            raise ValueError(f"archive member is outside {root}/: {member.name}")
        if not (member.isdir() or member.isfile()):
            raise ValueError(f"unsupported archive member: {member.name}")
    source.extractall(output, members=members, filter="data")
PY
    then
      echo "ERROR: Certbot wheelhouse extraction failed or archive is unsafe" >&2
      rm -rf -- "$temp_dir"
      return 1
    fi
    rm -f -- "$temp_dir/wheelhouse.tar"
    if ! "$CERTBOT_PYTHON_RUNTIME_PYTHON" - "$wheelhouse" <<'PY'
import hashlib
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
manifest = root / "manifest.sha256"
lines = manifest.read_text(encoding="utf-8").splitlines()
entries = {}
for line in lines:
    match = re.fullmatch(r"([0-9a-f]{64})  (requirements-linux-amd64\.txt|wheels/[^/]+\.whl)", line)
    if not match or match.group(2) in entries:
        raise ValueError("invalid Certbot wheelhouse manifest")
    entries[match.group(2)] = match.group(1)
files = {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()}
if len(entries) != 19 or files != {*entries, "manifest.sha256"}:
    raise ValueError("Certbot wheelhouse manifest does not cover exactly 19 files")
for name, expected in entries.items():
    if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
        raise ValueError(f"Certbot wheelhouse manifest mismatch: {name}")
requirements = (root / "requirements-linux-amd64.txt").read_text(encoding="utf-8").splitlines()
pattern = re.compile(r"[A-Za-z0-9_.-]+==[^ ]+ --hash=sha256:[0-9a-f]{64}")
if len(requirements) != 18 or len(set(requirements)) != 18 or not all(pattern.fullmatch(line) for line in requirements):
    raise ValueError("Certbot requirements must contain 18 unique exact hashes")
PY
    then
      rm -rf -- "$temp_dir"
      return 1
    fi
    if ! "$CERTBOT_PYTHON_RUNTIME_PYTHON" -m venv "$temp_dir/venv" \
      || ! "$temp_dir/venv/bin/python" -m pip install --no-index \
        --find-links "$wheelhouse/wheels" --require-hashes --no-compile \
        -r "$wheelhouse/requirements-linux-amd64.txt" \
      || ! "$temp_dir/venv/bin/python" -m pip check \
      || ! chmod -R go-w,u-s,g-s "$temp_dir/venv" \
      || ! verify_certbot_venv "$temp_dir/venv" \
      || ! relocate_certbot_venv "$temp_dir/venv" "$target" \
      || ! mv -T "$temp_dir/venv" "$target"; then
      rm -rf -- "$temp_dir"
      return 1
    fi
    rm -rf -- "$temp_dir"
  fi
  verify_certbot_venv "$target"
  CERTBOT_VENV_TARGET="$target"
}

activate_certbot_venv() {
  local next_link="$CERTBOT_VENV_LINK.next.$$" rollback_link resolved_target
  if [ -e "$CERTBOT_VENV_LINK" ] && [ ! -L "$CERTBOT_VENV_LINK" ]; then
    echo "ERROR: Certbot venv activation path is not a symlink" >&2
    return 1
  fi
  if [ -L "$CERTBOT_VENV_LINK" ]; then
    CERTBOT_VENV_BEFORE="$(readlink -f "$CERTBOT_VENV_LINK")" \
      && [ -d "$CERTBOT_VENV_BEFORE" ] || {
        echo "ERROR: existing Certbot venv symlink is broken" >&2
        return 1
      }
    CERTBOT_VENV_HAD_LINK=1
  fi
  ln -s "$CERTBOT_VENV_TARGET" "$next_link"
  mv -Tf "$next_link" "$CERTBOT_VENV_LINK"
  CERTBOT_VENV_SWITCHED=1
  if ! resolved_target="$(readlink -f -- "$CERTBOT_VENV_LINK")" \
    || [ "$resolved_target" != "$CERTBOT_VENV_TARGET" ] \
    || ! verify_certbot_venv "$resolved_target"; then
    if [ "$CERTBOT_VENV_HAD_LINK" -eq 1 ]; then
      rollback_link="$CERTBOT_VENV_LINK.rollback.$$"
      ln -s "$CERTBOT_VENV_BEFORE" "$rollback_link"
      mv -Tf "$rollback_link" "$CERTBOT_VENV_LINK"
    else
      rm -f -- "$CERTBOT_VENV_LINK"
    fi
    CERTBOT_VENV_SWITCHED=0
    return 1
  fi
}

validate_private_host_address() {
  local address="$1"
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
    echo "ERROR: Bridge address is not an RFC1918 IPv4 address: ${address:-<empty>}" >&2
    return 1
  fi
  if ! ip -4 -o addr show | awk '{sub(/\/.*/, "", $4); print $4}' | grep -Fqx "$address"; then
    echo "ERROR: Bridge address is not assigned to this host: $address" >&2
    return 1
  fi
}

resolve_hermes_bridge_bind_address() {
  local address container
  container="$(docker compose -p "$COMPOSE_PROJECT" ps -q api)"
  if [ -z "$container" ]; then
    echo "ERROR: running Compose API container is required for Bridge preflight" >&2
    return 1
  fi
  if ! address="$(docker compose -p "$COMPOSE_PROJECT" exec -T api python -c \
    "import signal,socket; signal.alarm(5); print(socket.gethostbyname('host.docker.internal'))")"; then
    echo "ERROR: API container could not resolve host.docker.internal" >&2
    return 1
  fi
  if [ -z "$address" ] || [[ "$address" == *$'\n'* ]]; then
    echo "ERROR: API container must resolve host.docker.internal to exactly one address" >&2
    return 1
  fi
  validate_private_host_address "$address" || return 1
  printf '%s\n' "$address"
}

preflight_hermes_bridge_network() {
  HERMES_BRIDGE_BIND_ADDRESS="$(resolve_hermes_bridge_bind_address)"
  export HERMES_BRIDGE_BIND_ADDRESS
  if docker compose -p "$COMPOSE_PROJECT" exec -T api python -c \
    "import json,urllib.request; assert json.load(urllib.request.urlopen('http://$HERMES_BRIDGE_BIND_ADDRESS:9118/health', timeout=5)).get('status') == 'ok'"; then
    return 0
  fi
  (
    local probe_dir probe_pid="" rc
    probe_dir="$(mktemp -d /tmp/hermes-bridge-probe.XXXXXX)"
    cleanup_probe() {
      rc=$?
      trap - EXIT INT TERM
      if [ -n "$probe_pid" ]; then
        kill "$probe_pid" 2>/dev/null || true
        wait "$probe_pid" 2>/dev/null || true
      fi
      rm -rf -- "$probe_dir"
      exit "$rc"
    }
    trap cleanup_probe EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    python3 - "$HERMES_BRIDGE_BIND_ADDRESS" "$probe_dir/ready" <<'PY' &
import http.server
import json
import sys

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return
        body = json.dumps({"status": "ok"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass

server = http.server.HTTPServer((sys.argv[1], 9118), Handler)
open(sys.argv[2], "x").close()
server.serve_forever()
PY
    probe_pid=$!
    for _ in $(seq 1 20); do
      kill -0 "$probe_pid" 2>/dev/null || return 1
      [ ! -e "$probe_dir/ready" ] || break
      sleep 0.1
    done
    [ -e "$probe_dir/ready" ] || return 1
    docker compose -p "$COMPOSE_PROJECT" exec -T api python -c \
      "import json,urllib.request; assert json.load(urllib.request.urlopen('http://$HERMES_BRIDGE_BIND_ADDRESS:9118/health', timeout=5)).get('status') == 'ok'"
  )
}

verify_hermes_bridge_network() {
  local attempt candidate_address
  candidate_address="$(resolve_hermes_bridge_bind_address)"
  if [ "$candidate_address" != "$HERMES_BRIDGE_BIND_ADDRESS" ]; then
    echo "ERROR: candidate host-gateway address does not match the preflight address" >&2
    return 1
  fi
  docker compose -p "$COMPOSE_PROJECT" exec -T api python -c \
    "import socket; assert socket.gethostbyname('host.docker.internal') == '$HERMES_BRIDGE_BIND_ADDRESS'"
  for attempt in $(seq 1 30); do
    if docker compose -p "$COMPOSE_PROJECT" exec -T api python -c \
      "import json,urllib.request; assert json.load(urllib.request.urlopen('http://$HERMES_BRIDGE_BIND_ADDRESS:9118/health', timeout=1)).get('status') == 'ok'" \
      2>/dev/null; then
      return 0
    fi
    [ "$attempt" -eq 30 ] || sleep 1
  done
  echo "ERROR: Hermes Bridge did not become healthy from the candidate API container within 30 attempts" >&2
  return 1
}

configure_hermes_bridge_network() {
  local env_dir env_file="$HERMES_BRIDGE_ENV_FILE" temp_file
  : "${HERMES_BRIDGE_BIND_ADDRESS:?Bridge network preflight was not completed}"
  env_dir="$(dirname "$env_file")"
  install -d -o root -g root -m 0755 "$env_dir"
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
  install -m 0644 "$APP_LINK/ops/systemd/ai-lab-certbot-renew.service" \
    /etc/systemd/system/ai-lab-certbot-renew.service
  install -m 0644 "$APP_LINK/ops/systemd/ai-lab-certbot-renew.timer" \
    /etc/systemd/system/ai-lab-certbot-renew.timer
  systemctl daemon-reload
  verify_hermes_bridge_unit
  systemctl enable hermes-bridge.service hermes-chat-worker.service
  verify_hermes_units_enabled
  systemctl enable --now ai-lab-certbot-renew.timer
}

verify_hermes_units_enabled() {
  systemctl is-enabled --quiet hermes-bridge.service
  systemctl is-enabled --quiet hermes-chat-worker.service
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
      systemctl restart "$unit" || return 1
    else
      echo "hermes_restart_status=skipped_absent unit=$unit"
    fi
  done
  return 0
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

repair_note_path_ancestors() {
  local vault_root="$1" path
  for path in "$vault_root/raw" "$vault_root/raw/dialogues"; do
    if [ -L "$path" ] || [ ! -d "$path" ]; then
      echo "ERROR: note path ancestor must be a real directory: $path" >&2
      return 1
    fi
    chown quantumn-hermes:quantumn-hermes "$path"
    chmod 0755 "$path"
  done
}

resolve_api_runtime_identity() {
  local config image runtime_uid
  config="$(docker compose -p "$COMPOSE_PROJECT" config --format json)" || return 1
  image="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["services"]["api"]["image"])' <<< "$config")" || return 1
  if [[ ! "$image" =~ ^[[:alnum:]][[:alnum:]./_:@-]*$ ]]; then
    echo "ERROR: invalid API image reference: ${image:-<empty>}" >&2
    return 1
  fi
  if [ -z "${ATTESTED_API_IMAGE:-}" ] || [ "$image" != "$ATTESTED_API_IMAGE" ]; then
    echo "ERROR: API runtime identity image is not the already-attested Compose image" >&2
    return 1
  fi
  runtime_uid="$(docker run --rm --pull never --network none --read-only \
    --cap-drop ALL --security-opt no-new-privileges --entrypoint id "$image" -u)" || return 1
  if [[ ! "$runtime_uid" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: hardened API image runtime UID must be a non-zero integer: ${runtime_uid:-<empty>}" >&2
    return 1
  fi
  API_RUNTIME_IMAGE="$image"
  API_RUNTIME_UID="$runtime_uid"
}

validate_shared_data_root() {
  local data_root="$1" expected="$SHARED_ROOT/data"
  if [ "$data_root" != "$expected" ] || [ -L "$data_root" ] \
    || [ "$(readlink -f -- "$data_root")" != "$data_root" ]; then
    echo "ERROR: ACL/probe target must be the exact shared data tree: $expected" >&2
    return 1
  fi
}

configure_shared_data_acl() {
  local data_root="$1" api_uid="$2" hermes_uid="$3" directory acl
  for tool in setfacl getfacl; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      echo "ERROR: $tool is required for shared data interoperability" >&2
      return 1
    fi
  done
  validate_shared_data_root "$data_root" || return 1
  setfacl -P -R -m "u:$api_uid:rwX,u:$hermes_uid:rwX,m::rwX" -- "$data_root" || return 1
  while IFS= read -r -d '' directory; do
    setfacl -m "d:u:$api_uid:rwx,d:u:$hermes_uid:rwx,d:m::rwx" -- "$directory" || return 1
  done < <(find -P "$data_root" -type d -print0)
  acl="$(getfacl -cpn -- "$data_root")" || return 1
  for entry in "user:$api_uid:rwx" "user:$hermes_uid:rwx" \
    "default:user:$api_uid:rwx" "default:user:$hermes_uid:rwx"; do
    grep -Fqx "$entry" <<< "$acl" || {
      echo "ERROR: shared data ACL verification failed: $entry" >&2
      return 1
    }
  done
}

verify_shared_data_access() {
  local data_root="$1" image="$2" api_uid="$3"
  validate_shared_data_root "$data_root" || return 1
  docker run --rm --pull never --network none --read-only \
    --cap-drop ALL --security-opt no-new-privileges \
    --mount "type=bind,src=$data_root,dst=/app/data" --env "EXPECTED_UID=$api_uid" \
    --entrypoint python "$image" -c '
import os, pathlib, tempfile
assert os.getuid() == int(os.environ["EXPECTED_UID"])
data = pathlib.Path("/app/data")
(data / "knowledge_matrix.json").read_bytes()
(data / "hermes_chat_runs.sqlite3").open("r+b").close()
for root in (data, data / "vault/raw/dialogues/tenants"):
    pathlib.Path(tempfile.mkdtemp(prefix=".api-acl-probe-", dir=root)).rmdir()
(data / "vault/.incremental-compile.lock").touch(exist_ok=True)
'
  runuser -u quantumn-hermes -- python3 -c '
import pathlib, sys, tempfile
data = pathlib.Path(sys.argv[1])
(data / "knowledge_matrix.json").read_bytes()
(data / "hermes_chat_runs.sqlite3").open("r+b").close()
for root in (data, data / "vault/raw/dialogues/tenants"):
    pathlib.Path(tempfile.mkdtemp(prefix=".hermes-acl-probe-", dir=root)).rmdir()
(data / "vault/.incremental-compile.lock").touch(exist_ok=True)
' "$data_root"
}

verify_offline_images() {
  local config service image operating_system architecture user healthcheck actual expected count
  local services=(postgres redis api workflow-worker planning-worker agent-evaluation-worker taskboard frontend)
  local attestations="${AI_LAB_OFFLINE_IMAGE_ATTESTATIONS:-$SHARED_ROOT/offline-images.attested}"
  if [ -L "$attestations" ] || [ ! -f "$attestations" ]; then
    echo "ERROR: offline image attestation file is missing or a symlink: $attestations" >&2
    return 1
  fi
  if [ "$(stat -c '%u' "$attestations")" != "0" ] \
    || [ $((8#$(stat -c '%a' "$attestations") & 8#022)) -ne 0 ]; then
    echo "ERROR: offline image attestations must be root-owned and not group/world writable" >&2
    return 1
  fi
  python3 - "$attestations" "${services[@]}" <<'PY' || return 1
import re
import sys

path, *expected = sys.argv[1:]
records = []
for line in open(path, encoding="utf-8").read().splitlines():
    match = re.fullmatch(r"([a-z][a-z0-9-]*)=(sha256:[0-9a-f]{64})", line)
    if not match:
        raise SystemExit(f"ERROR: invalid offline image attestation record: {line!r}")
    records.append(match.group(1))
if len(records) != len(set(records)) or set(records) != set(expected):
    raise SystemExit("ERROR: offline image attestations must contain exactly: " + " ".join(expected))
PY
  config="$(docker compose -p "$COMPOSE_PROJECT" config --format json)" || return 1
  COMPOSE_CONFIG="$config" python3 - <<'PY' || return 1
import json
import os

services = json.loads(os.environ["COMPOSE_CONFIG"])["services"]
for name in ("postgres",):
    healthcheck = services[name].get("healthcheck")
    test = healthcheck.get("test") if isinstance(healthcheck, dict) else None
    if (
        not isinstance(test, list)
        or len(test) < 2
        or test[0] not in {"CMD", "CMD-SHELL"}
        or not all(isinstance(item, str) and item for item in test[1:])
    ):
        raise SystemExit(f"ERROR: {name} must have a structured Compose healthcheck")
for name in ("postgres", "redis"):
    if any(port.get("host_ip") != "127.0.0.1" for port in services[name].get("ports", [])):
        raise SystemExit(f"ERROR: {name} host ports must bind to 127.0.0.1")
PY
  for service in "${services[@]}"; do
    image="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["services"][sys.argv[1]]["image"])' "$service" <<< "$config")" || return 1
    if [ -z "$image" ]; then
      echo "ERROR: required offline Compose image is unresolved: $service" >&2
      return 1
    fi
    count="$(awk -F= -v service="$service" '$1 == service {count++} END {print count+0}' "$attestations")"
    expected="$(awk -F= -v service="$service" '$1 == service {print $2}' "$attestations")"
    if [ "$count" -ne 1 ] || [[ ! "$expected" =~ ^sha256:[0-9a-f]{64}$ ]]; then
      echo "ERROR: missing or invalid offline image attestation: $service" >&2
      return 1
    fi
    if ! actual="$(docker image inspect --format '{{.Id}}' "$image")" \
      || ! operating_system="$(docker image inspect --format '{{.Os}}' "$image")" \
      || ! architecture="$(docker image inspect --format '{{.Architecture}}' "$image")"; then
      echo "ERROR: required offline image is missing: $service=$image" >&2
      return 1
    fi
    if [ "$actual" != "$expected" ]; then
      echo "ERROR: offline image hash mismatch: $service=$image" >&2
      return 1
    fi
    if [ "$operating_system" != "linux" ] || [ "$architecture" != "amd64" ]; then
      echo "ERROR: offline image must use linux/amd64: $service=$image" >&2
      return 1
    fi
    if ! user="$(docker image inspect --format '{{.Config.User}}' "$image")" \
      || ! healthcheck="$(docker image inspect --format '{{json .Config.Healthcheck}}' "$image")"; then
      echo "ERROR: required offline image metadata is missing: $service=$image" >&2
      return 1
    fi
    if [ -z "$user" ] || [[ "$user" =~ ^([Rr][Oo][Oo][Tt]|0+)(:|$) ]]; then
      echo "ERROR: offline image must configure a non-root user: $service=$image" >&2
      return 1
    fi
    if ! HEALTHCHECK_METADATA="$healthcheck" python3 -c '
import json
import os

value = json.loads(os.environ["HEALTHCHECK_METADATA"])
test = value.get("Test") if isinstance(value, dict) else None
valid = (
    isinstance(test, list)
    and len(test) >= 2
    and test[0] in {"CMD", "CMD-SHELL"}
    and all(isinstance(item, str) and item for item in test[1:])
)
raise SystemExit(0 if valid else 1)
'; then
      echo "ERROR: offline image must configure a healthcheck: $service=$image" >&2
      return 1
    fi
    [ "$service" != api ] || ATTESTED_API_IMAGE="$image"
  done
}

repair_taskboard_data_permissions() {
  local config image volume_rows volume count
  config="$(docker compose -p "$COMPOSE_PROJECT" config --format json)" || return 1
  image="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["services"]["taskboard"]["image"])' <<< "$config")" || return 1
  if [[ ! "$image" =~ ^[[:alnum:]][[:alnum:]./_:@-]*$ ]]; then
    echo "ERROR: invalid taskboard image reference: ${image:-<empty>}" >&2
    return 1
  fi
  volume_rows="$(docker volume ls \
    --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" \
    --filter "label=com.docker.compose.volume=taskboard_data" \
    --format '{{.Name}}')" || return 1
  count="$(printf '%s\n' "$volume_rows" | awk 'NF {count++} END {print count+0}')"
  if [ "$count" -ne 1 ]; then
    echo "ERROR: expected exactly one Compose taskboard_data volume, found $count" >&2
    return 1
  fi
  volume="$(printf '%s\n' "$volume_rows" | awk 'NF {print}')"
  if [[ ! "$volume" =~ ^[[:alnum:]][[:alnum:]_.-]*$ ]]; then
    echo "ERROR: invalid taskboard_data volume name: $volume" >&2
    return 1
  fi
  docker run --rm --pull never --network none --read-only \
    --cap-drop ALL --cap-add CHOWN --security-opt no-new-privileges --user 0 \
    --mount "type=volume,src=$volume,dst=/data" --entrypoint chown "$image" \
    -R 1000:1000 /data
}

managed_compose_services() {
  printf '%s\n' postgres redis api workflow-worker planning-worker \
    agent-evaluation-worker taskboard frontend
}

capture_failed_release_diagnostics() {
  local service containers container timestamp
  timestamp="$(date --iso-8601=seconds 2>/dev/null)" || timestamp=unknown
  echo "==> failed release diagnostics timestamp=$timestamp" >&2
  if ! docker compose -p "$COMPOSE_PROJECT" ps --format \
    'table {{.Name}}\t{{.Image}}\t{{.State}}\t{{.Status}}' \
    $(managed_compose_services) >&2; then
    echo "WARN: failed to capture Compose service status" >&2
  fi
  while IFS= read -r service; do
    if ! containers="$(docker compose -p "$COMPOSE_PROJECT" ps -q --all "$service" 2>/dev/null)"; then
      echo "WARN: failed to locate diagnostic container name=$service" >&2
      continue
    fi
    while IFS= read -r container; do
      [ -n "$container" ] || continue
      if ! docker inspect --format \
        '{{printf "name=%q image_id=%q image_ref=%q state_status=%q exit_code=%d restart_count=%d" .Name .Image .Config.Image .State.Status .State.ExitCode .RestartCount}}{{if .State.Health}}{{printf " health_status=%q" .State.Health.Status}}{{range .State.Health.Log}}{{printf "\nhealth_log exit_code=%d output=%.2048q" .ExitCode .Output}}{{end}}{{else}} health_status="none"{{end}}' \
        "$container" >&2; then
        echo "WARN: failed to inspect diagnostic container name=$service" >&2
      fi
      echo "logs name=$service timestamp=$timestamp since=10m tail=200" >&2
      if ! docker logs --timestamps --since 10m --tail 200 "$container" >&2; then
        echo "WARN: failed to capture container logs name=$service" >&2
      fi
    done <<< "$containers"
  done < <(managed_compose_services)
  return 0
}

normalize_mutable_image_reference() {
  local reference="$1" leaf="${1##*/}"
  if [[ -z "$reference" || "$reference" == *@* || "$reference" =~ ^sha256: \
    || "$reference" =~ ^[0-9a-f]{12,64}$ ]]; then
    echo "ERROR: rollback requires an ordinary mutable image tag: ${reference:-<empty>}" >&2
    return 1
  fi
  if [[ "$leaf" != *:* ]]; then
    reference="$reference:latest"
  fi
  if [[ ! "$reference" =~ ^[a-z0-9]+([._-][a-z0-9]+)*(:[0-9]+)?(/[a-z0-9]+([._-][a-z0-9]+)*)*:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ ]]; then
    echo "ERROR: rollback requires an ordinary mutable image tag: ${reference:-<empty>}" >&2
    return 1
  fi
  printf '%s\n' "$reference"
}

validate_mutable_image_reference() {
  normalize_mutable_image_reference "$1" >/dev/null
}

snapshot_managed_images() {
  local config service containers count container image_id available_id image_ref temp_file
  config="$(cd "$CURRENT_DIR" && docker compose -p "$COMPOSE_PROJECT" config --format json)" || return 1
  if ! python3 -c '
import json, sys
services = json.load(sys.stdin).get("services", {})
raise SystemExit(0 if all(service in services for service in sys.argv[1:]) else 1)
' $(managed_compose_services) <<< "$config"; then
    echo "ERROR: Compose config must contain all managed services" >&2
    return 1
  fi
  IMAGE_ROLLBACK_FILE="$UNIT_BACKUP_DIR/compose-images.tsv"
  temp_file="$(mktemp "$UNIT_BACKUP_DIR/.compose-images.XXXXXX")"
  chmod 0600 "$temp_file"
  while IFS= read -r service; do
    containers="$(cd "$CURRENT_DIR" && docker compose -p "$COMPOSE_PROJECT" ps -q --all "$service")" || return 1
    count="$(printf '%s\n' "$containers" | awk 'NF {count++} END {print count+0}')"
    if [ "$count" -ne 1 ]; then
      echo "ERROR: expected exactly one existing container for rollback: $service (found $count)" >&2
      return 1
    fi
    container="$(printf '%s\n' "$containers" | awk 'NF {print}')"
    image_id="$(docker inspect --format '{{.Image}}' "$container")" || return 1
    image_ref="$(docker inspect --format '{{.Config.Image}}' "$container")" || return 1
    if [[ ! "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]]; then
      echo "ERROR: invalid existing container image ID for rollback: $service=${image_id:-<empty>}" >&2
      return 1
    fi
    image_ref="$(normalize_mutable_image_reference "$image_ref")" || return 1
    available_id="$(docker image inspect --format '{{.Id}}' "$image_id")" || return 1
    if [ "$available_id" != "$image_id" ]; then
      echo "ERROR: existing container image is unavailable for rollback: $service" >&2
      return 1
    fi
    printf '%s\t%s\t%s\n' "$service" "$image_id" "$image_ref" >> "$temp_file"
  done < <(managed_compose_services)
  mv -f "$temp_file" "$IMAGE_ROLLBACK_FILE"
}

restore_managed_images() {
  local service expected_id image_ref actual count
  if [ -L "$IMAGE_ROLLBACK_FILE" ] || [ ! -f "$IMAGE_ROLLBACK_FILE" ] \
    || [ "$(stat -c '%u' "$IMAGE_ROLLBACK_FILE")" != "0" ] \
    || [ $((8#$(stat -c '%a' "$IMAGE_ROLLBACK_FILE") & 8#077)) -ne 0 ]; then
    echo "ERROR: rollback image snapshot is missing or not root-only" >&2
    return 1
  fi
  if ! awk -F '\t' 'NF != 3 {bad=1} END {exit bad || NR != 8}' "$IMAGE_ROLLBACK_FILE"; then
    echo "ERROR: rollback image snapshot must contain exactly eight valid records" >&2
    return 1
  fi
  while IFS= read -r service; do
    count="$(awk -F '\t' -v service="$service" '$1 == service {count++} END {print count+0}' "$IMAGE_ROLLBACK_FILE")"
    if [ "$count" -ne 1 ]; then
      echo "ERROR: rollback image snapshot must contain exactly one record: $service" >&2
      return 1
    fi
    IFS=$'\t' read -r _ expected_id image_ref < <(awk -F '\t' -v service="$service" '$1 == service {print}' "$IMAGE_ROLLBACK_FILE")
    if [[ ! "$expected_id" =~ ^sha256:[0-9a-f]{64}$ ]]; then
      echo "ERROR: invalid saved rollback image ID: $service" >&2
      return 1
    fi
    validate_mutable_image_reference "$image_ref" || return 1
    docker image tag "$expected_id" "$image_ref" || return 1
  done < <(managed_compose_services)
  while IFS= read -r service; do
    IFS=$'\t' read -r _ expected_id image_ref < <(awk -F '\t' -v service="$service" '$1 == service {print}' "$IMAGE_ROLLBACK_FILE")
    actual="$(docker image inspect --format '{{.Id}}' "$image_ref")" || return 1
    if [ "$actual" != "$expected_id" ]; then
      echo "ERROR: restored rollback image tag does not resolve to saved ID: $service" >&2
      return 1
    fi
  done < <(managed_compose_services)
}

managed_unit_paths() {
  printf '%s\n' \
    hermes-bridge.service:/etc/systemd/system/hermes-bridge.service \
    hermes-chat-worker.service:/etc/systemd/system/hermes-chat-worker.service \
    ai-lab-certbot-renew.service:/etc/systemd/system/ai-lab-certbot-renew.service \
    ai-lab-certbot-renew.timer:/etc/systemd/system/ai-lab-certbot-renew.timer \
    hermes-bridge.agent-os:/etc/systemd/system/hermes-bridge.service.d/agent-os-mode.conf \
    hermes-serve.agent-os:/etc/systemd/system/hermes-serve.service.d/agent-os-mode.conf \
    hermes-gateway.agent-os:/etc/systemd/system/hermes-gateway.service.d/agent-os-mode.conf \
    hermes-bridge.env:"$HERMES_BRIDGE_ENV_FILE"
}

snapshot_managed_units() {
  local key path
  UNIT_BACKUP_DIR="$SHARED_ROOT/rollbacks/update-$SHORT_SHA-units.$(date +%s).$$"
  install -d -o root -g root -m 0700 "$UNIT_BACKUP_DIR"
  while IFS=: read -r key path; do
    if [ -e "$path" ] || [ -L "$path" ]; then
      cp -a "$path" "$UNIT_BACKUP_DIR/$key"
    else
      : > "$UNIT_BACKUP_DIR/$key.absent"
    fi
  done < <(managed_unit_paths)
  systemctl is-enabled --quiet ai-lab-certbot-renew.timer && CERT_TIMER_WAS_ENABLED=1 || true
  systemctl is-enabled --quiet hermes-bridge.service && BRIDGE_WAS_ENABLED=1 || true
  systemctl is-enabled --quiet hermes-chat-worker.service && CHAT_WORKER_WAS_ENABLED=1 || true
  systemctl is-active --quiet ai-lab-certbot-renew.timer && CERT_TIMER_WAS_ACTIVE=1 || true
  systemctl is-active --quiet hermes-bridge.service && BRIDGE_WAS_ACTIVE=1 || true
  systemctl is-active --quiet hermes-chat-worker.service && CHAT_WORKER_WAS_ACTIVE=1 || true
}

restore_managed_units() {
  local key path
  if systemctl cat ai-lab-certbot-renew.timer >/dev/null 2>&1; then
    systemctl stop ai-lab-certbot-renew.timer || return 1
  fi
  while IFS=: read -r key path; do
    if [ -e "$UNIT_BACKUP_DIR/$key.absent" ]; then
      rm -f -- "$path"
    else
      install -d -o root -g root -m 0755 "$(dirname "$path")"
      rm -f -- "$path"
      cp -a "$UNIT_BACKUP_DIR/$key" "$path"
    fi
  done < <(managed_unit_paths)
  systemctl daemon-reload || return 1
  if [ "$CERT_TIMER_WAS_ENABLED" -eq 1 ]; then
    systemctl enable ai-lab-certbot-renew.timer || return 1
  fi
  if [ "$BRIDGE_WAS_ENABLED" -eq 1 ]; then
    systemctl enable hermes-bridge.service || return 1
  else
    systemctl disable hermes-bridge.service || return 1
  fi
  if [ "$CHAT_WORKER_WAS_ENABLED" -eq 1 ]; then
    systemctl enable hermes-chat-worker.service || return 1
  else
    systemctl disable hermes-chat-worker.service || return 1
  fi
  if [ "$CERT_TIMER_WAS_ACTIVE" -eq 1 ]; then
    systemctl start ai-lab-certbot-renew.timer || return 1
  fi
}

verify_application_services() {
  docker compose -p "$COMPOSE_PROJECT" exec -T api python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=5).read()" || return 1
  docker compose -p "$COMPOSE_PROJECT" exec -T taskboard \
    node -e "fetch('http://127.0.0.1:47823/api/meta').then(response => process.exit(response.ok ? 0 : 1)).catch(() => process.exit(1))" || return 1
  docker compose -p "$COMPOSE_PROJECT" exec -T workflow-worker python -c \
    "import pathlib; assert b'backend.workers.workflow_worker' in pathlib.Path('/proc/1/cmdline').read_bytes()" || return 1
  docker compose -p "$COMPOSE_PROJECT" exec -T planning-worker python -c \
    "import pathlib; assert b'backend.workers.workflow_planning_worker' in pathlib.Path('/proc/1/cmdline').read_bytes()" || return 1
  docker compose -p "$COMPOSE_PROJECT" exec -T agent-evaluation-worker python -c \
    "import pathlib; assert b'backend.workers.agent_evaluation_worker' in pathlib.Path('/proc/1/cmdline').read_bytes()" || return 1
  docker compose -p "$COMPOSE_PROJECT" exec -T frontend \
    wget --no-check-certificate -q -O /dev/null https://127.0.0.1:9081/ || return 1
}

verify_rollback_health() {
  local env_file="$HERMES_BRIDGE_ENV_FILE" line restored_address
  verify_application_services || return 1
  [ "$BRIDGE_WAS_ACTIVE" -eq 0 ] || systemctl is-active --quiet hermes-bridge.service || return 1
  [ "$CHAT_WORKER_WAS_ACTIVE" -eq 0 ] || systemctl is-active --quiet hermes-chat-worker.service || return 1
  [ "$BRIDGE_WAS_ACTIVE" -eq 1 ] || return 0
  if [ -L "$env_file" ] || [ ! -f "$env_file" ] || [ "$(wc -l < "$env_file")" -ne 1 ]; then
    echo "ERROR: restored Hermes Bridge environment is missing or invalid" >&2
    return 1
  fi
  IFS= read -r line < "$env_file"
  if [[ ! "$line" =~ ^HERMES_BRIDGE_BIND_ADDRESS=([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
    echo "ERROR: restored Hermes Bridge bind address is malformed" >&2
    return 1
  fi
  restored_address="${line#HERMES_BRIDGE_BIND_ADDRESS=}"
  validate_private_host_address "$restored_address" || return 1
  docker compose -p "$COMPOSE_PROJECT" exec -T api python -c \
    "import socket; assert socket.gethostbyname('host.docker.internal') == '$restored_address'" || return 1
  docker compose -p "$COMPOSE_PROJECT" exec -T api python -c \
    "import json,urllib.request; assert json.load(urllib.request.urlopen('http://$restored_address:9118/health', timeout=5)).get('status') == 'ok'" || return 1
}

rollback_deployment() {
  local rollback_link rollback_venv_link rollback_certbot_link
  restore_managed_units || return 1
  if [ "$SWITCHED" -eq 1 ]; then
    rollback_link="$APP_LINK.rollback.$$"
    ln -s "$CURRENT_DIR" "$rollback_link" || return 1
    mv -Tf "$rollback_link" "$APP_LINK" || return 1
  fi
  if [ "$BRIDGE_WORKER_VENV_SWITCHED" -eq 1 ]; then
    if [ "$BRIDGE_WORKER_VENV_HAD_LINK" -eq 1 ]; then
      rollback_venv_link="$BRIDGE_WORKER_VENV_LINK.rollback.$$"
      ln -s "$BRIDGE_WORKER_VENV_BEFORE" "$rollback_venv_link" || return 1
      mv -Tf "$rollback_venv_link" "$BRIDGE_WORKER_VENV_LINK" || return 1
    else
      rm -f -- "$BRIDGE_WORKER_VENV_LINK" || return 1
    fi
  fi
  if [ "${CERTBOT_VENV_SWITCHED:-0}" -eq 1 ]; then
    if [ "$CERTBOT_VENV_HAD_LINK" -eq 1 ]; then
      rollback_certbot_link="$CERTBOT_VENV_LINK.rollback.$$"
      ln -s "$CERTBOT_VENV_BEFORE" "$rollback_certbot_link" || return 1
      mv -Tf "$rollback_certbot_link" "$CERTBOT_VENV_LINK" || return 1
      [ "$(readlink -f "$CERTBOT_VENV_LINK")" = "$CERTBOT_VENV_BEFORE" ] || return 1
      [ -x "$CERTBOT_VENV_LINK/bin/certbot" ] || return 1
    else
      rm -f -- "$CERTBOT_VENV_LINK" || return 1
    fi
  fi
  cd "$CURRENT_DIR" || return 1
  restore_managed_images || return 1
  docker compose -p "$COMPOSE_PROJECT" up -d --no-build --pull never || return 1
  restart_hermes_runtime || return 1
  verify_rollback_health || return 1
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
CERTBOT_VENV_TARGET=""
CERTBOT_VENV_BEFORE=""
CERTBOT_VENV_HAD_LINK=0
CERTBOT_VENV_SWITCHED=0
UNIT_BACKUP_DIR=""
IMAGE_ROLLBACK_FILE=""
CERT_TIMER_WAS_ENABLED=0
CERT_TIMER_WAS_ACTIVE=0
BRIDGE_WAS_ACTIVE=0
CHAT_WORKER_WAS_ACTIVE=0
BRIDGE_WAS_ENABLED=0
CHAT_WORKER_WAS_ENABLED=0
API_RUNTIME_IMAGE=""
API_RUNTIME_UID=""
ATTESTED_API_IMAGE=""
cleanup() {
  rc=$? rollback_ok=1
  trap - EXIT
  if [ "$TARBALL_VALIDATED" -eq 1 ] && [ -n "$TARBALL" ]; then
    rm -f "$TARBALL"
  fi
  if [ "$rc" -ne 0 ] && [ "$RUNTIME_CHANGED" -eq 1 ]; then
    capture_failed_release_diagnostics
    echo "WARN: 发布失败，恢复旧 release: $CURRENT_DIR" >&2
    if ! rollback_deployment; then
      echo "ERROR: deployment rollback or restored health verification failed" >&2
      rollback_ok=0
      rc=1
    fi
  fi
  if [ "$rollback_ok" -eq 1 ] \
    && { [ "$SWITCHED" -eq 0 ] || [ "$rc" -ne 0 ]; } \
    && [ "$RELEASE_VALIDATED" -eq 1 ]; then
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
if ! command -v flock >/dev/null 2>&1; then
  echo "ERROR: flock is required for serialized deployment" >&2
  exit 1
fi
install -d -o root -g root -m 0755 /run/lock
exec 9>/run/lock/ai-lab-platform-update.lock
if ! flock -n 9; then
  echo "ERROR: another AI Lab deployment is already running" >&2
  exit 1
fi
cd "$CURRENT_DIR"
docker compose -p "$COMPOSE_PROJECT" config >/dev/null
preflight_hermes_bridge_network
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
validate_shared_data_root "$DATA_TARGET"
repair_runtime_store_permissions "$DATA_TARGET"
rm -rf "$STAGING_DIR/data" "$STAGING_DIR/backups" "$STAGING_DIR/rollbacks"
ln -s "$SHARED_ROOT/.env" "$STAGING_DIR/.env"
ln -s "$DATA_TARGET" "$STAGING_DIR/data"
ln -s "$SHARED_ROOT/backups" "$STAGING_DIR/backups"
ln -s "$SHARED_ROOT/rollbacks" "$STAGING_DIR/rollbacks"
cd "$RELEASE_DIR"
echo "==> [3/6] 验证预载离线镜像并启动 Compose 服务"
verify_hermes_install
prepare_bridge_worker_venv "$RELEASE_DIR"
prepare_certbot_venv
verify_offline_images
resolve_api_runtime_identity
configure_shared_data_acl "$DATA_TARGET" "$API_RUNTIME_UID" "$AI_LAB_RUNTIME_UID"
snapshot_managed_units
snapshot_managed_images
RUNTIME_CHANGED=1
activate_bridge_worker_venv
activate_certbot_venv
AI_LAB_DEPLOY_LOCK_HELD=1 bash scripts/renew_tls_certificate.sh --preflight-only
echo "==> [3a/6] 执行 QuantumWorkspace additive schema migration"
docker compose -p "$COMPOSE_PROJECT" run --rm --no-deps --pull never api \
  python scripts/migrate_quantum_workspace.py
repair_taskboard_data_permissions
docker compose -p "$COMPOSE_PROJECT" up -d --no-build --pull never

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
if [[ "$KNOWLEDGE_MATRIX_TARGET" != "$DATA_TARGET/"* ]]; then
  echo "ERROR: knowledge_matrix.json must resolve inside the shared data tree" >&2
  exit 1
fi
chown quantumn-hermes:quantumn-hermes "$KNOWLEDGE_MATRIX_TARGET"
chmod 0640 "$KNOWLEDGE_MATRIX_TARGET"
configure_shared_data_acl "$DATA_TARGET" "$API_RUNTIME_UID" "$AI_LAB_RUNTIME_UID"
docker compose -p "$COMPOSE_PROJECT" exec -T api \
  python scripts/audit_runtime_contracts.py --data-dir /app/data
printf '%s\n' "$EXPECTED_SHA" > .deployed-sha

echo "==> [4b/6] 建立 Hermes Vault 可见性链接并修复笔记共享权限"
VAULT_ROOT="$DATA_TARGET/vault"
repair_vault_runtime_permissions "$VAULT_ROOT"
repair_note_path_ancestors "$VAULT_ROOT"
bash scripts/link_release_vault.sh "$RELEASE_DIR" "$RELEASE_ROOT" "$VAULT_ROOT"
python3 scripts/repair_user_note_permissions.py \
  --owner-uid "$AI_LAB_RUNTIME_UID" --owner-gid "$AI_LAB_RUNTIME_GID" \
  "$VAULT_ROOT/raw/dialogues/tenants"
install -d -o quantumn-hermes -g quantumn-hermes -m 0700 "$VAULT_ROOT/wiki/tenant"
install -d -o quantumn-hermes -g quantumn-hermes -m 0755 "$VAULT_ROOT/wiki/contributions"
configure_shared_data_acl "$DATA_TARGET" "$API_RUNTIME_UID" "$AI_LAB_RUNTIME_UID"

echo "==> [5/6] 原子切换 release 并重启 Hermes runtime"
LINK_TMP="$APP_LINK.next.$$"
ln -s "$RELEASE_DIR" "$LINK_TMP"
mv -Tf "$LINK_TMP" "$APP_LINK"
SWITCHED=1
configure_cloud_agent_os_mode
install_hermes_units
restart_hermes_runtime
if [ "$AI_LAB_HERMES_QUARANTINED" != "1" ]; then
  verify_hermes_bridge_network
fi
repair_runtime_store_permissions "$DATA_TARGET"
repair_vault_runtime_permissions "$VAULT_ROOT"
python3 scripts/repair_user_note_permissions.py \
  --owner-uid "$AI_LAB_RUNTIME_UID" --owner-gid "$AI_LAB_RUNTIME_GID" \
  "$VAULT_ROOT/raw/dialogues/tenants"
configure_shared_data_acl "$DATA_TARGET" "$API_RUNTIME_UID" "$AI_LAB_RUNTIME_UID"
verify_shared_data_access "$DATA_TARGET" "$API_RUNTIME_IMAGE" "$API_RUNTIME_UID"

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
verify_application_services
verify_hermes_units_enabled
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
