-- ════════════════════════════════════════════════════════════════
-- 徽远成 AI-PM — 数据库初始化脚本
-- 在 PostgreSQL Docker 容器首次启动时自动执行
-- 创建必要的扩展和初始管理员账号
-- ════════════════════════════════════════════════════════════════

-- UUID 扩展（id 字段使用 gen_random_uuid()）
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 默认密码 aipm2026 的 bcrypt 哈希
-- 使用 passlib bcrypt 生成：CryptContext(schemes=['bcrypt']).hash('aipm2026')
-- ── 插入初始管理员 ──
INSERT INTO users (id, name, phone, role, department, wechat_userid, hashed_password, is_active, created_at)
VALUES (
    'a0000000-0000-0000-0000-000000000001',
    '新雷',
    '13800000001',
    'admin',
    '管理层',
    'wx_boss',
    '$2b$12$HRoS5wVb6OdQvpR/ZfDxtOAAr/8XixU2hqqCn0ApwR/EdK1naAABi',
    true,
    NOW()
) ON CONFLICT (id) DO NOTHING;

-- ── 插入测试用户（开发/演示环境 7 人团队，密码均为 aipm2026）──
INSERT INTO users (id, name, phone, role, department, wechat_userid, hashed_password, is_active, created_at)
VALUES
    ('a0000000-0000-0000-0000-000000000002', '张毅',   '13800000002', 'employee', '软件研发部', 'wx_zhangyi',    '$2b$12$HRoS5wVb6OdQvpR/ZfDxtOAAr/8XixU2hqqCn0ApwR/EdK1naAABi', true, NOW()),
    ('a0000000-0000-0000-0000-000000000003', '郭震',   '13800000003', 'employee', '软件研发部', 'wx_guozhen',    '$2b$12$HRoS5wVb6OdQvpR/ZfDxtOAAr/8XixU2hqqCn0ApwR/EdK1naAABi', true, NOW()),
    ('a0000000-0000-0000-0000-000000000004', '林跃文', '13800000004', 'employee', '采购部',     'wx_linyuewen',  '$2b$12$HRoS5wVb6OdQvpR/ZfDxtOAAr/8XixU2hqqCn0ApwR/EdK1naAABi', true, NOW()),
    ('a0000000-0000-0000-0000-000000000005', '郑韬慧', '13800000005', 'employee', '硬件测试部', 'wx_zhengtaohui','$2b$12$HRoS5wVb6OdQvpR/ZfDxtOAAr/8XixU2hqqCn0ApwR/EdK1naAABi', true, NOW()),
    ('a0000000-0000-0000-0000-000000000006', '陶群',   '13800000006', 'employee', '仓储物流部', 'wx_taoqun',     '$2b$12$HRoS5wVb6OdQvpR/ZfDxtOAAr/8XixU2hqqCn0ApwR/EdK1naAABi', true, NOW()),
    ('a0000000-0000-0000-0000-000000000007', '陈家云', '13800000007', 'employee', '仓储物流部', 'wx_chenjiayun', '$2b$12$HRoS5wVb6OdQvpR/ZfDxtOAAr/8XixU2hqqCn0ApwR/EdK1naAABi', true, NOW())
ON CONFLICT (id) DO NOTHING;
