#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
# backup.sh — 生产数据库每日备份脚本
#
# 用法:
#   bash scripts/backup.sh                      # 手动跑一次
#   # 进 crontab 每日 03:00 自动执行:
#   0 3 * * * cd /opt/aipm/backend && bash scripts/backup.sh >> /var/log/aipm-backup.log 2>&1
#
# 行为:
#   1. pg_dump 整库到 ./backups/aipm_db_YYYYMMDD_HHMMSS.sql.gz
#   2. 删除 14 天前的本地备份(默认 RETENTION_DAYS=14)
#   3. 可选:上传到 OSS(配 BACKUP_OSS_BUCKET 后启用)
#
# 安全:
#   - 从 .env 读取 POSTGRES_PASSWORD,通过 PGPASSWORD 环境变量传给 pg_dump
#     (避免出现在 ps 输出 / shell history 中)
#   - 备份文件 chmod 600,只有 owner 可读
# ════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${BACKEND_DIR}"

# ── 配置(可被 env 覆盖) ─────────────────────────────────────────
BACKUP_DIR="${BACKUP_DIR:-${BACKEND_DIR}/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
DB_NAME="${DB_NAME:-aipm_db}"
DB_USER="${DB_USER:-aipm}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"

# ── 从 .env 提取 POSTGRES_PASSWORD(只读取一次,导出为 PGPASSWORD) ──
if [[ -f .env ]]; then
    POSTGRES_PASSWORD="$(grep -E '^POSTGRES_PASSWORD=' .env | head -1 | cut -d= -f2-)"
fi
if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
    echo "❌ POSTGRES_PASSWORD 未配置 — 检查 .env" >&2
    exit 1
fi
export PGPASSWORD="${POSTGRES_PASSWORD}"

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"

TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/aipm_db_${TS}.sql.gz"

echo "[$(date '+%F %T')] 开始备份 ${DB_NAME} → ${BACKUP_FILE}"

# pg_dump --format=custom 可以并行 restore,但 .sql.gz 文本更通用易读
# 大库可改成 -Fc 自定义格式
if pg_dump \
        -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
        --no-owner --no-privileges \
        --verbose 2>/dev/null \
    | gzip -9 > "${BACKUP_FILE}.tmp"; then
    mv "${BACKUP_FILE}.tmp" "${BACKUP_FILE}"
    chmod 600 "${BACKUP_FILE}"
    SIZE="$(du -h "${BACKUP_FILE}" | cut -f1)"
    echo "[$(date '+%F %T')] ✅ 备份成功 size=${SIZE}"
else
    rm -f "${BACKUP_FILE}.tmp"
    echo "[$(date '+%F %T')] ❌ pg_dump 失败" >&2
    exit 2
fi

# ── 清理过期备份 ────────────────────────────────────────────────
echo "[$(date '+%F %T')] 清理 ${RETENTION_DAYS} 天前的备份..."
find "${BACKUP_DIR}" -name 'aipm_db_*.sql.gz' -mtime "+${RETENTION_DAYS}" -delete -print | wc -l | xargs -I{} echo "  删除了 {} 个旧备份"

# ── 可选:上传 OSS ────────────────────────────────────────────────
if [[ -n "${BACKUP_OSS_BUCKET:-}" ]]; then
    if command -v ossutil >/dev/null 2>&1; then
        echo "[$(date '+%F %T')] 上传 OSS..."
        ossutil cp -f "${BACKUP_FILE}" "oss://${BACKUP_OSS_BUCKET}/aipm-backups/aipm_db_${TS}.sql.gz"
        echo "[$(date '+%F %T')] ✅ OSS 上传成功"
    else
        echo "⚠️  BACKUP_OSS_BUCKET 已配置但未装 ossutil,跳过上传" >&2
    fi
fi

unset PGPASSWORD
echo "[$(date '+%F %T')] 完成"
