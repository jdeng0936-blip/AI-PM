#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
# 徽远成 AI-PM — PostgreSQL 自动备份脚本
#
# 功能：
#   1. pg_dump 压缩备份 → 本地 /backup/aipm/
#   2. 上传至阿里云 OSS（需安装 ossutil）
#   3. 清理 7 天前的本地备份
#
# 部署：
#   chmod +x scripts/pg_backup.sh
#   crontab -e
#   添加：0 3 * * * /path/to/scripts/pg_backup.sh >> /var/log/aipm_backup.log 2>&1
# ════════════════════════════════════════════════════════════════

set -euo pipefail

# ── 配置（按实际情况修改）──────────────────────────────────────
CONTAINER_NAME="aipm-postgres"
DB_NAME="aipm_db"
DB_USER="aipm"
BACKUP_DIR="/backup/aipm"
OSS_BUCKET="oss://huiyuancheng-backup/aipm-db/"
RETENTION_DAYS=7

# ── 初始化 ─────────────────────────────────────────────────────
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/aipm_backup_${DATE}.sql.gz"

mkdir -p "${BACKUP_DIR}"

echo "════════════════════════════════════"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始备份..."

# ── Step 1: 执行 pg_dump 并 gzip 压缩 ─────────────────────────
docker exec "${CONTAINER_NAME}" \
    pg_dump -U "${DB_USER}" "${DB_NAME}" \
    | gzip > "${BACKUP_FILE}"

SIZE=$(du -sh "${BACKUP_FILE}" | cut -f1)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 备份完成：${BACKUP_FILE}（${SIZE}）"

# ── Step 2: 上传至 OSS（需提前配置 ossutil config）────────────────
if command -v ossutil &> /dev/null; then
    ossutil cp "${BACKUP_FILE}" "${OSS_BUCKET}" --force
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 已上传至 OSS：${OSS_BUCKET}"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️  ossutil 未安装，跳过 OSS 上传"
fi

# ── Step 3: 清理超期本地备份 ─────────────────────────────────────
DELETED=$(find "${BACKUP_DIR}" -name "aipm_backup_*.sql.gz" -mtime "+${RETENTION_DAYS}" -print -delete | wc -l)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 已清理 ${DELETED} 个超过 ${RETENTION_DAYS} 天的备份文件"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ 备份流程完成"
echo "════════════════════════════════════"
