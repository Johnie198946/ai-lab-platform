#!/bin/bash
# PostgreSQL 备份脚本（容器感知版）
# 用法: bash scripts/backup.sh
# 定时: crontab -e → 0 3 * * * bash /opt/ai-lab-platform/scripts/backup.sh
#
# postgres 运行在 docker compose 容器内，通过 docker compose exec 执行 pg_dump

set -euo pipefail
cd "$(dirname "$0")/.."

BACKUP_DIR="./backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILE="${BACKUP_DIR}/ailab_${TIMESTAMP}.sql.gz"
mkdir -p "$BACKUP_DIR"

# 从 .env 读取数据库凭据（若有）
POSTGRES_USER="${POSTGRES_USER:-ailab}"
POSTGRES_DB="${POSTGRES_DB:-ai_lab}"
[ -f .env ] && . ./.env 2>/dev/null || true
POSTGRES_USER="${POSTGRES_USER:-ailab}"
POSTGRES_DB="${POSTGRES_DB:-ai_lab}"

echo "Backing up to $FILE ..."
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip > "$FILE"

# 只保留最近 7 天
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +7 -delete

echo "Done. Size: $(du -h "$FILE" | cut -f1)"
