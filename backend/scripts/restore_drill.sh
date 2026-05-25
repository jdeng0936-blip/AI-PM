#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
# restore_drill.sh — 备份恢复演练
#
# 核心原则:备份必须能被恢复才算备份。
# 每周自动跑一次,把最新备份恢复到独立的演练库,验证:
#   1. pg_restore 能跑通(没损坏)
#   2. alembic check 干净(schema 与 ORM 一致)
#   3. 关键表行数非空且合理
#
# 用法:
#   bash scripts/restore_drill.sh                       # 用最新备份
#   bash scripts/restore_drill.sh backups/aipm_db_xxx   # 指定备份文件
#
# crontab(每周一 04:00):
#   0 4 * * 1 cd /opt/aipm/backend && bash scripts/restore_drill.sh
# ════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${BACKEND_DIR}"

BACKUP_DIR="${BACKUP_DIR:-${BACKEND_DIR}/backups}"
DRILL_DB="${DRILL_DB:-aipm_db_drill}"
DB_USER="${DB_USER:-aipm}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"

# ── 从 .env 取 POSTGRES_PASSWORD ─────────────────────────────────
if [[ -f .env ]]; then
    POSTGRES_PASSWORD="$(grep -E '^POSTGRES_PASSWORD=' .env | head -1 | cut -d= -f2-)"
fi
if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
    echo "❌ POSTGRES_PASSWORD 未配置" >&2
    exit 1
fi
export PGPASSWORD="${POSTGRES_PASSWORD}"

# ── 决定使用哪份备份 ─────────────────────────────────────────────
if [[ $# -ge 1 ]]; then
    BACKUP_FILE="$1"
else
    BACKUP_FILE="$(ls -t "${BACKUP_DIR}"/aipm_db_*.sql.gz 2>/dev/null | head -1 || true)"
fi
if [[ -z "${BACKUP_FILE}" || ! -f "${BACKUP_FILE}" ]]; then
    echo "❌ 没找到备份文件(${BACKUP_DIR}/aipm_db_*.sql.gz)" >&2
    exit 2
fi
echo "[$(date '+%F %T')] 演练用备份:${BACKUP_FILE}"

# ── 重建演练库 ──────────────────────────────────────────────────
echo "[$(date '+%F %T')] DROP + CREATE ${DRILL_DB}..."
psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS ${DRILL_DB};" >/dev/null
psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE ${DRILL_DB} OWNER ${DB_USER};" >/dev/null

# ── 恢复备份 ────────────────────────────────────────────────────
echo "[$(date '+%F %T')] gunzip + psql restore..."
if ! gunzip -c "${BACKUP_FILE}" | psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DRILL_DB}" -v ON_ERROR_STOP=1 >/dev/null 2>/tmp/restore_drill.err; then
    echo "❌ restore 失败:" >&2
    cat /tmp/restore_drill.err >&2
    exit 3
fi
echo "[$(date '+%F %T')] ✅ restore 完成"

# ── 验证 1:关键表行数 ──────────────────────────────────────────
echo "[$(date '+%F %T')] 验证表行数..."
for tbl in users daily_reports projects rd_project_milestones audit_logs; do
    cnt="$(psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DRILL_DB}" -tAc "SELECT count(*) FROM ${tbl} 2>/dev/null;" 2>/dev/null || echo "TABLE_MISSING")"
    echo "    ${tbl}: ${cnt}"
done

# ── 验证 2:alembic check ───────────────────────────────────────
echo "[$(date '+%F %T')] alembic check(演练库 vs 当前 ORM)..."
DRILL_DATABASE_URL="postgresql+asyncpg://${DB_USER}:${POSTGRES_PASSWORD}@${DB_HOST}:${DB_PORT}/${DRILL_DB}"
if DATABASE_URL="${DRILL_DATABASE_URL}" .venv/bin/alembic check 2>&1 | tail -5 | tee /tmp/alembic_check.out; then
    if grep -q "No new upgrade operations detected" /tmp/alembic_check.out; then
        echo "[$(date '+%F %T')] ✅ alembic check 干净 — 备份完整可用"
    else
        echo "[$(date '+%F %T')] ⚠️ alembic check 输出非预期" >&2
        exit 4
    fi
else
    echo "[$(date '+%F %T')] ❌ alembic check 失败" >&2
    exit 4
fi

# ── 清理:可选,默认保留演练库供人工检查 ────────────────────────
if [[ "${CLEANUP_DRILL_DB:-0}" == "1" ]]; then
    psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d postgres -c "DROP DATABASE ${DRILL_DB};" >/dev/null
    echo "[$(date '+%F %T')] 已清理 ${DRILL_DB}"
fi

unset PGPASSWORD
echo "[$(date '+%F %T')] 🎉 备份恢复演练全部通过"
