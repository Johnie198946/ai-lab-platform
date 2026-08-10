#!/usr/bin/env bash
# 云端 → 本地 增量回流脚本（含冲突检测与隔离）
#
# 功能：
#   1. 冲突检测：遍历两端共有文件，MD5 不一致 → 标冲突
#   2. 冲突处理：服务器版 → raw/待合并/<YYYY-MM-DD>/<filename>.server.md
#                本地版保留原位
#   3. 生成 冲突清单.md（双方差异摘要）
#   4. 增量回流：rsync --update（跳过冲突文件·含访客画像/）
#   5. 幂等：多次运行不产生 .server.server 递归后缀
#   6. 安全：无 --delete·全链增量
#
# 用法: bash scripts/sync_cloud_back_to_local.sh
# 输出: 冲突时生成 raw/待合并/<日期>/冲突清单.md 并打印摘要
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
SERVER_VAULT_PATH="${SERVER_VAULT_PATH:-/opt/ai-lab-platform/data/vault}"
LOCAL_VAULT_PATH="${LOCAL_VAULT_PATH:-/Users/dengzhaoyu/Desktop/AI Lab/AI Lab}"

if [ -z "${SERVER_HOST}" ]; then
  echo "❌ 未配置 SERVER_HOST, 跳过回流"
  exit 1
fi

TODAY=$(date '+%Y-%m-%d')
MERGE_DIR="${LOCAL_VAULT_PATH}/raw/待合并/${TODAY}"
CONFLICT_LIST="${MERGE_DIR}/冲突清单.md"

# 同步目录列表（不含访客画像·访客画像单独处理）
SYNC_DIRS=("raw" "wiki")

echo "==> [1/4] 冲突检测：比对两端共有文件 MD5..."
mkdir -p "${MERGE_DIR}"

# 初始化冲突清单
cat > "${CONFLICT_LIST}" <<EOF
# 冲突清单 - ${TODAY}

生成时间: $(date '+%Y-%m-%d %H:%M:%S')

## 冲突文件列表

EOF

CONFLICT_COUNT=0
CONFLICT_FILES=()

# 创建临时文件列表
TMP_LOCAL=$(mktemp)
TMP_SERVER=$(mktemp)
trap 'rm -f "${TMP_LOCAL}" "${TMP_SERVER}"' EXIT

for DIR in "${SYNC_DIRS[@]}"; do
  LOCAL_DIR="${LOCAL_VAULT_PATH}/${DIR}"
  SERVER_DIR="${SERVER_VAULT_PATH}/${DIR}"

  # 跳过不存在的目录
  [ -d "${LOCAL_DIR}" ] || continue

  # 获取本地文件列表（相对路径）
  (cd "${LOCAL_DIR}" && find . -type f -name "*.md" -o -name "*.json" | sed 's|^\./||' | sort) > "${TMP_LOCAL}"

  # 获取服务器文件列表
  ssh -o ConnectTimeout=10 "${SERVER_USER}@${SERVER_HOST}" \
    "cd '${SERVER_DIR}' 2>/dev/null && find . -type f -name '*.md' -o -name '*.json' | sed 's|^\./||' | sort" \
    > "${TMP_SERVER}" 2>/dev/null || true

  # 找出两端共有的文件
  comm -12 "${TMP_LOCAL}" "${TMP_SERVER}" | while IFS= read -r rel_path; do
    LOCAL_FILE="${LOCAL_DIR}/${rel_path}"
    SERVER_FILE="${SERVER_DIR}/${rel_path}"

    # 计算本地 MD5
    LOCAL_MD5=$(md5 -q "${LOCAL_FILE}" 2>/dev/null || md5sum "${LOCAL_FILE}" | awk '{print $1}')

    # 计算服务器 MD5
    SERVER_MD5=$(ssh -o ConnectTimeout=10 "${SERVER_USER}@${SERVER_HOST}" \
      "md5sum '${SERVER_FILE}' 2>/dev/null | awk '{print \$1}' || md5 -q '${SERVER_FILE}'" 2>/dev/null)

    # 比对 MD5
    if [ "${LOCAL_MD5}" != "${SERVER_MD5}" ] && [ -n "${SERVER_MD5}" ]; then
      # 冲突！
      echo "  ⚠️  冲突: ${DIR}/${rel_path}"

      # 幂等命名：避免 .server.server 递归
      BASENAME=$(basename "${rel_path}")
      DIRNAME=$(dirname "${rel_path}")
      # 如果已有 .server 后缀，不再追加
      if [[ "${BASENAME}" == *.server.md ]] || [[ "${BASENAME}" == *.server.json ]]; then
        SERVER_BASENAME="${BASENAME}"
      else
        EXT="${BASENAME##*.}"
        NAME="${BASENAME%.*}"
        SERVER_BASENAME="${NAME}.server.${EXT}"
      fi

      # 服务器版落盘到待合并区
      MERGE_SUBDIR="${MERGE_DIR}/${DIRNAME}"
      mkdir -p "${MERGE_SUBDIR}"
      MERGE_FILE="${MERGE_SUBDIR}/${SERVER_BASENAME}"

      scp -q -o ConnectTimeout=10 \
        "${SERVER_USER}@${SERVER_HOST}:${SERVER_FILE}" \
        "${MERGE_FILE}" 2>/dev/null || true

      # 记录到冲突清单
      cat >> "${CONFLICT_LIST}" <<EOF
### ${DIR}/${rel_path}
- 本地路径: \`${LOCAL_FILE}\`
- 服务器路径: \`${SERVER_FILE}\`
- 服务器版备份: \`${MERGE_FILE}\`
- 本地 MD5: \`${LOCAL_MD5}\`
- 服务器 MD5: \`${SERVER_MD5}\`

EOF

      CONFLICT_COUNT=$((CONFLICT_COUNT + 1))
      CONFLICT_FILES+=("${DIR}/${rel_path}")
    fi
  done
done

echo "  冲突文件数: ${CONFLICT_COUNT}"

if [ ${CONFLICT_COUNT} -gt 0 ]; then
  echo "  📋 冲突清单: ${CONFLICT_LIST}"
else
  echo "  ✅ 无冲突"
  # 无冲突时删除空清单
  rm -f "${CONFLICT_LIST}"
  rmdir "${MERGE_DIR}" 2>/dev/null || true
fi

echo ""
echo "==> [2/4] 增量回流：rsync --update（跳过冲突文件）..."

# 构建 exclude 列表（冲突文件不覆盖）
EXCLUDE_ARGS=()
for cf in "${CONFLICT_FILES[@]}"; do
  EXCLUDE_ARGS+=(--exclude="${cf}")
done

# raw/ 增量
rsync -avz --update --timeout=30 \
  -e "ssh -o ConnectTimeout=10" \
  --exclude='.obsidian/' --exclude='_archive/' --exclude='00_Inbox/' \
  --exclude='模板/' --exclude='.git/' \
  --exclude='待合并/' \
  "${EXCLUDE_ARGS[@]}" \
  "${SERVER_USER}@${SERVER_HOST}:${SERVER_VAULT_PATH}/raw/" "${LOCAL_VAULT_PATH}/raw/"

# wiki/ 增量
rsync -avz --update --timeout=30 \
  -e "ssh -o ConnectTimeout=10" \
  "${EXCLUDE_ARGS[@]}" \
  "${SERVER_USER}@${SERVER_HOST}:${SERVER_VAULT_PATH}/wiki/" "${LOCAL_VAULT_PATH}/wiki/"

# knowledge_matrix.json
scp -q -o ConnectTimeout=10 \
  "${SERVER_USER}@${SERVER_HOST}:${SERVER_VAULT_PATH}/knowledge_matrix.json" \
  "${PROJECT_ROOT}/data/knowledge_matrix.json" 2>/dev/null || true

echo ""
echo "==> [3/4] 访客画像回流（服务器→本地·单向）..."
# 访客画像/ 目录：服务器→本地（上行 exclude·本地只收不发）
rsync -avz --update --timeout=30 \
  -e "ssh -o ConnectTimeout=10" \
  "${SERVER_USER}@${SERVER_HOST}:${SERVER_VAULT_PATH}/访客画像/" \
  "${LOCAL_VAULT_PATH}/访客画像/" 2>/dev/null || {
    echo "  ⚠️  服务器无 访客画像/ 目录或同步失败（跳过）"
  }

echo ""
echo "==> [4/4] 汇总..."
echo "✅ 回流完成: $(date '+%Y-%m-%d %H:%M:%S')"

if [ ${CONFLICT_COUNT} -gt 0 ]; then
  echo ""
  echo "⚠️  发现 ${CONFLICT_COUNT} 个冲突文件："
  for cf in "${CONFLICT_FILES[@]}"; do
    echo "  - ${cf}"
  done
  echo ""
  echo "📋 冲突清单: ${CONFLICT_LIST}"
  echo "📦 服务器版备份: ${MERGE_DIR}/"
  echo ""
  echo "🔔 请人工确认合并后删除待合并区文件。"
  # 输出 JSON 摘要供 cron 微信通知
  echo "CONFLICT_SUMMARY:冲突文件数=${CONFLICT_COUNT},清单路径=${CONFLICT_LIST}"
fi
