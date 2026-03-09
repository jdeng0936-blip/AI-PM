-- ════════════════════════════════════════════════════════════════
-- 徽远成 AI-PM — 数据库初始化脚本
-- 在 PostgreSQL Docker 容器首次启动时自动执行
-- 创建必要的扩展（表结构由 Alembic migration 创建）
-- ════════════════════════════════════════════════════════════════

-- UUID 扩展（id 字段使用 gen_random_uuid()）
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
-- pgvector 扩展（Rule 01-Stack-Database: 知识库向量检索）
CREATE EXTENSION IF NOT EXISTS "vector";

-- 注意：用户数据由后端 Alembic migration + seed 脚本写入
-- 原 INSERT 语句已移除，避免表未创建时报错导致容器崩溃循环
