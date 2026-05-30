#!/bin/bash
# ════════════════════════════════════════════════════════════════
# scripts/seed_users.sh — 初始化种子用户（幂等）
#
# 用法：
#   bash scripts/seed_users.sh
#   POSTGRES_CONTAINER=aipm-postgres bash scripts/seed_users.sh
#
# 前提：PostgreSQL 容器已运行且 Alembic 迁移已完成
# ════════════════════════════════════════════════════════════════

set -e

if command -v docker >/dev/null 2>&1; then
  DOCKER_CMD="${DOCKER_CMD:-docker}"
else
  DOCKER_CMD="${DOCKER_CMD:-/Applications/Docker.app/Contents/Resources/bin/docker}"
fi

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-aipm-dev-postgres}"
POSTGRES_USER="${POSTGRES_USER:-aipm}"
POSTGRES_DB="${POSTGRES_DB:-aipm_db}"

echo "🌱 正在写入种子用户..."

$DOCKER_CMD exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
INSERT INTO users (
  id,
  wechat_userid,
  name,
  phone,
  department,
  role,
  is_active,
  job_title,
  must_change_password,
  status,
  story_points_capacity,
  tenant_id
)
VALUES
  (gen_random_uuid(), 'admin',          '管理员',    '13800000000', '管理层',     'admin',    true, '系统管理员', false, 'active', 8, 'default'),
  (gen_random_uuid(), 'wx_zhangyi',     '张毅',      '13800000001', '软件研发部', 'manager',  true, '技术部长',   false, 'active', 8, 'default'),
  (gen_random_uuid(), 'wx_guozhen',     '郭震',      '13800000002', '软件研发部', 'employee', true, '研发工程师', false, 'active', 8, 'default'),
  (gen_random_uuid(), 'wx_zhangwei',    '张维',      '13800000007', '软件研发部', 'employee', true, '研发工程师', false, 'active', 8, 'default'),
  (gen_random_uuid(), 'wx_chenxiang',   '陈翔',      '13800000008', '软件研发部', 'employee', true, '研发工程师', false, 'active', 8, 'default'),
  (gen_random_uuid(), 'wx_linyuewen',   '林跃文',    '13800000003', '软件研发部', 'employee', true, '研发工程师', false, 'active', 8, 'default'),
  (gen_random_uuid(), 'wx_zhengtaohui', '郑韬慧',    '13800000004', '软件研发部', 'employee', true, '研发工程师', false, 'active', 8, 'default'),
  (gen_random_uuid(), 'wx_songweicheng','宋伟承',    '13800000009', '生产部',     'employee', true, '生产工程师', false, 'active', 8, 'default'),
  (gen_random_uuid(), 'wx_taoqun',      '陶群',      '13800000005', '采购部',     'employee', true, '采购专员',   false, 'active', 8, 'default'),
  (gen_random_uuid(), 'wx_chenjiayun',  '陈家云',    '13800000006', '仓储物流部', 'employee', true, '物流专员',   false, 'active', 8, 'default')
ON CONFLICT (wechat_userid) DO UPDATE SET
  name = EXCLUDED.name,
  phone = EXCLUDED.phone,
  department = EXCLUDED.department,
  role = EXCLUDED.role,
  is_active = EXCLUDED.is_active,
  job_title = EXCLUDED.job_title,
  must_change_password = EXCLUDED.must_change_password,
  status = EXCLUDED.status,
  story_points_capacity = EXCLUDED.story_points_capacity,
  tenant_id = EXCLUDED.tenant_id;
"

echo ""
echo "✅ 种子用户写入完成！当前用户列表："
$DOCKER_CMD exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT name, role, department, job_title, status, story_points_capacity FROM users ORDER BY department, role, name;"
