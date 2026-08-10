#!/usr/bin/env bash
# AI Lab — 本地数据/知识库点对点直传云服务器脚本（完全与 GitHub 解耦）
#
# 说明:
# 1. 知识库 (Obsidian Vault) 与 knowledge_matrix.json 属于核心资产，绝不推送至 GitHub；
# 2. 本脚本通过 SSH/rsync 将本地数据直接直传至云服务器挂载目录；
# 3. 传输全程加密，点对点双向可控，零第三方中转。
#
# 用法:
#   # 方式 1: 在 .env 或环境变量中指定 SERVER_HOST 后直接运行
#   SERVER_HOST="your-server-ip" bash scripts/sync_data_to_server.sh
#
#   # 方式 2: 提前在 .env 配置 SERVER_HOST, SERVER_USER, SERVER_PATH

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# 加载 .env 环境变量（若存在）
if [ -f .env ]; then
  set -o allexport
  source .env
  set +o allexport
fi

SERVER_USER="${SERVER_USER:-root}"
SERVER_HOST="${SERVER_HOST:-}"
SERVER_PATH="${SERVER_PATH:-/opt/ai-lab-platform/data}"
LOCAL_VAULT_PATH="${LOCAL_VAULT_PATH:-/Users/dengzhaoyu/Desktop/AI Lab/AI Lab}"
LOCAL_MATRIX_PATH="${PROJECT_ROOT}/data/knowledge_matrix.json"

echo "========================================================"
echo "  AI Lab 知识库点对点私密直传工具 (完全解耦 GitHub)"
echo "========================================================"

if [ -z "${SERVER_HOST}" ]; then
  echo "❌ 错误: 未指定服务器 IP/域名 (SERVER_HOST)。"
  echo "请在 .env 中设置 SERVER_HOST=xxx.xxx.xxx.xxx 或运行时传入:"
  echo "  SERVER_HOST=\"1.2.3.4\" bash scripts/sync_data_to_server.sh"
  exit 1
fi

# 1. 本地重新构建知识矩阵
echo "==> [1/3] 本地重新编译低 Token 知识矩阵 (knowledge_matrix.json)..."
if [ -f "${PROJECT_ROOT}/.venv/bin/python" ]; then
  PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
else
  PYTHON_BIN="python3"
fi

"${PYTHON_BIN}" scripts/build_knowledge_matrix.py \
  --vault-dir "${LOCAL_VAULT_PATH}" \
  --output "${LOCAL_MATRIX_PATH}"

echo "    ✅ 矩阵生成完成: ${LOCAL_MATRIX_PATH}"

# 2. 测试 SSH 连通性
echo "==> [2/3] 检查云服务器点对点 SSH 连接 (${SERVER_USER}@${SERVER_HOST})..."
if ! ssh -o ConnectTimeout=5 -q "${SERVER_USER}@${SERVER_HOST}" exit; then
  echo "❌ 错误: 无法连接至云服务器 ${SERVER_USER}@${SERVER_HOST}，请检查 SSH 密钥配置或网络通道。"
  exit 1
fi

# 3. 点对点 rsync 直传（同步 Vault 与 Matrix）
echo "==> [3/3] 开始点对点直传数据至云服务器 ${SERVER_PATH}..."

# 确保远程目录存在
ssh "${SERVER_USER}@${SERVER_HOST}" "mkdir -p ${SERVER_PATH}/vault"

# 同步 Obsidian Vault (排除 .obsidian 临时配置文件)
# ⚠️ 2026-08-09 修正: 去掉 --delete — 云端子 Agent 自生长会新增 raw/wiki 文件,
#    --delete 会把它们当"本地已删"清掉。改为 --update 增量: 本地新/改文件覆盖同名,
#    云端新文件保留(由 sync_cloud_back_to_local.sh 回流本地)。
# ⚠️ 2026-08-10 约定: 访客画像/ 目录仅存在于服务器端(体验中心业务·本地不需要)。
#    本地严禁创建同名 访客画像/ 目录 — 否则 rsync --update 会把本地同名文件
#    覆盖到服务器端。服务器端访客画像自生长·永不回传本地。
# ⚠️ 2026-08-10 修正: 上行 exclude 访客画像/ — 防止本地误创建同名目录后回推覆盖服务器端。
#    访客画像单向回流（服务器→本地）由 sync_cloud_back_to_local.sh 处理。
echo "    → 直传 Obsidian Vault 编译知识库(增量, 保留云端自生长)..."
rsync -avz --update \
  --exclude=".obsidian/" \
  --exclude="*.tmp" \
  --exclude="访客画像/" \
  "${LOCAL_VAULT_PATH}/" \
  "${SERVER_USER}@${SERVER_HOST}:${SERVER_PATH}/vault/"

# 同步 knowledge_matrix.json
echo "    → 直传 knowledge_matrix.json 机器索引..."
rsync -avz \
  "${LOCAL_MATRIX_PATH}" \
  "${SERVER_USER}@${SERVER_HOST}:${SERVER_PATH}/knowledge_matrix.json"

echo "========================================================"
echo "🎉 直传完成！云服务端数据已同步最新版本（零 GitHub 依赖）。"
echo "建议云端执行: docker compose restart api (刷新挂载与内存缓存)"
echo "========================================================"
