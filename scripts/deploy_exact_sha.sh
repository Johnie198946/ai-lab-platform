#!/bin/bash
# 从本地已审查的 Git commit 导出并执行目标 SHA 的服务器部署脚本。
# 用法: AI_LAB_DEPLOY_HOST=root@example.com bash scripts/deploy_exact_sha.sh <40位 commit SHA>

set -euo pipefail

if [ "$#" -ne 1 ] || [[ ! "$1" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "ERROR: 必须提供且仅提供一个精确的 40 位 commit SHA" >&2
  exit 2
fi

EXPECTED_SHA="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
DEPLOY_HOST="${AI_LAB_DEPLOY_HOST:?ERROR: 必须设置 AI_LAB_DEPLOY_HOST}"
LOCAL_SCRIPT="$(mktemp "${TMPDIR:-/tmp}/ai-lab-update.XXXXXX")"
REMOTE_SCRIPT=""

cleanup() {
  rc=$?
  trap - EXIT
  rm -f "$LOCAL_SCRIPT"
  if [[ "$REMOTE_SCRIPT" =~ ^/tmp/ai-lab-update\.[A-Za-z0-9]{6}$ ]]; then
    ssh -o BatchMode=yes "$DEPLOY_HOST" rm -f -- "$REMOTE_SCRIPT" >/dev/null 2>&1 || true
  fi
  exit "$rc"
}
trap cleanup EXIT

git cat-file -e "$EXPECTED_SHA^{commit}"
git show "$EXPECTED_SHA:scripts/update.sh" > "$LOCAL_SCRIPT"
bash -n "$LOCAL_SCRIPT"
LOCAL_HASH="$(shasum -a 256 "$LOCAL_SCRIPT" | cut -d' ' -f1)"

REMOTE_SCRIPT="$(ssh -o BatchMode=yes "$DEPLOY_HOST" mktemp /tmp/ai-lab-update.XXXXXX)"
if [[ ! "$REMOTE_SCRIPT" =~ ^/tmp/ai-lab-update\.[A-Za-z0-9]{6}$ ]]; then
  echo "ERROR: 远端未返回受控的随机临时路径" >&2
  exit 1
fi

scp -q "$LOCAL_SCRIPT" "$DEPLOY_HOST:$REMOTE_SCRIPT"
ssh -o BatchMode=yes "$DEPLOY_HOST" bash -s -- \
  "$REMOTE_SCRIPT" "$EXPECTED_SHA" "$LOCAL_HASH" <<'REMOTE'
set -euo pipefail
REMOTE_SCRIPT="$1"
EXPECTED_SHA="$2"
LOCAL_HASH="$3"
REMOTE_HASH="$(sha256sum "$REMOTE_SCRIPT" | cut -d' ' -f1)"
test "$REMOTE_HASH" = "$LOCAL_HASH"
bash "$REMOTE_SCRIPT" "$EXPECTED_SHA"
REMOTE
