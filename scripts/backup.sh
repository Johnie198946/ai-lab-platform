#!/bin/bash
# PostgreSQL 备份脚本
# 用法: bash scripts/backup.sh
# 定时: crontab -e → 0 3 * * * bash /app/scripts/backup.sh

BACKUP_DIR="./backups"
DB_NAME="${DATABASE_URL:-postgresql://ailab:ailab_dev@localhost:5432/ai_lab}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILE="${BACKUP_DIR}/ailab_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "Backing up to $FILE ..."
pg_dump "$DB_NAME" | gzip > "$FILE"

# 只保留最近 7 天
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +7 -delete

echo "Done. Size: $(du -h "$FILE" | cut -f1)"
