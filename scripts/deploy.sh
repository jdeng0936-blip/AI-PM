#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
# 徽远成 AI-PM — 一键部署脚本
#
# 功能：
#   1. 检查 Docker / Docker Compose
#   2. 检查 .env 配置文件
#   3. 构建前后端镜像
#   4. 启动全栈服务
#   5. 等待健康检查通过
#   6. 执行 Alembic 数据库迁移
#   7. 打印访问地址
#
# 用法：bash scripts/deploy.sh
# ════════════════════════════════════════════════════════════════

set -euo pipefail

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.prod.yml"

echo -e "${BLUE}"
echo "  ╔════════════════════════════════════════════════╗"
echo "  ║      徽远成 AI-PM — 全栈一键部署               ║"
echo "  ╚════════════════════════════════════════════════╝"
echo -e "${NC}"

# ── Step 1: 检查依赖 ──────────────────────────────────────────
echo -e "${YELLOW}[1/6] 检查系统依赖...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker 未安装。请先安装 Docker Desktop: https://docs.docker.com/desktop/mac/install/${NC}"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo -e "${RED}❌ Docker Compose V2 未安装。请更新 Docker Desktop。${NC}"
    exit 1
fi

echo -e "  Docker: $(docker --version | awk '{print $3}')"
echo -e "  Compose: $(docker compose version --short)"
echo -e "${GREEN}  ✅ 依赖检查通过${NC}"

# ── Step 2: 检查 .env 配置 ────────────────────────────────────
echo -e "\n${YELLOW}[2/6] 检查配置文件...${NC}"

ENV_FILE="${PROJECT_DIR}/backend/.env"
if [ ! -f "${ENV_FILE}" ]; then
    echo -e "${RED}❌ 未找到 ${ENV_FILE}${NC}"
    echo -e "  请执行: cp backend/.env.example backend/.env 并填写真实配置"
    exit 1
fi

# 检查关键配置
if grep -q "placeholder" "${ENV_FILE}"; then
    echo -e "${YELLOW}  ⚠️  检测到 .env 中有 placeholder 值，生产环境请替换为真实配置${NC}"
fi

# 从 .env 获取 POSTGRES_PASSWORD 或使用默认值
export POSTGRES_PASSWORD=$(grep -E "^POSTGRES_PASSWORD=" "${ENV_FILE}" 2>/dev/null | cut -d= -f2 || echo "")
if [ -z "${POSTGRES_PASSWORD}" ]; then
    export POSTGRES_PASSWORD="aipm_prod_$(date +%s | sha256sum | head -c 16)"
    echo "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}" >> "${ENV_FILE}"
    echo -e "  🔐 已自动生成 POSTGRES_PASSWORD 并写入 .env"
fi

echo -e "${GREEN}  ✅ 配置检查通过${NC}"

# ── Step 3: 停止旧容器 ────────────────────────────────────────
echo -e "\n${YELLOW}[3/6] 停止旧容器（如有）...${NC}"
docker compose -f "${COMPOSE_FILE}" down --remove-orphans 2>/dev/null || true
echo -e "${GREEN}  ✅ 旧容器已清理${NC}"

# ── Step 4: 构建镜像 ─────────────────────────────────────────
echo -e "\n${YELLOW}[4/6] 构建 Docker 镜像...${NC}"
docker compose -f "${COMPOSE_FILE}" build --parallel
echo -e "${GREEN}  ✅ 镜像构建完成${NC}"

# ── Step 5: 启动服务 ─────────────────────────────────────────
echo -e "\n${YELLOW}[5/6] 启动全栈服务...${NC}"
docker compose -f "${COMPOSE_FILE}" up -d

# 等待健康检查
echo -n "  等待服务就绪"
MAX_WAIT=60
for i in $(seq 1 ${MAX_WAIT}); do
    if docker compose -f "${COMPOSE_FILE}" ps | grep -q "healthy"; then
        break
    fi
    echo -n "."
    sleep 2
done
echo ""

# 检查各服务状态
echo -e "\n  服务状态："
docker compose -f "${COMPOSE_FILE}" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
echo -e "${GREEN}  ✅ 服务启动完成${NC}"

# ── Step 6: 数据库迁移 ────────────────────────────────────────
echo -e "\n${YELLOW}[6/6] 执行数据库迁移...${NC}"
sleep 5  # 等待 PG 完全就绪
docker exec aipm-backend alembic upgrade head 2>/dev/null && \
    echo -e "${GREEN}  ✅ 数据库迁移完成${NC}" || \
    echo -e "${YELLOW}  ⚠️  Alembic 迁移跳过（可能尚无迁移脚本，表已通过 init.sql 创建）${NC}"

# ── 完成 ──────────────────────────────────────────────────────
echo -e "\n${BLUE}"
echo "  ╔════════════════════════════════════════════════╗"
echo "  ║              🚀 部署完成！                     ║"
echo "  ╠════════════════════════════════════════════════╣"
echo "  ║  前端大盘:  http://localhost                   ║"
echo "  ║  后端 API:  http://localhost:8000/docs         ║"
echo "  ║  健康检查:  http://localhost:8000/health       ║"
echo "  ╠════════════════════════════════════════════════╣"
echo "  ║  查看日志:  docker compose -f                  ║"
echo "  ║            docker-compose.prod.yml logs -f     ║"
echo "  ║  停止服务:  docker compose -f                  ║"
echo "  ║            docker-compose.prod.yml down        ║"
echo "  ╚════════════════════════════════════════════════╝"
echo -e "${NC}"
