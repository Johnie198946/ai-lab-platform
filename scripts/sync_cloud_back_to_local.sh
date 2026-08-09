#!/usr/bin/env bash
# 云端 → 本地 回流脚本: 把云端自生长产生的知识增量同步回本地 vault
# (云端子 Agent 产生的 raw/ 新文件 + wiki 增量, rsync 拉回本地)
# 用法: bash scripts/sync_cloud_back_to_local.sh
# 注意: 与 sync_data_to_server.sh(本地→云端 --delete 全量镜像)互补, 方向相反
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

if [ -f .env ]; then
  set -o allexport
  source .env
  set +o allexport
fi

SERVER_USER="${SERVER_USER:-root}"
SERVER_HOST="${SERVER_HOST:-}"
SERVER_PATH="${SERVER_PATH:-/opt/ai-lab-platform/data/vault}"
LOCAL_VAULT_PATH="${LOCAL_VAULT_PATH:-/Users/dengzhaoyu/Desktop/AI Lab/AI Lab}"

if [ -z "${SERVER_HOST}" ]; then
  echo "❌ 未配置 SERVER_HOST, 跳过回流"
  exit 1
fi

echo "==> 云端 → 本地 增量回流 (rsync --update 不删本地文件)"
# raw/ 增量(云端自生长产物) + wiki/ 增量
rsync -avz --update --timeout=30 \
  -e "ssh -o ConnectTimeout=10" \
  --exclude='.obsidian/' --exclude='_archive/' --exclude='00_Inbox/' \
  --exclude='模板/' --exclude='.git/' \
  "${SERVER_USER}@${SERVER_HOST}:${SERVER_PATH}/raw/" "${LOCAL_VAULT_PATH}/raw/"

rsync -avz --update --timeout=30 \
  -e "ssh -o ConnectTimeout=10" \
  "${SERVER_USER}@${SERVER_HOST}:${SERVER_PATH}/wiki/" "${LOCAL_VAULT_PATH}/wiki/"

# knowledge_matrix.json(云端重建的)
scp -q -o ConnectTimeout=10 \
  "${SERVER_USER}@${SERVER_HOST}:${SERVER_PATH}/knowledge_matrix.json" \
  "${PROJECT_ROOT}/data/knowledge_matrix.json" 2>/dev/null || true

echo "✅ 回流完成: $(date '+%Y-%m-%d %H:%M:%S')"
